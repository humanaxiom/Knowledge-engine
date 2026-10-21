# audit-nt: review + security audit of PS-3.8 notices, I-OC1b-2, Q1, Q2

Verdict: **PASS / APPROVED**. No critical or high finding. One medium (licence compliance beyond ruling R4, for the human) and five lows, all non-blocking.

Scope: HEAD e3d3fed plus the working tree: `engine/notices.py`, `tests/test_engine_notices.py`, `scripts/bundle.sh`, `scripts/smoke.sh`, `NOTICE.md`, `licenses/{GPL,LGPL}-3.0.txt`, `.gitattributes`, `docs/quickstart.md`, `tests/{fake_docker,test_offline_bundle,test_offline_netprobe}.py`. I read the tester's and developer's newest handoff sections, `green-nt-verify-full.txt` (667 tests OK, skipped=8; mypy "no issues found in 19 source files"; notices.py 99%; offline_check PASS; verify full PASS) and `green-nt-real-third-party-notices.md`.
Raw output: `audit-nt-probes.txt` (P1 to P8, mutants M, secrets grep). Every ad-hoc `docker run` used `--network none --pull never` and its own `--label com.docker.compose.project=ke-sec-nt-*`, and none was left behind. HEAD, the index and tracked files were not touched.

## Confirmations
1. **notices.py.**
   - Imports are `re`, `sys`, `importlib.metadata` and `pathlib` only, with no socket or subprocess. The real ke-app image runs it under `--network none` with rc 0.
   - Exit codes: 0 prints the table; 1 means a package has no licence file (stdout empty, stderr names the package); 2 means it was given arguments. All three are tested. mypy --strict is clean (verify full).
   - It reads only METADATA and RECORD through importlib.metadata, and only `stat`s candidate files (`is_file`). It never reads a licence file's contents.
   - License-File values are handled as claimed: absolute paths, `../..` and `licenses/../../..` are all ignored (P7).
   - Exception: see L-NT2. RECORD entries and symlinks can still name a path outside site-packages.
2. **bundle.sh.**
   - The notices run is `docker run --rm --network none --pull never --label com.docker.compose.project=<project>-notices --entrypoint python <ke-app ref> -m engine.notices`. The project name passes an anchored check first.
   - The NOTICE.md and licenses checks, the vendor-row check and the generator all run before `mkdir "$out/images"`, so any refusal leaves --out empty and writes no record. This is tested by `_assert_nothing_written` (package and vendor cases) and holds in my probes.
   - P8 is 21 crafted NOTICE.md files run through the verbatim bundle.sh lines 190-223 and 290-293:
     - **No shell execution.** `$(...)`, backticks, `${IFS}` and `%s/%n/%q` all appear verbatim, and no `/tmp/pwned*` file was created.
     - **No break-out into another row.** Each line is one record, and a duplicate reference dies.
     - **Fails closed** for a missing row, an empty or tab-only licence, `Unknown`/`TBD`/`???`, an indented row, a short row, a reference with a prefix or suffix, a row in prose, a row for another digest, no NOTICE.md, and an empty LGPL text.
     - CRLF files parse correctly.
     - The weak spots are in L-NT3.
   - An image with no row fails, naming the reference (test plus mutant M2 killed).
3. **Licence texts.** I fetched both over HTTPS from gnu.org myself.
   - GPL sha256 is `3972dc97...6986` (35149 B) and LGPL is `e3a994d8...3118` (7652 B). Both are identical to the committed files and to the developer's recorded hashes.
   - `.gitattributes` `licenses/* -text`: a fresh repo with `core.autocrlf=true` round-trips both files byte-exact (`i/lf w/lf attr/-text`). The control without the attribute checks out CRLF and the hashes change (P2).
4. **Vendor licences at the pinned digests** (P3 to P6; each image ID equals its pinned digest).
   - **Phoenix** (fa28e9cd...): `arize_phoenix-20.22.0.dist-info/licenses/LICENSE` is "Elastic License 2.0 (ELv2)" (3794 B, sha256 1c5916f5...775f). `IP_NOTICE` says ELv2 plus 2 US patents. METADATA `License: Elastic-2.0`; the image label says `NOASSERTION`. **Elastic-2.0 confirmed.**
   - **Neo4j** (0a6e7aed...): Neo4j 5.26.32. `/var/lib/neo4j/LICENSE.txt` is "GNU GENERAL PUBLIC LICENSE Version 3" (Neo4j Sweden AB), and its GPL body matches `licenses/GPL-3.0.txt` apart from one leading space. The tag `5.26.32` exists on github.com/neo4j/neo4j, and its LICENSE.txt is GPLv3. **Confirmed.**
   - **Valkey** (081c2f5c...): v8.1.10. Upstream `COPYING` at 8.1.10 is two BSD-3-Clause grants (Valkey contributors; Redis Ltd. 2006-2020), and the image has no licence file. **Confirmed.**
   - Also confirmed: PostgreSQL 16.15 `License: PostgreSQL`; nginx 1.28.2 with an Apache-2.0 label and BSD-2 `COPYRIGHT`; psycopg and psycopg-binary are `LGPL-3.0-only`, and the sdist URL and sha256 match uv.lock.
5. **Requested mutants are all killed** (M, scratch copies, gates image):
   - M1 and M1b (the generator allows a missing licence) are killed by NoticesTest and 4 BundleNoticesTest cases.
   - M2 (bundle skips the vendor-row check) is killed by the `widget` case.
   - M3 (smoke drops the control label) is killed by the static check and 2 project cases.
   - Also killed: M4 (`--network none` dropped) and M7 (all License-File filters dropped).
