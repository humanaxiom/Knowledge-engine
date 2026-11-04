"""security U7d rework r1 code probes (platform-sbom). python -I, gates image; loopback + fake network only."""
import base64, copy, datetime, hashlib, importlib.util, json, socket, ssl, sys, threading, time, urllib.error
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m
R = load("srv7dr1", "/work/scripts/sources_resolve.py")
sys.path.insert(0, "/work")
import tests.test_sources_lock as tl
from tests.test_sbom_bundle import load_sbom_check
sc = load_sbom_check()
P = print
P("== R1-A1. Real opener: what URLError reasons become (loopback) ==")
def listener(behaviour):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(1)
    def run():
        try:
            c, _ = s.accept()
            if behaviour == "silent":
                time.sleep(5)
            elif behaviour == "garbage":
                c.recv(1024); c.sendall(b"NOT TLS AT ALL\r\n\r\n")
            c.close()
        except OSError:
            pass
    threading.Thread(target=run, daemon=True).start()
    return s.getsockname()[1]
def classify(url, timeout=1):
    try:
        R._default_opener(url, timeout); return "no error"
    except BaseException as e:
        retried = isinstance(e, (TimeoutError, socket.timeout))
        return f"{type(e).__name__} (URLError={isinstance(e, urllib.error.URLError)}) -> {'retried' if retried else 'not retried'}"
p = listener("silent"); P(f"  TLS handshake to a silent server (timeout 1 s): {classify(f'https://127.0.0.1:{p}/x')}")
p = listener("garbage"); P(f"  TLS handshake answered with plain text:      {classify(f'https://127.0.0.1:{p}/x')}")
s = socket.socket(); s.bind(("127.0.0.1", 0)); closed = s.getsockname()[1]; s.close()
P(f"  connection refused (closed port):           {classify(f'https://127.0.0.1:{closed}/x')}")
P(f"  unknown host name:                          {classify('https://no-such-host.invalid/x')}")
P(f"  _transport on ssl.SSLError: {type(R._transport('h', 'u', ssl.SSLError('x'), 60)).__name__}; on TimeoutError: {type(R._transport('h', 'u', TimeoutError(), 60)).__name__}")

P("\n== R1-A2. Item 8: aports symlinks (_check_link with a fake files API) ==")
C40 = "1" * 40
class Net:
    def __init__(self, routes): self.routes = routes
    def __call__(self, url, timeout):
        r = self.routes.get(url); return R.Response(404, {}, b"") if r is None else R.Response(*r)
ALLOW = set(json.load(open("/work/docker/source-policy.json"))["hosts"])
def meta(target_bytes, size=None, enc="base64", content=None, sha=None):
    return json.dumps({"encoding": enc, "size": len(target_bytes) if size is None else size,
                       "content": base64.b64encode(target_bytes).decode() if content is None else content,
                       "content_sha256": sha or hashlib.sha256(target_bytes).hexdigest()}).encode()
def link(label, target, blobs=None, sums=None, rel="sub/l", **kw):
    blobs = blobs or {"real": "sub/real", "top": "top", "APKBUILD": "APKBUILD"}
    url = f"{R.APORTS_API}/files/{R.quote('main/x/' + rel, safe='')}?ref={C40}"
    R.OPENER = Net({url: (200, {}, meta(target, **kw))})
    try:
        R._check_link("apk:x@1-r0", "x", "main", C40, rel.rsplit("/", 1)[-1], rel, blobs, sums or {}, ALLOW); out = "skipped (accepted)"
    except R.ResolveError as e:
        out = f"refused: {str(e)[:80]}"
    P(f"  {label:52s} -> {out}")
