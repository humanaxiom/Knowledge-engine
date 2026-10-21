"""Greedy (LPT) shard plan for the experiment. Prints one shard per line."""
import json, sys, unittest
jobs, unit, mods = int(sys.argv[1]), sys.argv[2], sys.argv[3:]
w = json.load(open("/scratch/weights.json"))
items = []
if unit == "size":
    import os
    for m in mods:
        items.append((os.path.getsize(m.replace(".", "/") + ".py"), m))
elif unit == "module":
    for m in mods:
        items.append((sum(v for k, v in w.items() if k.startswith(m + ".")) or 0.5, m))
else:
    seen = set()
    for m in mods:
        for suite in unittest.defaultTestLoader.loadTestsFromName(m):
            for t in suite:
                cls = f"{type(t).__module__}.{type(t).__qualname__}"
                if cls not in seen:
                    seen.add(cls); items.append((w.get(cls, 0.5), cls))
items.sort(key=lambda x: -x[0])
shards = [[0.0, []] for _ in range(jobs)]
for wt, name in items:
    s = min(shards, key=lambda x: x[0]); s[0] += wt; s[1].append(name)
for wt, names in shards:
    print(" ".join(names))
for wt, names in shards:
    print(f"est {wt:.0f}s", file=sys.stderr)
