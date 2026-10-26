# platform-sbom U7b rework round 1 review (reviewer, 2026-10-25)

Scope: the U7b GREEN targets against the working tree for scripts/sources_resolve.py,
scripts/sources_lock.sh and scripts/sbom_check.py (each equals `u7b/r1-target-*`); the
compose file is unchanged. Tests: ReworkR1* in tests/test_sources_resolve.py and
tests/test_sources_lock.py, and the resolver model in tests/fake_docker.py. Rulings:
design-notes "U7b rework round 1", l.1444-1563.

Verdict: **APPROVED.** No blocking findings.

Evidence:
- `u7b/reviewer-r1-controls.txt`: `r1_controls.py --base repo` re-run in the gates image
  (ke-reviewer-u7b) after the tester fixed the harness: 71 rows, 66 must-fail,
  5 must-pass, 0 unexpected.
- `u7b/reviewer-r1-probes.txt`, from `u7b/reviewer-probes/probe_u7b_r1.py`: my round-0
  inputs re-run, plus new ones.
- `u7b/r1-green-verify-fast.txt`: 1016 tests, OK.

## Closed
- **B1.** Each round-0 input now gives exactly one line,
  `sources_lock: FAIL (resolve: <key>: <host>: <why>: <url>; the lock is unchanged)`,
  exit 1, and no lock.new.json:
  - a mid-body `TimeoutError` gives `timeout after 60 s`;
  - mid-body `IncompleteRead` and `ConnectionResetError`;
  - an OPENER that raises `InvalidURL` or `BadStatusLine`.

  `_guarded` enforces the 600 s per-file wall-clock deadline, started in `fetch` so it
  covers the redirects. It also enforces the 4 GiB cap, checked before a chunk past the
  cap is hashed. `main` turns any other exception into the one FAIL line (N6:
  writing `/out`, wrong-typed needs). Real-opener error bodies are read to 1 MiB and
  dropped (I-1).
- **B2.** `lock-check --pending-neo4j` decides on the full in-memory list
  (`only_neo4j_misses`), and the script branches on exit 0/3/other only. My round-0
  input (79 problems, the first 20 all neo4j) now gives False, so exit 1. The
  end-to-end test `test_a_truncated_neo4j_list_is_not_pending` has the script exit 1
  with the lock byte-identical.
- **N1.** Each hop is refused for:
  - a non-printable character, checked on the raw Location before `urljoin`, which
    would drop tabs;
  - a non-literal `https://`;
  - userinfo, a port or a fragment;
  - a path that is not plain, with no `%` after the first request.

  A query is allowed. My port and userinfo redirects are refused, and so is the tab.
  pypi.org is allowed only on hop 0 of the JSON request (L-2), and keys are validated
  before any URL is built (I-3).
- **N2-N4.**
  - jq, git and docker are checked before anything else.
  - The EXIT trap removes the `docker/` temp file (tested with failing `chmod` and `mv`).
  - Exactly the six images, or a named FAIL.
  - The ke-neo4j tar arg is derived from the name list.
  - `chmod 0644` runs before the `mv` (L-5).
  - `$work/sboms/tmp` is created (the A34 defect).
- **Happy-path test** (`ReworkR1LockScriptRunTest`). With fake docker running the real
  resolver, it asserts:
  - six saves and six sbom runs, then lock-needs, resolve and lock-check in that order;
  - `--pending-neo4j` is passed and the sbom tmp dir exists;
  - exit 0 with the canonical lock written 0644, no temp left and `git diff --stat`;
  - exit 3 with a neo4j candidate printed.

## Nits (non-blocking; for U7c first rows)
- **R1-N1. The pypi JSON sdist URL is server-supplied but fetched as a first request,
  so it is exempt from the path-% rule** (scripts/sources_resolve.py l.390-391:
  `stream(sd["url"], allow)` runs hop 0 with `first=True`). Ruling 3 exempts only the
  fixed request templates of the resolver.
  - Input: pypi.org JSON for `pypi:pandas@2.3.3` whose sdist url is
    `https://files.pythonhosted.org/packages/33/01/%2e%2e/%2e%2e/<60 d>/pandas-2.3.3.tar.gz`.
    The resolver requests it. The produced entry is then refused by the U7a lock check
    (`url path is not a plain path`), so no lock is written, and the request stays on
    files.pythonhosted.org.
  - Fix (cheap): before streaming, check the JSON url with the hop rules (`first=False`)
    or against the exact U7a pypi path `/packages/<2>/<2>/<60>/<name>`.
- **R1-N2.** `six=(...)` in sources_lock.sh is a literal list beside the compose-derived
  names. It works as ruling 6's "exactly those six names", but a seventh bundled image
  would need both bundle.sh and this script edited. Noted.

## Checked
- `fetch` rules:
  - hop counting allows 5 redirects;
  - a Location with a scheme other than a literal `https://` is refused before `urljoin`
    lower-cases it;
  - `//host` and backslash Locations are refused;
  - the `first_allow` precedence is right (`(allow | first) if hop == 0 else allow`).
- `only_neo4j_misses` matches lines by exact text, and every miss line carries its key,
  so no other problem can match. A stale manual neo4j entry is not a miss, so it exits 1.
- The resolver still writes only `/out/lock.new.json`, through a temp file in `/out`.
- `unlicensed_report`, the classifier and `exempt_matches` are untouched.
- PS-1.2 holds.
- Observability: a maintainer tool; no spans needed.
