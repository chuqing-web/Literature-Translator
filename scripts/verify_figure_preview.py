import json
import urllib.request

DOC = "699c8478-e2b0-45f8-a074-0a1c161739bd"
blocks = json.load(
    urllib.request.urlopen(f"http://127.0.0.1:8787/api/documents/{DOC}/pages/1/blocks")
)
ph = [b for b in blocks if b["block_type"].startswith("placeholder")]
print("placeholders", len(ph))
for b in ph:
    print(" ", b["block_type"], round(b["bbox_x1"] - b["bbox_x0"], 1), "x", round(b["bbox_y1"] - b["bbox_y0"], 1))
if ph:
    url = f"http://127.0.0.1:8787/api/documents/{DOC}/blocks/{ph[0]['id']}/preview.png"
    req = urllib.request.urlopen(url)
    data = req.read()
    print("preview", req.status, req.headers.get("content-type"), "bytes", len(data))
    out = r"c:\Projects\Literature Translator\verify-figure-preview.png"
    open(out, "wb").write(data)
    print("wrote", out)
