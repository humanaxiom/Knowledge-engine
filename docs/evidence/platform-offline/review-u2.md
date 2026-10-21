# Review: platform-offline unit 2 (PS-3.1 bundle and install), 2026-10-19

Reviewer. Base 1fe81dd, working tree on agent/platform-offline (uncommitted).
Read: `git diff 1fe81dd` (.gitignore, .dockerignore, tests/fake_docker.py, n1-n4
edits) and untracked scripts/bundle.sh, scripts/install.sh, scripts/install.ps1,
tests/test_offline_bundle.py. Checked against requirements PS-3.1 (+ additions),
architecture §2.5 Bundle/Install, ADR-KE-012.

Verdict: **CHANGES REQUESTED** (2 blocking).

## Verify
`COMPOSE_PROJECT_NAME=ke-review-u2 scripts/verify.sh fast` -> `== verify fast: PASS ==`,
462 tests OK. Full log: `docs/evidence/platform-offline/review-u2-verify-fast.txt`.
Developer full run (not re-run): `green-u2-verify-full.txt` -> PASS (193s).

## Mutation runs
Scratch copy of the tree (never the repo); tests run in `ke-gates:latest`
with `--network none`: `python -m unittest tests.test_offline_bundle.<Class>`.
Baseline: 27 tests OK.

| # | Mutant | Result |
|---|---|---|
| m1 | install.sh: drop hash compare | caught (a_changed_file) |
| m2 | install.sh: `docker info` moved before the manifest check | caught (9 failures: every tamper case sees a docker call) |
| m3 | install.sh: drop the dot / dot-dot segment check | **survives** |
| m4 | install.sh: drop the non-file/non-dir (symlink) check | **survives** |
| m5 | install.sh: drop duplicate-path check | caught |
| m6 | install.sh: drop unlisted-file check | caught |
| p1 | install.ps1: drop link/reparse-point check | caught (symlink case) |
| p2 | install.ps1: `docker info` before the manifest | caught (9 failures) |
| p3 | install.ps1: drop the dot / dot-dot segment check | **survives** |
| p4 | install.ps1: drop hash compare | caught |
| b1 | bundle.sh: drop linux/amd64 refusal | caught (non_amd64) |
| b2 | bundle.sh: drop `<name>` collision refusal | caught (name collision refused) |
| b3 | bundle.sh: drop `as` collision refusal | survives; equivalent mutant (unreachable, N4) |

The two mutants asked for (drop one manifest check; `docker info` before the
manifest) are caught for the hash, duplicate and unlisted checks and for the
order swap in both installers. The empty-docker-log assertion in
`_assert_refused_before_docker` is real.

m4 is not harmless. Probe (fixture bundle plus an unlisted `app/evil -> /etc`
directory symlink, run in the gates image):
- base install.sh: rc=1, "install: manifest: not a regular file or directory (symlink, fifo or device): ./app/evil", 0 docker calls.
- m4: rc=0, 8 docker calls, `<target>/evil` is a symlink to /etc.
`find -type f` does not descend into a symlinked directory, so without the
`odd` check an unlisted directory link passes the file-set check and `cp -R`
carries it into the target. The test's `symlink` case lists a *file* link in
the manifest, which the "listed file is missing" rule also refuses, so it
cannot tell the link rule from the file-set rule.

## Findings

### Blocking
- **B1 Tamper test does not pin the link and dot-dot rules (m3, m4, p3 survive).**
  `tests/test_offline_bundle.py` `_tamper_cases`: `symlink`, `dotdot_path`
  (and `leading_slash`, `backslash`, `malformed_line`, `duplicate_path`) pass
  `name=None`, and each is also refused by another rule, so deleting the rule
  under test leaves the suite green. Fix (tester): add an unlisted directory
  symlink case (the m4 probe shape) and an unlisted file symlink, and assert
  each case's refusal names its rule (§2.5 "A message names the rule and the
  path"), for sh and ps1. Re-run m3/m4/p3 and show them caught.
