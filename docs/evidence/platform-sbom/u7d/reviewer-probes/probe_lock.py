import sys, json, re, collections, hashlib
sys.path.insert(0, r"c:\repos\Knowledge-engine")
import tests.test_sources_lock as tl
check = tl.load_sbom_check()
raw = open(r"c:\repos\Knowledge-engine\docker\sources.lock.json", "rb").read()
text = raw.decode("utf-8")
lock = json.loads(text)
c = lock["components"]
print("bytes", len(raw), "| CR present:", b"\r" in raw, "| canonical:", check.lock_text(lock) == text, "| format", lock["format"])
print("keys", len(c), "== FIXTURE_KEYS:", set(c) == set(tl.FIXTURE_KEYS))
print("kinds", dict(collections.Counter(k.split(":")[0] for k in c)))
probs = check.lock_problems(text, tl.policy(), tl.fixture_docs(), "amd64")
print("lock_problems(fixture docs):", len(probs), probs[:3])
print("arches set:", {tuple(e["arches"]) for e in c.values()}, "| origins:", dict(collections.Counter(e["origin"] for e in c.values())))
files = [(k, f) for k, e in c.items() for f in e["files"]]
print("files", len(files), "| total bytes", sum(f["size"] for _, f in files))
print("hosts used:", dict(collections.Counter(re.match(r"https://([^/]+)/", f["url"]).group(1) for _, f in files)))
print("upstream algs by kind:", {k: dict(collections.Counter(f["upstream"]["alg"] for kk, f in files if kk.startswith(k + ":"))) for k in ("deb","pgdg","apk","neo4j","temurin","pypi","maven")})
froms = collections.Counter(re.sub(r"[0-9a-f]{40}", "<c>", re.sub(r"\S+\.dsc", "<dsc>", f["upstream"]["from"])) for _, f in files)
print("from forms:"); [print("   ", n, ascii(t)[:110]) for t, n in froms.most_common()]
print("zero-size files:", [(k, f["name"]) for k, f in files if f["size"] == 0])
print("underscore names:", [(k, f["name"]) for k, f in files if f["name"].startswith("_")])
print("query urls by kind:", dict(collections.Counter(k.split(":")[0] for k, f in files if "?" in f["url"])))
print("percent urls by kind:", dict(collections.Counter(k.split(":")[0] for k, f in files if "%" in f["url"])))
n = c["neo4j:neo4j@5.26.32"]; print("neo4j:", json.dumps(n, sort_keys=True)[:400])
t = c["temurin:jdk-21.0.12.1+1"]; print("temurin:", json.dumps(t, sort_keys=True)[:420])
for k in sorted(c):
    if k.startswith("pgdg:"): print(k, "suite", c[k]["suite"], [ (f["name"], f["upstream"]["from"]) for f in c[k]["files"]])
print("maven:", json.dumps(c["maven:javax.xml.bind:jaxb-api@2.2.12"], sort_keys=True)[:420])
print("pypi urls:", [c[k]["files"][0]["url"].split(".org")[1][:40] + "..." + c[k]["files"][0]["name"] for k in sorted(c) if k.startswith("pypi:")], [c[k]["files"][0]["upstream"]["from"] for k in sorted(c) if k.startswith("pypi:")])
bl = c.get("apk:alpine-baselayout@3.7.2-r1"); print("alpine-baselayout files:", [f["name"] for f in bl["files"]], bl["repo"], bl["branch"])
print("deb bash:", [(f["name"], f["upstream"]["alg"], f["upstream"]["from"]) for f in c["deb:bash@5.2.15-2"]["files"]])
print("sample:", check.sample_keys(lock, "amd64"))
gcc = [k for k in c if k.startswith("deb:gcc")]; print("gcc keys:", gcc)
