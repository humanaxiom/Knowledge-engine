# platform-sbom U4 review (reviewer, 2026-10-23)

Scope: `git diff 464fa11` plus untracked `docker/source-policy.json`,
`tests/sbom_support.py`, `tests/test_sbom_obligations.py` and `u4/`.
Read: the handoff U4 sections, PSC-22 and PSC-14's U4 line, design-notes N1
(amendment U4), N7, N8, N8a, N10 and N15, and the U3 review N1-N9.

**Verdict: CHANGES REQUESTED** (2 blocking, both small; 8 nits).

## What holds
- `unlicensed_report` follows N8's exact rule: a field is missing when it is
  absent, null, not a string, or exactly "", NONE or NOASSERTION (case-
  sensitive, no strip). `licenseInfoFromFiles` that is not a list, or whose
  entries are all missing, counts as missing. The DESCRIBES root is excluded
  by relationship, rows are counted per purl type, and no-purl rows go under
  `none`. The tester's oracle is independent and the wrong-type cases are
  exercised (a-g).
- `always_matches`: a versionless purl matches by an exact split at "@", so
  psycopg does not match psycopg-c and busybox does not match busyboxx.
  `upstream=` matches the qualifier name before any "@". Reviewer probe:
  all 16 committed `always` entries match at least one package in the real
  U3 SBOMs (`u3/sboms/*.pkgs.tsv`). This includes pkg:generic/oracle/openjdk,
  pkg:maven/org.neo4j/neo4j@5.26.32, and upstream=openldap/cyrus-sasl2 in
  ke-app. So U9 will not trip on a dead entry.
- `drift_problems` and `psycopg_problems`:
  - the deb name sets are subtracted by name;
  - pip is matched on PEP 503-normalised names;
  - CPython must be exactly one pkg:generic/python version, and each
    licence file's line 1 must equal it (all three files read "CPython
    3.12.15:");
  - libpq5 must be at the pin with upstream postgresql-<major>;
  - psycopg-c must be at its lock version, and psycopg-binary must be absent.
- `added_packages` uses ast and never imports the module. A non-literal value
  or a non-frozenset call raises ValueError.
- uv.lock is read as name -> set of versions (N7). The installed version must
  be in the set and listed in the SBOM, and a version outside the set fails.
  This is tested.
- `offline_check.sh`:
  - The base is pulled once by name:tag@sha256 (regex pinned, no leading
    "-"). The pull comes after the generator pull and before bundle.sh,
    fails closed, and is not retried.
  - The drift step runs after bundle.sh and before dind, in a `mktemp -d`
    under dist/, which is in df_paths. Its order is: `docker save` (Git Bash
    path conversion kept), then the generator run (--pull never, no -p,
    inheriting the offline project, MSYS_NO_PATHCONV), then the checker in
    the bundled ke-app image (no network, read-only, cap-drop ALL, --pull
    never, ro mounts).
  - Every step ends in `|| die`, under `set -euo pipefail`. The EXIT trap
    removes the work dir.
- `bundle.sh`: the report is printed to stderr per image, after the document
  is written. The work dir is .ke-sbom.* in dirname(--out), outside --out
  and never in the manifest. The N2 comment is fixed.
- `docker/source-policy.json` matches PSC-22 and U4 rulings 1-2:
  - busybox, apk-tools and ssl_client in valkey and ke-gateway;
  - Temurin, Neo4j and glibc in neo4j;
  - psycopg, psycopg-c, glibc, upstream=openldap and upstream=cyrus-sasl2
    in ke-app only;
  - glibc in postgres and phoenix.
  The postgres openldap/sasl entries are left to the orchestrator, as the
  architect flagged.
- Tests were not weakened. The one re-targeted order assertion
  (test_offline_check_pulls_sbom_generator_before_bundle) gains "pull base"
  and "drift" and is documented. The fake docker's `save` now refuses an
  unknown image, which is stricter.
- Evidence:
  - RED (u4/red-verify-fast.txt): 18 distinct tests fail, all U4.
  - Reach PASS (u4/target-reach-verify-fast.txt).
  - GREEN fast: 832 OK. GREEN full: 832 + 15 OK, offline_check PASS 192 s.
    The 8 unit skips are the existing Windows-ACL ones, and no U4 test is
    skipped.
  - u4/real-run-report.txt shows the real per-image report and the drift
    success line.
- Observability: no agent loop, model call, retrieval or tool call was added,
  so no span is needed.