6. **smoke.sh / quickstart.**
   - I-OC1b-2 is fixed: the control run carries `<project>-probe`.
   - Q2: the plain-words line is added.
   - Q1: the advice and `export COMPOSE_PROJECT_NAME` now come before `launch.sh`.
7. **Secrets.** A grep over the 1535-line diff plus the new files found 4 hits, all benign: quickstart prose, the test fixture `.env` (`local-secret`, which asserts .env is not shipped) and a test literal `/etc/passwd`. No profile path or SID appears in the new evidence.

## Findings
- **M-NT1 (medium; licence compliance, not security; non-blocking, for the human beyond ruling R4).** The bundle redistributes binaries whose licence conditions neither the image nor the bundle meets:
  - **Valkey, BSD-3-Clause.** Binary redistribution must reproduce the copyright notices, conditions and disclaimer. The image has no licence file and the bundle ships no copy (P5).
  - **GPL-2.0-only Alpine packages.** busybox, apk-tools and ssl_client sit in the valkey image and in ke-gateway's nginx-alpine base. The Debian GPL packages in the postgres, neo4j and ke-app bases are in the same position: no source offer.
  - **ke-app's own base is not mentioned.** CPython (PSF), the Debian layers and the `uv` binary in `/usr/local/bin` appear nowhere in NOTICE.md, although ke-gateway's base is covered.
  - **psycopg-binary's vendored native libraries** are unlisted: `psycopg_binary.libs` holds libpq, OpenSSL, krb5, libsasl2, libldap, and libcrypt and libkeyutils under LGPL-2.1. This is related to Q42.
  - Fix: ship Valkey's `COPYING` under `licenses/` and add a ke-app base paragraph. Raise one question for the human on OS-layer source offers.
- **L-NT1 (low; NOTICE.md wording that asserts more than the facts).**
  - Neo4j: "the corresponding source is at the URL given" claims GPLv3 section 6 compliance. Under 6(d) the distributor remains obligated when a third-party server hosts the source, and the image also holds Temurin JDK and Debian packages. Write "Upstream source: <url> (tag 5.26.32)".
  - Phoenix: the summary names two of ELv2's three limitations and leaves out circumventing licence-key functionality. List all three, or add "see the licence for all limitations".
  - "Knowledge Engine is ... the `ke-app` and `ke-gateway` images" is too broad, because the images contain third-party layers. Write "the code in this repository, built into ...".
  - The psycopg statement is accurate: LGPL-3.0-only, imported dynamically, sdist URL and hash. It would be complete with a pointer to the vendored libraries (M-NT1).
- **L-NT2 (low; path containment).**
  - Candidates taken from RECORD are not filtered for `..`. A RECORD entry `d1-1.0.dist-info/licenses/../../../outside/NOT_A_LICENCE`, with `licenses/` present, is listed as a licence file. A symlinked `licenses/LICENSE` pointing outside site-packages is also accepted (P7).
  - Only `stat` runs, never a read, and the image is built from locked wheels, so the impact is limited to the "has a licence file" check being satisfied by a non-licence path. The docstring's "no files outside the interpreter's own sys.path" is still inaccurate.
  - Fix: apply the absolute/`..` filter to every candidate, and require `Path(locate_file(p)).resolve()` to lie under `locate_file("").resolve()` (or reject symlinks).
  - Test gap: M6 (the License-File `..` filter removed) survives, because the fixture's `../../outside` resolves to a path that does not exist.
- **L-NT3 (low; vendor-table parse robustness).** These issues stay within a row:
  - A unit-separator byte (0x1F) inside a cell shifts fields, so an empty Licence cell is satisfied by text from the Image cell (case 07), and a 0x1F in the Reference cell still keys the row (case 08).
  - A no-break-space licence is accepted (case 17).
  - A pipe in a cell is accepted, with NF>7 silently shifting Source and Note (case 06).
  - "see LICENSE" is accepted, while the tests' `_PLACEHOLDER_LICENCE` treats `see .*` as a placeholder.
  - Fix: in awk, refuse a row unless NF==7 and it has no `[\001-\037\177]` byte; require an SPDX-like licence pattern; add the cases as tests.
- **L-NT4 (low; test gaps, surviving mutants).**
  - M2c: the placeholder regex removed, so `Unknown` is accepted.
  - M5: the notices run's `--label` removed. The tester flagged this as untested.
  - M6: see L-NT2.
  - M8c: the generator-header check loosened to `"|"*`.
  - None is caught by the 667-test suite, apart from shellcheck on non-lint-clean forms.
- **L-NT5 (low; L-7 parity).** `cp -R -- licenses` ships any untracked or ignored file dropped into `licenses/`, and the manifest then lists it. config/ uses `git ls-files` for this reason. Copy `git ls-files -z -- licenses` instead.

## Info
- I-NT1: the notices run has no `--read-only`, `--cap-drop ALL` or timeout. It runs as image USER `ke` under `--network none`, so this is hardening only.
- I-NT2: the labels `<project>-notices` and `<project>-probe` would be seen by a real compose project of that exact name.
- I-NT3: quickstart step 5 says "Every install ... shares the compose project `knowledge-engine`" just before exporting `ke-site-a`; "by default" would read better. The Windows line (`scripts\launch.ps1`) has no `$env:COMPOSE_PROJECT_NAME` equivalent.
- I-NT4: NOTICE.md is not `-text`, so a Windows checkout gets CRLF. The parse handles it (case 10), and the bundle ships the working-tree bytes.
