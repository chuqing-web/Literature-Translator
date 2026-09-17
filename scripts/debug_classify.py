import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "apps/api")

import pymupdf
from app.services import pdf_parse as pp

doc = pymupdf.open(r"data/library/699c8478-e2b0-45f8-a074-0a1c161739bd.pdf")
for pi in [0, 6, 8]:
    p = doc[pi]
    spans = pp._collect_spans(p)
    figs = pp._page_image_figure_regions(p)
    tabs = pp._page_table_regions(p)
    charts = pp._page_chart_regions(p, spans)
    print(f"=== page {pi}")
    print("  figs", len(figs), [(round(r.y0), round(r.y1)) for r in figs])
    print("  tabs", len(tabs), [(round(r.y0), round(r.y1)) for r in tabs])
    print("  charts", [(round(r.x0), round(r.y0), round(r.x1), round(r.y1)) for r in charts])
    for b in p.get_text("blocks"):
        x0, y0, x1, y1, text, *_ = b
        text = (text or "").strip()
        if not text:
            continue
        avg = pp._avg_font_size(spans, x0, y0, x1, y1)
        cls = pp._classify(
            text,
            x1 - x0,
            y1 - y0,
            float(p.rect.width),
            x0,
            y0,
            x1,
            y1,
            figs,
            tabs,
            charts,
            avg,
        )
        t = text.replace("\n", " ")[:55]
        print(f"  {cls:12s} font={avg} h={y1-y0:.1f} {t!r}")
doc.close()
