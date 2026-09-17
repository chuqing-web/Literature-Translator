import json
import time
import urllib.request

DOC = "699c8478-e2b0-45f8-a074-0a1c161739bd"
JOB = "6f5586d4-9f2f-4490-8a35-0d6937390ff0"

for i in range(20):
    j = json.load(
        urllib.request.urlopen(f"http://127.0.0.1:8787/api/translate/jobs/{JOB}")
    )
    p1 = json.load(
        urllib.request.urlopen(f"http://127.0.0.1:8787/api/documents/{DOC}/pages/1/blocks")
    )
    done = sum(1 for b in p1 if b.get("translation"))
    print(
        f"{j['status']} {j['done']}/{j['total']} page1 {done}/{len(p1)} err={j.get('error','')[:60]}"
    )
    if j["status"] not in ("pending", "running"):
        break
    if done >= len(p1) and j["done"] > 10:
        break
    time.sleep(3)
