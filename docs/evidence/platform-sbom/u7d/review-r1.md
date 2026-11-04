# platform-sbom U7d rework round 1 + the lock: review (reviewer, 2026-10-26)

Scope:
- The diffs of `u7d/target-<file>` against scripts/ for sources_resolve.py, sbom_check.py
  and sources_lock.sh; each equals `u7d/r1-target-*` byte for byte.
- Tests ReworkR1U7d* and tests/test_sources_lock_committed.py.
- The uncommitted `docker/sources.lock.json`, read only. Runs: lock-run-3 exit 3,
  lock-run-4 exit 0.
- Rulings: design-notes "U7d rework round 1" l.2492-2721.

Verdict: **APPROVED.** No blocking findings in the code, the rule changes or the lock.

Two conditions sit outside this verdict and gate the commit:
- the item-13 scanner exemption is pending, so verify is red on one hit;
- the third Neo4j fetch (item 7) is still with the human.

Evidence:
- Controls re-run with `--base repo` in the gates image (ke-reviewer-u7d), each with 0
  unexpected:
  - `u7d/reviewer-r1_controls.txt`: 33 rows, 29 must-fail, 4 must-pass;
  - `u7d/reviewer-r1i10_controls.txt`: 35 rows, 31 must-fail, 4 must-pass;
  - `u7d/reviewer-s7_controls.txt`: 31 rows, 24 must-fail, 7 must-pass.
- `u7d/reviewer-r1-probes.txt`, from `reviewer-probes/probe_lock.py` and
  `probe_u7d_r1.py`.
- On the host, tests.test_sources_lock_committed gives 7 OK. RepositoryScanTest fails on
  `docker/sources.lock.json:8760` value 8080 (item 13).

## Closed
- **B1.** `_default_opener` unwraps a URLError that carries an exception reason. A
  TimeoutError reason is then retried by `_transport`; SSL errors, ConnectionRefused,
  other OSErrors and string reasons are not. The tests stub `urllib.request.build_opener`
  against the real opener (ReworkR1U7dUrlErrorTest), as ruled. My loopback case maps to
  TimeoutError now.
- **B2.** `docker save -o` through `hostpath` is pinned by a cygpath shim row
  (`test_docker_save_gets_the_host_path`). The lesson is recorded as items 2 and 9.
- **N1.** `lock_problems` binds a pgdg `suite` to `pgdg_suite(distro)`, the function
  lock-needs shares. Mixed suites fail (`packages derive suites`); a mismatch fails with
  the ruled text.
- **N2.** `--evidence-dir` is required, must be a writable directory, and is resolved
  from the repo root. The InRelease is copied before the move. A link, a non-regular
  file or a failed copy fails with the lock unchanged (security L-1). Nothing is
  hard-coded to u7d any more.

## Rule changes, read as rules
- **Item 8, symlinks (resolver side; links are never locked).**
  - A mode 120000 blob is set aside. Its target comes from the files-API metadata:
    base64 with validate, size 1-1024, content_sha256 bound, ASCII with no NUL, CR or
    LF.
  - The target must be one safe segment naming a regular blob in the same directory, and
    the link must not be named in sha512sums. It is then skipped, with one key-prefixed
    information line.
  - Fail closed: a chain, a tree, `..`, `/`, absolute or missing targets, and bad base64.
  - A link named APKBUILD leaves no top-level APKBUILD, so it fails "no APKBUILD".
  - I found no input that passes but should not.
- **Item 10, a leading underscore.** One pattern on both sides, asserted equal. A leading
  `-` or `.` and `..` anywhere are still refused. A lone `_` is a legal name, which is
  harmless. The real `_apk`, `__NR_riscv_hwprobe.patch` and `__stack_chk_fail_local.c`
  are in the lock.
- **Item 12, size 0.** Allowed only for apk files at the GitLab API raw form, with the
  empty SHA-256 (and the empty SHA-512 when the alg is sha512). Distfiles and every other
  kind keep 1 byte to 4 GiB. The lock holds no zero-size file. See R1-N1.

## The lock (read only)
- **Shape.** 472945 bytes, LF only, canonical (lock_text of the parsed text equals the
  text), format 1.
