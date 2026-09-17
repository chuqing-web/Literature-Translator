import json
import sys
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

DOC = "699c8478-e2b0-45f8-a074-0a1c161739bd"

# reparse
req = urllib.request.Request(
    f"http://127.0.0.1:8787/api/documents/{DOC}/parse",
    method="POST",
    data=b"",
)
print("reparse", json.load(urllib.request.urlopen(req)).get("status"))

bad_needles = (
    "clicks per",
    "edited frames",
    "phase 1",
    "all small",
    "#videos",
    "frame 1",
    "step 1",
    "points box",
    "number of annotated",
    "average j&f",
)

for pi in [0, 1, 3, 4, 6, 8]:
    blocks = json.load(
        urllib.request.urlopen(f"http://127.0.0.1:8787/api/documents/{DOC}/pages/{pi}/blocks")
    )
    print(f"page{pi} n={len(blocks)}", dict(Counter(b["block_type"] for b in blocks)))
    for b in blocks[:4]:
        t = (b.get("text") or "").replace("\n", " ")[:55]
        print(f"  {b['block_index']} {b['block_type']:8s} {t}")
    for b in blocks:
        t = (b.get("text") or "").replace("\n", " ").strip().lower()
        for needle in bad_needles:
            if needle in t and len(t) < 120:
                print(f"  !! KEPT chart/table text: {t[:70]}")
                break

# restart translate
req = urllib.request.Request(
    f"http://127.0.0.1:8787/api/documents/{DOC}/translate",
    method="POST",
    data=b"",
)
print("job", json.load(urllib.request.urlopen(req))["job"]["id"])
