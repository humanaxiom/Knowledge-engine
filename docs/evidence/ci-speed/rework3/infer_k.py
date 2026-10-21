"""Infer the pool's k on CI: replay test.sh's schedule (largest file first, at most k at
once) with each module's CI wall seconds from its `unit:` line, for k = 1..4, and compare
with the measured pool wall (lint PASS -> first output line after the pool).
Usage: python infer_k.py <sizes.txt: "<bytes> tests/<m>.py" lines> <ci.log> <measured wall s>"""
import heapq
import re
import sys

sizes = {}
for line in open(sys.argv[1]):
    b, f = line.split()
    sizes[f[:-3].replace("/", ".")] = int(b)
secs = {m: int(s) for s, m in re.findall(r"unit: (\d+)s rc=\d+ (\S+)", open(sys.argv[2], encoding="utf-8").read())}
order = sorted(secs, key=lambda m: (-sizes[m], m))
for k in (1, 2, 3, 4):
    slots = [0.0] * k
    for m in order:
        t = heapq.heappop(slots)
        heapq.heappush(slots, t + secs[m])
    print(f"k={k}: replayed pool wall {max(slots):6.0f} s (module sum {sum(secs.values())} s); measured {sys.argv[3]} s")
