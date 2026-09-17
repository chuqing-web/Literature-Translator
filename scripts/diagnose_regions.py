"""Dump raw image/table/chart regions for problem pages."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(r"c:\Projects\Literature Translator\apps\api")))

import pymupdf
from app.services.pdf_parse import (
    _collect_spans,
    _page_chart_regions,
    _page_image_figure_regions,
    _page_table_regions,
)

pdf = Path(r"c:\Projects\Literature Translator\data\library\699c8478-e2b0-45f8-a074-0a1c161739bd.pdf")
doc = pymupdf.open(pdf)
for pi in [3, 4, 6]:
    page = doc[pi]
    spans = _collect_spans(page)
    figs = _page_image_figure_regions(page)
    tabs = _page_table_regions(page)
    charts = _page_chart_regions(page, spans)
    print(f"\n=== page {pi+1} size={page.rect.width:.0f}x{page.rect.height:.0f} ===")
    print(f"  images/figures ({len(figs)}):")
    for r in figs:
        print(f"    {r.x0:.0f},{r.y0:.0f}-{r.x1:.0f},{r.y1:.0f}  {r.width:.0f}x{r.height:.0f}")
    print(f"  tables ({len(tabs)}):")
    for r in tabs:
        print(f"    {r.x0:.0f},{r.y0:.0f}-{r.x1:.0f},{r.y1:.0f}  {r.width:.0f}x{r.height:.0f}")
    print(f"  charts ({len(charts)}):")
    for r in charts:
        print(f"    {r.x0:.0f},{r.y0:.0f}-{r.x1:.0f},{r.y1:.0f}  {r.width:.0f}x{r.height:.0f} area={r.get_area():.0f}")
    # captions from text blocks
    for raw in page.get_text("blocks"):
        t = (raw[4] or "").strip().replace("\n", " ")
        if t.lower().startswith(("figure", "fig.", "table", "tab.")):
            print(f"  CAPTION y={raw[1]:.0f}-{raw[3]:.0f}: {t[:70]!r}")
doc.close()
