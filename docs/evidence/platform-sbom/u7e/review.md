# platform-sbom U7e: reviewer (2026-10-28)

Verdict: **CHANGES REQUESTED**. Two blocking findings, both docs/evidence only;
no code or test change is required. The code and test diff is sound and is
otherwise approved. Re-review is limited to B-1 and B-2.

Diff read: `git diff 45411ae -- docker/ licenses/ NOTICE.md tests/ docs/requirements.md docs/architecture.md`
(16 files, +466/-150). Evidence cross-read: u7e/key-diff.txt, fixture-diff.txt,
base-dpkg-diff.txt, tester-repin-verify-full.txt (Ran 1110 OK skipped=8; integration
OK skipped=5; scan l.2083-2367 done; drift l.2514 `CPython 3.12.16 (3 licence files)`;
l.2515 pulls the new digest; `verify full: PASS (1152s)`), design-notes l.422-544,
requirements PSC-27 l.4378-4520.

Local sanity (not a gate): `uv run python -m unittest tests.test_psycopg_c
tests.test_notice_ke_app tests.test_sbom_obligations.DriftLogicTest
tests.test_sources_lock_committed` on the Windows host: every U7e target and
re-pinned test passes; the only failures are test_psycopg_c.SmokePsycopgTest
(bash smoke script run outside the gate container, host-environment), untouched by U7e.

## 1. Design conformance (R1-R4)

- R1: 3 python FROM lines (app.Dockerfile l.13, l.45; gates.Dockerfile l.9) and
  NOTICE.md l.74 = `...6dd8b6da...9753`, byte-equal. No libssl/openssl pin, no
  `ARG OPENSSL_VERSION`; the runtime apt RUN is unchanged. OK.
- R2: licence files change in header lines only (HACL/KaRaMeL l.1-4,
  incorporated l.1-2); `Source sha256` of license.rst unchanged (security: bodies
  byte-identical). NOTICE.md l.122-134 -> 3.12.16 URLs. All LF (`git ls-files --eol`
  i/lf w/lf; licenses are `-text`). OK.
- R3: libpq5 pin unchanged (15.19-0+deb12u1), ADDED_PACKAGES unchanged; drift
  line in full confirms. OK.
- R4: whole ke-app fixture replaced; 6 differing rows, each mapped in
  fixture-diff.txt to base-dpkg-diff.txt or the CPython change or the image-root
  digest. Lock: +openssl~u2, +ca-certificates~u2, -ca-certificates~u1 (183 keys);
  the new entries are tool shape (snapshot /file/<sha1>, .dsc sha1 upstream,
  Checksums-Sha256 upstream), security re-fetched both .dsc; openssl~u1 kept for
  postgres; tzdata has no key (public domain). No unexplained key. OK.

## 2. RED tests

- `ruled_base_problems` / `test_python_bases_are_the_ruled_digest`
  (test_psycopg_c.py l.571-583, l.1170-1198): counts per file (2/1) and byte-equality;
  regex anchors `python` at start or after `/`, so registry-prefixed refs are caught
  and `mypython` is not. 8 controls each fail on a distinct defect (old digest, each
  of the three lines unmoved, tag only, registry-prefixed other digest, extra stage,
  lost stage). Sound.
- `release_licence_problems` / `release_notice_problems`
  (test_notice_ke_app.py l.772-820; controls from l.1590 and l.1738): exact line 1
  prefix with `: `, exact line 4, missing file -> problem; NOTICE base section must name
  exactly one ref, both URLs present, no other CPython X.Y.Z (four URL/text forms).
  Controls bite (8 + 8). Sound.
- `test_ke_app_real_rows_cpython_is_the_ruled_release` (test_sbom_obligations.py
  l.670-700): control (headers 3.12.99 vs real rows) fails drift by name; real rows
  vs committed headers; rows == [CPYTHON_RELEASE]. A genuine new fast check (the
  existing drift tests use the stub ke_app_doc, not the real rows). Sound.
- The `3.12.16 -> 3.12.99` control change (l.657-664) is stronger than HEAD: it adds
  an assertNotEqual guard that the control changed the text.
- The restored `"{rel} line 1 does not parse"` subtest (l.665-668) is identical to
  HEAD 45411ae l.661-664 (it shows as unchanged context in the diff).
- Pins: RULED_PYTHON_BASE defined once (test_psycopg_c.py l.76), imported by
  test_notice_ke_app; CPYTHON_RELEASE / CPYTHON_TARBALL_SHA256 defined once
  (test_notice_ke_app.py l.254-255), imported by test_sbom_obligations. Every pin is
  enforced against repository files, so none can drift silently. Nothing weakened.

## 3. Re-pins

- FIXTURE_KEYS (test_sources_lock.py l.187-238; set from l.194): exactly key-diff.txt's +2/-1;
  Counter deb 152->153; committed-lock message 183; U7cCoverage (153, 19);
  U7dCoverage 183. Each carries a reason comment. Nothing loosened.
- ReworkR1 B2 (test_sources_lock.py l.1256-1269) left at (79, 6): correct. The drop
  set (neo4j, pandas, 3 pgdg) and the per-package miss counts do not depend on the
  openssl/ca-certificates version moves (same packages map to the new keys), so the
  83/10 seen by the developer came only from the stale FIXTURE_KEYS.
