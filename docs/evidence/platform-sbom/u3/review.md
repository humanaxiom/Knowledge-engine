# platform-sbom U3 (PSC-13): reviewer, 2026-10-23

Verdict: **APPROVED**. No blocking findings; nits N1-N9 below.

Read: `git diff 98b6d27` (12 files) plus untracked `scripts/sbom_check.py`,
`tests/test_sbom_bundle.py` and `u3/`; PSC-13 (requirements.md l. 3380-3412)
and PSC-24; ADR-KE-016 points 1, 2 and 6; design-notes N1 (run, down,
presence), N3 (checker), N6 (namespace ruling (b)) and N7; `u2/review.md`
conditions; the U2 commit-gate carry list.

## Diff vs targets
- `sbom_check.py`, `docker-compose.sbom.yml` and `offline_check.sh` are
  byte-equal to `u3/target-*`.
- `bundle.sh` differs from the target only by the Windows-host fixes:
  `hostpath()`, `MSYS_NO_PATHCONV=1` on the syft run and the checker run,
  and `mkdir` then `chmod 0700`.

## bundle.sh SBOM section: conforms
- Run argv: `-p "$sbom_project" --env-file .env.example -f
  docker-compose.sbom.yml run --rm --pull never sbom
  docker-archive:/in/<name>.tar --scope all-layers -o
  spdx-json=/out/raw.spdx.json`, with the three `KE_SBOM_*` keys. Matches N1
  and ADR pt 1.
- `<project>-sbom` is set; `project` is pattern-checked at l. 292.
- EXIT trap: `down` runs from `repo_root` in a subshell (cwd is `$out` by
  then), with the same -p, --env-file and the three keys. It warns on
  failure and removes `sbom_work`. Bash keeps the script's exit status.
  This is the only trap in the script.
- Checker run: `--network none --read-only --cap-drop ALL --security-opt
  no-new-privileges --pull never --user "$sbom_user"` with label
  `<project>-sbomcheck`. All three mounts are `:ro` and there is no socket.
  It runs as `python -I`, in `$app_ref`, which is ADR pt 2.
- `sbom_user` is checked against `^[0-9]+:[0-9]+$`.
- Generator arch: `{{.Os}}/{{.Architecture}}` must equal `linux/$arch`
  before any write (closes U2 N2).
- `ref_re` first character is `[a-z0-9]`, applied to the generator and to
  stack refs (closes I-1).
- Failure: both `die`s name the image. MANIFEST and the record are never
  written (PSC-24 bullet 1). `--out` keeps the partial tree, as the existing
  post-write failures do, and install cannot accept it.

## Windows-host fixes (developer, beyond targets)
- They are correct. I reproduced `mkdir -m 0700` failing in Git Bash on NTFS
  ("cannot change permissions", rc 1), while `mkdir` then `chmod` gives rc 0.
- `MSYS_NO_PATHCONV` is needed because MSYS would rewrite
  `spdx-json=/out/...` and the `-v` container targets. With it set, host
  paths need `cygpath -m`.
- They are inert on Linux and CI. With no `cygpath`, `hostpath` is
  `printf %s`. `MSYS_NO_PATHCONV` is not forwarded into either container
  (no `-e`, no compose `environment:`). On Linux, `mkdir` then `chmod`
  equals `mkdir -m`, and the parent `mktemp -d` is already 0700.
- Coverage, measured with reviewer probes in `review-controls-base-repo.txt`:
  - The Linux identity branch of `hostpath` is pinned: mutant killed by
    `test_sbom_generator_run_is_pinned`.
  - Removing `chmod 0700` survives, and so does removing `MSYS_NO_PATHCONV`.
    No test sees them.
  - The Windows branch is exercised only by the Windows host half of
    `verify full` (`green-verify-full.txt`, df on `C:`), by
    `bundle-run.txt`, and by the parallel A34 proof. See N4.