## Blocking
- **B1 (U3 carry N5 / ruling 5 item 6 not achieved).**
  `XDG_CACHE_HOME: /tmp/cache` does nothing. Every generator run in
  u4/green-verify-full.txt (l. 2046-2125, 7 runs including the base run)
  still warns "mkdir /tmp/cache: permission denied". The compose comment
  ("syft's cache on the tmpfs, not /.cache") is therefore false, and the
  warning just moved. Fix with option (a) below. Test first: sbom's /tmp
  tmpfs entry carries mode=1777, as test_gate_services_tmp_is_exec_tmpfs
  asserts for the gate services (PS-3.5 precedent, docker-compose.yml
  l. 52). Then a real run must show no cache warning.
- **B2 (U3 carry N1 not closed).** The U3 review said to drop the
  sbom_check.py docstring line "(tester's reach target ...; the developer
  owns the real file)". It was rewritten instead: l. 30 now reads "(tester's
  U4 reach target; the developer owns the real file)". Drop it. It is a
  tester's note in a shipped script.

## Cache recommendation: (a)
Add mode=1777 to the tmpfs: `tmpfs: ["/tmp:mode=1777"]`. Do not add exec.
- The U2 hardening test allows it: test_image_scan._tmpfs_targets splits at
  ":", so "tmpfs exactly ['/tmp']" still holds.
- The repo already does this for its non-root gate services (PS-3.5).
- The container runs a single uid with a read-only root, no network and no
  capabilities. A world-writable sticky tmpfs that dies with the `run --rm`
  container exposes nothing, and with every remote lookup off the cache
  stays near-empty.
- It makes the mode explicit on every engine (Docker Desktop shows it is not
  1777 there), and it keeps the cache off /out (I-2 and ADR-KE-013 am. 1
  D1).
- Reject (c): a setting that has no effect, with a comment that says it does,
  is dead config.
- (b) is the fallback only if (a) still warns on a real run. In that case,
  drop the key and record the warning as benign in N8a.

## Nits
- **N1** drift(): the psycopg-c version is `locked[0] if len(locked) == 1
  else "?"`. A forked lock (N7 now accepts one) fails with "does not list
  psycopg-c ?". Pass the locked set and require a listed version in it. This
  fails closed today, so it is a nit.
