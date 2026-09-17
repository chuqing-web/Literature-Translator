import json
import sys
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
DOC = "699c8478-e2b0-45f8-a074-0a1c161739bd"
for pi in [0, 1]:
    blocks = json.load(
        urllib.request.urlopen(
            f"http://127.0.0.1:8787/api/documents/{DOC}/pages/{pi}/blocks"
        )
    )
    types = Counter(b["block_type"] for b in blocks)
    done = sum(1 for b in blocks if b.get("translation"))
    print(f"page{pi}", dict(types), f"translated={done}/{len(blocks)}")
    for b in blocks[:8]:
        tr = (b.get("translation") or "").replace("\n", " ")[:40]
        src = (b.get("text") or "").replace("\n", " ")[:36]
        print(
            f"  {b['block_index']:02d} {b['block_type']:20s} "
            f"font={float(b.get('font_size') or 0):.1f} "
            f"src={src!r} zh={tr!r}"
        )
