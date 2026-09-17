"""Diagnose figure/table/chart regions on problem pages."""
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import pymupdf

DOC = "699c8478-e2b0-45f8-a074-0a1c161739bd"
# Resolve PDF path via API metadata isn't enough — open from library
lib = Path(r"c:\Projects\Literature Translator\apps\api\data\library")
pdfs = list(lib.glob(f"{DOC}.pdf"))
if not pdfs:
    lib = Path(r"c:\Projects\Literature Translator\data\library")
    pdfs = list(lib.glob(f"{DOC}.pdf"))
print("pdf", pdfs)

# Also dump API blocks for pages 3,4,6 (1-based 4,5,7)
for pi in [3, 4, 6]:
    blocks = json.load(
        urllib.request.urlopen(
            f"http://127.0.0.1:8787/api/documents/{DOC}/pages/{pi}/blocks"
        )
    )
    types = Counter(b["block_type"] for b in blocks)
    print(f"\n=== API page {pi+1} ===", dict(types))
    for b in blocks:
        t = (b.get("text") or "").replace("\n", " ")[:50]
        w = b["bbox_x1"] - b["bbox_x0"]
        h = b["bbox_y1"] - b["bbox_y0"]
        print(
            f"  {b['block_index']:02d} {b['block_type']:20s} "
            f"y={b['bbox_y0']:.0f}-{b['bbox_y1']:.0f} "
            f"{w:.0f}x{h:.0f} {t!r}"
        )
