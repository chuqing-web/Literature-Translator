import json
import urllib.request
from pathlib import Path

import pymupdf

DOC = "699c8478-e2b0-45f8-a074-0a1c161739bd"
pdf = Path(r"c:\Projects\Literature Translator\data\library") / f"{DOC}.pdf"
doc = pymupdf.open(pdf)
for pi in [3, 4, 6]:
    page = doc[pi]
    print(f"\npage {pi+1} h={page.rect.height} threshold={page.rect.height*0.85:.1f}")
    for raw in page.get_text("blocks"):
        t = (raw[4] or "").strip()
        if t.isdigit() and len(t) <= 3:
            print(f"  digit block y={raw[1]:.1f}-{raw[3]:.1f} w={raw[2]-raw[0]:.1f} h={raw[3]-raw[1]:.1f} text={t!r}")
    blocks = json.load(
        urllib.request.urlopen(f"http://127.0.0.1:8787/api/documents/{DOC}/pages/{pi}/blocks")
    )
    pn = [b for b in blocks if b["block_type"] == "page_number"]
    print("  api page_number", pn)
    ph = [b for b in blocks if b["block_type"].startswith("placeholder")]
    for b in ph:
        bid = b["id"]
        data = urllib.request.urlopen(
            f"http://127.0.0.1:8787/api/documents/{DOC}/blocks/{bid}/preview.png"
        ).read()
        out = Path(rf"c:\Projects\Literature Translator\verify-p{pi+1}-{b['block_type']}.png")
        out.write_bytes(data)
        print(f"  preview {out.name} {len(data)}B size={b['bbox_x1']-b['bbox_x0']:.0f}x{b['bbox_y1']-b['bbox_y0']:.0f}")
doc.close()