- **Keys.** 182, equal to FIXTURE_KEYS: deb 152, pgdg 3, apk 19, neo4j 1, temurin 1,
  maven 1, pypi 5. All arches amd64, with 181 generated and 1 manual.
- **`lock_problems` on the text, with the policy and the six fixture docs, for amd64,
  is empty.**
- **Files.** 872 files, 1327035158 bytes (about 1.33 GB, inside the 1-2.5 GB of PSC-15).
  Hosts: snapshot 491, gitlab 344, distfiles 21, apt-archive 8, pythonhosted 5,
  github 2, maven 1.
- **URL forms.**
  - Queries appear only on the 344 apk GitLab API raw urls.
  - `%` appears only there and in the one temurin `%2B`.
  - deb uses `/file/<sha1>`, pgdg the pool path, and pypi
    `/packages/<2>/<2>/<60>/<name>`.
- **Upstream `from` texts,** all as designed:
  - `<dsc> Checksums-Sha256`: 344;
  - `APKBUILD sha512sums at <commit>`: 329;
  - `snapshot.debian.org mr/package fileinfo`: 152;
  - `gitlab files API content_sha256 at <commit>`: 36;
  - `apt-archive.postgresql.org bookworm-pgdg-archive Sources`: 3;
  - `uv.lock`: 2;
  - `pypi.org JSON <name> <ver>`: 3;
  - one each for the maven `.sha1`, the temurin `.sha256.txt` and the neo4j second fetch.
- **Algorithms.** deb sha1 for the `.dsc` and sha256 for the others; pgdg all sha256;
  apk sha256 (36) and sha512 (329); maven sha1; the rest sha256.
- **Manual neo4j entry.** One file `5.26.32.tar.gz` with sha256 182ae2e5...91e3 and
  20907800 bytes, equal to the second fetch by security in sources-provenance.md. The
  `from` is the second-fetch form.
- **Temurin.** sha256 573057d0...8234, equal to the sidecar security recorded.
- **pypi.** psycopg and psycopg-c have url, sha256 and size equal to the uv.lock sdist
  (checked independently).
- **pgdg.** All three entries have suite `bookworm-pgdg-archive`; each has its `.dsc`
  plus orig and debian (or native) tarballs.
- **The symlink.** alpine-baselayout has `.post-install` locked and no `.post-upgrade`
  (the link is skipped).
- **Sample.** One key per kind, seven: alpine-baselayout 3.7.1-r8, hostname, jaxb-api,
  neo4j, postgresql-common, autocommand, temurin.
- **Run evidence.** lock-run-3 exits 3, then lock-run-4 exits 0. drift.txt shows 182
  against 182, none added or missing. No profile paths in the run or drift evidence.
- **The committed-lock test.** It asserts:
  - lock_problems is empty with the committed policy and the fixtures;
  - the keys equal the 182;
  - LF-only canonical form and format 1;
  - the manual neo4j sha256, size, alg/value and `from` form;
  - one sample key per kind;
  - the `.gitattributes` eol=lf line.

  `.gitattributes` holds it.

## Nits (non-blocking)
- **R1-N1.** Item 12 lets the APKBUILD itself be empty. Input: the test fixture apk
  entry with the APKBUILD at size 0, sha256 and value set to the empty hash, still
  `gitlab files API content_sha256 at <commit>`. It passes `lock_problems`. The resolver
  cannot produce this, since an empty APKBUILD has no pkgver. One clause would close it:
  "the APKBUILD has size > 0".
- **R1-N2.** S6 asked drift.txt to record the package-count differences inside shared
  keys (the known neo4j:neo4j@5.26.32 72 fresh against 73 in the fixture). drift.txt
  says they were not compared because the run SBOMs are removed. The key-set check,
  which is the gate, is present. The count is information only and already recorded
  from A34. Note it, or keep the SBOMs of one run.
- **R1-N3 (gates, not findings).** The commit waits on the item-13 scanner exemption
  (verify is red now) and on the third Neo4j fetch (item 7, human).
- **R1-N4 (optional).** The committed-lock test pins neo4j to provenance values. The
  temurin sidecar sha256 and the ke-app pypi entries against uv.lock are equally
  checkable without network. I checked them by hand: they are equal.