- **N2** psycopg_problems compares the upstream qualifier exactly, while
  always_matches splits it at "@". Probe: upstream=postgresql-15@15.19-0+
  deb12u1 (syft's form when the source version differs) fails. It fails
  closed, but use the same split for consistency.
- **N3** added_packages: ast.parse SyntaxError and literal_eval TypeError
  (for example frozenset({('a', ['b'])})) escape as tracebacks. drift()
  catches only OSError, ValueError and KeyError. The run still fails closed,
  but the interface says ValueError, so wrap both.
- **N4** unlicensed_report raises on a non-list externalRefs (TypeError),
  which validate does not guard. _purl turns a None locator into the string
  "None". syft never writes either, and finish exits non-zero (fails
  closed). The tester's docstring says "it never raises", so guard
  externalRefs with an isinstance check, like licenseInfoFromFiles.
- **N5 (architect)** The N1 amendment says the floor probe "is dirname(--out)
  or one of its ancestors". That is false when --out already exists, which
  is allowed if it is empty. Then the probe is --out itself. If --out is an
  empty mount point (an exFAT stick, for example), the 7 GiB check measures
  the stick while the unpack lands on dirname(--out)'s filesystem. This
  fails closed, with syft's generic error (the N6 failure mode). Fix: also
  measure dirname(--out), or reword the claim.
- **N6** Drift checker output (the orchestrator's question): per-check lines
  are not needed for correctness. RED, the controls and the fail-path tests
  prove that each check bites, and each failure names its problem. Still,
  have drift print one summary line on success, so the evidence records
  what was compared without a re-run: the added set, "no pip", the CPython
  version and the 3 files, libpq5 pin/upstream, and psycopg-c version with
  no psycopg-binary.
- **N7** The offline checker `docker run` has no --label. bundle.sh's checker
  carries com.docker.compose.project=<project>-sbomcheck (N3). --rm covers
  the normal path, but label it for the same inventory.
- **N8 (carry, U3 N3 second bullet, still open)** sbom_cleanup's `down`
  passes raw (non-hostpath) KE_SBOM_*. That is harmless because `down` binds
  nothing, but neither the code nor N1's amendment says so. Add a one-line
  comment.

## For the next roles
- Linux engine unproven (U3 N8 carries): the base `docker save
  name:tag@digest` and the tmpfs mode have only run on Docker Desktop
  (containerd store). The architect asked for proof on both stores. The PR's
  CI run on ubuntu-24.04 is the first classic-store run, so read its
  offline_check output for the save and the cache warning.
- Security: u4/real-run-report.txt is the PSC-22 list to review. phoenix's
  unlicensed deb rows include GCC runtime libs (libgcc-s1, libstdc++6,
  libgomp1: GPL-3.0 with the runtime exception), libncursesw6 and
  python3.13-venv. postgres has 3 golang rows (gosu).

## U3 carry list status
| U3 nit | Status |
|---|---|
| N1 | open (B2) |
| N2 | closed |
| N3 | closed (bullet 2 is N8 here) |
| N4 | closed (3 tests) |
| N5 / ruling 5 item 6 | open (B1) |
| N6 | closed (claim caveat N5 here) |
| N7 | closed (with N1 here) |
| N8 | carries to CI |
| N9 | closed (203 control rows) |

## Controls re-run (reviewer)
`u4_controls.py --base repo` in the gates image (ke-gates:wt-33a132fbfdd7,
no build, project ke-review-u4): **203 rows, 178 must-fail, 25 must-pass,
0 unexpected, exit 0**. Full output: u4/review-controls-base-repo.txt.
Reviewer edge probes (scratch script, repository untouched) are summarised
in N2-N4 above.

# Re-check after rework round 1 (reviewer, 2026-10-23)

Scope: `git diff 464fa11` plus the untracked files. The repo files equal the
`u4/r1-target-*` files byte for byte, except bundle.sh, which adds one line:
the N8 comment above `sbom_cleanup`.

**Verdict: APPROVED** (0 blocking; 3 nits; 1 info for security).

## Round-1 findings
- **B1 closed.**
  - Compose has `tmpfs: ["/tmp:mode=1777"]` with no exec, and
    XDG_CACHE_HOME is kept.
  - Tests:
    - `test_sbom_tmp_tmpfs_is_mode_1777_not_exec` (it re-asserts the U2
      hardening pin);
    - `test_bundle_syft_runs_print_no_cache_warning`;
    - the offline B1 subtest;
    - the fake's cache model is controlled by
      `test_fake_syft_models_the_cache_warning`.
  - The real full run has 0 "unable to get filesystem cache" lines. The U4
    GREEN run had 7 (l. 2046-2125).
- **B2 closed.** The tester note is gone, and the docstring now documents
  `drift`.
- **N1 closed.** drift passes the locked set. Tested with a forked lock and a
  "neither listed" control.
- **N2 closed.** The upstream qualifier is split at "@". Controls:
  postgresql-(major+1), postgresql-(major)0, and a leading "@".
- **N3 closed.** SyntaxError, TypeError and RecursionError become ValueError.
  The CLI exits 1 with no traceback (tested).
- **N4 closed.** `_purl` guards a non-list externalRefs and a non-string
  locator. Tested with 5, a dict and None.
- **N5 closed.** `check_floor` runs on `--out` and on `dirname(--out)`, each
  at its nearest existing ancestor, and the second is skipped on the same
  probe. 4 tests: the parent refused (named), `--out` refused, both fit, and
  one df when `--out` is absent. The N1 U4 amendment claim is reworded.
- **N6 closed.** One `drift: ok:` line (r1-green-verify-full.txt l. 2203).
- **N7 closed.** `--label com.docker.compose.project=${project}-sbomcheck`,
  tested.
- **N8 closed.** The comment is added.

## Security findings
- **H-1.** `_hash_only` follows N8 word for word:
  - it splits on `[\s()]+`;
  - it drops AND, OR and WITH in any case, plus the token after WITH;
  - it needs at least one id, and every id must fullmatch
    `LicenseRef-[0-9a-f]{64}`;
  - it applies to both expression fields and to each licenseInfoFromFiles
    entry.

  The test oracle `hash_only` (l. 207) is independent. Rows cover parens,
  lower-case operators, WITH, the files field, and the near-misses (mixed,
  upper-case hex, 63, 65 and 16 hex). Reviewer probes: "WITH <hash>" alone
  and "MIT AND <hash>" are not missing; "<hash> OR <hash>" is.

  The marker "(unidentified licence text)" is pinned:
  - as `UNIDENTIFIED` in the test (l. 1038);
  - `marker_problems` checks every line both ways;
  - the code's constant is identical;
  - the real run marks 59 rows, which equals security's 59.
- **M-1, M-2 and L-1.** All 25 `always` entries (16 old and 9 new) match at
  least one package in `tests/fixtures/sbom-u3/` (reviewer probe, per entry):

  | Match | Rows |
  |---|---|
  | `upstream=gcc-12` | 3 in ke-app, 3 in postgres |
  | `upstream=gcc-14` | 3 in neo4j, 4 in phoenix (libgomp1) |
  | jrt-fs | 1 in neo4j |
  | `upstream=busybox` | busybox-binsh and ssl_client, in valkey and ke-gateway |
  | `upstream=apk-tools` | libapk, in valkey and ke-gateway |

  The test also fails an entry that matches too widely: among the maven
  rows, only neo4j and jrt-fs may match.

  Fixtures:
  - The 6 fixtures are cmp-identical to `u3/sboms/*.pkgs.tsv`.
  - Their `git hash-object` equals the committed U3 blobs at 464fa11, so
    they commit byte-identical.
  - No test reads docs/evidence: in test_sbom_obligations.py and
    sbom_support.py the path appears only in comments.
- **L-3.** `_clean` escapes C0 and C1 as `\xNN` in each report row's purl,
  SPDXID and name. The image name is checked by NAME_RE, and the type keys
  are limited to `[a-z0-9.+-]`. A unit test and a bundle.sh end-to-end test
  cover ESC, CSI 0x9b and a forged newline.

## Evidence
- RED (r1-red-verify-fast.txt): 851 tests, 16 distinct failing (29 entries),
  all `ReworkR1*`.
- Reach (r1-target-reach-verify-fast.txt): PASS (851).
- GREEN fast: 851 OK (8 skipped: the existing Windows-ACL tests).
- GREEN full: 851 + 15 OK, offline_check PASS in 192 s, verify full PASS in
  937 s. 0 cache warnings, and the drift summary line is at l. 2203.
- Counts (full run l. 2071-2193 and r1-real-run-report.txt): ke-app 19,
  ke-gateway 0, neo4j 28, phoenix 35, postgres 25, valkey 1. These equal
  security's figures and r1-real-counts.txt.
- No test or assertion was removed. The fake docker only gains a cache
  model, the `save` refusal and per-run modes.

## Controls (reviewer re-run in ke-gates:wt-33a132fbfdd7, no build)
- `r1_controls.py --base repo`: **61 rows (59 must-fail, 2 must-pass), 0
  unexpected, exit 0**. No anchor needed adapting. Output:
  `u4/review-r1-controls-base-repo.txt`.
- `u4_controls.py --base repo` (the round-0 set, 203 rows) aborts on a
  stale anchor: `if isinstance(raw, list) else []` now occurs twice in
  sbom_check.py. Output: `u4/review-r1-u4controls-base-repo.txt`. This is
  nit R3. Those tests are green, and the r1 set covers the changed lines.

## Plan and design docs
These all agree with the code:
- the PSC-22 amendments (H-1, always, L-3);
- N8 "Hash-only ids";
- N10's U4-rework table, which is exactly the 9 new entries;
- the "N1 amendment, U4 rework" (tmpfs, the floor on both paths, the same
  message form);
- the reworded N1 U4 amendment;
- the ADR-KE-016 point 8 and tmpfs lines.

## Nits (optional; none blocks)
- **R1, traceability.** PSC-22 names
  `[unit: test_unlicensed_report_escapes_control_characters]` and says
  `test_unlicensed_packages_are_reported` "gains" the hash row. The tests are
  `test_report_lines_escape_control_characters` and
  `test_hash_only_licences_count_as_unlicensed`. Either rename the tests or
  amend PSC-22. U0 precedent: the requirements' names win.
- **R2, escaping beyond PSC-22's letter.** This is the same as security
  L-5, which is carried to U5. `_named` unquotes purl names, so a `%1b`
  reaches the drift and psycopg problem lines as a raw ESC. validate prints
  an SPDXID that SPDXID_RE accepts with a trailing newline, because `$`
  matches before a final newline (U3 code). Both cases fail closed, and
  neither is the bundle.sh report.
- **R3, stale controls.** Make the `u4_controls.py` anchor unique, or mark
  the round-0 set as superseded by `r1_controls.py`, as was done for U3 N9.

## Info for security
`_clean` covers C0 and C1 only, as PSC-22 defines it. U+202E (bidi
override) and U+2028 pass through, and a literal `\x1b` in a name reads the
same as an escaped ESC.

## Still open (not review gates)
- The A34 re-run of steps 2b and 3b after the compose change.
- The Linux classic-store proof (the base `docker save` by digest, and the
  tmpfs mode), on the PR's CI run.
