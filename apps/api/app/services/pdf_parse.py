from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

import pymupdf
from sqlalchemy.orm import Session

from app.models import Block, Document, Translation


@dataclass
class ParseResult:
    page_count: int
    block_count: int
    status: str
    message: str = ""


@dataclass
class _RawBlock:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    block_type: str
    font_size: float = 0.0


_CAPTION_RE = re.compile(r"^\s*(figure|fig\.|table|tab\.)\s*\d+", re.I)
_CAPTION_NUM_RE = re.compile(r"^\s*(figure|fig\.|table|tab\.)\s*(\d+)", re.I)
_FORMULA_HINT = re.compile(r"[=∫∑∏√≤≥±×÷]|\\frac|\\sum|\\begin\{")
_ARXIV_RE = re.compile(r"arxiv\s*:", re.I)
_HEADING_RE = re.compile(r"^(\d+(\.\d+)*|[IVXLC]+)\.\s+\S", re.I)
_DROP_CAP_TAIL_RE = re.compile(r"^(?P<stem>.*?)(?:\n+|\s+)(?P<letter>[A-Za-z])\s*$", re.S)
_SECTION_STEM_RE = re.compile(
    r"^((\d+(\.\d+)*|[IVXLC]+)\.\s+\S.{0,80}|"
    r"(abstract|introduction|related work|conclusion|references|acknowledgment|acknowledgement)s?\b)",
    re.I,
)
_FIGURE_LABEL_RE = re.compile(
    r"^(frame|step|stage|layer|encoder|decoder|mask|prompt|memory|bank|"
    r"image|video|points?|box|time|input|output|query|key|value|"
    r"phase|clicks?|edited|model|sam|iou|all|small|medium|large|"
    r"a|b|c|d)\b",
    re.I,
)
_AXIS_TICK_RE = re.compile(r"^[\d\s\.\,\%\-\–]+$")
_TABLE_HEADER_RE = re.compile(r"^#\w+")


@dataclass
class _VisualSlot:
    x0: float
    y0: float
    x1: float
    y1: float
    kind: str  # placeholder_figure | placeholder_table
    caption_key: str | None = None


def _caption_key(text: str) -> str | None:
    m = _CAPTION_NUM_RE.match(text or "")
    if not m:
        return None
    kind = "table" if m.group(1).lower().startswith("tab") else "figure"
    return f"{kind}:{int(m.group(2))}"


