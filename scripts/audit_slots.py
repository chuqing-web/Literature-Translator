import json
import urllib.request

DOC = "699c8478-e2b0-45f8-a074-0a1c161739bd"
for pi in range(0, 15):
    blocks = json.load(
        urllib.request.urlopen(
            f"http://127.0.0.1:8787/api/documents/{DOC}/pages/{pi}/blocks"
        )
    )
    caps = [b for b in blocks if b["block_type"] == "caption"]
    figs = [b for b in blocks if b["block_type"] == "placeholder_figure"]
    tabs = [b for b in blocks if b["block_type"] == "placeholder_table"]
    formulas = [b for b in blocks if b["block_type"] == "formula_skip"]
    pn = [b for b in blocks if b["block_type"] == "page_number"]
    if not (caps or figs or tabs or formulas):
        continue
    labels = [(b.get("text") or "").replace("\n", " ")[:28] for b in caps]
    print(
        f"p{pi+1}: figs={len(figs)} tabs={len(tabs)} formulas={len(formulas)} "
        f"caps={len(caps)} pn={len(pn)} | {labels}"
    )
    # Expect: each figure/table caption has exactly one matching placeholder before it
    for b in blocks:
        if b["block_type"] == "caption":
            pass
    # Check weave: placeholder immediately before its caption
    for i, b in enumerate(blocks):
        if b["block_type"] != "caption":
            continue
        prev = blocks[i - 1] if i else None
        ok = prev and prev["block_type"].startswith("placeholder")
        if not ok:
            print(f"  WARN caption without preceding placeholder: {labels}")
