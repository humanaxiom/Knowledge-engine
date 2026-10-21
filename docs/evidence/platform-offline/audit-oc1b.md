# audit-oc1b: scoped review + security confirmation of L-OC1a, NB1 and the smoke control_port fix

Verdict: **PASS / APPROVED**. There are no critical, high or medium findings. One low test gap and two info notes, all non-blocking. One process incident is recorded below.

Scope: HEAD f7e9074 plus the working tree (`git diff HEAD -- scripts engine/netprobe.py`, the untracked `scripts/image_tag.sh` and `engine/netprobe.py`). I read the developer's GREEN section and `green-oc1b-verify-full.txt`: 651 tests OK (skipped=8) plus 11 integration tests, lint PASS, offline_check PASS (89 s), verify full PASS (448 s).
Raw output is in `audit-oc1b-probes.txt` (P1 to P6, mutant M1, labels, secrets grep). All scratch work used `<scratch>` only. HEAD, the index and `git status` were unchanged before and after (hashes recorded).

## Confirmations
- **Every changed `cd` is `CDPATH='' cd --`.** The 11 scripts are build, bundle (entry cd and `cd -- "$out"`), env_value, image_tag, launch, lint, offline_check (entry cd and `cd -- "$target"`), smoke, teardown, test and verify. No bare `cd`/`pushd` is left under `scripts/` or `docker/` outside install.sh.
  - P4: each script's entry cd, run with `CDPATH=<decoy with scripts/>`, `.` and `decoy:.`, prints exactly one line and stays in its own tree. CDPATH is restored afterwards (the empty value is a temporary assignment only).
  - P4b: for the variable form, a relative `$out` reached the decoy before the fix and stays local after it.
- **install.sh `unset CDPATH`.** It is at line 34. Only `set -euo pipefail` runs before it, and the first `cd` is at line 95 (inside a function; `main "$@"; exit` keeps M-4).
  - It is safe under `set -u` when CDPATH was never set (P5).
  - It does not touch the staging pin (`cd -- "$staging"`, absolute, and the `pwd -P` equality check), the claim, or publish (`cd -- "$target"` with `-ef .`, absolute). It only stops CDPATH from rewriting the relative operands at L133 and L282.
  - Bash 3.2: `unset` is POSIX. The `CDPATH='' cd --` form in launch/teardown/env_value relies on a temporary assignment to a regular builtin plus `extract_colon_unit("")` returning NULL. Both behave the same way in 3.2 and 5.x, and the macOS 3.2/BSD static test is green. No bash 3.2 binary is available on this host, so that part was not run.
- **Tag regex.** `^wt-[0-9a-f]{12}$` is used via `=~` (POSIX ERE, no REG_NEWLINE, so the match is on the whole string) under `LC_ALL=C` in a subshell. It runs at verify.sh:30-38, before any docker call (the first one is at :50+).
  - P3: 16 bad values each exit rc 1 with **0 docker calls** and a `%q`-quoted message. The bad values are: two lines, a trailing line, uppercase, 11/13 hex, a leading space, a tab, `;id`, `$(id)`, `:x/y`, Arabic-Indic digits, a fullwidth `a`, `local`, empty, and an image_tag.sh exiting 3 (rc 3).
  - A caller's `LC_ALL` (C.UTF-8, en_US, tr_TR) does not change acceptance.
- **CDPATH probe re-run (security-oc1 P5/P5c).**
  - P1, image_tag.sh: 9 CDPATH/`$0` forms all give the single line `wt-<own hash>`. A pre-fix control copy reproduces the bug (`<dir>|wt-…`, and another tree's tag), so the probe is not blind.
  - P2, verify.sh with stub docker and stub stages, with a decoy tree that has a `wt-badbadbadbad` image_tag.sh: 5 CDPATH values x fast/full all give rc 0, the own tag in all 1/6 calls, pwd always the own tree, 0 decoy stages and 0 stray directory lines.
- **control_port.** smoke.sh:170 sets `control_port="$probe_port"` once. It is used in the control `docker run` (:171) and in the inconclusive message (:173). The service probes keep `$probe_port`.
- **NB1.** `MAX_WITHIN = 3600.0`, checked with `math.isfinite` and `0 < w <= 3600`. P6 (python -I, network none):
  - 3600 and 3599.999 still probe.
  - 3600.0001, 3601, 1e4, 1e300, 1e309 and inf all give `bad_arguments`, rc 1, 0 B on stderr.
  - Every caller in the repo uses 2 or 5 s.
- **Secrets and identifiers.** The pattern grep over the 721-line diff and the new files gets 3 hits, all prose comments. The evidence files contain no profile path, user name or SID.

## Findings
- **L-OC1b-a (low, tester; non-blocking test gap).** Mutant M1 removes install.sh's `unset CDPATH`.
  - It **survives**: the whole top-level suite (651 tests) fails the same 6 git-only tests in the base copy and the mutant, run twice. No test mentions CDPATH outside `test_stack_scripts.py`.
  - The behaviour matters. Under M1, `bash bundle/install.sh` with CDPATH exported resolves `root` to `<own>\n<own>`, or to `<decoy>/bundle\n<decoy>/bundle` (P5). That fails closed today, because the two-line path does not exist, but install breaks for any user with CDPATH. The documented form `cd bundle; bash install.sh` is unaffected.
  - Fix: add a test that runs the real install.sh as `bash <relative>/install.sh` with `CDPATH=<decoy holding the same name>:.` exported and expects a normal install from its own bundle.

## Info
- I-OC1b-1: Git Bash strips a CR in `$(…)`, so a CRLF tag is accepted cleanly there. Linux bash keeps the CR and the regex refuses it. Both are safe.
- I-OC1b-2: a plain `docker run` of a compose-built image inherits the image's `com.docker.compose.project/service` labels (see the incident). smoke.sh:171's control `docker run --rm … "$app_image"` therefore appears as a container of the project that built the app image for up to 5 s. This is harmless in the verify flow, where teardown runs after smoke. Consider explicit `--label com.docker.compose.project=<own>-probe` so a concurrent `down` or `ps` never counts it.

## Incident (my probes touched the orchestrator's verify project)
- At 2026-10-20T01:03:36Z I started two `docker run --rm --network none` containers (the auto-named `goofy_elbakyan` and `confident_saha`). They used the image **by ID** (sha256:c23c6b3e…, the current `ke-gates:wt-33a132fbfdd7`) to run the M1 base and mutant suites on read-only scratch copies.
- That image carries the build-time labels `com.docker.compose.project=ke-verify-1622726567` and `service=gates-it`, and `docker run` copies image labels to the container. They therefore looked like members of the orchestrator's live verify project, and its teardown failed. Earlier, one sub-second `--rm` Linux-bash CR check (P2 addendum) on the same image had the same labels.
- When I was told, both containers had already exited and were auto-removed (`docker ps -a` showed neither), so there was nothing to stop or remove. I touched nothing else.
- I re-ran M1 (base and mutant) and P6 as `ke-sec-oc1b-{base,mut,np}`, with `--label com.docker.compose.project=ke-sec-oc1b-*` overriding the inherited label (verified by `docker ps`; 0 of mine carry ke-verify-*). The results are identical to the first run. The orchestrator should re-run its verify full.
