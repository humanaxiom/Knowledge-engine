# platform-sbom U1 (PSC-14): review

Reviewer, 2026-10-22. Diff: `git diff 31bfed4` (NOTICE.md, docs/requirements.md
PSC-14 amendment, handoff, log) plus untracked `tests/test_notice_ke_app.py`,
`docs/evidence/platform-sbom/u1/`, `docs/handoffs/archive/platform-sbom-part2.md`.
Read against PSC-14 (including the 2026-10-23 amendment), ADR-KE-016 point 9, and
design notes N10 and N15.

## Verdict: CHANGES REQUESTED

The NOTICE.md text is accurate where it can be checked, the scope is clean, the
RED and GREEN evidence is real and the handoff split is faithful. Blocking
findings: one fail-open gap in the drift check (B1) and two places where a
criterion and the code or comments disagree (B2, B3). B2 and B3 are one-line
doc fixes.

## Blocking

- **B1. The test can pass a stale NOTICE after a base bump, and fails an honest
  update.** `base_paragraph_problems` reads the CPython minor with
  `re.match(r"python:(\d+\.\d+)\b", ref)` and falls back silently to `"3.12"`
  when that does not match (`py = m.group(1) if m else "3.12"`). It also
  hard-codes `Debian 12`. Probe (scratch copy, check functions unchanged):
  - P1: ref `docker.io/library/python:3.13-slim-bookworm@...` in both files, with
    NOTICE still saying "CPython 3.12": the check returns `[]` (passes stale).
  - P2: a `trixie` base in both files, NOTICE still saying "Debian 12 (bookworm)":
    the check returns `[]` (passes stale).
  - P3: the same `trixie` base with NOTICE saying "Debian 13 (trixie)": the check
    FAILS ("no block names the base's Debian 12 packages").
  The docstring says expected values come from committed files, and the
  CPython minor is meant to come from the tag. Fix: if the ref does not parse
  as a `python:X.Y-slim-CODENAME@sha256:` reference (optionally
  registry-prefixed), report a problem (no default). Derive the Debian release
  from the codename through a small map (bookworm to 12), and report a problem
  for an unknown codename. Add controls for "registry-prefixed ref, stale
  CPython minor" and "codename changed, stale Debian release".