- **B2 Installer runs `compose config`; requirements say it does not.**
  requirements.md PS-3.1 additions, *Compose override (R2)*: "taking the
  service names from the entries' `services` fields (it does not run
  `compose config`)". install.sh:175 / install.ps1:206 run
  `docker compose ... config --services` to implement the same bullet's
  "Given a stack service with no bundle.json entry, the installer exits
  non-zero naming the service", which the tester pinned. The code is the
  reasonable reading (there is no other way to know the stack's services),
  and real Compose v5.1.4 lists all 7 services from an app/ without docker/
  (checked locally). Resolution is a doc amendment, not a code change:
  analyst rewords the parenthetical; architect adds the step to §2.5 Install
  between 4 and 5. Blocking only until the docs agree.

### Non-blocking (nits)
- N1 Parity: install.ps1 refuses links/reparse points only; §2.5 also
  refuses fifos/devices (install.sh does). Only reachable under Linux pwsh.
- N2 Parity: link message. sh prints the relative path (`./app/evil`); ps1
  prints only the leaf (`Format-Safe $info.Name`). Print the bundle-relative path.
- N3 Parity: target. sh refuses a symlink target; ps1
  `Test-Path -PathType Container` follows it and accepts a link to an empty
  dir (a dangling link reaches `CreateDirectory`).
- N4 Dead code: bundle.sh `seen_as` collision can never fire (an `as`
  collision implies a `<name>` collision under the §2.5 scheme; b3 is
  equivalent). Drop it or comment it as a belt-and-braces guard.
- N5 install.ps1 `$listed`/`$present`/`$entryFile` are `@{}`, which compare
  case-insensitively; §2.5 says ordinal. On Windows a manifest listing
  `App/...` passes where install.sh refuses. Integrity is unaffected (bytes
  are still hashed); use `[hashtable]::new([StringComparer]::Ordinal)`.
- N6 Exit status of `compose config --services` is ignored in bundle.sh:64
  and install.sh:175 (process substitution); ps1 checks `$LASTEXITCODE`.
  Fails closed only on empty output.
- N7 Untested paths: unpinned non-`ke-*` image refusal (bundle.sh:101);
  "bundle.json names service the stack does not have"; the no-bundle-entry
  test does not assert zero `load` calls; installer does not check the
  first-party `as` sha12 against the header `git_sha`.
- N8 Floor is 10 GiB but messages say "10 GB"; "found N GB" truncates. Cosmetic.

## Rulings asked for
- **NOTICE.md / licenses copy-if-exists (bundle.sh:150-151), and
  net_isolated.sh likewise (bundle.sh:146).** None exists in the repo yet,
  so for unit 2 this is acceptable. It becomes a fail-open the moment they
  exist: §2.5 Bundle root lists them unconditionally. Carry (must close in
  the PS-3.8 unit, and the PS-3.3 unit for net_isolated.sh): copy
  unconditionally (`cp` fails under `set -e`) and pin the exact bundle file
  set with `test_bundle_contents` (§2.6 #6). Not blocking now.
- **amd64-only refusal.** Conforms: §2.5 Bundle 1 "It must be linux/amd64
  (Q20), read from the same inspect"; PS-3.1 *Platform*. bundle.sh reads
  `{{.Os}}/{{.Architecture}}` from the same `image inspect` that enforces the
  digest pin and never passes `--platform`. Keep it.
- **`as` scheme and collision checks.** Conform to §2.5 Bundle 2:
  first-party `ke-<x>:bundle-<sha12>` (repo must match `^ke-`), vendor
  `ke-vendor/<last path segment>:<digest12>`, `<name>` collision refused
  before any write (test exists; b2 caught). Installer `as_re` admits only
  these two shapes, so no digest or registry host reaches the override. The
  extra `as` collision check is unreachable (N4).

## Conformance notes (no finding)
- Manifest, daemon, target, bundle.json, load/tag/inspect, copy, override:
  same order in sh and ps1; matches §2.5 Install 1-7.
- No eval / Invoke-Expression; docker called with argv arrays; bundle.json
  values matched against fixed patterns before reaching YAML.
- No `--platform`, no pull/build/push in bundle.sh; `dist/` in both ignore files.
- n1-n4 test-only edits are as described and fine.
- Observability: shell scripts only; no agent loop, model, retrieval or tool
  call added, so no span is required.
