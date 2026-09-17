import json
import time
import urllib.request

JOB = "3d960c15-175d-4c51-8ad0-234e016627c1"
DOC = "699c8478-e2b0-45f8-a074-0a1c161739bd"


def get(url: str):
    return json.load(urllib.request.urlopen(url))


for _ in range(40):
    j = get(f"http://127.0.0.1:8787/api/translate/jobs/{JOB}")
    blocks = get(f"http://127.0.0.1:8787/api/documents/{DOC}/pages/0/blocks")
    done = sum(1 for b in blocks if b.get("translation"))
    err = (j.get("error") or "")[:80]
    print(f"job {j['status']} {j['done']}/{j['total']} page0 {done}/{len(blocks)} err={err}")
    if done >= max(1, len(blocks) - 1):
        break
    time.sleep(4)