- **B2. Where the pointer sits disagrees with the 2026-10-23 PSC-14 amendment.**
  The amendment says "`NOTICE.md`'s `ke-app` base section points to the
  generated 'Source code' section ... and to `sources/`". The pointer is in its
  own `## Source code` section, outside "Base of `ke-app`", and
  `pointer_problems` accepts it in any block (probe P4). N10 ("one section and
  one pointer") and the content support the current placement, because the
  generated section covers GPL-family components in every image (neo4j,
  busybox), not only ke-app. Fix: the analyst amends PSC-14 to "`NOTICE.md`
  points to ...". Do not move the pointer into the ke-app section.
- **B3. The test comment promises a check the plan does not contain.**
  `ADDED_PACKAGES`'s comment says "U4's SBOM test (PSC-22, full) checks the real
  image's dpkg packages against this list", and the tester's handoff line
  repeats it. PSC-22 and N15's U4 row list no such check, and N10 says "There
  is no image-side drift check." Three of the four package names NOTICE gives
  depend only on this constant, so if apt's resolution changes on a base or pin
  bump, NOTICE goes stale with nothing to catch it. Fix (pick one, and record
  it): (a) the analyst or architect adds "ke-app's dpkg packages not in the
  base equal `ADDED_PACKAGES`" to PSC-22/U4 with a test tag (it could also
  check pip's version, see N2); or (b) reword the comment to say there is no
  image-side check (N10).

## Nits

- **N1. Two present-tense forward references in NOTICE.md.** "in the image's
  SBOM" (U3) and `THIRD_PARTY_NOTICES.md`'s "Source code" section (U9) are not
  true for a bundle built from this branch today. PSC-14 accepts both (the
  original "and in the SBOM, PSC-13" and the 2026-10-23 amendment), so this is
  not blocking. The orchestrator should record in the handoff that the branch
  is not merged to main, and no operator bundle is cut from it, before U3 and
  U9 land. U9 should add a cross-file test that the generated heading is
  exactly the `Source code` NOTICE quotes; today only the NOTICE side is
  pinned.
- **N2. The pip 25.0.1 claim has no saved evidence.** The developer's handoff
  names a `docker run --network none` probe, but `u1/` has no output file for
  it. Save the command and its output, for example `u1/pip-version.txt`. The
  version is checked only for shape, so it goes stale silently when the digest
  is bumped (accepted by N10). B3(a) could close this.
- **N3. Whether `PSF-2.0` is the right licence identifier for CPython (security
  or analyst should confirm, not re-litigated here).** CPython's `LICENSE` is
  the stacked PSF/BeOpen/CNRI/CWI text, which SPDX lists as `Python-2.0`;
  `PSF-2.0` is only its top layer. CPython also bundles third-party code
  (libmpdec, expat and others) whose licences are in
  `/usr/local/lib/python3.12/LICENSE.txt`. The U3 SBOM may report
  `Python-2.0`. Consider pointing NOTICE at that file. ADR-KE-016 point 9, N10
  and PSC-14 all say PSF-2.0, so this needs a ruling, not a developer edit.
- **N4. `DATED_RE` exemption is broad.** Any block containing any
  `20YY-MM-DD` may name psycopg-binary. That is acceptable for history notes,
  but a vendor row or paragraph that happens to carry a date also escapes the
  check. Optional: require the date to begin the block.
- **N5. The test imports private helpers from other test modules**
  (`_stages`, `_apt_installs`, `_packages`, `_Scratch`). `test_psycopg_c` already
  does the same, so this follows existing practice. Optional: move them to
  `tests/support.py` or `engine_support` later.

## Questions the orchestrator asked

- **NOTICE accurate today?** The base ref and digest, the libpq5 pin
  (`15.19-0+deb12u1`) and the four added packages match `docker/app.Dockerfile`
  and the U0 apt record (`u0/green-verify-full.txt` lines 178-205: NEW
  libldap-2.5-0 libpq5 libsasl2-2 libsasl2-modules-db). "uv is not shipped"
  matches the Dockerfile (uv only in `builder`). Not true yet: SBOM and the
  "Source code" section (N1). Licence identifier: N3.
- **Tests and the 35 controls.** 25 base, 6 libpq and 4 pointer controls, plus
  three targets. The controls are in the test file as subtests, so they are
  permanent and not evidence-only. `u1/red-mutants.txt` shows 0 unexpected and
  the reach check passes; the driver `u1_controls.py` imports only the test
  module. No test reads `docs/evidence/**`: the only mention is a comment
  (orchestrator ruling met). The fixture values (digest a*64, pin 15.99-...,
  pip 24.0) differ from the repository's, so a check that read a copy instead
  of the given files would be caught. Weakness: B1.
- **Brittleness.** The checks look for N10's element tokens within one block
  (`/usr/local`, `PSF-2.0`, `copyright`, `SBOM`, `site-packages`, `uv.lock`,
  `Source code`, `sources/`), not exact sentences. Rewording around them
  passes. That is acceptable, because the tokens are the design's named
  elements. NOTICE's text is the tester's `_BASE` fixture almost word for
  word, so only one wording has been exercised. The uv rule (every block
  naming uv needs a negation word) is coarse but fails closed.
- **Base bump caught?** Digest: yes (byte for byte, both directions).
  libpq pin: yes. CPython minor: only for an unprefixed `python:` ref (B1).
  Debian release: no (B1). pip version: no, by design (N10, N2). Packages apt
  pulls in: only when the Dockerfile's apt names change (B3).
- **Handoff split.** The 90 lines removed from `docs/handoffs/platform-sbom.md`
  equal `archive/platform-sbom-part2.md` line for line (after trailing
  whitespace is normalised); only a 4-line archive header is added. The active
  doc has 84 lines (under the 200 cap). The U0 summary (rework 1 of 5, L-13
  closed, verify full 694 s, A34 path, no open nits) matches the archived
  orchestrator and reviewer sections.
- **RED/GREEN evidence.** `u1/red-verify-fast.txt`: Ran 785, FAILED
  (failures=3, skipped=8). All three new tests fail at their final repository
  assertion (test lines 367/377/388 match the current file), each for the
  expected reason (no section; no libpq5 + PostgreSQL licence block; no
  pointer). No other test fails. `u1/green-verify-fast.txt`: Ran 785, OK
  (skipped=8), lint and mypy clean, `verify fast: PASS`. The diff touches
  NOTICE.md, which is docs, so `fast` is the right loop.
  `orchestrator-verify-full.txt` was still being written during this review and
  is not judged here.
- **Scope.** NOTICE.md, one new test module, the PSC-14 amendment, handoff,
  log, evidence. Nothing outside U1. No agent loop, model call or retrieval,
  so no new spans are needed.

Probe (scratch, not committed): it ran the unchanged `base_paragraph_problems`
and `pointer_problems` on four variants. Results: P1 `[]`, P2 `[]`, P3 one
problem, P4 `[]`.

## Re-check (rework round 1), reviewer, 2026-10-23

Diff: `git diff 31bfed4` (NOTICE.md, requirements PSC-14/15/22 and the
standing rule, ADR-KE-016 point 9 and the TDD list, design notes N7/N8/N10/N15,
handoff, log) plus untracked `tests/test_notice_ke_app.py`,
`licenses/Apache-2.0.txt`, `licenses/MPL-2.0.txt` and `u1/`.

### Verdict: CHANGES REQUESTED (one blocking finding, B4, a one-paragraph NOTICE fix)

### Prior findings
- B1 resolved. `parse_base_ref` uses `BASE_REF_RE.fullmatch` (optional registry
  prefix), with no default, and `DEBIAN_RELEASES` (an unknown codename is a
  problem). Controls: P1 (registry 3.13 with NOTICE still saying 3.12) and P2
  (trixie with NOTICE still saying Debian 12) fail. P3 (honest trixie) and an
  honest registry 3.13 bump pass. Unparseable refs (no codename, no digest,
  63-hex digest, pypy) and `sid` fail.
- B2 resolved. PSC-14 now says "points, in its own "Source code" section", with
  the reason.
- B3 resolved by option (a). The image-side check is in PSC-22
  (`[full: ke-app SBOM's added dpkg set equals ADDED_PACKAGES and pip version
  matches NOTICE]`, U4), ADR TDD list U4, N7, N10 and the N15 U4 row. The
  `ADDED_PACKAGES` comment is now true. All of these agree.
- N1 resolved. The standing no-merge/no-bundle rule is in requirements and the
  handoff. PSC-15 tags `test_notice_source_code_heading_matches_generated` (U9).
- N2 resolved. `u1/pip-probe.txt` holds the command and its output (pip 25.0.1).
- N3 resolved. NOTICE gives `Python-2.0` and `/usr/local/lib/python3.12/LICENSE.txt`.
  The test derives the minor from the ref and has controls for PSF-2.0, a
  missing pointer and the wrong minor.
- N4 resolved. `DATED_RE` is anchored at the start of the block. "dated
  mid-text" fails and "History:" passes.
- N5 not taken (it was optional). Accepted.

### Security findings reflected
- M-1: the sentence is in NOTICE verbatim. `pointer_problems` requires it in the
  same block as the pointer. Controls cover: sentence absent, sentence in its own
  paragraph, no-section condition dropped, "has no sources/" dropped, and
  "provides". The positive-form regexes stop the M-1 sentence from standing in
  for the pointer.
- L-1: both SBOM mentions are conditional. Every SBOM block must carry "where the
  bundle carries one" (two controls).
- L-2: the pip bullet names `vendor.txt`, Apache-2.0, MPL-2.0, "ships no licence
  files" and both `licenses/` files (5 + 3 controls).
- L-3: covered by N3 above.

### Controls (re-run)
`uv run --locked python docs/evidence/platform-sbom/u1/u1_controls.py`
reports 68 must-fail and 3 must-pass, so 71 controls, all as named. It prints
"unexpected: 3" only because the three REPO rows still say "RED expected" and now
pass after GREEN (N6). The section text in `r1-target-notice-sections.md` is
identical to NOTICE.md's (checked by script).

### Licence-text test and the two files
- The checks are canonical markers, a length floor and NOTICE's pip block naming
  both files. Controls cover: missing, truncated, another licence, MPL 1.1, and
  the files named outside the pip block. Adequate.
- Provenance re-verified. The sha256 of each committed file equals the provenance
  table. `cmp` against `.venv/.../opentelemetry_api-1.45.1.dist-info/licenses/LICENSE`
  and `pathspec-1.1.1.dist-info/licenses/LICENSE` gives identical bytes. Both wheel
  hashes match `uv.lock` (lines 397 and 515). The Apache appendix placeholder
  `[yyyy] [name of copyright owner]` is intact, so there is no package preamble.
- Against canonical copies fetched into the scratchpad (apache.org
  LICENSE-2.0.txt, sha256 cfc7749b..., 11358 B; mozilla.org MPL 2.0 index.txt,
  16726 B):
  - Apache is identical after dropping the canonical file's *leading* newline.
  - MPL is not byte-identical to mozilla.org's current file. Line 38 has a
    trailing space, and Exhibit A has `http://mozilla.org/MPL/2.0/` where
    mozilla.org now has `https://`. The size is the same.
  - Both are text-equivalent. NOTICE's "unmodified, copied from the licence
    files of the locked packages" is true. The provenance note is not (N7).

### Blocking
- **B4. NOTICE.md cites a repository evidence path, and NOTICE ships in every
  bundle.** The new closing paragraph of "Licence texts" says "(see
  `docs/evidence/platform-sbom/u1/licence-texts-provenance.md`)". No bundle carries
  that file: `bundle.sh` copies only `docs/quickstart.md` from `docs/` (line 300),
  and `test_offline_bundle` pins the app tree to that. So a recipient is pointed
  to a file they do not have. This is the same class of defect as M-1, now in the
  licence section. It also breaks two rules:
  - NOTICE's convention: every other licence-text entry names its public upstream
    source.
  - The orchestrator's U1 ruling that evidence is history, not a source of truth.
    The cited file already carries a status line that goes stale on commit
    ("both files are untracked") and a wrong claim (N7).

  The same paragraph also overstates coverage: "They cover the packages that the
  base's pip vendors". The two texts cover only the Apache-2.0 and MPL-2.0 ones.
  Fix (developer; NOTICE.md only):
  - make the provenance self-contained in a file the bundle carries. Name the two
    wheels, `opentelemetry_api-1.45.1-py3-none-any.whl` and
    `pathspec-1.1.1-py3-none-any.whl`, and say that `uv.lock` (which ships) pins
    their sha256. Or give their PyPI URLs.
  - narrow the last sentence to "They cover the Apache-2.0 and MPL-2.0 packages
    that the base's pip vendors."

  The evidence path can stay in the handoff. Optional: the tester adds a control
  that NOTICE.md cites no `docs/evidence/` path.

