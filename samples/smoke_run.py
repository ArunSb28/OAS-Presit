"""End-to-end smoke run: generate + execute every test against the mock gateway."""
import collections
import sys

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
TARGET = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:9000"
c = httpx.Client(base_url=API, timeout=30)
tot = collections.Counter()
for e in c.get("/api/endpoints").json()["endpoints"]:
    for t in c.get(f"/api/endpoints/{e['id']}/testcases").json()["testcases"]:
        r = c.post("/api/execute", json={"endpoint_id": e["id"], "testcase": t, "base_url": TARGET}).json()
        k = "pass" if r.get("passed") else ("skip" if r.get("skipped") else "FAIL")
        tot[k] += 1
        if k != "pass":
            print(k, e["method"], e["full_path"], "|", t["name"], "|", r.get("status"), r.get("error"),
                  (r.get("contract") or {}).get("errors"), str(r.get("body"))[:120])
print(dict(tot))
