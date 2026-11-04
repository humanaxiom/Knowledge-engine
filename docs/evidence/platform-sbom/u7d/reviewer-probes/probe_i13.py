import sys, json, unittest, tempfile, os
sys.path.insert(0, r"c:\repos\Knowledge-engine")
import tests.test_sources_lock_committed as t
base = json.load(open(r"c:\repos\Knowledge-engine\docker\sources.lock.json"))
def run(label, mutate):
    d = json.loads(json.dumps(base)); mutate(d)
    p = os.path.join(tempfile.mkdtemp(), "lock.json")
    open(p, "w", newline="\n").write(json.dumps(d, indent=1, sort_keys=True) + "\n")
    t.LOCK = p
    r = unittest.TextTestRunner(stream=open(os.devnull, "w")).run(unittest.TestLoader().loadTestsFromName("CommittedLockTest.test_nothing_the_hardcoded_scan_would_miss", t))
    print(f"  {label}: {'caught' if r.failures else 'NOT caught'}")
k = "deb:bash@5.2.15-2"
run("unchanged", lambda d: None)
run("an entry key `port: 8080`", lambda d: d["components"][k].update(port=8080))
run("a file key `http_url`", lambda d: d["components"][k]["files"][0].update(http_url="x"))
run("a number in upstream (`value: 8080`)", lambda d: d["components"][k]["files"][0]["upstream"].update(value=8080))
run("a top-level `listen: 8080`", lambda d: d.update(listen=8080))
