import json
import urllib.request

blocks = json.load(
    urllib.request.urlopen(
        "http://127.0.0.1:8787/api/documents/699c8478-e2b0-45f8-a074-0a1c161739bd/pages/1/blocks"
    )
)
for b in blocks:
    text = (b.get("text") or "")[:80].replace("\n", " ")
    print(
        b["block_index"],
        b["block_type"],
        f"y={b['bbox_y0']:.0f}-{b['bbox_y1']:.0f}",
        f"x={b['bbox_x0']:.0f}-{b['bbox_x1']:.0f}",
        text,
    )
