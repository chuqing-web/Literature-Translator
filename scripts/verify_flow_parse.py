import json
import sys
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
DOC = "699c8478-e2b0-45f8-a074-0a1c161739bd"
req = urllib.request.Request(
    f"http://127.0.0.1:8787/api/documents/{DOC}/parse", method="POST", data=b""
)
print("reparse", json.load(urllib.request.urlopen(req)).get("status"))
for pi in [0, 1]:
    blocks = json.load(
        urllib.request.urlopen(f"http://127.0.0.1:8787/api/documents/{DOC}/pages/{pi}/blocks")
    )
    print(f"page{pi}", dict(Counter(b["block_type"] for b in blocks)))
    for b in blocks[:10]:
        t = (b.get("text") or "").replace("\n", " ")[:40]
        print(
            f"  {b['block_index']:02d} {b['block_type']:20s} font={float(b.get('font_size') or 0):.1f} {t}"
        )
req = urllib.request.Request(
    f"http://127.0.0.1:8787/api/documents/{DOC}/translate", method="POST", data=b""
)
print("job", json.load(urllib.request.urlopen(req))["job"]["id"])
