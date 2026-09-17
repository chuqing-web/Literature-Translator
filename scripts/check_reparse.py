import json
import sys
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

DOC = "699c8478-e2b0-45f8-a074-0a1c161739bd"
for pi in [0, 1, 3, 4]:
    blocks = json.load(
        urllib.request.urlopen(f"http://127.0.0.1:8787/api/documents/{DOC}/pages/{pi}/blocks")
    )
    print(f"page{pi} n={len(blocks)}", dict(Counter(x["block_type"] for x in blocks)))
    for x in blocks[:5]:
        t = (x.get("text") or "").replace("\n", " ")[:55]
        print(f"  {x['block_index']} {x['block_type']:12s} {t}")
    for x in blocks:
        t = (x.get("text") or "").replace("\n", " ").strip().lower()
        if t.startswith(("frame ", "step ", "points", "box ")) and len(t) < 40:
            print("  !! figure label kept:", t)

req = urllib.request.Request(
    f"http://127.0.0.1:8787/api/documents/{DOC}/translate",
    method="POST",
    data=b"",
)
print("job", json.dumps(json.load(urllib.request.urlopen(req)), ensure_ascii=False))
