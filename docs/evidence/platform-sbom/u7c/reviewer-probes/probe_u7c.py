import sys, copy, json, hashlib
sys.path.insert(0, r"c:\repos\Knowledge-engine")
import tests.test_sources_resolve as t
import tests.test_sources_lock as tl
mod = t.load_resolver(); check = tl.load_sbom_check()
fx = t.DebFixture(t.BASH_KEY)
print("## parse_dsc robustness")
txt = fx.text()
crlf = txt.replace("\n", "\r\n")
f = mod.parse_dsc(crlf)
print("  CRLF armoured: Source/Version", f.get("Source"), f.get("Version"), "| Files lines", len(f.get("Files", "").splitlines()))
plain = fx.text(armour=False)
dup = plain.replace("Checksums-Sha256:", "Checksums-Sha256: \n " + "0"*64 + " 1 evil.tar.xz\nChecksums-Sha256:", 1)
f2 = mod.parse_dsc(dup)
print("  duplicate Checksums-Sha256 field: parsed without error; kept value lines:", len(f2["Checksums-Sha256"].splitlines()), "| contains evil:", "evil" in f2["Checksums-Sha256"])
dupv = plain.replace("Version: 5.2.15-2", "Version: 9.9-9\nVersion: 5.2.15-2", 1)
print("  duplicate Version (first 9.9-9, last 5.2.15-2): parse_dsc gives", mod.parse_dsc(dupv).get("Version"))
lower = plain.replace("Checksums-Sha256:", "checksums-sha256:", 1)
try:
    mod.dsc_files(mod.parse_dsc(lower), "bash_5.2.15-2.dsc", "bash", "5.2.15-2", {n: "a"*40 for n in fx.files} )
    print("  lower-case field name: accepted")
except Exception as e:
    print("  lower-case field name:", type(e).__name__, str(e)[:80])
lead = "\n" + txt
f3 = mod.parse_dsc(lead)
print("  armour after a leading blank line: Source", f3.get("Source"), "Version", f3.get("Version"))
print("## lock rule (i): the APKBUILD taken from a subdirectory")
ax = t.ApkFixture()
e = ax.entry()
for fl in e["files"]:
    if fl["name"] == "APKBUILD":
        fl["url"] = ax.raw("tests/APKBUILD")
lock = {"format": 1, "components": {t.RL_KEY: e}}
docs = t.docs_for(t.RL_DOCS)
probs = [p for p in check.lock_problems(check.lock_text(lock), t.policy(), docs, "amd64") if p.startswith("lock: apk:")]
print("  lock_problems on an apk entry whose APKBUILD url is <origin>/tests/APKBUILD:", probs or "PASSES")
print("## APKBUILD: pkgver reassigned later (first assignment is checked)")
ab = ax.apkbuild().replace("pkgver=8.2.13\n", "pkgver=8.2.13\npkgver=9.0\n", 1)
try:
    print("  parse_apkbuild:", len(mod.parse_apkbuild(ab, ax.commit, ax.ver)), "sums; accepted although the last pkgver= is 9.0")
except Exception as ex:
    print("  ", type(ex).__name__, ex)
print("## APKBUILD: a second sha512sums= block (first is used)")
ab2 = ax.apkbuild() + 'sha512sums="\n' + "b"*128 + "  extra.patch\n" + '"\n'
print("  parse_apkbuild names:", [n for n, _ in mod.parse_apkbuild(ab2, ax.commit, ax.ver)])