- No test reads docs/evidence/**: the two added mentions are comments
  (test_sources_lock.py l.191-193; the parallel APACHE_2_SHA256 comment).

## Findings

### Blocking

- **B-1 (PSC-27 *Size* not recorded).** docs/requirements.md l.4488: "`ke-app`'s
  image and bundle tar sizes are recorded before and after, for PSC-16." No U7e
  evidence records them (u7e/ has no size file; developer-green.md, developer-build.txt
  and the verify logs carry no image/tar size). Design R7 does not schedule it, so it
  will be missed. Fix: developer records before (45411ae, e.g. a scratch-worktree build
  as u0/size.md did) and after (this tree) image size and bundle tar size in
  `docs/evidence/platform-sbom/u7e/size.md`. Evidence only.
- **B-2 (PSC-27 criterion names a check that does not exist).** docs/requirements.md
  l.4434-4439, under *Image-side drift check (PSC-22, in `offline_check.sh`)*: "The
  `ke-app` SBOM's `libssl3` and `openssl` rows carry `3.0.22-1~deb12u2`." Neither
  scripts/sbom_check.py (`drift`) nor scripts/offline_check.sh checks those rows (no
  libssl/openssl reference in either), and no test asserts it; design R1-R7 dropped it
  with the pin. The fact holds today (fixture l.93, l.114; the scan is green), but the
  criterion claims full-mode coverage that is not there. Fix (orchestrator's call):
  either the analyst amends that bullet to name the actual proof (the image scan
  under PSC-4 plus the R4 fixture rows; a version pin in drift would go stale at the
  next base bump), or the architect/tester add the check. I recommend the amendment.

### Nits

- **N-1** tests/test_sources_resolve.py l.2995 `test_the_182_keys` asserts 183. The
  docstring explains it, but a name that states a stale count misleads anyone reading
  a failure line, and every base bump repeats it. Not the sentinel and referenced
  nowhere else: rename to a count-free name (e.g. `test_every_fixture_key_resolves`).
- **N-2** docs/requirements.md l.4393 ("This blocks the U7d commit. U7e lands first.")
  and l.4528 ("U7e (PSC-27) runs after U7d's gate and before U7d's commit.") are stale
  since U7d is WIP 45411ae (the analyst already flagged l.4528). Mark them as history.
- **N-3** tests/test_sbom_obligations.py l.678-680: "the real rows are today's image,
  CPython 3.12.15" reads as current after GREEN; the other RED notes say "RED (U7e)" with
  no "today". Optional: "were the U7d image".
- **N-4** The base-bump pins live in two modules (RULED_PYTHON_BASE in test_psycopg_c;
  CPYTHON_RELEASE/TARBALL in test_notice_ke_app). Both comments say they move together,
  and each is enforced, so this is optional; co-locating them would make the next bump
  a one-place edit.

## Open gates outside this review (not findings)

- A34 Windows proof (`u7e/windows-run.txt`) is still to come (R5/R7 step 6).
- Orchestrator's own `scripts/verify.sh full` on the final tree (the tester's PASS was on
  `45411ae+dirty` before the analyst's docs and the APACHE_2_SHA256 comment edit).
- Security M-1 (ke-gates compose/uv fixable Highs) is a follow-up for the human.

## Re-review, rework round 1 (2026-10-28)

Verdict: **APPROVED**. Only what changed since the review above was checked.

- B-1 closed. `u7e/size.md` gives the image size (inspect) and the bundle tar size
  before and after: image 54,855,049 -> 54,854,801 B, tar 54,872,576 -> 54,872,064 B.
  "Before" is `ke-app:bundle-d8ffa2d451ef`. The stated pathspec omits two COPY inputs
  of app.Dockerfile (`harness_telemetry`, `config`; the file's `app` path does not
  exist). I re-ran it with every COPY source (`git log/diff d8ffa2d..45411ae --
  harness_telemetry config engine docker/app.Dockerfile uv.lock pyproject.toml`), and
  it is empty too, so the substitution holds (nit R-1: fix the pathspec in size.md if
  touched again).
- B-2 closed. requirements.md l.4440-4449 withdraws the version claim, quoting the old
  text. It names the real proof: the scan (tester-repin l.2083-2367) and fixture l.93
  and l.114. It matches the code (no libssl/openssl check in sbom_check.py or
  offline_check.sh).
- N-1 closed: `test_every_fixture_key_resolves` (tests/test_sources_resolve.py l.2995),
  with the docstring updated. The old name is referenced nowhere in tests, scripts or
  CI, and the renamed test is ok in tester-nits-verify-fast.txt (Ran 1110, OK skipped=8).
- N-2 partly: l.4393 annotated. l.4538 ("U7e (PSC-27) runs after U7d's gate and before
  U7d's commit.") is still unannotated (nit, non-blocking).
- N-3 closed: tests/test_sbom_obligations.py l.678-680 now reads as history.
- L-2: the APACHE_2_SHA256 comment (tests/test_notice_ke_app.py l.238-244) names the new
  base and security's re-confirmation. It is a comment only, and no test reads evidence.
- CHANGELOG U7e bullet: consistent with the diff (digest, 3.12.16, deb12u2, CVE,
  183 components).
- A34: a34-verify-full.txt PASS 1132 s (Ran 1110 OK; integration OK skipped=5). It
  predates the N-1/N-3 test edits; those are covered by tester-nits-verify-fast.txt.
  The orchestrator's final `verify.sh full` on the final tree is still required
  before the commit.
