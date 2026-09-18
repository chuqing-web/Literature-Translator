"""Heuristics for scholarly math / equation fragments.

Used by PDF parsing (mark formula_skip) and translation (keep formulas unchanged).
"""

from __future__ import annotations

import re

# Core equation / operator cues
_FORMULA_HINT = re.compile(
    r"[=∫∑∏√≤≥±×÷∞∂∇∈∉⊂⊆→←↔≈≠≡⋅∘⊕⊗]|\\frac|\\sum|\\sqrt|\\begin\{|\\text\{|softmax|argmax|argmin",
    re.I,
)
_EQ_NUMBER = re.compile(r"\(\s*\d{1,3}\s*\)\s*$")
_WORDISH = re.compile(r"[A-Za-z\u4e00-\u9fff]{4,}")
_AUTHOR_FOOTNOTE = re.compile(r"[∗*†‡§¶\d]+")
_DISPLAY_MATH = re.compile(r"\$\$[\s\S]*?\$\$")
_INLINE_MATH = re.compile(r"(?<!\$)\$([^\$\n]+)\$(?!\$)")
_FABRICATED_DEF = re.compile(
    r"^(其中|式中|这里|此处).{0,8}[A-Za-z].{0,6}(为|是|表示)",
)
_PURE_EQ_LINE = re.compile(
    r"^(\$\$.*\$\$|\$[^$]+\$|[A-Za-z][A-Za-z0-9_]*\s*=\s*.+)$"
)
_WHERE_DEF_SRC = re.compile(
    r"\bwhere\s+[A-Za-z]|"
    r"\bin which\s+[A-Za-z]|"
    r"\bwith\s+[A-Za-z]\s+(?:the|a|an|being)\b",
    re.I,
)
_INTRO_ONLY_SRC = re.compile(
    r"(denoted as follows|as follows|can be (?:written|expressed|represented)|"
    r"is given by|given by|defined as)\s*:?\s*$",
    re.I,
)
_STRUCT_LINE = re.compile(
    r"^(?:"
    r"Demo|Code|Website|Websites|GitHub|Paper|Project|Homepage|Source|Dataset|"
    r"演示|代码|网站|主页|项目|数据|论文"
    r")\s*[:：]",
    re.I,
)
_URL_LINE = re.compile(r"^https?://\S+", re.I)
_LABEL_URL = re.compile(
    r"(?<![A-Za-z\u4e00-\u9fff])(?:Demo|Code|Website|Websites|GitHub|Paper|Project|"
    r"Homepage|演示|代码|网站|主页|项目)\s*[:：]\s*https?://",
    re.I,
)


def _is_structural_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return True
    if _STRUCT_LINE.match(s) or _URL_LINE.match(s):
        return True
    # Short "Label: value" rows (links, footnotes) keep their breaks.
    if re.match(r"^[\w\u4e00-\u9fff .]{1,24}\s*[:：]\s*\S", s) and len(s) <= 140:
        if "://" in s or "@" in s or s.count(" ") <= 6:
            return True
    return False


def _should_join_soft_wrap(prev: str, nxt: str) -> bool:
    p = (prev or "").rstrip()
    n = (nxt or "").lstrip()
    if not p or not n:
        return False
    if _is_structural_line(p) or _is_structural_line(n):
        return False
    # Hyphenated wrap already handled before split; remaining wraps:
    # mid-sentence / mid-phrase PDF column breaks.
    if re.search(r"[.!?。！？]$", p):
        return False
    if _STRUCT_LINE.match(n) or _URL_LINE.match(n):
        return False
    # Very short token lines (Index\nTerms\n…) — join.
    if len(p) <= 28 or len(n) <= 28:
        return True
    if n[:1].islower() or n[:1] in "，、；,;)]}":
        return True
    if not re.search(r"[.!?。！？:：]$", p) and len(p) < 70:
        return True
    return False


def restore_structural_breaks(text: str) -> str:
    """Re-insert newlines before Demo/Code/Website rows if they were flattened."""
    raw = text or ""
    if not raw.strip():
        return ""
    # Split before each structural label that starts a URL row.
    raw = re.sub(
        r"(?<!^)\s+(?="
        r"(?:Demo|Code|Website|Websites|GitHub|Paper|Project|Homepage|"
        r"演示|代码|网站|主页|项目)\s*[:：]\s*https?://"
        r")",
        "\n",
        raw,
        flags=re.I,
    )
    return raw


