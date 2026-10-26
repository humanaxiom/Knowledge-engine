"""security U5 probes (platform-sbom). Pure Python; loads modules by path.
Run in the gates image: python -I /scratch/probes.py"""
import importlib.util, json, re, sys, time, io, contextlib, argparse

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m

sc = load("sc_new", "/work/scripts/sbom_check.py")
old = load("sc_old", "/scratch/head_sbom_check.py")
hs = load("hs_new", "/work/tests/hardcoded_scan.py")
H = "LicenseRef-" + "0123456789abcdef" * 4
HU = "LicenseRef-" + "0123456789ABCDEF" * 4
CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]")

def P(*a): print(*a)
def row(label, pkg):
    r = sc.classify_package(pkg)
    P(f"  {label:58s} needs={r['needs']!s:5} unparsed={r['unparsed']!s:5} unident={r['unidentified']!s:5} "
      f"unlic={r['unlicensed']!s:5} expr={r['expression']!r}"[:260])
    return r
P("== A. L-4: classifier fail-open hunt (classify_package) ==")
A = [
 ("A1 declared <hash>, concluded MIT", {"licenseDeclared": H, "licenseConcluded": "MIT"}),
 ("A2 declared MIT, concluded <hash>", {"licenseDeclared": "MIT", "licenseConcluded": H}),
 ("A3 declared NOASSERTION, concluded <hash>", {"licenseDeclared": "NOASSERTION", "licenseConcluded": H}),
 ("A4 <hash> OR NOASSERTION", {"licenseDeclared": f"{H} OR NOASSERTION"}),
 ("A5 MIT AND NOASSERTION", {"licenseDeclared": "MIT AND NOASSERTION"}),
 ("A6 (NOASSERTION)", {"licenseDeclared": "(NOASSERTION)"}),
 ("A7 MIT OR NONE", {"licenseDeclared": "MIT OR NONE"}),
 ("A8 <hash> WITH Classpath-exception-2.0", {"licenseDeclared": f"{H} WITH Classpath-exception-2.0"}),
 ("A9 MIT OR (<hash> WITH x)", {"licenseDeclared": f"MIT OR ({H} WITH x)"}),
 ("A10 MIT AND (<hash> WITH x)", {"licenseDeclared": f"MIT AND ({H} WITH x)"}),
 ("A11 URL-folded gnu lgpl", {"licenseDeclared": "LicenseRef-https---www.gnu.org-licenses-lgpl-2.1.html"}),
 ("A12 URL-folded gnu copyleft/lesser (no gpl token)", {"licenseDeclared": "LicenseRef-https---www.gnu.org-copyleft-lesser.html"}),
 ("A13 spelled out GNU-General-Public-License-v2", {"licenseDeclared": "LicenseRef-GNU-General-Public-License-v2"}),
 ("A14 spelled out, junk text", {"licenseDeclared": "GNU General Public License v2"}),
 ("A15 mixed case gPl-2.0-OnLy", {"licenseDeclared": "gPl-2.0-OnLy"}),
 ("A16 MIT oR GPL-2.0-only aNd Apache-2.0", {"licenseDeclared": "MIT oR GPL-2.0-only aNd Apache-2.0"}),
 ("A17 lower-case noassertion leaf", {"licenseDeclared": "noassertion"}),
 ("A18 NoAssertion AND MIT", {"licenseDeclared": "NoAssertion AND MIT"}),
 ("A19 upper-hex hash (I-4)", {"licenseDeclared": HU}),
 ("A20 63-hex hash", {"licenseDeclared": H[:-1]}),
 ("A21 Cyrillic ER in GPL", {"licenseDeclared": "G\u0420L-3.0-only"}),
 ("A22 fullwidth GPL", {"licenseDeclared": "\uff27\uff30\uff2c-3.0"}),
 ("A23 zero-width joiner in GPL", {"licenseDeclared": "G\u200dPL-2.0"}),
 ("A24 dotless-i as WITH: MIT w-dotless-ith GPL-3.0", {"licenseDeclared": "MIT w\u0131th GPL-3.0-only"}),
 ("A25 MIT WITH GPL-3.0-only (exception slot)", {"licenseDeclared": "MIT WITH GPL-3.0-only"}),
 ("A26 GPL-2.0-only WITH x", {"licenseDeclared": "GPL-2.0-only WITH Classpath-exception-2.0"}),
 ("A27 parentheses: ((MIT)) OR (GPL-2.0)", {"licenseDeclared": "((MIT)) OR (GPL-2.0)"}),
 ("A28 parentheses: MIT) OR (GPL-2.0", {"licenseDeclared": "MIT) OR (GPL-2.0"}),
 ("A29 parentheses: ()", {"licenseDeclared": "()"}),
 ("A30 junk MIT AND AND NOASSERTION", {"licenseDeclared": "MIT AND AND NOASSERTION"}),
 ("A31 junk MIT AND AND <hash>", {"licenseDeclared": f"MIT AND AND {H}"}),
 ("A32 junk Public Domain OR <hash>", {"licenseDeclared": f"Public Domain OR {H}"}),
 ("A33 junk: the LGPL, version 2.1", {"licenseDeclared": "the LGPL, version 2.1"}),
 ("A34 MIT,GPL-2.0 (comma leaf)", {"licenseDeclared": "MIT,GPL-2.0"}),
 ("A35 MIT/LGPLv2.1+", {"licenseDeclared": "MIT/LGPLv2.1+"}),
 ("A36 declared list [GPL-2.0], concluded MIT", {"licenseDeclared": ["GPL-2.0"], "licenseConcluded": "MIT"}),
 ("A37 declared dict, concluded MIT", {"licenseDeclared": {"x": "GPL"}, "licenseConcluded": "MIT"}),
 ("A38 declared 123, concluded MIT", {"licenseDeclared": 123, "licenseConcluded": "MIT"}),
 ("A39 declared padded NOASSERTION", {"licenseDeclared": " NOASSERTION "}),
 ("A40 declared blank spaces", {"licenseDeclared": "   "}),
 ("A41 files [GPL-2.0-only] only", {"licenseInfoFromFiles": ["GPL-2.0-only"]}),
 ("A42 files [MIT, <hash>]", {"licenseInfoFromFiles": ["MIT", H]}),
 ("A43 files [MIT, NOASSERTION, 5, None]", {"licenseInfoFromFiles": ["MIT", "NOASSERTION", 5, None]}),
 ("A44 files str GPL-2.0 (not a list)", {"licenseInfoFromFiles": "GPL-2.0"}),
 ("A45 declared MIT, files [GPL-2.0-only] (files ignored)", {"licenseDeclared": "MIT", "licenseInfoFromFiles": ["GPL-2.0-only"]}),
 ("A46 declared empty/concluded NONE/files []", {"licenseDeclared": "", "licenseConcluded": "NONE", "licenseInfoFromFiles": []}),
 ("A47 NEL-separated MIT NEL GPL-2.0", {"licenseDeclared": "MIT\x85GPL-2.0"}),
 ("A48 NUL-separated MIT NUL OR NUL GPL", {"licenseDeclared": "MIT\x00OR\x00GPL-2.0"}),
 ("A49 LicenseRef-GNU-Affero-General-Public-License", {"licenseDeclared": "LicenseRef-GNU-Affero-General-Public-License"}),
 ("A50 GPLv2orlater (no separator)", {"licenseDeclared": "GPLv2orlater"}),
 ("A51 DocumentRef-x:LicenseRef-GPL-2.0", {"licenseDeclared": "DocumentRef-x:LicenseRef-GPL-2.0"}),
 ("A52 declared GPL-2.0 OR MIT, concluded MIT", {"licenseDeclared": "GPL-2.0 OR MIT", "licenseConcluded": "MIT"}),
 ("A53 blank blank NOASSERTION tab", {"licenseDeclared": "NOASSERTION\t"}),
]
for label, pkg in A:
    pkg = dict(pkg); pkg.setdefault("SPDXID", "SPDXRef-x"); pkg.setdefault("name", "x")
    row(label, pkg)

