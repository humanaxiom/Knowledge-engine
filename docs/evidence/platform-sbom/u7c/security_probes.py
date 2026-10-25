"""security U7c gate probes (platform-sbom). python -I, gates image; fake network plus one loopback server."""
import copy, datetime, hashlib, importlib.util, io, json, os, socket, sys, tarfile, tempfile, threading, time
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
R = load("srv7c", "/work/scripts/sources_resolve.py")
sys.path.insert(0, "/work")
import tests.test_sources_lock as tl
from tests.test_sbom_bundle import load_sbom_check
sc = load_sbom_check()
P = print
NL = chr(10)
def show(label, fn):
    try:
        out = fn()
        P(f"  {label:58s} -> {str(out)[:150]}")
    except R.ResolveError as e:
        P(f"  {label:58s} -> ResolveError: {str(e)[:110]}")
    except Exception as e:
        P(f"  {label:58s} -> RAISED {type(e).__name__}: {str(e)[:80]}")
H64 = "a" * 64; H32 = "b" * 32; H40 = "c" * 40
def dsc(extra_fields="", files=None, sig=True, trailer="", before="", sep=NL):
    files = files or [("x_1.orig.tar.gz", 100)]
    body = sep.join(["Format: 3.0 (quilt)", "Source: x", "Version: 1-1",
                     "Checksums-Sha256:"] + [f" {H64} {z} {n}" for n, z in files] + ["Files:"] + [f" {H32} {z} {n}" for n, z in files]) + extra_fields
    if sig:
        return before + "-----BEGIN PGP SIGNED MESSAGE-----" + NL + "Hash: SHA256" + NL + NL + body + NL + "-----BEGIN PGP SIGNATURE-----" + NL + "xx" + NL + "-----END PGP SIGNATURE-----" + NL + trailer
    return body
NAMES = {"x_1.orig.tar.gz": H40, "evil.tar.gz": "d" * 40, "x_1-1.dsc": "e" * 40}
def files_of(text):
    f = R.parse_dsc(text)
    return [(x["name"], x["size"], x["url"][-10:]) for x in R.dsc_files(f, "x_1-1.dsc", "x", "1-1", NAMES)]
P("== U7c-1. parse_dsc / dsc_files on crafted .dsc text ==")
show("baseline", lambda: files_of(dsc()))
show("NEL (U+0085) injects a Checksums line inside a value", lambda: R.parse_dsc(dsc(extra_fields=NL + "Description: a" + chr(0x85) + "Checksums-Sha256: x")).get("Checksums-Sha256", "")[:80])
show("U+2028 injects a field", lambda: sorted(R.parse_dsc(dsc(extra_fields=NL + "Homepage: a" + chr(0x2028) + "Source: evil"))))
show("U+2028 Source override -> Source value", lambda: R.parse_dsc(dsc(extra_fields=NL + "Homepage: a" + chr(0x2028) + "Source: evil")).get("Source"))
show("duplicate Checksums-Sha256 (last wins?)", lambda: files_of(dsc(extra_fields=NL + "Checksums-Sha256:" + NL + f" {H64} 5 evil.tar.gz" + NL + "Files:" + NL + f" {H32} 5 evil.tar.gz")))
show("trailer after the signature (unsigned text)", lambda: files_of(dsc(trailer="Checksums-Sha256:" + NL + f" {H64} 5 evil.tar.gz" + NL)))
show("text before BEGIN SIGNED MESSAGE", lambda: files_of(dsc(before="Checksums-Sha256:" + NL + f" {H64} 5 evil.tar.gz" + NL)))
show("unsigned .dsc", lambda: files_of(dsc(sig=False)))
show("CRLF line ends", lambda: files_of(dsc(sep="\r" + NL)))
show("dash-escaped field line '- Files:'", lambda: R.parse_dsc("-----BEGIN PGP SIGNED MESSAGE-----" + NL + "Hash: SHA256" + NL + NL + "- Source: x").get("Source"))
show("name with /", lambda: files_of(dsc(files=[("../x_1.orig.tar.gz", 100)])))
show("name with ..", lambda: files_of(dsc(files=[("x..y", 100)])))
show("name with NUL", lambda: files_of(dsc(files=[("x" + chr(0) + "y", 100)])))
show("name not in snapshot srcfiles", lambda: files_of(dsc(files=[("other.tar.gz", 100)])))
show("size 0", lambda: files_of(dsc(files=[("x_1.orig.tar.gz", 0)])))
show("size 10**20", lambda: files_of(dsc(files=[("x_1.orig.tar.gz", 10 ** 20)])))
show("size with Arabic digits", lambda: R.dsc_files(R.parse_dsc(dsc().replace(" 100 ", " " + chr(0x661) + "00 ")), "x_1-1.dsc", "x", "1-1", NAMES))
show("Files and Checksums-Sha256 differ", lambda: R.dsc_files(R.parse_dsc(dsc().replace(f"{H32} 100", f"{H32} 101")), "x_1-1.dsc", "x", "1-1", NAMES))
show("Checksums-Sha1 disagrees with snapshot", lambda: files_of(dsc(extra_fields=NL + "Checksums-Sha1:" + NL + f" {'f' * 40} 100 x_1.orig.tar.gz")))
show("Source/Version mismatch", lambda: R.dsc_files(R.parse_dsc(dsc().replace("Source: x", "Source: y")), "x_1-1.dsc", "x", "1-1", NAMES))
show("continuation ' .' line in Files", lambda: files_of(dsc(extra_fields="").replace("Files:" + NL, "Files:" + NL + " ." + NL)))
show("field name with tab", lambda: sorted(R.parse_dsc("Sou\trce: x" + NL + "Source: y")))
t0 = time.perf_counter(); R.parse_dsc("A: b" + NL + (" c" + NL) * 300000); P(f"  parse_dsc 1 MB continuation lines: {time.perf_counter() - t0:.3f}s")