def _overlap_ratio(a: tuple[float, float, float, float], b: pymupdf.Rect) -> float:
    ax0, ay0, ax1, ay1 = a
    ix0, iy0 = max(ax0, b.x0), max(ay0, b.y0)
    ix1, iy1 = min(ax1, b.x1), min(ay1, b.y1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    area = max(1.0, (ax1 - ax0) * (ay1 - ay0))
    return (iw * ih) / area


def _merge_rects(rects: list[pymupdf.Rect], gap: float = 28.0) -> list[pymupdf.Rect]:
    if not rects:
        return []
    pending = [pymupdf.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False
        out: list[pymupdf.Rect] = []
        while pending:
            cur = pending.pop(0)
            i = 0
            while i < len(pending):
                other = pending[i]
                expanded = pymupdf.Rect(
                    cur.x0 - gap, cur.y0 - gap, cur.x1 + gap, cur.y1 + gap
                )
                if expanded.intersects(other):
                    cur = cur | other
                    pending.pop(i)
                    changed = True
                else:
                    i += 1
            out.append(cur)
        pending = out
    return pending


def _page_image_figure_regions(page: pymupdf.Page) -> list[pymupdf.Rect]:
    images: list[pymupdf.Rect] = []
    try:
        for info in page.get_image_info():
            bbox = info.get("bbox")
            if not bbox:
                continue
            r = pymupdf.Rect(bbox)
            if r.width >= 8 and r.height >= 8:
                images.append(r)
    except Exception:  # noqa: BLE001
        pass

    if not images:
        return []

    page_h = float(page.rect.height)
    page_w = float(page.rect.width)

    if len(images) >= 4:
        union = pymupdf.Rect(images[0])
        for r in images[1:]:
            union |= r
        if (
            union.height <= page_h * 0.55
            and union.width >= page_w * 0.28
            and union.get_area() >= 8_000
        ):
            return [
                pymupdf.Rect(union.x0 - 28, union.y0 - 28, union.x1 + 28, union.y1 + 18)
            ]

    regions: list[pymupdf.Rect] = []
    for r in _merge_rects(images, gap=36.0):
        area = r.width * r.height
        if area >= 8_000 or (r.width >= 140 and r.height >= 60):
            regions.append(pymupdf.Rect(r.x0 - 24, r.y0 - 24, r.x1 + 24, r.y1 + 16))
    return regions


def _page_table_regions(page: pymupdf.Page) -> list[pymupdf.Rect]:
    regions: list[pymupdf.Rect] = []
    try:
        finder = page.find_tables()
        tables = list(finder.tables) if finder else []
    except Exception:  # noqa: BLE001
        return regions
    for table in tables:
        r = pymupdf.Rect(table.bbox)
        # Reject chrome chips / false positives inside figures
        if r.height < 40 or r.width < 90 or r.get_area() < 5_000:
            continue
        regions.append(pymupdf.Rect(r.x0 - 8, r.y0 - 10, r.x1 + 8, r.y1 + 8))
    return _merge_rects(regions, gap=12.0)


def _collect_spans(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, float, str]]:
    spans: list[tuple[pymupdf.Rect, float, str]] = []
    try:
        data = page.get_text("dict")
    except Exception:  # noqa: BLE001
        return spans
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = (span.get("text") or "").strip()
                bbox = span.get("bbox")
                size = float(span.get("size") or 0)
                if not bbox or size <= 0:
                    continue
                spans.append((pymupdf.Rect(bbox), size, text))
    return spans


def _page_chart_regions(
    page: pymupdf.Page, spans: list[tuple[pymupdf.Rect, float, str]]
) -> list[pymupdf.Rect]:
    """Cluster tiny-font spans + drawing ink into chart / plot bands."""
    page_w = float(page.rect.width)
    page_h = float(page.rect.height)

    # Only very small fonts (axis ticks / in-plot labels). Do NOT include ~9pt
    # author lines or body text — those false-create page-wide "chart" bands.
    tiny_boxes = [
        r for r, size, _ in spans if size <= 8.5 and r.width > 1 and r.height > 1
    ]

    draw_boxes: list[pymupdf.Rect] = []
    try:
        for drawing in page.get_drawings():
            rect = drawing.get("rect")
            if not rect:
                continue
            r = pymupdf.Rect(rect)
            # Ignore hairline section rules
            if r.height < 1.5 and r.width > page_w * 0.4:
                continue
            if r.width < 1.5 and r.height > page_h * 0.4:
                continue
            # Ignore page-frame / clip rectangles (common in academic PDFs)
            if r.width > page_w * 0.6 and r.height > page_h * 0.22:
                continue
            if r.get_area() >= 80 or (r.width >= 40 and r.height >= 20):
                draw_boxes.append(r)
    except Exception:  # noqa: BLE001
        pass

    seeds = tiny_boxes + draw_boxes
    if len(seeds) < 3 and len(tiny_boxes) < 2:
        return []

    merged = _merge_rects(seeds, gap=18.0)
    regions: list[pymupdf.Rect] = []
    for r in merged:
        if r.height < 3 and r.width > page_w * 0.5:
            continue
        # Reject huge bands spanning the title block of a page
        if r.width > page_w * 0.7 and r.height > page_h * 0.28:
            tiny_hits = sum(1 for t in tiny_boxes if not (t & r).is_empty)
            if tiny_hits < 6:
                continue
        tiny_hits = sum(1 for t in tiny_boxes if not (t & r).is_empty)
        draw_hits = sum(1 for d in draw_boxes if not (d & r).is_empty)
        if tiny_hits >= 2 or (draw_hits >= 2 and r.height >= 40 and r.width >= 80):
            regions.append(pymupdf.Rect(r.x0 - 14, r.y0 - 18, r.x1 + 14, r.y1 + 14))
        elif tiny_hits >= 1 and draw_hits >= 1 and r.width >= 100:
            regions.append(pymupdf.Rect(r.x0 - 14, r.y0 - 18, r.x1 + 14, r.y1 + 14))
    return regions


def _avg_font_size(
    spans: list[tuple[pymupdf.Rect, float, str]],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> float | None:
    box = pymupdf.Rect(x0, y0, x1, y1)
    sizes: list[float] = []
    for rect, size, _text in spans:
        inter = rect & box
        if inter.is_empty:
            continue
        if inter.get_area() / max(rect.get_area(), 1.0) >= 0.35:
            sizes.append(size)
    if not sizes:
        return None
    return sum(sizes) / len(sizes)


def _inside_region(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    regions: list[pymupdf.Rect],
    *,
    center_pad: float = 4.0,
    min_overlap: float = 0.3,
) -> bool:
    if not regions:
        return False
    box = (x0, y0, x1, y1)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    w, h = x1 - x0, y1 - y0
    for region in regions:
        if (
            region.x0 - center_pad <= cx <= region.x1 + center_pad
            and region.y0 - center_pad <= cy <= region.y1 + center_pad
        ):
            return True
        if _overlap_ratio(box, region) >= min_overlap:
            return True
        if w < 160 and h < 36 and _overlap_ratio(box, region) >= 0.1:
            return True
    return False


def _classify(
    text: str,
    w: float,
    h: float,
    page_width: float,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    figure_regions: list[pymupdf.Rect],
    table_regions: list[pymupdf.Rect],
    chart_regions: list[pymupdf.Rect],
    avg_font: float | None,
    *,
    page_index: int = 0,
    page_height: float = 792.0,
) -> str:
    compact = " ".join(text.split())
    is_caption = bool(_CAPTION_RE.match(text))
    # Allow slightly taller boxes — drop-caps often inflate heading bbox height
    is_heading = bool(_HEADING_RE.match(compact) and len(compact) < 90 and h < 56)

    # Footer page numbers — keep before any tiny-font / chrome skips
    if (
        re.fullmatch(r"\d{1,3}", compact)
        and h < 22
        and w < 48
        and y0 >= page_height * 0.90
        and abs((x0 + x1) / 2.0 - page_width / 2.0) < page_width * 0.18
    ):
        return "page_number"

    # Vertical gutter / watermark
    if h > max(48.0, w * 2.4) and w < 48:
        return "skip"
    if x0 < page_width * 0.06 and h > 100 and w < 40:
        return "skip"
    if _ARXIV_RE.search(text) and w < 50:
        return "skip"

    # Table cells — never translate (captions stay)
    if not is_caption and _inside_region(x0, y0, x1, y1, table_regions, min_overlap=0.25):
        return "skip"

    # Raster figures / photo grids
    if _inside_region(x0, y0, x1, y1, figure_regions):
        if not is_caption and not (len(text) > 100 and h > 36):
            return "skip"

    # Vector charts / plots / legends
    significant_charts = [
        r
        for r in chart_regions
        if r.get_area() >= 6_000 or (r.width >= 100 and r.height >= 48)
    ]
    if (
        not is_caption
        and not is_heading
        and _inside_region(x0, y0, x1, y1, significant_charts, min_overlap=0.2)
    ):
        # Keep body prose that only overlaps a plot band
        if len(text) > 60 and (avg_font or 99) >= 9.5 and h >= 18:
            pass
        else:
            return "skip"
    # Tiny logo/draw chips: only suppress equally tiny labels whose CENTER sits in chip
    micro_charts = [r for r in chart_regions if r not in significant_charts]
    if micro_charts and not is_caption and not is_heading and h <= 14 and len(compact) <= 40:
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        for region in micro_charts:
            if region.x0 <= cx <= region.x1 and region.y0 <= cy <= region.y1:
                return "skip"

    # Tiny plot fonts (axis ticks, legend chips, in-plot annotations).
    # Author lists also use ~8.5–9pt — keep wider multi-line meta blocks.
    if avg_font is not None and avg_font <= 9.15 and not is_caption and not is_heading:
        looks_like_meta = h >= 18 and w >= 90 and len(compact) >= 12
        looks_like_title = h >= 18 and w >= 200 and len(compact) < 160
        looks_like_link = "http://" in compact.lower() or "https://" in compact.lower()
        if not looks_like_meta and not looks_like_title and not looks_like_link:
            return "skip"

    # Short low-height chips typical of chart chrome
    if (
        not is_caption
        and not is_heading
        and h <= 12.5
        and len(compact) <= 90
        and (
            (avg_font is not None and avg_font <= 9.4)
            or _FIGURE_LABEL_RE.match(compact)
            or _AXIS_TICK_RE.match(compact)
            or _TABLE_HEADER_RE.match(compact)
            or (compact.count(" ") >= 3 and h <= 10.5)
            or ("http://" in compact.lower() or "https://" in compact.lower())
        )
    ):
        # Keep link lines (demo/code/website) — handled as meta, not chart chrome
        if "http://" in compact.lower() or "https://" in compact.lower():
            pass
        else:
            return "skip"

    # Diagram chips near figures
    if (
        figure_regions
        and not is_caption
        and len(compact) <= 42
        and h < 28
        and w < 280
        and _FIGURE_LABEL_RE.match(compact)
    ):
        for region in figure_regions:
            if y1 >= region.y0 - 36 and y0 <= region.y1 + 24:
                return "skip"

    # Table-like numeric dumps (many numbers, small font) — but not prose with a few citations
    if (
        not is_caption
        and not is_heading
        and (avg_font is None or avg_font <= 9.5)
        and h <= 80
        and len(re.findall(r"\d+(?:\.\d+)?", compact)) >= 5
        and len(compact) <= 220
        and (
            compact.count("%") >= 1
            or compact.count(" - ") >= 2
            or len(re.findall(r"\b\d+\.\d+\b", compact)) >= 3
            or len(re.findall(r"\b\d+(?:\.\d+)?[KkMm]\b", compact)) >= 3
        )
    ):
        return "skip"
    if is_caption:
        return "caption"
    if is_heading:
        return "heading"
    if _FORMULA_HINT.search(text) and len(text) < 120:
        return "formula_skip"
    if re.fullmatch(r"\d{1,3}", compact) and h < 22 and w < 48:
        return "skip"
    if len(text) <= 2 and w < 24:
        return "skip"
    # Title-page heuristics
    if (
        page_index == 0
        and avg_font is not None
        and avg_font >= 14
        and h < 48
        and len(compact) < 180
        and y0 < 120
    ):
        return "title"
    # Author / affiliation / link lines on the first page
    if (
        page_index == 0
        and y0 < 220
        and h < 55
        and len(compact) < 500
        and (
            "http://" in compact.lower()
            or "https://" in compact.lower()
            or (avg_font is not None and avg_font <= 9.5 and w / max(h, 1) > 2.2)
            or ("@" in compact and len(compact) < 200)
        )
    ):
        return "meta"
    return "text"


def _merge_fragments(items: list[_RawBlock]) -> list[_RawBlock]:
    if not items:
        return []
    merged: list[_RawBlock] = [items[0]]
    for cur in items[1:]:
        prev = merged[-1]
        if prev.block_type != "text" or cur.block_type != "text":
            merged.append(cur)
            continue
        gap = cur.y0 - prev.y1
        same_column = abs(cur.x0 - prev.x0) < 28
        similar_width = abs((cur.x1 - cur.x0) - (prev.x1 - prev.x0)) < 90
        short_lines = (prev.y1 - prev.y0) < 24 and (cur.y1 - cur.y0) < 24
        if same_column and similar_width and short_lines and -2 <= gap <= 12:
            joiner = "" if prev.text.endswith("-") else " "
            prev.text = f"{prev.text.rstrip('-')}{joiner}{cur.text}".strip()
            prev.x0 = min(prev.x0, cur.x0)
            prev.y0 = min(prev.y0, cur.y0)
            prev.x1 = max(prev.x1, cur.x1)
            prev.y1 = max(prev.y1, cur.y1)
            if cur.font_size:
                prev.font_size = prev.font_size or cur.font_size
            continue
        merged.append(cur)
    return merged


def _looks_like_word_continuation(letter: str, nxt: str) -> bool:
    """True when nxt is the remainder of a word after ornamental drop-cap letter."""
    if not letter or not nxt or not nxt[0].isalpha():
        return False
    # Classic academic drop-cap: B + IOMEDICAL...
    if nxt[0].isupper() and len(nxt) >= 2:
        return True
    # b + iomedical...
    if nxt[0].islower():
        return True
    return False


def _reattach_drop_caps(items: list[_RawBlock]) -> list[_RawBlock]:
    """Move ornamental drop-cap letters from section titles onto the next body line.

    PyMuPDF often yields ``I. INTRODUCTION\\nB`` then ``IOMEDICAL image...``,
    which surfaces as a stray translated ``B`` under the Chinese heading.
    """
    if not items:
        return []
    out: list[_RawBlock] = []
    i = 0
    while i < len(items):
        cur = items[i]
        text = (cur.text or "").strip()
        m = _DROP_CAP_TAIL_RE.match(text)
        if m and i + 1 < len(items):
            stem = (m.group("stem") or "").strip()
            letter = m.group("letter")
            nxt = items[i + 1]
            nxt_text = (nxt.text or "").lstrip()
            if (
                stem
                and _SECTION_STEM_RE.match(stem)
                and nxt.block_type in ("text", "heading", "title", "meta", "caption")
                and _looks_like_word_continuation(letter, nxt_text)
            ):
                heading_type = "heading" if _HEADING_RE.match(stem) or _SECTION_STEM_RE.match(stem) else cur.block_type
                # Prefer heading when stem is a numbered/Roman section title
                if _HEADING_RE.match(stem):
                    heading_type = "heading"
                out.append(
                    _RawBlock(cur.x0, cur.y0, cur.x1, min(cur.y1, nxt.y0 - 1) if nxt.y0 > cur.y0 else cur.y1, stem, heading_type, cur.font_size)
                )
                out.append(
                    _RawBlock(
                        nxt.x0,
                        min(cur.y0, nxt.y0),
                        nxt.x1,
                        nxt.y1,
                        letter + nxt_text,
                        "text" if nxt.block_type == "heading" else nxt.block_type,
                        nxt.font_size,
                    )
                )
                i += 2
                continue

        # Standalone single-letter block sitting before a body paragraph
        if (
            re.fullmatch(r"[A-Za-z]", text)
            and i + 1 < len(items)
            and items[i + 1].block_type in ("text", "meta")
            and _looks_like_word_continuation(text, (items[i + 1].text or "").lstrip())
        ):
            nxt = items[i + 1]
            out.append(
                _RawBlock(
                    nxt.x0,
                    min(cur.y0, nxt.y0),
                    nxt.x1,
                    nxt.y1,
                    text + (nxt.text or "").lstrip(),
                    nxt.block_type,
                    nxt.font_size or cur.font_size,
                )
            )
            i += 2
            continue

        out.append(cur)
        i += 1
    return out


def _band_text_union(
    page: pymupdf.Page,
    y_lo: float,
    y_hi: float,
    *,
    exclude_caption: bool = True,
) -> pymupdf.Rect | None:
    """Union of text blocks strictly inside a vertical band (for table cells)."""
    boxes: list[pymupdf.Rect] = []
    for raw in page.get_text("blocks"):
        x0, y0, x1, y1, text, *_rest = raw
        text = (text or "").strip()
        if not text:
            continue
        if exclude_caption and _CAPTION_RE.match(text):
            continue
        if y1 <= y_lo or y0 >= y_hi:
            continue
        # Prefer content that mostly sits inside the band
        if y0 < y_lo - 4:
            continue
        boxes.append(pymupdf.Rect(float(x0), float(y0), float(x1), float(y1)))
    if not boxes:
        return None
    union = pymupdf.Rect(boxes[0])
    for b in boxes[1:]:
        union |= b
    return union


def _clip_rect(r: pymupdf.Rect, y_lo: float, y_hi: float, page: pymupdf.Page) -> pymupdf.Rect | None:
    clipped = pymupdf.Rect(
        max(0.0, float(r.x0)),
        max(y_lo, float(r.y0)),
        min(float(page.rect.width), float(r.x1)),
        min(y_hi, float(r.y1)),
    )
    if clipped.width < 10 or clipped.height < 10:
        return None
    return clipped


def _union_rects(rects: list[pymupdf.Rect]) -> pymupdf.Rect | None:
    if not rects:
        return None
    u = pymupdf.Rect(rects[0])
    for r in rects[1:]:
        u |= r
    return u


def _build_caption_slots(
    page: pymupdf.Page,
    captions: list[_RawBlock],
    figure_regions: list[pymupdf.Rect],
    table_regions: list[pymupdf.Rect],
    chart_regions: list[pymupdf.Rect],
) -> list[_VisualSlot]:
    """One visual placeholder per Figure/Table caption — merged, not fragmented."""
    page_h = float(page.rect.height)
    page_w = float(page.rect.width)
    caps = sorted(captions, key=lambda c: (c.y0, c.x0))
    slots: list[_VisualSlot] = []

    # All detector seeds (figures + charts + tables)
    seeds = list(figure_regions) + list(chart_regions) + list(table_regions)

    for i, cap in enumerate(caps):
        key = _caption_key(cap.text)
        if not key:
            continue
        is_table = key.startswith("table:")
        kind = "placeholder_table" if is_table else "placeholder_figure"

        y_lo = caps[i - 1].y1 + 6 if i > 0 else 0.0
        # Don't stretch across half a page of prose for mid-page tables
        if is_table:
            y_lo = max(y_lo, cap.y0 - min(220.0, page_h * 0.35))
        else:
            y_lo = max(y_lo, cap.y0 - min(420.0, page_h * 0.55))
        y_hi = max(y_lo + 8, cap.y0 - 2)

        pieces: list[pymupdf.Rect] = []
        for seed in seeds:
            if seed.y1 <= y_lo or seed.y0 >= y_hi:
                continue
            clipped = _clip_rect(seed, y_lo, y_hi, page)
            if clipped:
                pieces.append(clipped)

        # Prefer table-finder hits for tables; fall back to text-cell union
        if is_table:
            tab_hits = [
                c
                for c in (_clip_rect(t, y_lo, y_hi, page) for t in table_regions)
                if c is not None
            ]
            if tab_hits:
                pieces = tab_hits
            elif not pieces or (
                (u := _union_rects(pieces)) is not None and u.get_area() < 4_000
            ):
                text_u = _band_text_union(page, y_lo, y_hi)
                if text_u and text_u.height >= 28 and text_u.width >= 80:
                    pieces = [text_u]

        if not pieces and not is_table:
            # Vector-only figures: denser drawing ink in the band
            draw_boxes: list[pymupdf.Rect] = []
            try:
                for drawing in page.get_drawings():
                    rect = drawing.get("rect")
                    if not rect:
                        continue
                    r = pymupdf.Rect(rect)
                    if r.get_area() < 40:
                        continue
                    clipped = _clip_rect(r, y_lo, y_hi, page)
                    if clipped:
                        draw_boxes.append(clipped)
            except Exception:  # noqa: BLE001
                pass
            if draw_boxes:
                merged = _merge_rects(draw_boxes, gap=22.0)
                big = [r for r in merged if r.get_area() >= 3_000 or r.width >= 120]
                pieces = big or merged

        union = _union_rects(pieces)
        if not union:
            continue

        # Pad, then clamp under caption
        slot = _VisualSlot(
            x0=max(0.0, union.x0 - 6),
            y0=max(0.0, union.y0 - 4),
            x1=min(page_w, union.x1 + 6),
            y1=min(y_hi, union.y1 + 4),
            kind=kind,
            caption_key=key,
        )
        if slot.y1 - slot.y0 < 16 or slot.x1 - slot.x0 < 24:
            continue
        slots.append(slot)

    # Drop slots heavily covered by a larger same-page sibling
    slots.sort(key=lambda s: (s.y0, s.x0))
    kept: list[_VisualSlot] = []
    for slot in slots:
        area = max(1.0, (slot.x1 - slot.x0) * (slot.y1 - slot.y0))
        dominated = False
        for other in kept:
            ix0 = max(slot.x0, other.x0)
            iy0 = max(slot.y0, other.y0)
            ix1 = min(slot.x1, other.x1)
            iy1 = min(slot.y1, other.y1)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            overlap = (ix1 - ix0) * (iy1 - iy0) / area
            other_area = (other.x1 - other.x0) * (other.y1 - other.y0)
            if overlap >= 0.55 and other_area >= area:
                dominated = True
                break
        if not dominated:
            kept.append(slot)
    return kept


def _slot_covers_block(slot: _VisualSlot, block: _RawBlock, *, min_overlap: float = 0.45) -> bool:
    bw = max(1.0, block.x1 - block.x0)
    bh = max(1.0, block.y1 - block.y0)
    ix0 = max(slot.x0, block.x0)
    iy0 = max(slot.y0, block.y0)
    ix1 = min(slot.x1, block.x1)
    iy1 = min(slot.y1, block.y1)
    if ix1 <= ix0 or iy1 <= iy0:
        return False
    return ((ix1 - ix0) * (iy1 - iy0)) / (bw * bh) >= min_overlap


def _insert_placeholders(
    items: list[_RawBlock],
    slots: list[_VisualSlot],
) -> list[_RawBlock]:
    """Weave one placeholder before each matched caption; drop covered fragments."""
    if not slots and not any(i.block_type == "formula_skip" for i in items):
        return items

    # Remove text fragments that sit inside a visual slot (cells / labels)
    cleaned: list[_RawBlock] = []
    for item in items:
        if item.block_type in ("caption", "heading", "title", "page_number", "formula_skip"):
            cleaned.append(item)
            continue
        if any(_slot_covers_block(s, item) for s in slots):
            continue
        cleaned.append(item)

    by_key = {s.caption_key: s for s in slots if s.caption_key}
    used_keys: set[str] = set()
    out: list[_RawBlock] = []

    for item in cleaned:
        if item.block_type == "caption":
            key = _caption_key(item.text)
            slot = by_key.get(key) if key else None
            if slot and key not in used_keys:
                out.append(
                    _RawBlock(
                        slot.x0,
                        slot.y0,
                        slot.x1,
                        slot.y1,
                        "",
                        slot.kind,
                        0.0,
                    )
                )
                used_keys.add(key)
        out.append(item)

    # Orphan slots (no caption match) — insert by vertical position
    orphans = [s for s in slots if not s.caption_key or s.caption_key not in used_keys]
    if orphans:
        combined = out + [
            _RawBlock(s.x0, s.y0, s.x1, s.y1, "", s.kind, 0.0) for s in orphans
        ]
        combined.sort(key=lambda b: (round(b.y0, 1), round(b.x0, 1)))
        return combined
    return out


def parse_document(db: Session, document: Document) -> ParseResult:
    block_ids = [
        row[0]
        for row in db.query(Block.id).filter(Block.document_id == document.id).all()
    ]
    if block_ids:
        db.query(Translation).filter(Translation.block_id.in_(block_ids)).delete(
            synchronize_session=False
        )
    db.query(Block).filter(Block.document_id == document.id).delete()
    db.flush()

    try:
        doc = pymupdf.open(document.path)
    except Exception as exc:  # noqa: BLE001
        document.status = "error"
        document.status_message = f"Failed to open PDF: {exc}"
        db.commit()
        return ParseResult(0, 0, "error", document.status_message)

    total_chars = 0
    block_count = 0

    for page_index, page in enumerate(doc):
        page_width = float(page.rect.width)
        page_height = float(page.rect.height)
        spans = _collect_spans(page)
        figure_regions = _page_image_figure_regions(page)
        table_regions = _page_table_regions(page)
        chart_regions = _page_chart_regions(page, spans)

        raw_blocks = page.get_text("blocks")
        ordered = sorted(raw_blocks, key=lambda b: (round(b[1], 1), round(b[0], 1)))
        page_items: list[_RawBlock] = []
        for raw in ordered:
            x0, y0, x1, y1, text, *_rest = raw
            text = (text or "").strip()
            if not text:
                continue
            w = float(x1 - x0)
            h = float(y1 - y0)
            if w < 2 or h < 2:
                continue
            total_chars += len(text)
            avg_font = _avg_font_size(spans, float(x0), float(y0), float(x1), float(y1))
            page_items.append(
                _RawBlock(
                    float(x0),
                    float(y0),
                    float(x1),
                    float(y1),
                    text,
                    _classify(
                        text,
                        w,
                        h,
                        page_width,
                        float(x0),
                        float(y0),
                        float(x1),
                        float(y1),
                        figure_regions,
                        table_regions,
                        chart_regions,
                        avg_font,
                        page_index=page_index,
                        page_height=page_height,
                    ),
                    float(avg_font or 0.0),
                )
            )

        merged = _reattach_drop_caps(_merge_fragments(page_items))
        captions = [item for item in merged if item.block_type == "caption"]
        slots = _build_caption_slots(
            page, captions, figure_regions, table_regions, chart_regions
        )
        kept = [item for item in merged if item.block_type != "skip"]
        ordered_items = _insert_placeholders(kept, slots)
        for local_idx, item in enumerate(ordered_items):
            db.add(
                Block(
                    id=str(uuid.uuid4()),
                    document_id=document.id,
                    page_index=page_index,
                    block_index=local_idx,
                    text=item.text,
                    bbox_x0=item.x0,
                    bbox_y0=item.y0,
                    bbox_x1=item.x1,
                    bbox_y1=item.y1,
                    block_type=item.block_type,
                    font_size=item.font_size,
                    page_width=page_width,
                    page_height=page_height,
                )
            )
            block_count += 1

    page_count = doc.page_count
    doc.close()

    document.page_count = page_count
    if page_count > 0 and total_chars < max(40, page_count * 15):
        document.status = "unsupported_scan"
        document.status_message = (
            "Very little extractable text. Scanned image PDFs are not supported yet."
        )
        status = "unsupported_scan"
    else:
        document.status = "ready"
        document.status_message = ""
        status = "ready"

    if not document.title:
        document.title = document.filename.rsplit(".", 1)[0]

    db.commit()
    return ParseResult(page_count, block_count, status, document.status_message)