link("link to a sibling regular blob", b"real")
link("link to a blob in another directory", b"top")
link("link with ../", b"../top")
link("link to a subdirectory path real/x", b"sub/real")
link("link to a name not in the tree", b"missing")
link("link to . ", b".")
link("link target with NUL", b"re\x00al")
link("link target non-ASCII", "r\u00e9al".encode())
link("content not strict base64 (spaces)", b"real", content="cm Vh bA==")
link("content_sha256 does not match content", b"real", sha="0" * 64)
link("size 2000 (> 1 KiB)", b"real", size=2000)
link("size 0", b"real", size=0)
link("encoding text", b"real", enc="text")
link("link named in sha512sums", b"real", sums={"l": "a" * 128})
link("link to the APKBUILD (same dir? APKBUILD is top)", b"APKBUILD")
P("  _tree_blobs: a link whose name equals a blob name ->", end=" ")
try:
    R._tree_blobs([{"path": "main/x/a", "name": "a", "type": "blob", "mode": "100644"}, {"path": "main/x/sub/a", "name": "a", "type": "blob", "mode": "120000"}], "main", "x", C40, {})
    P("accepted")
except R.ResolveError as e:
    P(f"refused: {e}")
P("  _tree_blobs: a 120000 link with links=None (old callers) ->", end=" ")
try:
    R._tree_blobs([{"path": "main/x/l", "name": "l", "type": "blob", "mode": "120000"}], "main", "x", C40); P("accepted")
except R.ResolveError as e:
    P(f"refused: {str(e)[:60]}")

P("\n== R1-A3. Items 10 and 12 in lock-check (fixture lock) ==")
FD = tl.fixture_docs(); POL = tl.policy(); LOCK = tl.good_lock(tl.FIXTURE_KEYS)
def probs(lock):
    return sc.lock_problems(tl.canon(lock), POL, FD, "amd64", today=datetime.date(2026, 10, 26))
base_p = probs(LOCK); P("  baseline problems:", base_p[:2])
AK = "apk:busybox@1.37.0-r30"; E = LOCK["components"][AK]; C = E["commit"]
api = f"https://gitlab.alpinelinux.org/api/v4/projects/alpine%2Faports/repository/files/main%2Fbusybox%2F{{}}/raw?ref={C}"
gl_from = f"gitlab files API content_sha256 at {C}"
E0 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
def add(label, f, key=AK):
    d = copy.deepcopy(LOCK); d["components"][key]["files"].append(f)
    pr = [x for x in probs(d) if x not in base_p]
    P(f"  {label:56s} accepted={not pr!s:5} {[x[:100] for x in pr[:1]]}")
def gf(name, size, sha, url=None, alg="sha256", value=None, frm=None):
    return {"name": name, "url": url or api.format(name), "sha256": sha, "size": size,
            "upstream": {"alg": alg, "value": value or sha, "from": frm or gl_from}}
add("apk GitLab file, size 0, empty sha256", gf("empty.patch", 0, E0))
add("apk GitLab file, size 0, other sha256", gf("empty.patch", 0, "a" * 64))
add("apk GitLab file, size -1", gf("neg.patch", -1, E0))
add("apk distfiles file, size 0, empty hashes", {"name": "z.tar.gz", "url": "https://distfiles.alpinelinux.org/distfiles/v3.23/z.tar.gz", "sha256": E0, "size": 0,
     "upstream": {"alg": "sha512", "value": sc.EMPTY_SHA512, "from": f"APKBUILD sha512sums at {C}"}})
add("apk GitLab sha512 file, size 0, wrong sha512", gf("e.patch", 0, E0, alg="sha512", value="f" * 128, frm=f"APKBUILD sha512sums at {C}"))
DK = "deb:bash@5.2.15-2"; df = LOCK["components"][DK]["files"][1]
add("deb file size 0 (empty hash)", dict(df, name="bash_x.tar.xz", size=0, sha256=E0, upstream=dict(df["upstream"], value=E0)), key=DK)
add("name with a leading underscore (_service)", gf("_service", 10, "b" * 64))
add("name '_' alone", gf("_", 10, "c" * 64))
add("name '_..x' (dot-dot)", gf("_..x", 10, "d" * 64))
add("name '-x' (leading dash still refused)", gf("-x", 10, "e" * 64))
PK = "pgdg:postgresql-common@293.pgdg12+1"
d = copy.deepcopy(LOCK); e = d["components"][PK]; e["suite"] = "trixie-pgdg-archive"; e["files"][0]["upstream"]["from"] = "apt-archive.postgresql.org trixie-pgdg-archive Sources"
P(f"  N1: pgdg entry suite trixie for bookworm packages -> {[x[:110] for x in probs(d) if x not in base_p][:1]}")
