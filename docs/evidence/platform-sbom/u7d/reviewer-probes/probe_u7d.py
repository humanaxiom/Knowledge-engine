import sys, copy
sys.path.insert(0, r"c:\repos\Knowledge-engine")
import tests.test_sources_lock as tl
check = tl.load_sbom_check()
K = "pgdg:postgresql-common@293.pgdg12+1"
docs = tl.fixture_docs()
def run(label, suite):
    lock = tl.good_lock(tl.FIXTURE_KEYS)
    e = lock["components"][K]
    e["suite"] = suite
    for f in e["files"]:
        if f["name"].endswith(".dsc"):
            f["upstream"]["from"] = f"apt-archive.postgresql.org {suite} Sources"
    probs = [p for p in check.lock_problems(check.lock_text(lock), tl.policy(), docs, "amd64") if p.startswith("lock: pgdg:")]
    print(f"  {label}: {'PASSES' if not probs else 'refused: ' + ascii(probs[0])[:140]}")
print("## pgdg suite on a postgres (debian-12, bookworm) package")
run("bookworm-pgdg-archive (expected)", "bookworm-pgdg-archive")
run("trixie-pgdg-archive (wrong codename for debian-12)", "trixie-pgdg-archive")
run("evil-pgdg-archive (no such codename)", "evil-pgdg-archive")
