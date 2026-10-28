"""Read-only aports probe (U7d round 1, item 11): for each apk lock key, the
GitLab recursive tree listing at the key's commit (main and community), the
APKBUILD through the files API metadata (base64 content; no raw endpoint),
and each symlink's metadata. Reports every shape the current rules reject.
Usage: python -I aports_probe.py <keys.txt> <resolver.py> <out.txt>"""
import base64
import hashlib
import importlib.util
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

KEYS_FILE, RESOLVER, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
WANT = {
    "apk:alpine-baselayout@3.7.1-r8", "apk:alpine-baselayout@3.7.2-r1", "apk:apk-tools@3.0.3-r1",
    "apk:apk-tools@3.0.8-r0", "apk:busybox@1.37.0-r30", "apk:busybox@1.37.0-r31", "apk:gcc@15.2.0-r2",
    "apk:gcc@15.2.0-r5", "apk:geoip@1.6.12-r6", "apk:gettext@0.24.1-r1", "apk:libcap-ng@0.8.5-r2",
    "apk:libidn2@2.3.8-r0", "apk:libunistring@1.4.1-r0", "apk:musl@1.2.5-r21", "apk:musl@1.2.6-r2",
    "apk:pax-utils@1.3.8-r2", "apk:pax-utils@1.3.9-r1", "apk:util-linux@2.42.3-r1", "apk:xz@5.8.2-r0",
}
API = "https://gitlab.alpinelinux.org/api/v4/projects/alpine%2Faports/repository"
OLD = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+~-]{0,254}")
NEW = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._+~-]{0,254}")
BRANCH = {"gw": "v3.23", "vk": "v3.24"}
IMAGE = {"gw": "ke-gateway", "vk": "valkey"}

