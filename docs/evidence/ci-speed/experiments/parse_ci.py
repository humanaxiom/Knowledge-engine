"""Parse a GitHub Actions log of `verify.sh full` into stage and per-test times."""
import re
import sys
from collections import defaultdict
from datetime import datetime

TS = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)Z ?(.*)$")
START = re.compile(r"^(test_\w+) \((tests\.[\w.]+)\)")
END = re.compile(r"\.\.\. ?(ok|skipped.*|FAIL|ERROR|expected failure)\s*$|^(ok|FAIL|ERROR)\s*$")


def ts(s):
    s = s[:26]
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f")


def main(path, top=40):
    lines = []
    for raw in open(path, encoding="utf-8", errors="replace"):
        parts = raw.rstrip("\n").split("\t", 2)
        if len(parts) < 3:
            continue
        m = TS.search(parts[2])
        if not m:
            continue
        lines.append((parts[1], ts(m.group(1)), m.group(2)))
    marks = {}

    def first(key, pred, after=None):
        for step, t, txt in lines:
            if after and t < after:
                continue
            if pred(step, txt):
                marks.setdefault(key, t)
                return t
        return None

    def last(key, pred):
        r = None
        for step, t, txt in lines:
            if pred(step, txt):
                r = t
        marks[key] = r
        return r

    job0 = lines[0][1]
    jobend = lines[-1][1]
    v0 = first("verify start", lambda s, x: "Run ./scripts/verify.sh full" in x)
    built = last("build end", lambda s, x: re.search(r"^\s*\S+\s+Built\s*$", x) is not None and "ke-offline" not in x)
    up = first("launch end (stack is up)", lambda s, x: x.startswith("stack is up:"))
    g0 = first("gates-it start", lambda s, x: re.match(r"== verify full: [0-9a-f]+", x) is not None)
    lint = first("lint PASS", lambda s, x: x.strip() == "lint: PASS")
    ran = [(t, x) for s, t, x in lines if x.startswith("Ran ")]
    mypy = first("mypy done", lambda s, x: x.startswith("Success: no issues"))
    gpass = first("gates-it PASS", lambda s, x: x.strip() == "== verify full: PASS ==")
    spass = first("host smoke PASS", lambda s, x: x.strip() == "smoke: PASS", after=gpass)
    off0 = first("offline start", lambda s, x: x.startswith("offline: df start"))
    bund = first("bundle written", lambda s, x: x.startswith("bundle written"))
    dind = first("dind up", lambda s, x: x.startswith("offline: df after dind up"))
    inst = first("client install start", lambda s, x: x.startswith("offline-client: install"))
    instd = first("client install done", lambda s, x: x.startswith("installed to"))
    cup = first("client stack up", lambda s, x: x.startswith("stack is up:"), after=instd)
    csm = first("client smoke PASS", lambda s, x: x.strip() == "smoke: PASS", after=instd)
    cdone = first("client run done", lambda s, x: x.startswith("offline: df after client run"))
    offp = first("offline PASS", lambda s, x: x.startswith("== offline_check: PASS"))
    vpass = first("verify PASS", lambda s, x: x.startswith("== verify full: PASS ("))
    # unit vs integration
    first_test = first("first test", lambda s, x: START.match(x) is not None, after=lint)
    first_it = first("first integration test", lambda s, x: x.startswith("test_") and "(tests.integration." in x)

    def d(a, b):
        return f"{(b - a).total_seconds():7.1f}" if a and b else "    n/a"

    print(f"== {path}")
    print(f"job total (set-up to cleanup)        {d(job0, jobend)} s")
    print(f"pre-verify (set-up, checkout)        {d(job0, v0)}")
    print(f"build.sh (images)                    {d(v0, built)}")
    print(f"launch.sh (pull stores, up --wait)   {d(built, up)}")
    print(f"gates-it start + lint                {d(up, lint)}")
    print(f"  (gates-it container start -> lint) {d(g0, lint)}")
    print(f"unit suite (lint PASS -> Ran #1)     {d(lint, ran[0][0]) if ran else 'n/a'}   [{ran[0][1] if ran else ''}]")
    if len(ran) > 1:
        print(f"integration suite                    {d(ran[0][0], ran[1][0])}   [{ran[1][1]}]")
        print(f"coverage combine/report + mypy       {d(ran[1][0], mypy)}")
    print(f"container OTLP smoke                 {d(mypy, gpass)}")
    print(f"host smoke                           {d(gpass, spass)}")
    print(f"teardown (verify project)            {d(spass, off0)}")
    print(f"offline_check total                  {d(off0, offp)}")
    print(f"  bundle.sh (save)                   {d(off0, bund)}")
    print(f"  dind pull + up                     {d(bund, dind)}")
    print(f"  client install (load)              {d(inst, instd)}")
    print(f"  client launch                      {d(instd, cup)}")
    print(f"  client smoke                       {d(cup, csm)}")
    print(f"  client teardown                    {d(csm, cdone)}")
    print(f"  dind teardown                      {d(cdone, offp)}")
    print(f"verify.sh total                      {d(v0, vpass)}")

    # per-test
    cur = None
    prev_end = None
    durs = []
    for s, t, x in lines:
        if lint and t < lint:
            continue
        m = START.match(x)
        if m:
            if cur is None and prev_end is None:
                prev_end = t
            cur = (m.group(2), m.group(1))
        if cur and END.search(x):
            durs.append((cur, (t - prev_end).total_seconds()))
            prev_end = t
            cur = None
        if x.startswith("Ran "):
            prev_end = None
            cur = None
    bymod = defaultdict(float)
    bycls = defaultdict(float)
    cnt = defaultdict(int)
    for (dotted, name), sec in durs:
        mod = ".".join(dotted.split(".")[:2]) if not dotted.startswith("tests.integration") else ".".join(dotted.split(".")[:3])
        bymod[mod] += sec
        cnt[mod] += 1
        bycls[".".join(dotted.split(".")[:-1])] += sec
    tot = sum(s for _, s in durs)
    print(f"\nper-test timings: {len(durs)} tests, {tot:.1f} s summed")
    print("by module:")
    for k, v in sorted(bymod.items(), key=lambda kv: -kv[1])[:20]:
        print(f"  {v:7.1f} s {100*v/tot:5.1f}%  n={cnt[k]:3d}  {k}")
    print("by class (top 20):")
    for k, v in sorted(bycls.items(), key=lambda kv: -kv[1])[:20]:
        print(f"  {v:7.1f} s  {k}")
    print(f"slowest {top} tests:")
    for (dotted, name), sec in sorted(durs, key=lambda r: -r[1])[:top]:
        print(f"  {sec:6.1f} s  {dotted.split('.',1)[1]}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 40)
