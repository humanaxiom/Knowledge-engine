import sys, json
sys.path.insert(0, r"c:\repos\Knowledge-engine")
import tests.test_sources_resolve as t
import tests.test_sources_lock as tl
check = tl.load_sbom_check()
E256 = check.EMPTY_SHA256
ax = t.ApkFixture(); docs = t.docs_for(t.RL_DOCS)
def run(label, mutate):
    e = ax.entry(); mutate(e)
    probs = [p for p in check.lock_problems(check.lock_text({"format": 1, "components": {t.RL_KEY: e}}), t.policy(), docs, "amd64") if p.startswith("lock: apk:")]
    print(f"  {label}: {'PASSES' if not probs else 'refused: ' + ascii(probs[0])[:140]}")
def empty(name):
    def m(e):
        for f in e["files"]:
            if f["name"] == name:
                f["size"] = 0; f["sha256"] = E256; f["upstream"]["value"] = E256
    return m
print("## item 12 size 0 at the GitLab API raw form")
run("an empty .post-install (ruled good)", empty("readline.post-install"))
run("an empty APKBUILD (resolver can never produce it)", empty("APKBUILD"))
