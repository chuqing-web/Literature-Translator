import json
import urllib.request

DOC = "699c8478-e2b0-45f8-a074-0a1c161739bd"
blocks = json.load(
    urllib.request.urlopen(f"http://127.0.0.1:8787/api/documents/{DOC}/pages/0/blocks")
)
print("p0", len(blocks), "done", sum(1 for x in blocks if x.get("translation")))
for b in blocks:
    print(b["block_index"], b.get("translation_status"), (b.get("translation") or "")[:50])

req = urllib.request.Request(
    f"http://127.0.0.1:8787/api/documents/{DOC}/translate",
    method="POST",
    data=b"",
)
print("job", json.load(urllib.request.urlopen(req)))