P("\n== A-b. Non-ASCII characters whose upper() is ASCII letters (operator look-alikes) ==")
hits = [c for c in range(0x80, 0x110000) if not (0xd800 <= c < 0xe000) and chr(c).upper().isascii() and chr(c).upper().isalpha()]
P("  chars:", [hex(c) for c in hits], [chr(c).upper() for c in hits])
P("  'w\u0131th'.upper() == 'WITH':", "w\u0131th".upper() == "WITH")
low = [c for c in range(0x80, 0x110000) if not (0xd800 <= c < 0xe000) and any(ch in "abcdefghijklmnopqrstuvwxyz0123456789" for ch in chr(c).lower())]
P("  non-ASCII whose lower() holds ASCII a-z0-9:", [hex(c) for c in low])
P("\n== A-c. Robustness: nesting, width, length (never raises; timing) ==")
def timed(label, expr):
    t = time.perf_counter()
    try:
        n, info = sc.needs_source(expr); out = f"needs={n} {info}"
    except BaseException as e:
        out = f"RAISED {type(e).__name__}"
    P(f"  {label:44s} {time.perf_counter()-t:7.3f}s {out}")
for d in (100, 199, 200, 1000, 3000, 100000):
    timed(f"depth {d} GPL-2.0", "(" * d + "GPL-2.0" + ")" * d)
    timed(f"depth {d} MIT", "(" * d + "MIT" + ")" * d)
