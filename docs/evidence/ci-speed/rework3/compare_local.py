"""Per-test seconds from --durations blocks in two plain-text runs: ratio pooled/one-process.
Usage: python compare_local.py <pooled.txt> <one-process.txt>"""
import re
import sys

DUR = re.compile(r"^\s*([0-9.]+)s\s+(test_\w+) \((tests\.[\w.]+)\)")


def durs(path):
    out = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        m = DUR.match(line)
        if m:
            out[m.group(3)] = max(out.get(m.group(3), 0.0), float(m.group(1)))
    return out


pool, one = durs(sys.argv[1]), durs(sys.argv[2])
both = sorted(set(pool) & set(one), key=lambda k: -pool[k])
print(f"{'pool':>7} {'onep':>7} {'ratio':>6}  test (tests in both --durations lists)")
for k in both:
    print(f"{pool[k]:7.1f} {one[k]:7.1f} {pool[k] / one[k]:6.2f}  {k.split('.', 1)[1]}")
sp, so = sum(pool[k] for k in both), sum(one[k] for k in both)
print(f"{sp:7.1f} {so:7.1f} {sp / so:6.2f}  SUM over {len(both)} tests")
