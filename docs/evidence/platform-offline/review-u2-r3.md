# Review: platform-offline unit 2, re-review after rework round 3/5 (2026-10-19)

Reviewer. Base 1fe81dd; working tree on agent/platform-offline (uncommitted).
Read: the staged scripts/install.sh (index == working tree, 100755), the untracked scripts/install.ps1 and
tests/test_offline_bundle.py, `git diff 1fe81dd` for tests/fake_docker.py and docs/quickstart.md, and the
handoff from "unit-2 rework round 3/5" on. Developer evidence: green-u2r3-verify-full.txt and
green-u2r3b-verify-full.txt (`== verify full: PASS ==`, Ran 544, OK skipped=2); green-u2r3-windows-acl.txt (2 OK).
Raw probes, mutant diffs and results: `review-u2-r3-probes.txt`. Verify: `review-u2-r3-verify-fast.txt`.

Verdict: **CHANGES REQUESTED** (1 blocking, introduced by the I-7 fix in this round).

## Verify
- `COMPOSE_PROJECT_NAME=ke-review-r3 scripts/verify.sh fast`: `== verify fast: PASS ==`, Ran 544, OK (skipped=2).
- No probe debris in the repo root.

## 1. Earlier findings
| Finding | Status | Evidence |
|---|---|---|
| RB3 in-place rewrite (M-4b) | fixed | tail is `main "$@"; exit` (install.sh:600). Mutants split (two-line tail) and unwrap are both killed by `test_install_ignores_script_rewritten_in_place` |
| RB4 quickstart `scriptsaunch.ps1` | fixed | quickstart.md:34 reads `scripts\launch.ps1`; `test_quickstart_names_existing_scripts` |
| RB5a ps1 PATH rule | fixed | mutant pspath killed (5 subtests: relative, dot, leading/trailing/middle empty) |
| RB5b launch.sh `at_least` | fixed | mutant atl killed (2.23.9 and 2, under bash and the BSD shims) |
| N1 §2.5 conformance | fixed | sh warns on a parent owned by neither `id -u` nor root; ps1 counts GenericWrite/GenericAll |
| N2 cleanup marker check | fixed | mutant clshc killed (planted-dir sentinel) |
| N3 quickstart | mostly fixed | `pwsh -NoProfile -File`, PATH note split by script, step 5 `bash scripts/launch.sh`. install.sh's `next:` line still prints `scripts/launch.sh` (N6) |

New mutants (all killed):
- l11 (L-11 owner/mode check dropped): `test_install_sh_refuses_staging_loosened_before_cd`.
- i7 / i7ps (I-7 emptying dropped, sh / ps1): `test_install_empties_swapped_staging` (sh and ps1).
- l13 (L-13 rmdir dropped): `test_install_sh_leaves_no_target_when_claim_mkdir_fails`.
- chre / chreps (re-check before chmod dropped, sh / ps1): `..._refuses_target_swapped_for_link_before_chmod`
  (behavioural) and `..._rechecks_target_is_dir_right_before_chmod` (static).

## 2. Blocking
- **RB6 The I-7 cleanup empties whatever directory the `cd` landed in, and the L-11 check accepts any
  operator-owned 0700 directory.**
  - install.sh:284-293 does `cd -- "$staging"` (by name, follows a symlink), then checks only `-O .` and
    `drwx------`, then sets `pinned=1`. From then on, any failure runs `rm -rf -- ./* ./.[!.]* ./..?*` (line 90).
  - Attack in the L-11 window (between `chmod 0700` and `cd`; reachable because install.sh only warns on a
    group-writable parent): rename staging away, put a symlink under its name to an operator-owned 0700
    directory (`~/.ssh`, `~/.gnupg`, a 0700 home on Fedora/RHEL). The checks pass, `cp -R` copies the
    bundle into it, the manifest check fails on the victim's own files ("file is not listed"), and cleanup
    deletes everything in the victim directory.
  - Probe (tests/scratch_r3.py, a `chmod` shim as racer like the L-11 test): victim `id_ed25519` and
    `sub/keep` before; `victim after: []`, rc 1. With I-7 removed (mutant i7) the victim keeps its files
    (it is only polluted with bundle files), so this round's change turned the race into deletion.
  - Fix (developer): before `pinned=1`, require the directory to be empty
    (`[ -z "$(ls -A -- .)" ] || die ...`). A fresh mktemp dir is empty, and nobody else can write into an
    operator-owned 0700 dir, so cleanup can then only remove what this run copied. Optional extra: compare
    `pwd -P` with `$parent/${staging##*/}`. Mutant fixempty (the empty check alone) passes the full
    test_offline_bundle suite and stops the deletion.
  - Test (tester): the probe above as a sh test. The victim's files survive, the run exits non-zero, and no
    docker command runs.

## 3. Cleanup `rm` scope (orchestrator question)
- Before the pin it cannot run. `pinned` is set to 0 at top level before the EXIT trap is installed, and its
  only `pinned=1` (line 293) comes after a successful `cd` and the L-11 check.
- A failed `cd` exits under `set -e` with `pinned=0` (trap.sh probe: cleanup ran with pinned=0, rc 1).
- Subshells do not run the EXIT trap. This was probed with a command substitution containing `cd`, a
  pipeline brace group that calls `die`, and `( exit )`, under bash 5.2. POSIX resets traps in subshells,
  so bash 3.2 should behave the same, but it was not available to probe.
- The `./`-prefixed globs cannot be read as options, and `rm -rf` does not follow links inside the directory.
- The gap is RB6: "pinned" proves "a 0700 operator-owned directory", not "the staging this run created".

## 4. Nits
- N6 install.sh:597 prints `next: cd <target> && scripts/launch.sh`, while the quickstart says
  `bash scripts/launch.sh` so that the file mode does not matter. Use `bash scripts/launch.sh` there too.
- N7 (parity, not exploitable today) install.ps1's I-7 gate keys on the working directory's name
  (`.ke-install.` prefix). On Linux, after a rename, getcwd returns the new name, so a rename to any other
  name skips the emptying (the fake renames to `<name>.swapped`, which keeps the prefix). That cannot be
  reached: off Windows ps1 refuses a shared parent, and Windows cannot rename a working directory. Still,
  for parity with RB6, also assert that staging is empty after `Set-Location` in Initialize-Staging.
- N8 The untracked docs/knowledge-engine-claude-code-prompt.md is not part of this item. Leave it out of
  the commit unless it is meant to be there.

## 5. Quickstart accuracy (checked against the scripts)
These are accurate:
- the PATH rules per script (install.sh refuses empty and relative entries; install.ps1 refuses relative
  entries and drops empty ones on Windows);
- the warn-on-shared-parent text, and the ps1 Windows-only line;
- the `/opt/ke` recipe (gives no warning);
- `-Target`/`-ExpectManifest` and `--expect-manifest`;
- the arch refusal, and the printed hash and next step;
- step 5 and the macOS notes.

The only mismatch is N6.

## Conformance (no finding)
- No eval or Invoke-Expression, argv arrays only, no secrets.
- Observability: these are operator shell/pwsh scripts with no agent loop, model, retrieval or tool call, so
  no span is required.