timed("depth 3000 NOASSERTION", "(" * 3000 + "NOASSERTION" + ")" * 3000)
timed("depth 3000 <hash>", "(" * 3000 + H + ")" * 3000)
timed("depth 3000 MIT OR (... GPL)", "MIT OR " + "(" * 3000 + "GPL-2.0" + ")" * 3000)
timed("depth 3000 unbalanced open", "(" * 3000 + "MIT")
timed("width 200k MIT AND", "MIT AND " * 200000 + "MIT")
timed("width 200k MIT OR + GPL", "MIT OR " * 200000 + "GPL-2.0")
timed("WITH chain 100k", "MIT WITH " * 100000 + "x")
timed("1MB single leaf a-", "a-" * 500000)
timed("1MB gpl-with-a-a-", "gpl-with-" + "a-" * 500000 + "x")
timed("1MB LicenseRef-aaaa (hash search)", "LicenseRef-" + "a" * 1000000)
timed("1MB repeated LicenseRef-", "LicenseRef-" * 90000)
timed("non-str None", None); timed("non-str list", ["GPL"]); timed("non-str bytes", b"GPL")
for rx_name in ("GPL_ID_RE", "GPL_TOKEN_RE", "HASH_ID_RE", "CONTROL_RE"):
    rx = getattr(sc, rx_name)
    for s in ("gpl-" + "1." * 200000 + "x", "gpl-with-" + "a-" * 300000 + "exceptio", "l" + "gpl" * 300000, "LicenseRef-" * 100000, "gpl-v" + "9" * 300000 + "-with-" + "-" * 300000):
        t = time.perf_counter(); rx.fullmatch(s); rx.search(s); dt = time.perf_counter() - t
        P(f"  {rx_name:12s} on {len(s):7d}-char adversarial input: {dt:.3f}s")
for rx_name in ("SPDXID_RE", "NAMESPACE_RE", "RFC3339_UTC", "NAME_RE", "SHA_RE"):
    rx = getattr(sc, rx_name); s = "SPDXRef-" + "a" * 1000000 + "\x1b"
    t = time.perf_counter(); rx.fullmatch(s); P(f"  {rx_name:12s} 1MB: {time.perf_counter()-t:.3f}s")
