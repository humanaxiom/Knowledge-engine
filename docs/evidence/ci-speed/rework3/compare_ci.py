"""Compare per-test seconds: serial CI run (streamed timestamps) vs pooled CI runs
(--durations 10 blocks), plus the local serial --durations 80 profile.
Usage: python compare_ci.py <serial.log> <local-durations.txt> <pooled.log>..."""
import re
import sys
from collections import defaultdict
from datetime import datetime

TS = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)Z ?(.*)$")
START = re.compile(r"^(test_\w+) \((tests\.[\w.]+)\)")
END = re.compile(r"\.\.\. ?(ok|skipped.*|FAIL|ERROR|expected failure)\s*$|^(ok|FAIL|ERROR)\s*$")
DUR = re.compile(r"^\s*([0-9.]+)s\s+(test_\w+) \((tests\.[\w.]+)\)")


def rows(path):
    for raw in open(path, encoding="utf-8", errors="replace"):
        parts = raw.rstrip("\n").split("\t", 2)
        if len(parts) < 3:
            continue
        m = TS.search(parts[2])
        if m:
            yield datetime.strptime(m.group(1)[:26], "%Y-%m-%dT%H:%M:%S.%f"), m.group(2)


def serial(path):
    out = defaultdict(float)
    cur = prev = None
    started = False
    for t, x in rows(path):
        if x.strip() == "lint: PASS":
            started = True
            continue
        if not started:
            continue
        m = START.match(x)
        if m:
            if cur is None and prev is None:
                prev = t
            cur = m.group(2)
        if cur and END.search(x):
            out[cur] += (t - prev).total_seconds()
            prev, cur = t, None
        if x.startswith("Ran "):
            break
    return out


def durations(path, tsv=True):
    out = {}
    src = (x for _, x in rows(path)) if tsv else open(path, encoding="utf-8", errors="replace")
    for x in src:
        m = DUR.match(x)
        if m:
            out[m.group(3)] = max(out.get(m.group(3), 0.0), float(m.group(1)))
    return out


ser = serial(sys.argv[1])
loc = durations(sys.argv[2], tsv=False)
pools = [durations(p) for p in sys.argv[3:]]
keys = sorted(set().union(*[p.keys() for p in pools]), key=lambda k: -max(p.get(k, 0) for p in pools))
print(f"{'pool1':>7} {'pool2':>7} {'serialCI':>8} {'local':>6} {'p/ser':>6} {'p/loc':>6}  test")
for k in keys:
    p = [pp.get(k) for pp in pools]
    vals = [v for v in p if v]
    if not vals:
        continue
    pm = sum(vals) / len(vals)
    s, l = ser.get(k), loc.get(k)
    f = lambda v: f"{v:7.1f}" if v else "    n/a"
    r1 = f"{pm/s:6.2f}" if s else "   n/a"
    r2 = f"{pm/l:6.2f}" if l else "   n/a"
    print(f"{f(p[0])} {f(p[1]) if len(p) > 1 else ''} {f(s):>8} {f(l)[1:]:>6} {r1} {r2}  {k.split('.',1)[1]}")
