import json
import urllib.request

DOC = "699c8478-e2b0-45f8-a074-0a1c161739bd"
req = urllib.request.Request(
    f"http://127.0.0.1:8787/api/documents/{DOC}/translate",
    method="POST",
    data=b"",
)
print(json.dumps(json.load(urllib.request.urlopen(req)), ensure_ascii=False))