### Nits
- **N6.** `u1_controls.py`: the REPO rows still expect RED, so after GREEN the
  driver exits 1 with "unexpected: 3". Relabel them, or add a `--green` mode, so
  a later re-run is not misread.
- **N7.** `u1/licence-texts-provenance.md` has two inaccuracies:
  - the Apache file lacks the canonical *leading* newline, not a trailing one;
  - the MPL file is pathspec's older revision of the text (the trailing space
    and `http://` above), not the canonical bytes.
  Correct the note, and drop the "untracked" status line when the files are
  committed.
- **N8. Commit hygiene.** `licenses/Apache-2.0.txt`, `licenses/MPL-2.0.txt` and
  `tests/test_notice_ke_app.py` are untracked. The test reads the filesystem, so
  a commit that omits them passes locally and fails on CI (it fails closed, but
  only after the commit). `bundle.sh` ships `git ls-files -- licenses` only.
  Before commit, the orchestrator checks `git status`. It also re-runs
  `verify.sh full`: `orchestrator-verify-full.txt` predates the rework.
- **N9 (for security or the analyst, not a developer edit).** pip's other
  vendored licences (BSD-2/3-Clause, ISC, PSF-2.0, MIT) also ask that their
  notice reach the recipient, and pip ships none of them. The human ruled on
  Apache-2.0 and MPL-2.0 only. Record whether the NOTICE sentence ("keep their
  own licences") is enough for the rest, or whether this is on the drop-pip
  follow-up.
- **N10.** The first PSC-14 bullet still says "and in the SBOM, PSC-13"
  unconditionally, and the amendment says the wording is conditional "until U3".
  The test makes the conditional wording permanent, which stays true after U3.
  The analyst could reconcile the two in one line.

### Plan, design and evidence agreement
- PSC-14 as amended, PSC-15 (U9 heading test, standing rule), PSC-22 (U4 drift
  check; I-1 deb source or reviewed exemption), ADR-KE-016 point 9 and N10 agree
  with NOTICE.md and the four tests. The only gap is N10 above.
- RED `r1-red-verify-fast.txt`: Ran 786, FAILED (failures=3, skipped=8), lint
  PASS, sentinel ok. Each of the three tests fails at its final repository
  assertion (lines 619, 642 and 664 match the file), for the expected reason
  (base: Python-2.0/LICENSE.txt and the rest; pointer: no M-1 sentence; licences:
  both files missing and not named). `test_notice_names_libpq_as_a_debian_package`
  stays green.
- GREEN `r1-green-verify-fast.txt`: Ran 786, OK (skipped=8), mypy clean,
  `verify fast: PASS`.
- `fast` is right for this diff (docs, licence texts, a pure static test).
  `full` is still due before commit.
- Scope: within U1 plus the human's ruling. No agent loop, model call, retrieval
  or tool call, so no spans are needed. Handoff: 130 lines, under the cap.

## Re-check 2 (rework round 2: pip dropped, ke-app flattened), reviewer, 2026-10-23

Diff: `git diff 31bfed4` (app.Dockerfile, smoke.sh, NOTICE.md, fake_docker.py,
test_image_scan.py, test_psycopg_c.py, test_stack_compose.py, requirements,
architecture, design notes, handoff, log) plus untracked
`licenses/CPython-3.12-incorporated.txt`, `tests/test_ke_app_no_pip.py`,
`tests/test_notice_ke_app.py`, `u1/` and `archive/platform-sbom-part2.md`/`part3.md`.
Read against PSC-14/22/25 as amended, ADR-KE-016 point 9, the ADR-KE-013 am. 1
D10 note, design notes N10/N10a/N15, and the orchestrator's empty-output ruling.

### Verdict: CHANGES REQUESTED (B5, B6: both doc-only, no code or test change)

The code, the tests, the licence file and the evidence are sound. Two plan or
design texts still describe what the code no longer does.

### Prior findings
- B4 resolved. NOTICE.md has no `docs/` path (grep). The licence-texts paragraph
  names the public URL and the header sha256. `test_notice_cites_no_repo_evidence_path`
  (EVIDENCE_RE, 5 must-fail and 1 must-pass) pins it. The "cover all pip
  packages" overstatement went away with pip.
- N6 open (nit, carried). The driver's REPO rows still say "RED expected", so
  after GREEN it prints "unexpected: 5" and exits 1 (re-run below).
- N7 superseded. `licence-texts-provenance.md` is headed SUPERSEDED, and both texts are deleted.
- N8 still applies at commit; see N12.
- N9 superseded by the drop-pip ruling: no pip, so pip's vendored notices are gone.
- N10 resolved. PSC-14 now says the conditional SBOM wording stays after U3.

### docker/app.Dockerfile
- Shape matches N10a byte for byte (builder and uv unchanged). `runtime`'s FROM
  equals the builder's FROM exactly. libpq5 RUN, then the pip RUN, with `&&` and
  `rm` without `-f`. The last stage is `FROM scratch` and starts
  `COPY --from=runtime / /` once. After it: ENV, D10's two copies, WORKDIR, useradd, USER ke, CMD.
- Built for real (`r2-green-verify-full.txt` l.164-168: "Successfully
  uninstalled pip-25.0.1"). Smoke `no pip` passes on the build host (l.1657-1658)
  and in the offline client (l.2187-2188). The scan still matches dpkg (Debian
  detection works with no base layer) and the `python 3.12.15` binary. The scan
  lists no pip.
- ENV. The base config (`r2-pip-probe.txt`) is Env PATH/LANG/GPG_KEY/PYTHON_VERSION/
  PYTHON_SHA256 and Cmd `["python3"]`. PATH is re-set as `/opt/venv/bin:` plus
  the base PATH, with the base's duplicate `/usr/local/bin` removed. LANG is
  re-set. Nothing in the repo reads the three dropped keys (grep of py/sh/yml/ps1/
  Dockerfiles: only the Dockerfile comment). Q48's PYTHON_SHA256 anchor is read
  from the base digest, not from ke-app (N10a), so it is unaffected. U4's
  CPython version comes from syft's binary cataloguer. The scan already reports
  it without the env. Dropping them is safe.
- Other config lost by FROM scratch: Cmd only, which the last stage overrides.
  The base sets no Entrypoint, User or WorkingDir per the probe. Healthchecks live
  in compose (docker-compose.yml, offline.yml), not in the image. No repo
  Dockerfile uses LABEL. The probe records setuid/setgid, hardlinks, `dpkg -l`
  and `/tmp` 1777 as unchanged. ADR-KE-016 Consequences notes the lost layer
  sharing. Tar shrinks by 3,945,472 B (`u1/size.md`). Nothing lost that matters (see N13).

### scripts/smoke.sh `no pip`
- `/usr/local/bin/python3 -I`: os.walk of /usr and /opt plus a `find_spec`
  fallback, one token. Host side: `read -r` and a string compare against `-`,
  never evaluated. A failed exec fails. Empty output fails (`"$pip_hits" != -`,
  orchestrator ruling). Mutant S10 (`${pip_hits:--}`) is killed
  (`r2-red-mutants.txt`). Container output is printed only inside a quoted
  message to stderr. Adequate.

### NOTICE.md and licences/CPython-3.12-incorporated.txt
- NOTICE from `## Base of` to the end, and the 5-line file header, equal the
  tester's targets (`r2-target-notice-sections.md`, diffed by script). The
  facts match the Dockerfile and the U0 apt record.
- Independent fetch (scratchpad, the provenance file's curl flags): license.rst
  sha256 is `341832873f...cadf4e5`, equal to the header and to
  `cpython-incorporated-provenance.md`. Heading at line 298, once. The `sed`
  re-extract `cmp`-equals `tail -n +6` of the committed file. Extract sha256 is
  `d4f3b214...40698a`. LF only, `licenses/* -text`. expat and libmpdec are both in the extract.

### Tests
- The four re-targets keep their intent, with real controls. U0's runtime
  controls and D10's controls each run on both shapes (`flat:` copies), plus
  13 and 14 further must-fails, mostly N10a shapes. The digest test allows exactly `scratch`.
  It has 8 must-fails (`scratch:latest`, registry scratch, `Scratch`, `scratchy`,
  busybox after a scratch stage, and others). The notice base read goes through
  `shipped_stage`, with 8 `flat:` controls.
- New: `test_ke_app_last_stage_removes_pip` (28 must-fail, 3 must-pass, including
  the U0 shape with a layer delete, `;`/`||`/`-f`/glob widening, wrong minor,
  `$PATH`, and pip removal in the scratch stage). Smoke: clean plus near misses
  pass. Ten fail cases, each named: package, dist-info, pip3, pip3.12, wheel,
  venv pip, importable-only, whole base, exec fails, empty output. Six
  injection payloads, none executed.
- Re-run: `uv run --locked python docs/evidence/platform-sbom/u1/u1_controls.py`
  gives 212 must-fail + 21 must-pass = 233. Every control behaves as named. The
  5 "unexpected" are the stale REPO "RED expected" labels (N6).
  Host unittest of the static classes (KeAppNoPipStaticTest, test_notice_ke_app,
  PsycopgCStaticTest, AppImageTest, ServicesTest): 19 tests OK. The smoke
  classes need Linux bash and cannot run on this host (WSL error), so for them
  I rely on the gates-image runs below.
- No test reads `docs/evidence`.

### RED and GREEN evidence
- RED `r2-red-verify-fast.txt`: Ran 791, failures=23, skipped=8, lint PASS,
  sentinel ok. All 23 are U1 round 2, each at its repository assertion for the
  expected reason: the static test (5 problems: not scratch, no COPY /, `$PATH`,
  no LANG, no runtime); smoke (no step, so it passes); notice x4 (Apache named,
  no CPython file, L-6 wording, evidence path). This includes the
  empty-output subtest.
- GREEN `r2-green-verify-fast.txt`: `verify fast: PASS`, mypy clean.
  `r2-green-verify-full.txt`: Ran 791 OK (skipped=8), smoke PASS on the host
  and offline, scan done, `verify full: PASS (718s)`. It was built from
  `31bfed4+dirty`, with the licence file and the two test files untracked (N12).

### Blocking
- **B5. PSC-14 and PSC-25 still put the pip removal and libpq5 in "the last
  stage"; the code and tests forbid that.** requirements.md l.3415
  ("shipped (last) stage"), l.3453 ("The last stage of `ke-app` removes the
  base's pip"), l.3466 (tag text "the last stage removes pip"), l.3480
  ("packages the last stage adds"), and PSC-25 l.3865/l.3870 ("the last stage
  installs `libpq5`", "The last stage may also hold the pip removal"). Under
  N10a the last stage is `FROM scratch`. The tests require both RUNs in
  `runtime` and fail them in the last stage (controls "pip removal in the
  scratch stage, not runtime", "the libpq5 apt RUN moved to the scratch stage",
  "last stage (FROM scratch): a RUN installs or removes"). Same class as B2.
  Fix (analyst): say "the shipped stage (`runtime`, which the `FROM scratch`
  last stage copies whole; N10a)" at those lines. Test names stay.
- **B6. N10a's smoke snippet still shows the fail-open default the
  orchestrator overruled.** design-notes.md l.747:
  `[ "${pip_hits:--}" = - ] && ...`. The ruling (handoff, tester round 2 RED)
  makes empty output fail and supersedes this. The tester asked the design
  owner to amend it, and nobody has. A later editor who copies the design
  restores mutant S10. Fix (architect): `[ "$pip_hits" = - ] && [ -z "$pip_rest" ]`,
  plus one clause that says empty output fails (ruling 2026-10-23).

### Nits
- **N6 (carried).** Relabel the driver's REPO rows, or add a `--green` mode.
- **N11.** Handoff "U1 so far" still says "next is tester round-2 RED". Update it when the round closes.
- **N12 (commit order, I-4/N8).** `bundle.sh` ships `git ls-files -- licenses`,
  so the green full's offline bundle had NOTICE naming
  `licenses/CPython-3.12-incorporated.txt` without the file. N1 means nobody
  received it. Before commit, `git add` the licence file and both new test
  modules, then run the orchestrator's `verify.sh full` on that index.
- **N13 (optional).** The probe records only Env and Cmd of the base config.
  Record `docker image inspect <base> --format '{{json .Config}}'` once
  (Labels, Healthcheck, Entrypoint, StopSignal null) to close the question on
  evidence rather than on knowledge of the official images.

### Scope and observability
Within U1 and the human's drop-pip ruling. No agent loop, model call, retrieval
or tool call, so no spans are needed. The A34 Windows proof (running in
parallel) and the orchestrator's `verify.sh full` are still due before commit.
The handoff has 99 lines before this append.

## Re-check 3 (rework round 3: HACL* file, whole-output smoke, tracked licences, L-12), reviewer, 2026-10-22

Diff: `git diff 31bfed4` plus the index (`licenses/CPython-3.12-HACL.txt`,
`licenses/CPython-3.12-incorporated.txt`, `tests/test_ke_app_no_pip.py`,
`tests/test_notice_ke_app.py`; the working tree equals the index for all four)
plus untracked `u1/` and `archive/platform-sbom-part2.md`/`part3.md`.
`NEXT-SESSION.md` and `knowledge-engine-claude-code-prompt.md` were ignored.

### Verdict: APPROVED (U1 as a whole, for commit once the orchestrator's `verify.sh full` on this index is PASS)

### Prior findings
- B5 resolved. PSC-14 (requirements l.3415, 3466, 3480, 3495) and PSC-25
  (l.3885) say "the shipped stage (`runtime`, which the `FROM scratch` last
  stage copies whole; N10a)". Test names are kept. The only "last stage" left
  in the plan is l.3118 (unrelated) and a quoted follow-up title.
- B6 resolved. N10a (design-notes l.748-760) shows `[ "$pip_out" = - ] || FAIL`
  and says empty output and `-` plus a second line both fail (ruling, I-6). No
  `${pip_hits:--}` remains except as the named mutant S10.
- N6 resolved. Re-run `uv run --locked python docs/evidence/platform-sbom/u1/u1_controls.py`
  (default mode): 265 must-fail + 26 must-pass = 291, `unexpected: 0`, exit 0.
  Every REPO row says "want pass | passes" (base, libpq, pointer, incorp, hacl,
  tracked, evidence, pip, u0-run, d10, digest x3).
- N11 resolved by the orchestrator's append-only correction (handoff l.121).
- N12 resolved. The two licence files and the two test modules are staged.
  `test_notice_named_licence_files_are_tracked` now pins this. The
  orchestrator's `verify.sh full` on this index is the remaining gate.
- N13 resolved. `u1/base-config.json` is `.Config` with Env and Cmd only
  (Docker omits null fields). I reproduced it byte for byte with
  `docker image inspect python:3.12-slim-bookworm@sha256:34386ef0... --format '{{json .Config}}'`.

### Security items
- L-9 handled. `licenses/CPython-3.12-HACL.txt` is a 4-line header, a blank
  line and the extract. Independent fetch (scratchpad, the provenance curl
  flags): tarball sha256 `c2c43219...94fd5a` (= PYTHON_SHA256), member
  `Hacl_Hash_SHA2.c` `30638efb...201b31`, `sed -n '1,/^ \*\/$/p'` gives 23
  lines with sha256 `998ce04f...d78c`, and this `cmp`-equals `tail -n +6` of
  the staged file. Whole file `d83382d7...c483` = the tester's target. LF
  only, and `licenses/* -text` applies. Survey of `Modules/_hacl/`: the
  same header appears byte for byte in 13 of 20 `.c`/`.h` files (all
  Hacl_Hash_* and internal/*), so the single extract covers the MIT code.
  Of the rest, 5 krml headers say "Licensed under the Apache 2.0 License",
  types.h and python_hacl_namespaces.h differ (see N15).
- NOTICE CPython bullet: "CPython also builds in third-party code under its
  own licences. CPython's own list of it (among them expat and libmpdec) is
  in ...; the HACL* hash code (MIT) in `_md5`, `_sha1`, `_sha2` and `_sha3`,
  which that list omits, is in ...". The bullet makes no completeness claim.
  COMPLETENESS_RE (`whose texts are in`, all, every, complete, full(y),
  entire(ly), whole) is applied to the bullet, with must-fail controls.
  The Licence-texts paragraph names the tarball URL and the source file, with
  no repo path. It equals the target (`u1/r3-target-notice.md`) inside the
  markers.
- L-12 handled. In `unpinned_bases` (tests/test_stack_compose.py), a name
  counts as a stage only if an earlier FROM defines it. The alias is added
  after the check, compared case-insensitively. `scratch` must match exactly,
  and an unpinned digest-less ref fails. Controls: 4 must-pass and 10
  must-fail, including `FROM alpine AS alpine` and the forward reference.
  All three repo Dockerfiles pass.
- I-6 handled. smoke.sh's no-pip step is byte-identical to
  `r3-target-smoke-block.sh`. The whole `$(...)` output is compared to `-`,
  with no `read` and no default. A failed exec fails. Container output is
  printed only inside a quoted stderr message. New subtest: "`-`, then a
  second line with a pip path" fails. Six injection payloads still never run.
- I-4 handled. `untracked_licence_problems` runs
  `git -C <repo> ls-files -z -- licenses` with GIT_* stripped and a ceiling
  dir. If git cannot run (OSError) or exits non-zero, it returns a named
  problem, never a skip. Controls in the test include "git cannot run" (a
  missing binary) and "not a git work tree". The gates image installs git
  and sets `safe.directory /work`. If git were absent, the test's own
  scratch `git init` would raise inside the named test (ERROR, not skip).
  The GREEN run proves it executes in gates against the real index.

### RED and GREEN evidence
- `u1/r3-red-verify-fast.txt`: Ran 792, FAILED (failures=5, skipped=8),
  lint PASS, sentinel ok. Each failure is round 3 and fails for the expected
  reason: the I-6 subtest (smoke passed with `-` plus a second line);
  tracked (incorporated file untracked); incorporated/HACL (10 problems,
  starting "bullet does not name ...HACL.txt"); L-12 x2 (both controls
  survive the old rule). The tester's later L-12 fix cut RED to 3, as the
  handoff records.
- `u1/r3-green-verify-fast.txt`: Ran 792, OK (skipped=8), mypy clean,
  `verify fast: PASS`. All four round-3 tests are `ok`.

### A34 and the Dockerfile
sha256 now: app.Dockerfile `128c5dbe...cda7de`, uv.lock `feff8833...c2a821`,
pyproject.toml `80d17709...b24cf8`. All three equal `u1/windows-run.txt`
l.143-146. Only smoke.sh changed (`c3a328e6...` -> `08a9f668...`). It is a
gate script that A34 does not exercise, so the A34 proof stands. The live
whole-output compare is proved only by the orchestrator's `verify.sh full`.

### U1 as a whole
The diff is scoped to PSC-14 and PSC-25 follow-through: N10a flatten, no pip,
NOTICE sections, the two CPython licence files, re-targeted and new tests,
and smoke no-pip. Plan (PSC-14, PSC-25), design (N10, N10a) and ADR-KE-016
point 9 agree with the code. No test was weakened: each re-target kept its
controls, and the retired pip-licence test is retired by plan. No test
reads `docs/evidence` (test_image_scan's provenance read predates U1). No
agent loop, model call, retrieval or tool call, so no spans are needed.

### Nits
- **N14.** `u1/base-config.json` does not record the command or image ref
  that produced it. I reproduced it (above). Optionally note the command in
  the handoff.
- **N15 (carry to security, not a review block).** Five KaRaMeL headers
  under `Modules/_hacl/include/krml/` say "Licensed under the Apache 2.0
  License". The architect left these open for security. NOTICE stays true
  either way. If security rules them in, U1 or a follow-up needs an
  Apache-2.0 text.
- **Commit hygiene.** Stage `docs/evidence/platform-sbom/u1/` (34 untracked
  files) and `docs/handoffs/archive/platform-sbom-part2.md`/`part3.md` with
  the commit. Leave `NEXT-SESSION.md` and the prompt file out.

## Re-check 4 (rework round 4: KaRaMeL notice and Apache-2.0 text, security L-9b and I-8), reviewer, 2026-10-23

Verdict: **APPROVED** for commit, provided the orchestrator's `verify.sh full`
on this index passes. Scope: round 4 delta only.

- **Tests.** `karamel_licence_problems` (l.688) checks that the CPython bullet
  names KaRaMeL, "INRIA and Microsoft", the SPDX `Apache-2.0` (a regex that
  skips the two paths), and both files. `_karamel_file_problems` checks the
  4-line header, the blank line, a 2-line extract, the version agreeing with
  the incorporated and HACL files, line 4 equal to the HACL file's tarball
  sha256, CR rejection, and the Licence-texts block (target.h and the URL).
  `_apache_problems` checks the pinned sha256 and the base-files, path and
  sha256 paragraph. I-8: `HACL_LICENCE_OF_RE` requires "the licence of the
  HACL* hash code ... is in <file>". The Apache rule in
  `base_paragraph_problems` (l.353-357) lets `licenses/Apache-2.0.txt` appear
  only in a block that names KaRaMeL or base-files and does not name pip.
  MPL-2.0.txt is still never allowed. This matches PSC-14 l.3491-3497. The
  pip-ban controls are still in place, and two new controls (Apache beside
  pip) were added. No test was weakened.
- **Controls.** `uv run --locked python .../u1_controls.py` (default mode)
  exits 0: 321 must-fail and 29 must-pass = 350, 0 unexpected (karamel 51+3).
  `r4-red-mutants.txt`: reach 0 unexpected, S10-S12 killed.
- **RED/GREEN.** `r4-red-verify-fast.txt`: Ran 792, FAILED (failures=2) on the
  expected subtests, repository='HACL' (I-8 wording) and
  repository='KaRaMeL and Apache-2.0' (8 problems).
  `r4-green-verify-fast.txt`: Ran 792, OK (skipped=8), mypy clean, PASS.
- **Files.** `licenses/CPython-3.12-KaRaMeL.txt` is sha256 `32300266...796d`.
  It is LF, `cmp`-equal to the tester's target, and its `tail -n +6` hashes
  to `6b7cb4bd...8a26`, as the provenance file records. Its text matches
  security's probe l.150-151. `licenses/Apache-2.0.txt` is 11358 B, sha256
  `cfc7749b...d30`, equal to security's probe l.177 and to the target. Both
  are staged; `ls-files --eol` gives i/lf, -text.
- **NOTICE.md.** It has the CPython bullet with the I-8 wording and the
  KaRaMeL clause, plus two Licence-texts paragraphs. It makes no completeness
  claim, and the text is true.
- **PSC-14** as amended in round 4 (l.3452-3469, 3495-3497) agrees with the
  code.
- **A34.** The sha256 values are unchanged: app.Dockerfile `128c5dbe...cda7de`,
  uv.lock `feff8833...c2a821`, pyproject `80d17709...b24cf8`, and smoke.sh
  `08a9f668...` (same as round 3). A34 stands.
- **Nit N16.** `_karamel_file_problems` compares the last extract line after
  `.strip()`, so the test does not pin the indent. Byte-exactness rests on
  the provenance hash, not on the test. This is acceptable as written in
  PSC-14.
- Carried: N14 and commit hygiene (stage `u1/` and archive part2/part3, not
  NEXT-SESSION.md or the prompt file). The I-7 bundle.sh twin is optional
  and out of scope.