## scripts/sbom_check.py: conforms
- It imports the standard library only, and `test_sbom_check_is_stdlib_and_never_shipped`
  checks this through the AST.
- It is never shipped: there is no Dockerfile `COPY` of `scripts`
  (checked), `bundle.sh` mounts it and never copies it, and it is not
  imported by engine/ or harness_telemetry.
- `validate`: N6's required-field set. It returns problems and never raises,
  using the `urn:uuid` v4 regex from ruling (b).
- `finish`:
  - It sets the name to the ref and draws a fresh `uuid4` per document.
  - It keeps syft's creators and adds `knowledge-engine-bundle-<sha12>`.
  - It adds 3 OTHER annotations, with `ke:image-config` taken from the
    tar's `manifest.json` (OCI and legacy layouts; exactly one image).
- ke-app runtime check (N7): every installed distribution except the project
  must be in `uv.lock` at its installed version, and listed as
  `pkg:pypi/<n>@<locked>`.
  - This matches amended PSC-13: the runtime set is what the final sync
    installs.
  - The test computes the expected set independently from the uv.lock graph
    (markers for linux CPython 3.12) and checks that it includes psycopg-c.
- CLI: `finish --name --ref --arch --git-sha --raw --tar [--site --lock]`.
  `--uuid` exits 2, a bad pattern or arch exits 2, a failure exits 1 with up
  to 20 lines.

## docker-compose.sbom.yml: conforms
- `user: ${KE_SBOM_USER:?set by scripts/bundle.sh}` (closes L-2).
- The header shows the exact U3 run form, and `down` uses the same values
  (closes U2 N1).
- The "no top-level name" wording is fixed (closes U2 N5).

## Tests and controls
- The tests match PSC-13's three tags. They also pin the run argv, project
  and teardown (my U2 condition), daemon arch, the leading `-`, SBOM failure
  (5 cases), L-1, L-2, N3 and I-2. Existing tests were tightened, not
  weakened: `app/` now expects `sboms/`, the offline_check pull needs
  `KE_SBOM_USER`, and I-2 narrows HOME/XDG to `/tmp`.
- The fake runs the real checker, so the stubs do not hide its logic.
- `u3_controls.py --base repo` no longer runs on the real `bundle.sh`. Its
  `RUN_ENV` anchor predates `hostpath` (AssertionError; see N9).
- I adapted the anchors (5 strings) and added 3 probe rows in
  `u3/review_u3_controls.py`, then ran it in the gates image (`--pull
  never`, project `ke-reviewer-u3`). Result: 124 rows, 123 ok
  (`u3/review-controls-base-repo.txt`).
- The one unexpected row, "no sbom_check.py (pre-U3)", is a driver artifact
  under `--base repo`. `_REPO_COPY` copies `scripts/` whole, so the real file
  is present and the mutant equals TARGET. It is not a test gap; that row
  was ok on the targets (`red-mutants.txt` l. 128).

## Evidence: consistent
- `red-verify-fast.txt`: 812 tests, 48 failures, all U3.
- `red-reach-verify-fast.txt`: PASS.
- `green-verify-fast.txt`: PASS, 812 tests, OK, skipped 8.
- `green-verify-full.txt`: PASS 855 s. Every `test_sbom_bundle` test ran and
  passed, and the sentinel ran. offline_check PASS shows 6 sbom-run
  containers and then "bundle written".
- `bundle-run.txt`: 6 runs, bundle written.
- `sboms/`:
  - The 2 stored documents carry the ref as name, a `urn:uuid` v4,
    `Tool: syft-1.54.1` plus the bundle tool, and the 3 annotations.
  - OS packages are listed as apk/deb purls.
- `gpl-family-packages.md`: per-image lists. For neo4j, jna 5.15.0
  (Apache-2.0 AND LGPL-2.1-only) and jaxb-api 2.2.12 (CDDL+GPL) are flagged
  for ruling 5.