P("\n== U7c-2. srcfiles_map ==")
show("baseline", lambda: R.srcfiles_map({"fileinfo": {H40: [{"name": "a"}], "d" * 40: [{"name": "b"}]}}))
show("same name, two sha1s", lambda: R.srcfiles_map({"fileinfo": {H40: [{"name": "a"}], "d" * 40: [{"name": "a"}]}}))
show("same name, same sha1 twice (two archives)", lambda: R.srcfiles_map({"fileinfo": {H40: [{"name": "a"}, {"name": "a", "archive_name": "debian-security"}]}}))
show("upper-case sha1 key", lambda: R.srcfiles_map({"fileinfo": {H40.upper(): [{"name": "a"}]}}))
show("entries not a list", lambda: R.srcfiles_map({"fileinfo": {H40: {"name": "a"}}}))
show("name int", lambda: R.srcfiles_map({"fileinfo": {H40: [{"name": 5}]}}))
show("fileinfo list", lambda: R.srcfiles_map({"fileinfo": []}))
show("name ../x accepted into the map (checked later)", lambda: R.srcfiles_map({"fileinfo": {H40: [{"name": "../x"}]}}))

P("\n== U7c-3. GitLab tree listing (_tree_blobs) ==")
C40 = "1" * 40
def blob(path, mode="100644", typ="blob", name=None):
    return {"path": path, "name": name if name is not None else path.rsplit("/", 1)[-1], "type": typ, "mode": mode}
tb = lambda listing: R._tree_blobs(listing, "main", "readline", C40)
show("baseline (APKBUILD, patch, sub/x.patch)", lambda: tb([blob("main/readline/APKBUILD"), blob("main/readline/a.patch"), blob("main/readline/sub", typ="tree", mode="040000"), blob("main/readline/sub/x.patch")]))
show("symlink 120000", lambda: tb([blob("main/readline/APKBUILD"), blob("main/readline/l", mode="120000")]))
show("submodule (type commit, 160000)", lambda: tb([blob("main/readline/APKBUILD"), blob("main/readline/m", typ="commit", mode="160000")]))
show("mode int 100644", lambda: tb([blob("main/readline/APKBUILD", mode=100644)]))
show("path with ..", lambda: tb([blob("main/readline/../bash/APKBUILD", name="APKBUILD")]))
show("path with %2e%2e", lambda: tb([blob("main/readline/%2e%2e/x", name="x")]))
show("path outside prefix (main/readline-x/)", lambda: tb([blob("main/readline-x/APKBUILD")]))
show("name differs from path basename", lambda: tb([blob("main/readline/a", name="APKBUILD")]))
show("basename collision (a.patch, sub/a.patch)", lambda: tb([blob("main/readline/a.patch"), blob("main/readline/sub/a.patch")]))
show("tree entry with odd path (skipped)", lambda: tb([blob("main/readline/APKBUILD"), blob("../../evil", typ="tree", mode="040000")]))
show("listing is a dict", lambda: tb({"path": "x"}))
show("entry type missing", lambda: tb([{"path": "main/readline/APKBUILD", "name": "APKBUILD", "mode": "100644"}]))
show("100 entries, no x-next-page (truncation check is header-only)", lambda: len(tb([blob(f"main/readline/f{i}") for i in range(100)])))