def soft_unwrap(text: str) -> str:
    """Join PDF soft wraps; keep real list / link / blank-line breaks."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        return ""
    # First restore flattened Demo/Code/Website rows.
    raw = restore_structural_breaks(raw)
    # "segmen-\ntation" → "segmentation"
    raw = re.sub(r"-\n\s*", "", raw)

    parts = raw.split("\n")
    out: list[str] = []
    buf = (parts[0] if parts else "").rstrip()
    for line in parts[1:]:
        if _should_join_soft_wrap(buf, line):
            joiner = "" if buf.endswith("-") else " "
            buf = f"{buf.rstrip('-')}{joiner}{line.lstrip()}".rstrip()
        else:
            out.append(buf)
            buf = line.rstrip()
    if buf or not out:
        out.append(buf)

    joined = "\n".join(out)
    # Collapse spaces on each physical line only.
    fixed_lines: list[str] = []
    for ln in joined.split("\n"):
        s = re.sub(r"[ \t\u00a0]+", " ", ln).strip()
        while True:
            nxt = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", s)
            if nxt == s:
                break
            s = nxt
        s = re.sub(r"([，。；：、！？])\s+", r"\1", s)
        s = re.sub(r"\s+([，。；：、！？])", r"\1", s)
        fixed_lines.append(s)
    joined = "\n".join(fixed_lines)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()


def is_author_line_text(text: str) -> bool:
    """Comma-separated person-name lines (paper authors), not affiliations/prose."""
    raw = (text or "").strip()
    if not raw or len(raw) > 420:
        return False
    compact = re.sub(r"\s+", " ", raw)
    lower = compact.lower()
    if any(k in lower for k in ("university", "institute", "department", "http://", "https://", "@")):
        return False
    # Need name separators
    if "," not in compact and " and " not in lower:
        return False
    cleaned = _AUTHOR_FOOTNOTE.sub("", compact)
    parts = [p.strip() for p in re.split(r",| and ", cleaned, flags=re.I) if p.strip()]
    if len(parts) < 2:
        return False
    nameish = 0
    for part in parts:
        words = [w for w in part.split() if w]
        if not words or len(words) > 5:
            continue
        ok = True
        for w in words:
            if w.lower() in ("and", "of", "the"):
                continue
            if not re.match(r"^[A-ZÀ-ÖØ-Þ]", w):
                ok = False
                break
            if len(w) > 18:
                ok = False
                break
        if ok:
            nameish += 1
    return nameish >= max(2, int(len(parts) * 0.65))


def is_formula_like_text(text: str) -> bool:
    """True when a block is (or continues) a display/inline equation, not prose."""
    raw = (text or "").strip()
    if not raw:
        return False
    compact = re.sub(r"\s+", " ", raw)
    if len(compact) > 220:
        return False

    if _FORMULA_HINT.search(raw) and len(compact) < 160:
        # Avoid treating normal prose sentences that merely contain '=' once
        # and lots of words as formulas.
        words = _WORDISH.findall(compact)
        if len(words) <= 4 or len(compact) < 80:
            return True

    # Split equation tails: "pdk)V,\n(3)" / "√d_k)V, (3)"
    if _EQ_NUMBER.search(compact) and len(compact) < 80:
        words = _WORDISH.findall(re.sub(r"\(\s*\d{1,3}\s*\)", "", compact))
        if len(words) <= 1:
            return True

    # Dense symbol / short identifier soup
    letters = sum(ch.isalpha() for ch in compact)
    digits = sum(ch.isdigit() for ch in compact)
    symbols = sum(ch in "=+-*/^_()[]{}\\<>|," for ch in compact)
    if len(compact) < 64 and symbols >= 3 and symbols + digits >= letters:
        return True

    return False


def sanitize_math_translation(source: str, translated: str) -> str:
    """Remove invented math so PDF equation glyphs stay visible and unchanged."""
    src = source or ""
    out = (translated or "").strip()
    if not out:
        return out

    src_has_dollar = "$" in src
    src_has_eq = bool(_FORMULA_HINT.search(src))
    # Source is itself a "where Q, K, V are…" definition — keep 其中… prose.
    src_is_where_def = bool(_WHERE_DEF_SRC.search(src))
    src_intro_only = bool(_INTRO_ONLY_SRC.search(soft_unwrap(src)))

    if not src_has_dollar:
        # Drop fabricated display equations entirely (do not keep their body).
        out = _DISPLAY_MATH.sub("", out)
        # Unwrap inline $var$ → var
        out = _INLINE_MATH.sub(r"\1", out)

    # Models often emit Markdown-escaped underscores inside math/names.
    out = out.replace("\\_", "_")
    out = out.replace("\\{", "{").replace("\\}", "}")

    # Only strip trailing fabricated glosses when the source does not already
    # explain the symbols (e.g. short "as follows:" intros). Never wipe a
    # full "where Q, K, and V are…" paragraph translation.
    if not src_has_eq and not src_is_where_def:
        out = re.sub(
            r"((?:如下|为下|表示为|记为|如下所示)[:：])\s*[\s\S]*$",
            r"\1",
            out,
        )
        kept: list[str] = []
        for line in out.splitlines():
            s = line.strip()
            if not s:
                if kept:
                    kept.append(line)
                continue
            if _DISPLAY_MATH.search(s) or _PURE_EQ_LINE.match(s):
                break
            if src_intro_only and _FABRICATED_DEF.match(s):
                break
            if (
                src_intro_only
                and re.search(r"(其中|式中)\s*[A-Za-z]", s)
                and re.search(r"(为|是|表示)", s)
            ):
                break
            kept.append(line)
        out = "\n".join(kept).rstrip()

    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    # PDF / model soft wraps must not become hard Chinese line breaks.
    return soft_unwrap(out)
