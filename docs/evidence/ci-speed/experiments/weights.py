import json, re, sys
from collections import defaultdict
from datetime import datetime
START = re.compile(r"^(test_\w+) \((tests\.[\w.]+)\)")
END = re.compile(r"\.\.\. ?(ok|skipped.*|FAIL|ERROR|expected failure)\s*$|^(ok|FAIL|ERROR)\s*$")
w = defaultdict(float); cur = None; prev = None
for raw in open(sys.argv[1], encoding="utf-8", errors="replace"):
    p = raw.rstrip("\n").split("\t", 2)
    if len(p) < 3: continue
    m = re.search(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6})\d*Z ?(.*)$", p[2])
    if not m: continue
    t = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S.%f"); x = m.group(2)
    if x.startswith("lint: PASS"): prev = t
    s = START.match(x)
    if s and prev is not None: cur = s.group(2)
    if cur and END.search(x):
        w[".".join(cur.split(".")[:-1])] += (t - prev).total_seconds(); prev = t; cur = None
    if x.startswith("Ran "): break
json.dump(w, open(sys.argv[2], "w"), indent=0, sort_keys=True)
print(len(w), round(sum(w.values()),1))