P("\n== U7c-4. The two lock-rule changes (lock_problems on a good apk entry) ==")
AK = "apk:readline@8.2.13-r1"
BASE = tl.good_lock(tl.SMALL_KEYS); POL = tl.policy(); DOCS = tl.small_docs()
def probs(lock):
    return sc.lock_problems(tl.canon(lock), POL, DOCS, "amd64", today=datetime.date(2026, 10, 25))
base_p = probs(BASE)
P(f"  baseline problems: {base_p}")
E = BASE["components"][AK]; commit = E["commit"]
rawb = f"https://gitlab.alpinelinux.org/alpine/aports/-/raw/{commit}/main/readline/"
gl_from = f"gitlab files API content_sha256 at {commit}"
def gl_file(name, url, frm=gl_from, alg="sha256"):
    sha = hashlib.sha256(name.encode()).hexdigest()
    return {"name": name, "url": url, "sha256": sha, "size": 10, "upstream": {"alg": alg, "value": sha if alg == "sha256" else "f" * 128, "from": frm}}
def with_entry(fn):
    d = copy.deepcopy(BASE); fn(d["components"][AK]); return d
def rep(label, d):
    pr = [x for x in probs(d) if x not in base_p]
    P(f"  {label:62s} accepted={not pr!s:5} {[x[:110] for x in pr[:1]]}")
rep("APKBUILD moved to a subdirectory (sub/APKBUILD)", with_entry(lambda e: e["files"][0].update(url=rawb + "sub/APKBUILD")))
rep("APKBUILD moved to sub/deeper/APKBUILD", with_entry(lambda e: e["files"][0].update(url=rawb + "sub/deeper/APKBUILD")))
rep("extra sha256 gitlab file at top level", with_entry(lambda e: e["files"].append(gl_file("a.patch", rawb + "a.patch"))))
rep("extra sha256 gitlab file in a subdirectory", with_entry(lambda e: e["files"].append(gl_file("x.patch", rawb + "sub/x.patch"))))
rep("sha256 gitlab-from file on distfiles", with_entry(lambda e: e["files"].append(gl_file("y.tar.gz", "https://distfiles.alpinelinux.org/distfiles/v3.23/y.tar.gz"))))
rep("sha256 file on gitlab at another commit", with_entry(lambda e: e["files"].append(gl_file("a.patch", rawb.replace(commit, "f" * 40) + "a.patch"))))
rep("sha256 gitlab file whose from names another commit", with_entry(lambda e: e["files"].append(gl_file("a.patch", rawb + "a.patch", frm=f"gitlab files API content_sha256 at {'f' * 40}"))))
rep("sha256 gitlab file with from 'uv.lock'", with_entry(lambda e: e["files"].append(gl_file("a.patch", rawb + "a.patch", frm="uv.lock"))))
rep("subdirectory segment with a dot-dot inside a name (a..b)", with_entry(lambda e: e["files"].append(gl_file("x.patch", rawb + "a..b/x.patch"))))
rep("subdirectory into another origin (../bash/)", with_entry(lambda e: e["files"].append(gl_file("x.patch", rawb + "../bash/x.patch"))))
rep("the upstream tarball as a gitlab sha256 file (in the tree)", with_entry(lambda e: e["files"].__setitem__(1, gl_file(e["files"][1]["name"], rawb + e["files"][1]["name"]))))
rep("APKBUILD with from 'APKBUILD sha512sums'", with_entry(lambda e: e["files"][0]["upstream"].update({"from": f"APKBUILD sha512sums at {commit}"})))
rep("two APKBUILDs (top and sub/)", with_entry(lambda e: e["files"].append(gl_file("APKBUILD", rawb + "sub/APKBUILD"))))

