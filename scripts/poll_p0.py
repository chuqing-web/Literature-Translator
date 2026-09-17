import json
import time
import urllib.request

DOC = "699c8478-e2b0-45f8-a074-0a1c161739bd"
JOB = "17bd73b2-7ae0-443c-9bb2-c1a9448b0a5b"

for _ in range(25):
    j = json.load(urllib.request.urlopen(f"http://127.0.0.1:8787/api/translate/jobs/{JOB}"))
    p0 = json.load(
        urllib.request.urlopen(f"http://127.0.0.1:8787/api/documents/{DOC}/pages/0/blocks")
    )
    done = sum(1 for b in p0 if b.get("translation"))
    print(f"{j['status']} {j['done']}/{j['total']} page0 {done}/{len(p0)} err={j.get('error','')[:50]}")
    if done >= len(p0) and done > 0:
        break
    if j["status"] not in ("pending", "running"):
        break
    time.sleep(3)