t = time.perf_counter(); sc.is_gpl_id("x" * 1000000); P(f"  is_gpl_id 1MB: {time.perf_counter()-t:.3f}s")

P("\n== A-d. Real U3 rows (all six images, real always): needs=False rows with GPL-ish words / odd keywords / non-ASCII ==")
sys.path.insert(0, "/work")
from tests import sbom_support as ss
SUS = re.compile(r"gnu|general|lesser|affero|copyleft|gpl|public.?licen", re.I)
ODDKW = re.compile(r"(?<![A-Za-z0-9-])(?!NONE(?![A-Za-z0-9-])|NOASSERTION(?![A-Za-z0-9-]))(?i:none|noassertion)(?![A-Za-z0-9-])")
always = json.load(open("/work/docker/source-policy.json"))["always"]
total = flagged = nosrc = 0
for image in ss.U3_IMAGES:
    name = "ke-neo4j" if image == "neo4j" else image
    doc = ss.spdx_doc(name, ss.u3_rows(image))
    for r in sc.classify_document(name, doc, always):
        total += 1
        e = r["expression"] or ""
        nosrc += not r["needs"]
        odd = bool(ODDKW.search(e)) or not e.isascii() or (bool(re.search(r"LicenseRef-[0-9a-fA-F]{64}", e)) and not sc.HASH_ID_RE.search(e))
        if not r["needs"] and (SUS.search(e) or odd):
            flagged += 1
            P(f"  {name}: needs=False unparsed={r['unparsed']} purl={r['purl']} expr={e!r}"[:300])
P(f"  rows classified: {total}; needs=False: {nosrc}; suspicious needs=False rows: {flagged}")
for image in ss.U3_IMAGES:
    name = "ke-neo4j" if image == "neo4j" else image
    rows = sc.classify_document(name, ss.spdx_doc(name, ss.u3_rows(image)), always)
    P(f"  {name:10s} rows={len(rows):4d} needs={sum(r['needs'] for r in rows):4d} unparsed={sum(bool(r['unparsed']) for r in rows):3d} "
      f"unidentified={sum(bool(r['unidentified']) for r in rows):3d} unlicensed={sum(r['unlicensed'] for r in rows):3d} always={sum(r['always'] for r in rows):3d}")

P("\n== F. unlicensed_report unchanged (HEAD vs working tree) ==")
import inspect
P("  function source identical:", inspect.getsource(old.unlicensed_report) == inspect.getsource(sc.unlicensed_report),
  "| _missing:", inspect.getsource(old._missing) == inspect.getsource(sc._missing),
  "| _hash_only:", inspect.getsource(old._hash_only) == inspect.getsource(sc._hash_only),
  "| report_lines:", inspect.getsource(old.report_lines) == inspect.getsource(sc.report_lines),
  "| _clean:", inspect.getsource(old._clean) == inspect.getsource(sc._clean),
  "| MISSING/HASH/CONTROL:", (old.MISSING, old.HASH_ID_RE.pattern, old.CONTROL_RE.pattern) == (sc.MISSING, sc.HASH_ID_RE.pattern, sc.CONTROL_RE.pattern))
same = 0
for image in ss.U3_IMAGES:
    doc = ss.spdx_doc(image, ss.u3_rows(image))
    a, b = old.unlicensed_report(doc), sc.unlicensed_report(doc)
    same += a == b
    P(f"  {image:10s} count HEAD={a['count']:3d} now={b['count']:3d} equal={a == b} lines-equal={old.report_lines(image, a) == sc.report_lines(image, b)}")
crafted = {"packages": [dict(p, SPDXID=f"SPDXRef-c{i}", name="c") for i, (l, p) in enumerate(A)], "relationships": []}
P("  crafted A-rows report equal:", old.unlicensed_report(crafted) == sc.unlicensed_report(crafted),
  "count", sc.unlicensed_report(crafted)["count"])
