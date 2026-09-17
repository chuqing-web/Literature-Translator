import json
import urllib.request
from pathlib import Path

DOC = "699c8478-e2b0-45f8-a074-0a1c161739bd"
blocks = json.load(
    urllib.request.urlopen(f"http://127.0.0.1:8787/api/documents/{DOC}/pages/6/blocks")
)
for i, b in enumerate(blocks):
    if b["block_type"].startswith("placeholder"):
        data = urllib.request.urlopen(
            f"http://127.0.0.1:8787/api/documents/{DOC}/blocks/{b['id']}/preview.png"
        ).read()
        path = Path(rf"c:\Projects\Literature Translator\verify-p7-slot{i}.png")
        path.write_bytes(data)
        print(i, b["block_type"], f"{b['bbox_y1']-b['bbox_y0']:.0f}h", path.name, len(data))
