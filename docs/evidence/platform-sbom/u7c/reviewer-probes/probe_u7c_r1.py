import sys, copy
from urllib.parse import quote
sys.path.insert(0, r"c:\repos\Knowledge-engine")
import tests.test_sources_resolve as t
import tests.test_sources_lock as tl
mod = t.load_resolver(); check = tl.load_sbom_check()
ax = t.ApkFixture(); docs = t.docs_for(t.RL_DOCS)
API = "https://gitlab.alpinelinux.org/api/v4/projects/alpine%2Faports/repository/files/"
def run(label, mutate):
    e = ax.entry(); mutate(e)
    probs = [p for p in check.lock_problems(check.lock_text({"format": 1, "components": {t.RL_KEY: e}}), t.policy(), docs, "amd64") if p.startswith("lock: apk:")]
    print(f"  {label}: {'PASSES' if not probs else 'refused: ' + ascii(probs[0])[:150]}")
def set_url(name, url):
    def m(e):
        for f in e["files"]:
            if f["name"] == name: f["url"] = url
    return m
c = ax.commit
print("## baseline"); run("fixture entry", lambda e: None)
print("## item 9 lock rule: candidate shapes")
for label, dec in (("middle segment `~@:` (decoded main/readline/~@:/fix-build.patch)", "main/readline/~@:/fix-build.patch"),
                   ("middle segment `..;`", "main/readline/..;/fix-build.patch"),
                   ("middle segment `a?b` (decoded ?)", "main/readline/a?b/fix-build.patch"),
                   ("middle segment `x&ref=0`", "main/readline/x&ref=0/fix-build.patch"),
                   ("middle segment `-` (leading dash)", "main/readline/-/fix-build.patch"),
                   ("APKBUILD in a subdirectory", None)):
    if dec is None:
        run(label, set_url("APKBUILD", API + quote("main/readline/sub/APKBUILD", safe="") + "/raw?ref=" + c))
    else:
        run(label, set_url("fix-build.patch", API + quote(dec, safe="") + "/raw?ref=" + c))
run("old /-/raw/ form", set_url("APKBUILD", f"https://gitlab.alpinelinux.org/alpine/aports/-/raw/{c}/main/readline/APKBUILD"))
run("ref of another commit", set_url("APKBUILD", API + quote("main/readline/APKBUILD", safe="") + "/raw?ref=" + "0"*40))
run("literal backslash in P", set_url("fix-build.patch", API + "main%2Freadline%2F" + chr(92) + "fix-build.patch/raw?ref=" + c))
run("deb file in the API form", lambda e: None)
print("## parse_dsc: junk line inside Checksums-Sha256 drops the lines after it")
fx = t.DebFixture(t.BASH_KEY)
plain = fx.text(armour=False)
lines = plain.split("\n")
i = next(k for k, l in enumerate(lines) if l.startswith("Checksums-Sha256:"))
mod_lines = lines[:i+2] + ["junk-without-colon"] + lines[i+2:]
f = mod.parse_dsc("\n".join(mod_lines))
print("  Checksums-Sha256 lines kept:", len(f["Checksums-Sha256"].splitlines()), "of", len(lines[i+1:i+1+len(fx.files)]))