spec = importlib.util.spec_from_file_location("resolver", RESOLVER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

lines: list[str] = []
requests = 0


def out(s: str = "") -> None:
    lines.append(s)
    print(s, flush=True)


def get(url: str) -> tuple[int, dict, bytes]:
    global requests
    requests += 1
    time.sleep(1)
    req = urllib.request.Request(url, headers={"User-Agent": "knowledge-engine-sources-lock-probe",
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(4 << 20)
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, b""


def ok(rx: re.Pattern, name: str) -> bool:
    return bool(rx.fullmatch(name)) and ".." not in name


keys = {}
for ln in open(KEYS_FILE, encoding="utf-8"):
    parts = ln.split()
    if len(parts) < 4:
        continue
    img, origin, ver, commit = parts[:4]
    k = f"apk:{origin}@{ver}"
    if k in WANT:
        keys[k] = (img, origin, ver, commit)
missing = sorted(WANT - set(keys))
out("aports probe (U7d round 1, item 11): read-only; GitLab API only (tree listing, files-API metadata); "
    "no raw endpoint, no distfiles")
out(f"keys: {len(keys)} of {len(WANT)} (origin, version, commit from lib/apk/db/installed o:/V:/c: of the local "
    "ke-gateway:local and valkey/valkey:8-alpine@sha256:081c2f5c... images; branch from etc/alpine-release)")
if missing:
    out(f"MISSING KEYS: {missing}")
out(f"rules: current name rule {OLD.pattern} (+ no '..'); item 10 rule {NEW.pattern}")
out("")

summary: list[str] = []
for k in sorted(keys):
    img, origin, ver, commit = keys[k]
    out(f"== {k}  image={IMAGE[img]} branch={BRANCH[img]} commit={commit}")
    found = {}
    for repo in ("main", "community"):
        path = urllib.parse.quote(f"{repo}/{origin}", safe="")
        st, hd, body = get(f"{API}/tree?path={path}&ref={commit}&recursive=true&per_page=100")
        listing = json.loads(body) if st == 200 and body else None
        n = len(listing) if isinstance(listing, list) else None
        out(f"  {repo}: HTTP {st}, entries={n}, x-next-page={hd.get('x-next-page')!r}, x-total={hd.get('x-total')!r}")
        if listing:
            found[repo] = (listing, hd)
    if len(found) != 1:
        out(f"  FLAG: found in {sorted(found) or 'neither'} repo")
        summary.append(f"{k}: in {sorted(found) or 'neither'}")
        continue
    repo, (listing, hd) = next(iter(found.items()))
    prefix = f"{repo}/{origin}/"
    if len(listing) >= 100:
        out("  FLAG: 100 or more entries (truncation rule)")
        summary.append(f"{k}: {len(listing)} entries")
    names: dict[str, list[str]] = {}
    links = {}
    for e in listing:
        typ, mode, p, name = e.get("type"), e.get("mode"), e.get("path"), e.get("name")
        rel = p[len(prefix):] if p.startswith(prefix) else p
        if typ == "tree":
            out(f"  subdirectory: {rel}/ (mode {mode}; skipped by the rules, its files are listed)")
            summary.append(f"{k}: subdirectory {rel}/")
            continue
        segs = rel.split("/")
        bad_old = [s for s in segs if not ok(OLD, s)]
        bad_new = [s for s in segs if not ok(NEW, s)]
        if bad_old or bad_new:
            out(f"  name: {rel}: fails current rule {bad_old}; fails item-10 rule {bad_new}")
            summary.append(f"{k}: name {rel} (current: {'refused' if bad_old else 'ok'}, item 10: "
                           f"{'refused' if bad_new else 'ok'})")
        if len(segs) > 1:
            out(f"  nested file: {rel} (type {typ}, mode {mode})")
            summary.append(f"{k}: nested file {rel}")
        if typ == "commit" or mode == "160000":
            out(f"  submodule: {rel} (type {typ}, mode {mode}) -> refused")
            summary.append(f"{k}: submodule {rel}")
        elif mode == "120000":
            links[name] = rel
        elif typ != "blob" or mode not in ("100644", "100755"):
            out(f"  other entry: {rel} type={typ} mode={mode} -> refused")
            summary.append(f"{k}: other entry {rel} {typ}/{mode}")
        names.setdefault(name, []).append(rel)
    for n, rels in names.items():
        if len(rels) > 1:
            out(f"  basename collision: {n}: {rels}")
            summary.append(f"{k}: basename collision {n}")
    # The real resolver functions, current rule then item-10 rule.
    verdict = {}
    for label, rx in (("current", OLD), ("item 10", NEW)):
        mod.NAME_RE = rx
        try:
            got_links: dict = {}
            mod._tree_blobs(listing, repo, origin, commit, got_links)
            verdict[label] = "ok"
        except mod.ResolveError as exc:
            verdict[label] = f"refused: {exc}"
        out(f"  _tree_blobs ({label} rule): {verdict[label]}")
    mod.NAME_RE = NEW
    # APKBUILD via files-API metadata (base64 content), parsed by the resolver's parse_apkbuild.
    st, _, body = get(f"{API}/files/{urllib.parse.quote(prefix + 'APKBUILD', safe='')}?ref={commit}")
    sums: dict = {}
    if st != 200:
        out(f"  APKBUILD metadata: HTTP {st}")
        summary.append(f"{k}: APKBUILD metadata HTTP {st}")
    else:
        meta = json.loads(body)
        text = base64.b64decode(meta["content"]).decode("utf-8")
        same = hashlib.sha256(text.encode("utf-8")).hexdigest() == meta.get("content_sha256")
        out(f"  APKBUILD: {meta.get('size')} bytes, content_sha256 binds: {same}")
        for label, rx in (("current", OLD), ("item 10", NEW)):
            mod.NAME_RE = rx
            try:
                parsed = mod.parse_apkbuild(text, commit, ver, origin)
                if label == "item 10":
                    sums = dict(parsed)
                out(f"  parse_apkbuild ({label} rule): ok, {len(parsed)} sha512sums names")
            except mod.ResolveError as exc:
                out(f"  parse_apkbuild ({label} rule): refused: {exc}")
                summary.append(f"{k}: parse_apkbuild ({label}) refused: {exc}")
        mod.NAME_RE = NEW
    local = {n for n in names if n != "APKBUILD"}
    in_tree = sorted(n for n in sums if n in names)
    distfiles = sorted(n for n in sums if n not in names)
    unsummed = sorted(n for n in local if n not in sums and n not in links)
    nested_sums = sorted(n for n in in_tree if any("/" in r for r in names[n]))
    out(f"  sha512sums: {len(sums)} names; {len(in_tree)} in the tree, {len(distfiles)} from distfiles")
    for n in distfiles:
        out(f"    distfile: {n}")
    if unsummed:
        out(f"  tree files not in sha512sums (locked by content_sha256): {unsummed}")
    if nested_sums:
        out(f"  FLAG: sha512sums names found only in a subdirectory: {nested_sums}")
        summary.append(f"{k}: sums names in a subdirectory {nested_sums}")
    for n, rel in sorted(links.items()):
        st, _, body = get(f"{API}/files/{urllib.parse.quote(prefix + rel, safe='')}?ref={commit}")
        if st != 200:
            out(f"  symlink {rel}: metadata HTTP {st}")
            summary.append(f"{k}: symlink {rel} metadata HTTP {st}")
            continue
        meta = json.loads(body)
        target = base64.b64decode(meta["content"]).decode("ascii", "replace")
        same_dir = "/" not in target and target in names and all("/" not in r for r in names[target])
        out(f"  symlink: {rel} -> {target!r} (size {meta.get('size')}; target a top-level regular blob: {same_dir}; "
            f"named in sha512sums: {n in sums})")
        summary.append(f"{k}: symlink {rel} -> {target} ({'skip rule holds' if same_dir and n not in sums else 'REFUSED'})")
    out("")

out(f"requests: {requests} (all to the GitLab API; none raw)")
out("")
out("SUMMARY (every shape found):")
for s in summary:
    out(f"  {s}")
open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