P("\n== U7c-5. tar reading of lib/apk/db/installed and etc/alpine-release ==")
W = tempfile.mkdtemp()
def save_tar(layers, members_extra=None):
    blobs, names = {}, []
    for files in layers:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as t:
            for name, spec in files.items():
                info = tarfile.TarInfo(name)
                if isinstance(spec, tuple):
                    kind, target = spec
                    info.type = tarfile.LNKTYPE if kind == "hard" else tarfile.SYMTYPE
                    info.linkname = target
                    t.addfile(info)
                else:
                    info.size = len(spec); t.addfile(info, io.BytesIO(spec))
        data = buf.getvalue(); name = f"blobs/sha256/{hashlib.sha256(data).hexdigest()}"
        blobs[name] = data; names.append(name)
    p = os.path.join(W, f"t{len(os.listdir(W))}.tar")
    with tarfile.open(p, "w") as t:
        for name, data in list(blobs.items()) + [("manifest.json", json.dumps([{"Config": "x", "Layers": names}]).encode())]:
            info = tarfile.TarInfo(name); info.size = len(data); t.addfile(info, io.BytesIO(data))
    return p
DB = "lib/apk/db/installed"
show("top layer wins", lambda: sc.tar_file_text(save_tar([{DB: b"old"}, {DB: b"new"}]), DB, 16 << 20))
show("top layer whiteout .wh.installed (lower copy still read)", lambda: sc.tar_file_text(save_tar([{DB: b"old"}, {"lib/apk/db/.wh.installed": b""}]), DB))
show("top layer hard link (skipped, lower wins)", lambda: sc.tar_file_text(save_tar([{DB: b"old", "x": b"other"}, {DB: ("hard", "x")}]), DB))
show("top layer symlink to /etc/passwd (skipped)", lambda: sc.tar_file_text(save_tar([{DB: b"old"}, {DB: ("sym", "/etc/passwd")}]), DB))
show("member over the 16 MiB limit", lambda: sc.tar_file_text(save_tar([{DB: b"P:x" + b"a" * (16 << 20)}]), DB, 16 << 20))
show("lower layer over the limit, top small", lambda: sc.tar_file_text(save_tar([{DB: b"a" * ((1 << 20) + 5)}, {DB: b"ok"}]), DB))
show("./-prefixed member name", lambda: sc.tar_file_text(save_tar([{"./" + DB: b"dot"}]), DB))
show("../-prefixed member name (no match)", lambda: sc.tar_file_text(save_tar([{"../" + DB: b"up"}]), DB))
st = sc.apk_stanzas("P:readline" + NL + "P:evil" + NL + "V:1" + NL + "o:readline" + NL + "c:" + "a" * 40 + NL + NL + NL + "P:x" + "\r" + NL + "V:2")
P(f"  apk_stanzas: duplicate P keeps the first: {st[0].get('P')}; CRLF stanza: {st[1]}")
t0 = time.perf_counter(); sc.apk_stanzas(("P:x" + NL + "V:1" + NL + NL) * 300000); P(f"  apk_stanzas on ~3 MB: {time.perf_counter() - t0:.2f}s")
t0 = time.perf_counter(); sc.apk_stanzas(NL + " " * 2000000 + "x"); P(f"  apk_stanzas on 2 MB of spaces between newlines: {time.perf_counter() - t0:.2f}s")

P("\n== U7c-6. read1 drip-feed re-probe (loopback HTTP, DEADLINE patched to 2 s) ==")
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1); port = srv.getsockname()[1]
def serve():
    c, _ = srv.accept(); c.recv(65536)
    c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100000\r\n\r\n")
    try:
        for i in range(400):
            c.sendall(b"x"); time.sleep(0.05)
    except OSError:
        pass
    c.close()
threading.Thread(target=serve, daemon=True).start()
R.DEADLINE = 2
url = f"http://127.0.0.1:{port}/drip"; result = {}
def run():
    t0 = time.monotonic()
    try:
        r = R._default_opener(url, 5); n = 0
        for chunk in R._guarded(r, "127.0.0.1", url, t0, 5):
            n += len(chunk)
        result["out"] = f"completed {n} bytes"
    except R.ResolveError as e:
        result["out"] = f"ResolveError after {time.monotonic() - t0:.1f}s: {str(e)[:60]}"
    except BaseException as e:
        result["out"] = f"{type(e).__name__} after {time.monotonic() - t0:.1f}s"
th = threading.Thread(target=run, daemon=True); t0 = time.monotonic(); th.start(); th.join(12)
P(f"  after {time.monotonic() - t0:.1f}s: {'still blocked' if th.is_alive() else result.get('out')}")
