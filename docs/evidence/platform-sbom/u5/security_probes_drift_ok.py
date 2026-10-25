import json, os, re, subprocess, sys, tempfile, tomllib
CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
W = tempfile.mkdtemp()
locked = sorted({p["version"] for p in tomllib.load(open("/work/uv.lock", "rb"))["package"] if p["name"] == "psycopg-c"})
def doc(purls):
    return {"packages": [{"SPDXID": f"SPDXRef-{i}", "externalRefs": [{"referenceType": "purl", "referenceLocator": u}]}
                         for i, u in enumerate(purls)], "relationships": []}
def w(n, o):
    p = os.path.join(W, n); open(p, "w").write(json.dumps(o)); return p
app = doc(["pkg:deb/debian/libpq5@17.0?upstream=postgresql-17", "pkg:generic/python@3.12.15",
           "pkg:generic/x/python@3.12.15%1b%5d0%3bOWNED%07%1b%5b2J", f"pkg:pypi/psycopg-c@{locked[0]}"])
added = os.path.join(W, "a.py"); open(added, "w").write('ADDED_PACKAGES = frozenset({"libpq5"})' + chr(10))
lic = os.path.join(W, "l.txt"); open(lic, "w").write("CPython 3.12.15: x" + chr(10))
r = subprocess.run([sys.executable, "-I", "/work/scripts/sbom_check.py", "drift", "--sbom", w("app.json", app),
                    "--base", w("base.json", doc([])), "--added-from", added, "--libpq", "17.0", "--lock", "/work/uv.lock",
                    "--licence", lic], capture_output=True, text=True)
print("drift success path: rc", r.returncode, "| raw control chars in stderr:",
      [hex(ord(c)) for c in CTRL.findall((r.stdout + r.stderr).rstrip(chr(10)))])
print("stdout (repr):", repr(r.stdout)); print("stderr (repr):", repr(r.stderr))
