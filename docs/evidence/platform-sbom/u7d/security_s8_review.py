"""security S8 lock review (platform-sbom U7d). python -I, gates image, no network."""
import collections, datetime, json, re, sys
from urllib.parse import urlsplit
sys.path.insert(0, "/work")
import tests.test_sources_lock as tl
from tests.test_sbom_bundle import load_sbom_check
sc = load_sbom_check()
P = print
text = open("/work/docker/sources.lock.json", encoding="utf-8", newline="").read()
lock = json.loads(text)
pol = json.load(open("/work/docker/source-policy.json"))
P("== S8-1. lock_problems (committed lock, committed policy, six U3 fixtures, amd64) ==")
pr = sc.lock_problems(text, pol, tl.fixture_docs(), "amd64")
P("  problems:", pr)
P("  canonical text:", text == sc.lock_text(lock), "| bytes", len(text.encode()), "| CRLF present:", "\r" in text)
P("  committed policy hosts:", len(pol["hosts"]), "| keys:", sorted(pol))
comps = lock["components"]
P("\n== S8-2. Shape review of all entries ==")
kinds = collections.Counter(k.split(":")[0] for k in comps)
P("  entries:", len(comps), dict(sorted(kinds.items())))
files = [(k, f) for k, e in comps.items() for f in e["files"]]
P("  files:", len(files))
P("  arches values:", collections.Counter(tuple(e["arches"]) for e in comps.values()))
P("  origin values:", collections.Counter((k.split(":")[0], e["origin"]) for k, e in comps.items()))
hosts = collections.Counter((k.split(":")[0], urlsplit(f["url"]).netloc) for k, f in files)
P("  (kind, host) pairs:", dict(sorted(hosts.items())))
def shape(k, f):
    u = f["url"]; kind = k.split(":")[0]
    if kind == "deb": return re.sub(r"[0-9a-f]{40}", "<sha1>", u)
    if kind == "apk":
        u = re.sub(r"ref=[0-9a-f]{40}", "ref=<commit>", u); u = re.sub(r"/files/[^/]+/raw", "/files/<P>/raw", u)
        return re.sub(r"distfiles/v[0-9.]+/[^/]+$", "distfiles/<branch>/<name>", u)
    if kind == "pypi": return re.sub(r"/packages/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{60}/[^/]+$", "/packages/<2>/<2>/<60>/<name>", u)
    if kind == "pgdg": return re.sub(r"/pool/main/[^/]+/[^/]+/[^/]+$", "/pool/main/<p>/<src>/<name>", u)
    if kind == "maven": return re.sub(r"/maven2/.*$", "/maven2/<g>/<a>/<v>/<name>", u)
    return re.sub(r"/[^/]+/[^/]+$", "/<tag>/<asset>", u) if kind == "temurin" else u
P("  URL shapes:", dict(collections.Counter(shape(k, f) for k, f in files)))
def ftmpl(k, f):
    fr = f["upstream"]["from"]
    fr = re.sub(r"[0-9a-f]{40}", "<commit>", fr)
    fr = re.sub(r"^\S+\.dsc Checksums-Sha256$", "<dsc> Checksums-Sha256", fr)
    fr = re.sub(r"^\S+\.sha256\.txt$", "<asset>.sha256.txt", fr)
    fr = re.sub(r"^\S+\.sha1$", "<jar>.sha1", fr)
    fr = re.sub(r"^pypi\.org JSON \S+ \S+$", "pypi.org JSON <n> <v>", fr)
    return (k.split(":")[0], f["upstream"]["alg"], fr)
P("  (kind, alg, from) templates:")
for t, n in sorted(collections.Counter(ftmpl(k, f) for k, f in files).items()):
    P(f"    {n:4d} {t}")
sizes = [f["size"] for _, f in files]
P(f"  sizes: min {min(sizes)} max {max(sizes)} total {sum(sizes)}; size 0: {[(k, f['name'], f['sha256'][:12]) for k, f in files if f['size'] == 0]}")
urls = collections.Counter(f["url"] for _, f in files)
dups = {u: n for u, n in urls.items() if n > 1}
P(f"  URLs used more than once: {len(dups)}")
for u, n in list(dups.items())[:10]:
    users = [(k, f["name"], f["sha256"][:12]) for k, f in files if f["url"] == u]
    P(f"    {n}x {u[:100]} {users}")
shas = collections.defaultdict(set)
for k, f in files:
    shas[f["sha256"]].add(f["url"])
P(f"  one sha256 under several URLs: {sum(1 for v in shas.values() if len(v) > 1)}")
same_url_diff_sha = [u for u in dups if len({f['sha256'] for _, f in files if f['url'] == u}) > 1]
P(f"  one URL with different sha256s: {same_url_diff_sha}")
P("  queries in URLs (kinds):", collections.Counter(k.split(":")[0] for k, f in files if "?" in f["url"]))
P("  any signed-query marker (sig=, X-Amz, jwt, token, __goaway):", [f["url"] for _, f in files if re.search(r"(?i)sig=|x-amz|jwt|token|goaway", f["url"])])
nj = comps.get("neo4j:neo4j@5.26.32")
P("\n== S8-3. The manual neo4j entry ==")
P("  ", json.dumps(nj, sort_keys=True))
apk = {k: e for k, e in comps.items() if k.startswith("apk:")}
P("\n== S8-4. Spot-check candidates (smallest file per kind) ==")
for kind in sorted(kinds):
    cand = sorted(((f["size"], k, f) for k, f in files if k.startswith(kind + ":")), key=lambda x: x[0])
    s, k, f = cand[0] if kind not in ("apk",) else next(c for c in cand if c[0] > 0)
    P(f"  {kind}: {k} {f['name']} size={s} sha256={f['sha256']} url={f['url']}")
d_apk = sorted(((f["size"], k, f) for k, f in files if k.startswith("apk:") and "distfiles" in f["url"]), key=lambda x: x[0])[0]
P(f"  apk distfiles: {d_apk[1]} {d_apk[2]['name']} size={d_apk[0]} sha256={d_apk[2]['sha256']} sha512={d_apk[2]['upstream']['value'][:16]}.. url={d_apk[2]['url']}")
deb_dsc = sorted(((f["size"], k, f) for k, f in files if k.startswith("deb:") and f["name"].endswith(".dsc")), key=lambda x: x[0])[0]
P(f"  deb .dsc: {deb_dsc[1]} {deb_dsc[2]['name']} size={deb_dsc[0]} sha256={deb_dsc[2]['sha256']} sha1={deb_dsc[2]['upstream']['value']} url={deb_dsc[2]['url']}")
for kind in ("maven", "temurin"):
    for k, f in files:
        if k.startswith(kind + ":"):
            P(f"  {kind}: {k} {f['name']} size={f['size']} sha256={f['sha256']} upstream={f['upstream']} url={f['url']}")
