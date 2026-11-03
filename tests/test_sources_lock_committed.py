"""platform-sbom U7d S7: the committed source lock (design-notes "U7d
precision" S7; PSC-15; N5 amendment U7 item 6 "U7d"; orchestrator brief
2026-10-26).

`docker/sources.lock.json` is checked as committed, in every verify run:
- `lock_problems(file text, the committed policy, the six U3 fixture docs,
  "amd64") == []` (schema, binding, coverage both ways: every needed key
  present, no stale entry);
- the file is canonical (`lock_text(json.loads(file)) == file`), LF only,
  `format` 1;
- the manual `neo4j` entry is security's second fetch
  (docs/evidence/platform-sbom/sources-provenance.md; the values are copied
  here, the test never reads docs/evidence);
- `sample_keys(lock, "amd64")` gives one key per kind present (seven, pgdg
  included);
- `.gitattributes` holds `docker/sources.lock.json text eol=lf`.

A missing lock is a named failure, never an error. `LOCK` and `GITATTRIBUTES`
are module paths (the controls point them at a stand-in).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from tests.engine_support import ROOT
from tests.test_sbom_bundle import load_sbom_check
from tests.test_sources_lock import FIXTURE_KEYS, fixture_docs, policy

LOCK = ROOT / "docker" / "sources.lock.json"
GITATTRIBUTES = ROOT / ".gitattributes"
ARCH = "amd64"
NEO4J_KEY = "neo4j:neo4j@5.26.32"
# Security's second fetch (sources-provenance.md, 2026-10-25).
NEO4J_SHA256 = "182ae2e5c3807bc3d7a09770dbf450d2e8667080bde93b3b6c829125db0f91e3"
NEO4J_SIZE = 20907800
KINDS = {"deb", "pgdg", "apk", "neo4j", "temurin", "pypi", "maven"}
EOL_LINE = "docker/sources.lock.json text eol=lf"
# U8c O-2 (PSC-23 U8-10): the redirect targets the real U8b fetches used, one
# per redirected kind (neo4j -> codeload.github.com, temurin ->
# release-assets.githubusercontent.com); the values are copied here, the test
# never reads docs/evidence. Every other policy host is a lock file URL host.
REDIRECT_HOSTS = {"codeload.github.com", "release-assets.githubusercontent.com"}


class CommittedLockTest(unittest.TestCase):

    def _bytes(self) -> bytes:
        path = Path(LOCK)
        if not path.is_file():
            self.fail(f"{path.name} is not committed: run scripts/sources_lock.sh --arch {ARCH} (U7d S5) "
                      "and commit it with its test (S7)")
        return path.read_bytes()

    def _lock(self) -> dict[str, Any]:
        try:
            data = json.loads(self._bytes().decode("utf-8"))
        except ValueError as exc:
            self.fail(f"docker/sources.lock.json is not UTF-8 JSON: {exc}")
        self.assertIsInstance(data, dict)
        return data

    def test_nothing_the_hardcoded_scan_would_miss(self):
        """U7d round 1, item 13: tests/hardcoded_scan.py skips this file whole,
        so no schema key names a port or http, and every number is a `size` or
        the `format`. Component keys (package identifiers, held to the key
        grammar by lock_problems) are not schema keys."""
        lock = self._lock()
        bad: list[str] = []

        def walk(node: Any, where: str, key: str) -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    if where != "components" and ("http" in str(k).lower() or "port" in str(k).lower()):
                        bad.append(f"key {k!r} at {where or '(top)'}")
                    walk(v, str(k) if where == "" else f"{where}/{k}", str(k))
            elif isinstance(node, list):
                for item in node:
                    walk(item, where + "[]", "")
            elif isinstance(node, (int, float)) and not isinstance(node, bool):
                if not ((key == "size" and where.endswith("/size")) or where == "format"):
                    bad.append(f"number {node!r} at {where}")
        walk(lock, "", "")
        self.assertEqual(bad, [], "the lock holds what the hardcoded scan's skip would hide")

    def test_no_lock_problems(self):
        check = load_sbom_check()
        problems = check.lock_problems(self._bytes().decode("utf-8"), policy(), fixture_docs(), ARCH)
        self.assertEqual(problems, [], "lock_problems on the committed lock")

    def test_policy_hosts_are_the_lock_url_hosts_and_their_redirect_targets(self):
        """U8c O-2 (PSC-23 U8-10): `hosts` lists exactly what the committed
        lock's file URLs and their real redirects use, and nothing unused
        (objects.githubusercontent.com is dropped)."""
        from urllib.parse import urlsplit
        url_hosts = {urlsplit(f.get("url", "")).hostname or ""
                     for e in (self._lock().get("components") or {}).values() if isinstance(e, dict)
                     for f in e.get("files") or [] if isinstance(f, dict)}
        self.assertNotIn("", url_hosts, "a lock file with no url host")
        self.assertEqual(url_hosts & REDIRECT_HOSTS, set(), "a redirect target is also a lock file URL host")
        hosts = set(policy().get("hosts") or [])
        self.assertEqual(sorted(hosts - (url_hosts | REDIRECT_HOSTS)), [],
                         "docker/source-policy.json `hosts` lists a host no lock file URL or redirect uses (U8-10)")
        self.assertEqual(sorted((url_hosts | REDIRECT_HOSTS) - hosts), [],
                         "a lock file URL or redirect host is not in docker/source-policy.json `hosts`")

    def test_no_lock_problems_without_the_dropped_host(self):
        """U8c O-2: the committed lock still passes lock_problems against the
        policy with objects.githubusercontent.com removed (green before and
        after the drop: no lock file URL names it)."""
        narrow = policy()
        narrow["hosts"] = [h for h in narrow.get("hosts") or [] if h != "objects.githubusercontent.com"]
        problems = load_sbom_check().lock_problems(self._bytes().decode("utf-8"), narrow, fixture_docs(), ARCH)
        self.assertEqual(problems, [], "lock_problems on the committed lock with the narrowed policy")

    def test_every_needed_key_and_nothing_else(self):
        # 182 -> 183 in U7e: u7e/key-diff.txt l.6-8 (the lock re-run, u7e/lock-run-1.txt).
        # 183 -> 184 at the Q83 (a) re-lock 2026-11-02 (relock-20261102/fixture-derivation.txt).
        self.assertEqual(set(self._lock().get("components") or {}), set(FIXTURE_KEYS),
                         "the committed lock's keys are not the fixtures' 184 needed keys")

    def test_canonical_lf_and_format(self):
        raw = self._bytes()
        self.assertNotIn(b"\r", raw, "the lock is not LF-only")
        text = raw.decode("utf-8")
        self.assertEqual(text, load_sbom_check().lock_text(json.loads(text)), "the lock is not in canonical form")
        self.assertIs(type(self._lock().get("format")), int)
        self.assertEqual(self._lock()["format"], 1)

    def test_the_manual_neo4j_entry(self):
        e = (self._lock().get("components") or {}).get(NEO4J_KEY)
        self.assertIsInstance(e, dict, f"no {NEO4J_KEY} entry")
        assert isinstance(e, dict)
        self.assertEqual(e.get("origin"), "manual")
        self.assertEqual(len(e.get("files") or []), 1)
        f = e["files"][0]
        self.assertEqual((f.get("sha256"), f.get("size")), (NEO4J_SHA256, NEO4J_SIZE),
                         "the neo4j tarball is not security's second fetch")
        up = f.get("upstream") or {}
        self.assertEqual((up.get("alg"), up.get("value")), ("sha256", NEO4J_SHA256))
        self.assertTrue(str(up.get("from", "")).startswith("second fetch: security ")
                        and str(up.get("from", "")).endswith(", docs/evidence/platform-sbom/sources-provenance.md"),
                        up.get("from"))

    def test_the_sample(self):
        lock = self._lock()
        sample = load_sbom_check().sample_keys(lock, ARCH)
        self.assertEqual(sorted(k.split(":", 1)[0] for k in sample), sorted(KINDS), sample)
        self.assertEqual(len(sample), len(KINDS), "one key per kind present")

    def test_gitattributes_pins_lf(self):
        path = Path(GITATTRIBUTES)
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        self.assertIn(EOL_LINE, [ln.strip() for ln in lines], f".gitattributes has no `{EOL_LINE}` line")


if __name__ == "__main__":
    unittest.main()
