# platform-sbom U0 (PSC-25): reviewer findings, 2026-10-23

Verdict: **CHANGES REQUESTED** (3 blocking, 6 nits).

Scope reviewed: `git diff 737750d` (NOTICE.md, README.md, docker/app.Dockerfile,
docker/gates.Dockerfile, docs/architecture.md ADR-KE-016, docs/log.md,
docs/open-questions.md Q61-Q66, docs/requirements.md PSC-13..16 amendments and
PSC-19..25, pyproject.toml, scripts/smoke.sh, tests/fake_docker.py,
tests/test_offline_bundle.py, uv.lock) plus untracked tests/test_psycopg_c.py,
docs/handoffs/platform-sbom.md, docs/handoffs/archive/platform-sbom-part1.md and
docs/evidence/platform-sbom/** (design-notes.md N0/N15, u0-psycopg-c.md, u0/*).
NEXT-SESSION.md and knowledge-engine-claude-code-prompt.md ignored as asked.

## Confirmed (no finding)

- pyproject.toml: `dependencies` has plain `psycopg>=3.3.6`; groups `pq-c =
  ["psycopg[c]>=3.3.6"]` and `pq-build` (`setuptools==83.0.0`, `wheel==0.48.0`);
  `[tool.uv] no-build-isolation-package = ["psycopg-c"]`; default groups stay
  `dev`. Matches ADR-KE-016 point 0 and N0.
- uv.lock: psycopg-binary is gone (no package entry, no `binary` extra);
  psycopg-c 3.3.6 has an `sdist` with sha256 `29c56842...19ff8` and no
  `wheels`; `pq-build`/`pq-c` sit under `[package.dev-dependencies]`;
  setuptools, wheel and wheel's dependency `packaging` 26.3 are hash-locked.
  No `dependency-metadata` was needed (u0-psycopg-c.md).
- docker/app.Dockerfile: one global `ARG LIBPQ_VERSION=15.19-0+deb12u1`
  before the first FROM, bare `ARG` in builder and last stage, the only
  literal. Builder: `gcc libc6-dev libpq-dev=${LIBPQ_VERSION}`,
  `--no-install-recommends`, lists removed. Three `--locked` syncs as N0;
  sync 3 is exact, so pq-build (and `packaging`) do not ship. Last stage: one
  apt RUN of `libpq5=${LIBPQ_VERSION}` only, lists removed, before USER; it
  copies only `/opt/venv` and `/app` from the builder. No compiler ships.
- docker/gates.Dockerfile: same pin, `gcc libc6-dev libpq-dev=` added to the
  existing apt line, three `--locked` syncs keeping both groups, chown in the
  same layer (L-5 unchanged).
- NOTICE.md: the psycopg section names psycopg and psycopg-c 3.3.6, each
  sdist URL and sha256 equal to uv.lock; no psycopg-binary.
- Pin drift is intended and documented: both Dockerfile headers (the old
  version leaves the mirror and the build fails by name; bump both together,
  never unpin), N0 "Drift and pin signals", ADR point 0 *Drift* and
  *Consequences* (red in build.sh when Debian ships a postgresql-15 update).
  `test_libpq_pin_matches_bookworm_base` keeps the two pins equal (mutant
  M11). See N2 for the missing operator-facing line.
- Evidence: RED `u0/red-verify-fast.txt` = 778 run, 21 failures, all U0 (7
  methods + 14 `test_smoke_checks_psycopg_c_impl_in_api` subtests), no other
  test. GREEN fast (778, OK skipped=8, all 8 U0 tests ok, the gates test ran)
  and GREEN full (PASS 711 s; both `== smoke: psycopg ==` lines, build host
  line 1919 and offline client line 2453; scan done) end PASS. File mtimes:
  every code and test file predates both GREEN runs; tests unchanged since RED.
- Mutants are real: `u0_mutants.py` and `u0_smoke_mutants.py` write scratch
  copies and run the `*_problems` checks and SmokePsycopgTest on them; 0
  unexpected. The block in `scripts/smoke.sh` is byte-identical to the
  tester's `u0/target_smoke_block.sh`, so the smoke mutants measure the
  shipped block.
- Windows proof `u0/windows-run.txt`: the reviewer re-computed sha256 of both
  Dockerfiles, uv.lock, pyproject.toml and smoke.sh on the working tree; all
  five equal the proof's section 0 and final check.
- `.github/agents/*`, `.claude/agents/*`, AGENTS.md, CLAUDE.md: untouched.
- Observability: no agent loop, model call, retrieval or tool call added;
  the ADR says "No agent step: no spans". Nothing to trace.
- engine/ untouched; the two gssencmode tests are unchanged.

## Blocking

### B1. The smoke step does not prove two image facts the criteria rest on

`scripts/smoke.sh` (the `== smoke: psycopg ==` step) checks impl `c`,
`version()` == `__build_version__` == the installed libpq5, and that the ldd
path of `psycopg_c.pq` matches
`^(/usr)?/lib/(x86_64|aarch64)-linux-gnu/libpq\.so\.5` with no
`psycopg_binary` in ldd's output. Missing:

1. **dpkg ownership.** PSC-25 *C implementation, system libpq*: the
   `libpq.so.5` the extension loads "is a file the dpkg package `libpq5`
   owns ... A smoke check in `full` asserts all three." Smoke asserts a path
   shape, not ownership. The fake already models `realpath`/`readlink -f`
   and `dpkg-query -S` for exactly this (tests/fake_docker.py, the
   "platform-sbom U0" block), but smoke never calls them.
2. **No vendored copy.** PSC-14, amended in this diff (requirements.md
   3404-3407 and 3413-3415), retires the real-image drift check "in favour
   of `[full: ke-app psycopg impl is c and links system libpq]`" and says
   "PSC-25's full check proves the directory is absent from the real image".
   It does not: smoke never looks for `psycopg_binary`,
   `psycopg_binary.libs` or `psycopg_binary-*.dist-info` in `/opt/venv`.
   psycopg loads `c` before `binary`, so an image with both installed passes
   every current check (impl `c`, ldd of psycopg_c clean). PSC-25 *arm64*
   also lists "no `psycopg_binary*`" among "the same image checks". Today
   only the lock test (indirect) and the gates test (ke-gates, not ke-app)
   cover it.

Fix (developer and tester): the python check also reports
`find_spec("psycopg_binary")` and whether any `psycopg_binary*` entry exists
in the venv's site-packages, and smoke fails on either; after ldd, smoke
resolves the libpq path (`realpath`) and runs `dpkg-query -S` on it, failing
unless the owner is `libpq5`. The tester adds failing subtests: psycopg_binary
co-installed with impl `c` (the fake needs a knob for it), and a libpq path
that dpkg does not own. `smoke.sh` is a gate-only bash script, so this does
not make the A34 Windows proof stale (Q34 scope ruling). If the orchestrator
prefers to narrow the criteria instead, PSC-14's retired drift check loses
its replacement, so the code fix is preferred.

### B2. PSC-25 *Size* is not met: the bundle tar size is not recorded

PSC-25 *Size*: "`ke-app`'s image size and its bundle tar size, before and
after, are recorded under `docs/evidence/platform-sbom/`." `u0/size.md` has
the image sizes (265 -> 259 MB) and says the bundle tar size is not printed by
`verify.sh full`; `u0-psycopg-c.md` lists it under "Not confirmed". The
numbers feed PSC-16's floor derivation. Fix: record the `ke-app` tar size
before (`ke-app:bundle-d6b70355c452`, or rebuilt from `737750d`) and after
(for example `docker save <tag> | wc -c`, or the bundle's
`images/ke-app.tar`), with the command, in `u0/size.md`.

### B3. Plan docs disagree with what was built (they ship in this first commit)

1. ADR-KE-016 *First tests* (docs/architecture.md 6717-6723) and N0 "U0 RED
   tests" (design-notes.md lines 192 and 210) name
   `test_app_builder_resolves_psycopg_c_from_locked_sdist` and
   `test_app_runtime_stage_installs_only_libpq5`; neither exists. The
   handoff records "requirements names win":
   `test_ke_app_resolves_psycopg_c_not_binary` and
   `test_runtime_stage_has_no_compiler`. The ADR list also has only 6 of the
   8 tests (no smoke test, no notice test).
2. ADR point 0 *Proof* (6582-6583) and N0 (line 152) say libpq resolves
   under `/usr/lib/<triplet>/` only. Bookworm's ldd prints the `/lib/` alias
   and smoke accepts both (recorded in u0-psycopg-c.md, not in the ADR). The
   ADR also says "both equal the pin"; smoke compares with the installed
   `libpq5` version from dpkg. That is the right choice (the offline client
   has no Dockerfile), but the ADR should say so.
3. PSC-13 (requirements.md 3376-3377) defines `ke-app`'s runtime packages as
   "each package `uv sync --locked --no-dev` installs", and PSC-25 *Lock*
   (3664-3666) uses the same words. The builder now syncs `--no-dev --group
   pq-c`, so that definition leaves out psycopg-c (LGPL-3.0-only), the one
   package U0 adds. `tests/test_offline_bundle.py` `_runtime_packages`
   already adds `pq-c`, but U3's `test_sbom_lists_every_locked_runtime_package`
   will be written from PSC-13's text.

Fix: the architect amends ADR-KE-016 point 0 and *First tests*, and N0; the
analyst amends PSC-13 and PSC-25 *Lock* to "`--no-dev --group pq-c`".

## Nits

- **N1.** PSC-25 *Windows (A34)* asks for "a recorded Windows run of
  `scripts/verify.sh full`". The evidence, like PSC-12's, is the PS-2.9 proof
  plus `verify.sh fast`. Either the analyst aligns the wording with PSC-12
  and PS-2.9, or the tester runs `full` on Windows. The proof itself is
  current.
- **N2.** Pin drift has no operator-facing line. README's build section could
  say that `build.sh` fails with apt's "Version ... was not found" whenever
  Debian ships a postgresql-15 update (about quarterly with PostgreSQL minor
  releases, plus DSAs); that this turns every branch and CI red at once; that
  rebuilding an old tag always hits it; and that the fix is a bump PR
  changing both Dockerfiles. Installs from a bundle are unaffected, because
  bundles carry built images.
- **N3.** smoke.sh robustness (none of these is a false pass): an empty or
  non-numeric dpkg version ends in a bash arithmetic error under `set -e`
  rather than a named `smoke: FAIL`; the `dpkg-query ... || { FAIL }` branch
  has no subtest; the libpq regex has no end anchor (add `(\.[0-9]+)*$`).
- **N4.** tests/test_offline_bundle.py: `NOTICE_LICENCE["psycopg-binary"]`
  is now dead, and the native-package case "follows the lock" (binary or c).
  After U0 it can assert psycopg-c directly. The transitional form would stay
  green if psycopg-binary came back (test_psycopg_c would catch that).
- **N5.** Q65's "the `uv run` log step keeps working on Windows" has no
  recorded output: u0-psycopg-c.md cites the handoff, which is not evidence.
  This reviewer's own log step (`HARNESS_TRACING=off uv run python -m
  harness_telemetry.log_event ...`) ran on the Windows host on this tree (see
  the reviewer's handoff line). Save one such command and its output under
  `u0/`.
- **N6.** README's L-13 sentence was rewritten before security confirmed the
  closure (N0: "when security confirms"). That is fine if security's U0
  review confirms it; otherwise restore the residual. The new line also runs
  past the file's wrap width.
- Housekeeping (the orchestrator's section, which other roles may not edit):
  the handoff header still says "ADR to be written", and the unit list's
  "U4 ... / drift" is stale (Q64 dropped the drift check; N15).

## For security (not reviewer findings)

- L-13 closure and the `require_auth` re-rating (Q66) are security's calls.

---

# Re-check after rework round 1 (reviewer, 2026-10-23)

Verdict: **APPROVED** (0 blocking; nits N6 width, N7-N9 open, none blocking).

Read: handoff rework sections (orchestrator round 1, documenter, analyst,
architect, tester RED, developer GREEN), `u0/security.md` M-1 and its re-check,
`git diff 737750d` (smoke.sh, fake_docker.py, test_offline_bundle.py,
test_stack_readiness.py, README.md, requirements/architecture), untracked
`tests/test_psycopg_c.py`, `u0/r1-*`, `u0/size.md`, `u0/q65-windows-uv-run.txt`,
`u0/u0-lock-regen.md`, design-notes.md N0. Reviewer scratch checks:
`u0/r1-review-mutants.txt`.

## Blocking findings: all resolved

- **B1 resolved.** smoke.sh's psycopg step (lines 131-193) is byte-identical to
  `u0/r1-target-smoke-block.sh` (diffed). It now (a) walks `sys.prefix` for any
  `psycopg_binary*` entry plus a `find_spec("psycopg_binary")` fallback and
  fails naming them; (b) runs `realpath -e` on ldd's libpq path, then
  `dpkg-query -S`, and requires the owner line to be exactly
  `libpq5[:arch]: <that path>` (one line; a multi-package or diversion line fails).
  New subtests are real: 4 methods, 18 subtests, all fail on the old block
  (`u0/r1-red-mutants.txt` CURRENT: 15 new fail, 0 old fail) and pass on the
  target; the tester's T1-T6 each kill at least one case. The reviewer ran 7 more
  mutants on the shipped file (`u0/r1-review-mutants.txt` section 1): R1 (ldd
  psycopg_binary text), R3 (literal /opt/venv scan), R4 (owner prefix only), R5
  (pq_bin check removed), R7 (build_version dropped) are all killed. R2 and R6
  survive, see N7. The fake's venv lives under `<tmp>/opt/venv` with
  `sys.prefix` pointed there, so a literal-path scan cannot pass vacuously (R3).
- **B2 resolved.** `u0/size.md`: `docker save` tar (bundle.sh line 281 uses
  `docker save -o`, so the method matches what `images/ke-app.tar` holds) before
  60,414,464 B (built from 737750d) -> after 58,818,048 B. The reviewer re-ran
  `docker save | wc -c`: the after tag gives 58,818,048 exactly; the d6b7035
  build gives 60,456,960, consistent with "before". Method sound. (The
  containerd store reports 265/259 MB unpacked; the tar holds compressed
  layers, so tar << image size is expected.)
- **B3 resolved.** No file names `test_app_builder_resolves_*` or
  `test_app_runtime_stage_installs_only_libpq5` any more. ADR-KE-016 *First
  tests* lists all 8 names as built; *Proof* covers `/usr/lib` or merged-usr
  `/lib`, realpath + `dpkg-query -S` owned by libpq5, no `psycopg_binary*`, the
  installed-dpkg version (not the pin) and the strict fail-closed regex; N0
  says the same. PSC-13 and PSC-25 *Lock* now define runtime packages as the
  builder's final sync `--no-dev --group pq-c --no-binary-package psycopg-c`,
  which matches app.Dockerfile line 39 (it adds `--no-editable`, which does not
  change the package set).

## Nits

- N1 resolved (PSC-25 *Windows (A34)* = PS-2.9 proof + `verify.sh fast`, as
  PSC-12). N2 resolved (README operator line on the libpq5 pin). N3 resolved
  (end anchor, named FAIL on dpkg-query failure / empty / non-numeric version,
  with subtests). N4 resolved (psycopg-binary dropped from NOTICE_LICENCE; the
  case asserts psycopg-c and no psycopg-binary). N5 resolved
  (`u0/q65-windows-uv-run.txt`, exit 0; its pasted output is missing the first
  `usage:` line, cosmetic). Housekeeping resolved by the orchestrator's
  correction line (append-only).
- **N6 partly open.** The L-13 sentence now cites security's ruling (which
  security confirmed: L-13 CLOSED), but the two new README lines are 278 and 296
  characters against the file's ~80-column wrap. Cosmetic.
- **N7 (new).** Two smoke branches are not pinned by their own test: removing
  the libpq end anchor (R2) or ignoring a realpath failure (R6) leaves every
  subtest green, because both cases then fail at `dpkg-query -S` instead. The
  subtest "ldd path runs on past libpq.so.5 (N3 end anchor)" therefore tests the
  dpkg check, not the anchor. Still fail-closed by name, so not a false pass.
  Optional: add a fake case where a realpath failure is the only fault, or
  rename the subtest.
- **N8 (new).** The shipped smoke.sh comment (line 133) says "U0 rework round 1
  (tester scratch target, not production)". It is production now. Replace it
  with a plain description of the checks (or drop the round history).
- **N9 (new).** Doc wording: N0 says "the two psycopg numbers must be
  `^[0-9]+$`"; the code string-compares them to the computed number, which is
  equivalent or stricter, but there is no such regex. N0 attributes the
  co-installed, malformed-version and dpkg-owner cases to
  `test_smoke_checks_psycopg_c_impl_in_api`; they live in the four new
  `SmokePsycopgTest` methods, which PSC-25's test list does not name.

## Security M-1: resolved

`$deb` must match `^([0-9]+)\.([0-9]+)-[0-9A-Za-z.+~]+$` before the one
`$(( ))`, which uses only the digit captures (`10#${BASH_REMATCH[n]}`). Nothing
runs between the match and its use. `pq_version`/`pq_build` only reach `!=`
string tests. The other `$(( ))` in smoke.sh (is_ipv4) is guarded by its own
regex and was already there. PoC re-run on the shipped lines (host bash 5.3,
`u0/r1-review-mutants.txt` section 2): `0+PPID[$(touch ..)]`,
`0+BASH_VERSINFO[...]`, `a[...]`, a valid version with `$(..)` or a newline
appended, empty, `x.y`, `15.19` and an epoch all fail with a named
`smoke: FAIL`, and no marker file was created. An overlong number wraps (no
execution) and then fails the compare.

## Verify runs

- `u0/r1-green-verify-fast.txt`: Ran 782, OK (skipped=8, the same 8
  Windows/uid skips), the 4 new tests ok, sentinel ok, `== verify fast: PASS ==`.
- `u0/r1-green-verify-full.txt`: `== verify full: PASS (707s) ==`; 782 OK
  (skipped=8) + gates-it 15 OK (skipped=5, model host unset, named); scan done;
  `smoke: psycopg c on Debian libpq5 15.19-0+deb12u1
  (/lib/x86_64-linux-gnu/libpq.so.5 -> /usr/lib/x86_64-linux-gnu/libpq.so.5.15)`
  at line 1611 (build host) and line 2145 (after "offline: running the offline
  client", line 2017). The line's format is the new block's, so the run used the
  shipped smoke.sh (mtime 18:58, before both runs).

## A34 Windows proof still covers the tree

sha256 now of app.Dockerfile, gates.Dockerfile, uv.lock and pyproject.toml equal
`u0/windows-run.txt` lines 141-144 (section 4 of `u0/r1-review-mutants.txt`).
Only `scripts/smoke.sh` differs, and it is a gate script (Q34 scope ruling, as
in the first review). No compose file and no build/launch/teardown script
changed since 737750d.