## U2 carry list: all closed
- Review N1 (--env-file and `KE_SBOM_*` on run and down): closed.
- Review N2 (arch check): closed and tested.
- Review N3 (offline header): closed and tested.
- Review N4 (wording "must include these eight"): closed.
- Review N5 (compose comment): closed.
- Security L-1: closed, with `test_compose_files_have_no_include_or_extends`.
- Security L-2: closed (`user:` plus `--user` on the checker).
- Security I-1: closed and tested.
- Security I-2: closed (`hardening_problems`, /tmp only).
- Reviewer conditions 5 and 8 (project, teardown, argv): closed by
  `test_sbom_generator_run_is_pinned` and the controls.
- Not U3 code: ruling 5 (jna, jaxb-api) is with the architect and must be
  decided before the commit gate.

## Findings
- **N1:** the `sbom_check.py` docstring, l. 21, still says "(tester's reach
  target for U3 RED; the developer owns the real file)". Drop it.
- **N2:** the `bundle.sh` comment "mkdir -m fails under Git Bash on NTFS
  (L-13)" cites the wrong finding. L-13 is the psycopg_binary vendored-libs
  finding. Cite the Git Bash behaviour, or nothing.
- **N3:** the Windows fixes are not in the forms design-notes N1 and N3 pin.
  Those forms still show `"$out/images"`, `-v "$work:/work:ro"` and
  `mkdir -m`.
  - Architect: add one line covering `hostpath` and `MSYS_NO_PATHCONV`
    (Git Bash only).
  - `sbom_cleanup`'s `down` uses raw paths, which is harmless because
    `down` binds nothing. Say so there, or make it consistent.
- **N4:** there is no automated test of the `cygpath` branch,
  `MSYS_NO_PATHCONV` or the 0700 chmod (both probes survive).
  - Possible tests: a fake `cygpath` on PATH that asserts `KE_SBOM_IN`,
    `KE_SBOM_OUT` and the `-v` sources pass through it, plus
    `MSYS_NO_PATHCONV=1` in the run env; and fake syft logging the mode of
    `KE_SBOM_OUT`.
  - Until then, the Windows path rests on the Windows-host `verify full`
    and A34. A34 should state that it ran the real SBOM stage.
- **N5:** each syft run warns "unable to get filesystem cache at
  /.cache/syft ... read-only file system" (6 per bundle). The cause is that
  HOME is `/` for a passwd-less uid.
  - N1's "Confirm at GREEN" outcome is not recorded in the handoff: whether
    `TMPDIR` is honoured, and whether syft writes only to `/out` and `/tmp`.
  - The warning shows syft does try another path, and the read-only root
    stops it.
  - Architect: accept and record it, or set `XDG_CACHE_HOME=/tmp/...`,
    which I-2 allows.
- **N6 (design, to architect):** the work dir is `mktemp -d
  ${TMPDIR:-/tmp}`, so the 1-2 GB unpack lands on the host's TMPDIR. R6's
  7 GiB floor is measured on `--out`'s filesystem.
  - Where /tmp is a tmpfs (Debian 13, Fedora, Arch) or a small separate
    filesystem, the N1 claim "the 7 GiB floor already covers" fails. Snap
    Docker has a private /tmp.
  - All of these fail closed, but with a generic "document is unreadable"
    message.
  - Options: make the work dir a sibling of `--out` (same filesystem, still
    outside it), or floor-check TMPDIR.
- **N7:** `runtime_problems` keys uv.lock by name, so a forked lock (two
  versions of one name) would collapse. There are 0 duplicate names today
  (checked). Revisit only if the lock forks.
- **N8:** the real syft stage has run only on the Windows host. The Linux
  host path (no `cygpath`, a native daemon, caller uid) is first run by CI or
  a Linux box. Green CI covers it before the PR.
- **N9:** `u3_controls.py` anchors are stale for `--base repo` since the
  Windows fixes. The tester may fold in `review_u3_controls.py`'s 5 anchor
  edits and probe rows, and should mark the "pre-U3" row as `--base
  targets` only.