P("\n== B. L-5/R2: escaping (ESC, CSI, NEL, DEL, trailing newline) ==")
BAD = ["SPDXRef-a\n", "SPDXRef-a\x1b[31m", "SPDXRef-a\x9b2J", "SPDXRef-a\x85", "SPDXRef-a\x7f"]
def base_doc():
    return {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT", "name": "x",
            "documentNamespace": "urn:uuid:12345678-1234-4123-8123-123456789abc",
            "creationInfo": {"created": "2026-10-24T00:00:00Z", "creators": ["Tool: syft-1.54.1"]},
            "packages": [{"SPDXID": "SPDXRef-r", "name": "r", "downloadLocation": "NONE"}],
            "relationships": [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-r"}]}
P("  control doc problems:", sc.validate(base_doc()))
for bad in BAD:
    for field in ("spdxVersion", "dataLicense", "SPDXID", "documentNamespace", "created", "pkg-SPDXID", "rel-end"):
        d = base_doc()
        if field == "created": d["creationInfo"]["created"] = "2026-10-24T00:00:00Z" + bad[9:]
        elif field == "pkg-SPDXID": d["packages"].append({"SPDXID": bad, "downloadLocation": "NONE"})
        elif field == "rel-end": d["relationships"].append({"spdxElementId": bad, "relationshipType": "CONTAINS", "relatedSpdxElement": "SPDXRef-r"})
        elif field == "documentNamespace": d[field] = d[field] + bad[9:]
        else: d[field] = bad
        p = sc.validate(d)
        raw = [x for x in p if CTRL.search(x)]
        P(f"  validate {field:17s} {bad!r:24s} problems={len(p)} raw-control-lines={len(raw)}")
d = base_doc(); d["packages"] += [{"SPDXID": ["SPDXRef-\x1b"], "downloadLocation": "x"}]
P("  validate list-typed SPDXID, no name:", [x for x in sc.validate(d) if "package" in x])
def drift_doc(purls):
    return {"packages": [{"SPDXID": f"SPDXRef-{i}", "externalRefs": [{"referenceType": "purl", "referenceLocator": u}]}
                         for i, u in enumerate(purls)], "relationships": []}
for bad in ("%1b%5b31m", "%c2%9b2J", "%c2%85", "%7f", "%0a"):
    app = drift_doc(["pkg:deb/debian/libpq5@1", f"pkg:deb/debian/evil{bad}@1", f"pkg:generic/python@3.12.15{bad}",
                     f"pkg:generic/python@3.12.16{bad}", f"pkg:pypi/pip@1{bad}", f"pkg:pypi/psycopg-c@9{bad}",
                     f"pkg:pypi/psycopg-binary@1{bad}", f"pkg:deb/debian/libpq5@17.0{bad}?upstream=postgresql-17"])
    p = sc.drift_problems(app, drift_doc([]), frozenset({"libpq5", "x"}), {"/l.txt": "CPython 3.12.15: x"})
    p += sc.psycopg_problems(app, "17.0", {"3.2.0"})
    app1 = drift_doc([f"pkg:generic/python@3.12.15{bad}"])
    p += sc.drift_problems(app1, drift_doc([]), frozenset(), {"/l.txt": "CPython 3.12.15: x"})
    raw = [x for x in p if CTRL.search(x)]
    P(f"  drift+psycopg purl-encoded {bad:10s} problems={len(p)} raw-control-lines={len(raw)}")
    if bad == "%1b%5b31m":
        for x in p: P("     ", x[:160])
P("  drift CLI path (main) with a hostile SBOM: see section B2 in the shell part")
P("  finish argv (fullmatch):")
for nm, sha in (("ke-app\n", "a" * 40), ("ke-app", "a" * 40 + "\n"), ("ke-app\x1b[2J", "a" * 40), ("ke-app\x85", "a" * 40)):
    ns = argparse.Namespace(name=nm, git_sha=sha, arch="amd64", raw="/nonexistent", tar="/x", ref="r", site=None, lock=None)
    err = io.StringIO()
    with contextlib.redirect_stderr(err): rc = sc.finish(ns)
    P(f"    name={nm!r} sha-tail={sha[-2:]!r} rc={rc} raw-control-in-stderr={bool(CTRL.search(err.getvalue().rstrip(chr(10))))} {err.getvalue().strip()[:100]!r}")
src = open("/work/scripts/sbom_check.py").read()
P("  $-anchored regexes used with .match/.search:", {rx: (src.count(rx + ".match("), src.count(rx + ".search(")) for rx in ("SPDXID_RE", "NAMESPACE_RE", "RFC3339_UTC", "NAME_RE", "SHA_RE")})
P("  every compiled pattern with a $ anchor:", [n for n, v in vars(sc).items() if isinstance(v, re.Pattern) and v.pattern.endswith("$")])

P("\n== C. PS-1.2 scanner continuation rule (find_hardcoded) ==")
real = open("/work/docker/neo4j.Dockerfile", encoding="utf-8").read()
from tests.test_engine_hardcoded import EXEMPTIONS as EXM
P("  exemption entries for docker/neo4j.Dockerfile:", [e for e in EXM if "neo4j.Dockerfile" in str(e)])
def scan(files, sym="7687"):
    return [(f.path, f.line, f.value) for f in hs.find_hardcoded(files, [sym], EXM)]
P("  real docker/neo4j.Dockerfile findings for 7687:", scan({"docker/neo4j.Dockerfile": real}))
L = "EXPOSE 7473 7474 7687"
BS = chr(92); NL = chr(10)
cases = {
 "first line": L,
 "after RUN x BS": "RUN x " + BS + NL + L,
 "after RUN x BS + blanks": "RUN x " + BS + " " + chr(9) + " " + NL + L,
 "after CRLF RUN x BS": "RUN x " + BS + chr(13) + NL + L,
 "comment line between (Docker strips it; still continued)": "RUN x " + BS + NL + "# c" + NL + L,
 "empty line between (BuildKit keeps continuing)": "RUN x " + BS + NL + NL + L,
 "after a comment ending in BS (Docker: not continued)": "# note " + BS + NL + L,
 "heredoc body": "RUN <<EOF" + NL + L + NL + "EOF",
 "same path, other file name docker/neo4j.dockerfile": None,
 "other Dockerfile docker/gateway.Dockerfile": None,
 "EXPOSE 7473 7474 7687 8080": "EXPOSE 7473 7474 7687 8080",
 "lead/trail spaces": "   " + L + "  ",
 "escape directive backtick then RUN x backtick": "# escape=`" + NL + "RUN x `" + NL + L,
 "after a line with BS inside, not at end": "RUN echo a" + BS + "b" + NL + L,
}
for k, v in cases.items():
    if v is None:
        path = "docker/neo4j.dockerfile" if "dockerfile" in k.split()[-1] else "docker/gateway.Dockerfile"
        P(f"  {k:58s} -> {scan({path: L})}")
    else:
        P(f"  {k:58s} -> {scan({'docker/neo4j.Dockerfile': v})}")
P("  Python exemption after a backslash line:", scan({"harness_telemetry/tracing.py": "X = 1 " + BS + NL + "  + 2" + NL + "DEFAULT_COLLECTOR = " + chr(34) + "http://localhost:47101" + chr(34) + NL}, "47101"))
P("\n== B2. CLI paths end to end (subprocess, python -I): drift and finish with hostile SBOMs ==")
import subprocess, tarfile, os, tempfile
W = tempfile.mkdtemp()
def j(name, obj):
    path = os.path.join(W, name); open(path, "w").write(json.dumps(obj)); return path
ESC, CSI, NEL, DEL = chr(27), chr(0x9b), chr(0x85), chr(0x7f)
def purl_doc(purls):
    return {"packages": [{"SPDXID": f"SPDXRef-{i}", "externalRefs": [{"referenceType": "purl", "referenceLocator": u}]}
                         for i, u in enumerate(purls)], "relationships": []}
hostile = purl_doc(["pkg:deb/debian/libpq5@1", "pkg:deb/debian/evil%1b%5b2J@1", "pkg:generic/python@3.12.15%c2%9b31m",
                    "pkg:pypi/pip@1%c2%85x", "pkg:pypi/psycopg-binary@1%7f", "pkg:pypi/psycopg-c@0%0aFAKE-LINE"])
added = os.path.join(W, "added.py"); open(added, "w").write('ADDED_PACKAGES = frozenset({"libpq5"})' + chr(10))
lic = os.path.join(W, "l.txt"); open(lic, "w").write("CPython 3.12.15: x" + chr(10))
def run(args):
    r = subprocess.run([sys.executable, "-I", "/work/scripts/sbom_check.py"] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="surrogateescape")
    lines = r.stderr.split(chr(10))
    raw = [l for l in lines if CTRL.search(l)]
    return r.returncode, len([l for l in lines if l]), raw, r.stderr
rc, n, raw, err = run(["drift", "--sbom", j("app.json", hostile), "--base", j("base.json", purl_doc([])), "--added-from", added,
                       "--libpq", "17.0", "--lock", "/work/uv.lock", "--licence", lic])
P(f"  drift: rc={rc} stderr-lines={n} raw-control-lines={len(raw)} injected-line-present={'FAKE-LINE' in err and any(l.startswith('FAKE-LINE') for l in err.split(chr(10)))}")
for l in err.strip().split(chr(10)): P("    ", l[:170])
# finish: a syft-shaped doc whose report rows and validate failures carry controls
tarp = os.path.join(W, "img.tar")
with tarfile.open(tarp, "w") as t:
    data = json.dumps([{"Config": "blobs/sha256/" + "a" * 64}]).encode()
    ti = tarfile.TarInfo("manifest.json"); ti.size = len(data)
    import io as _io; t.addfile(ti, _io.BytesIO(data))
def fdoc(extra_pkgs):
    return {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT", "name": "x",
            "documentNamespace": "urn:uuid:x", "creationInfo": {"created": "2026-10-24T00:00:00Z", "creators": ["Tool: syft-1.54.1"]},
            "packages": [{"SPDXID": "SPDXRef-r", "name": "r", "downloadLocation": "NONE"}] + extra_pkgs,
            "relationships": [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-r"}]}
bad = fdoc([{"SPDXID": "SPDXRef-a" + ESC + "[2J", "name": "n" + CSI, "downloadLocation": ""},
            {"SPDXID": "SPDXRef-b" + chr(10), "downloadLocation": "x"}])
bad["spdxVersion"] = "SPDX-2.3" + NEL
rc, n, raw, err = run(["finish", "--name", "ke-app", "--ref", "ke-app:x", "--arch", "amd64", "--git-sha", "a" * 40,
                       "--raw", j("bad.json", bad), "--tar", tarp])
P(f"  finish (validate fails): rc={rc} stderr-lines={n} raw-control-lines={len(raw)}")
for l in err.strip().split(chr(10)): P("    ", l[:170])
good = fdoc([{"SPDXID": "SPDXRef-c", "name": "n" + ESC + "]0;title" + chr(7), "downloadLocation": "x"},
             {"SPDXID": "SPDXRef-d", "name": "d", "downloadLocation": "x",
              "externalRefs": [{"referenceType": "purl", "referenceLocator": "pkg:deb/x" + NEL + DEL + CSI + "@1"}]}])
rc, n, raw, err = run(["finish", "--name", "ke-app", "--ref", "ke-app:x", "--arch", "amd64", "--git-sha", "a" * 40,
                       "--raw", j("good.json", good), "--tar", tarp])
P(f"  finish (ok, report lines): rc={rc} stderr-lines={n} raw-control-lines={len(raw)}")
for l in err.strip().split(chr(10)): P("    ", l[:170])
