import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
import pymupdf

pdf = Path(r"c:\Projects\Literature Translator\data\library\699c8478-e2b0-45f8-a074-0a1c161739bd.pdf")
doc = pymupdf.open(pdf)
page = doc[6]
print("=== page 7 all text blocks (y ordered) ===")
for raw in sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0])):
    t = (raw[4] or "").strip().replace("\n", " ")[:60]
    print(f"  y={raw[1]:.0f}-{raw[3]:.0f} x={raw[0]:.0f}-{raw[2]:.0f} {t!r}")
print("\n=== images ===")
for info in page.get_image_info():
    print(" ", info.get("bbox"))
print("\n=== drawings sample (large) ===")
for d in page.get_drawings():
    r = pymupdf.Rect(d.get("rect"))
    if r.get_area() > 500:
        print(f"  {r.x0:.0f},{r.y0:.0f}-{r.x1:.0f},{r.y1:.0f} {r.width:.0f}x{r.height:.0f}")
doc.close()
