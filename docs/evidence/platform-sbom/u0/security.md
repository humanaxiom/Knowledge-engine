# platform-sbom U0 (PSC-25): security audit

2026-10-22, security. Scope: `git diff 737750d` (NOTICE.md, README.md,
docker/app.Dockerfile, docker/gates.Dockerfile, pyproject.toml, uv.lock,
scripts/smoke.sh, tests/fake_docker.py, tests/test_offline_bundle.py, docs) plus
the untracked tests/test_psycopg_c.py and docs/evidence/platform-sbom/**.
Extra evidence written by this audit:
- `u0/security-image-inspect.txt`: offline (`--network none`) inspection of the
  shipped image `ke-app:bundle-737750d06839` and of the pinned base.
- `u0/security-smoke-arith-poc.txt`: proof for M-1.

## Verdict: PASS

No critical or high finding. One medium (M-1), two low, five info.

## Findings

### M-1 (medium, non-blocking; fix recommended in U0): arithmetic-expansion sink in the smoke psycopg step
`scripts/smoke.sh`, new step:
```
deb="$(compose exec -T api dpkg-query -W -f='${Version}' libpq5)"
deb_major="${deb%%.*}"
deb_minor="$(printf '%s' "$deb" | sed -E 's/^[0-9]+\.([0-9]+).*/\1/')"
want=$((10#$deb_major * 10000 + 10#$deb_minor))
```
`$deb` is container-supplied. Bash evaluates array subscripts inside `$(( ))`,
so a value such as `0+PPID[$(cmd)]` runs `cmd` on the host that runs smoke.sh
(the verify host, the CI runner, the offline client). `set -euo pipefail` does
not stop it, and the sed fallback (no match: prints the input) passes the raw
value to `deb_minor` too. Proven with the smoke lines verbatim:
`u0/security-smoke-arith-poc.txt`.
- Precondition: the attacker controls what `dpkg-query` prints in the api, i.e.
  a compromised ke-app image, base or Debian package, or root in the api
  container. The api runs as uid 10001 and cannot write `/var/lib/dpkg`. So the
  precondition is high, but the result crosses a trust boundary (container to
  host, and the host has the Docker socket). Hence medium, not low.
- The rest of the step is safe: the python program is a single-quoted literal
  run with `-I`; `$pq_ext` is quoted and goes to `ldd` inside the container;
  every other use of container output is a quoted `[ ... != ... ]` or `[[ =~ ]]`.
- Fix (developer): validate before any arithmetic and fail closed naming the
  value, e.g. `[[ $deb =~ ^([0-9]+)\.([0-9]+)-[0-9A-Za-z.+~]+$ ]] || fail`,
  then use `BASH_REMATCH[1]` and `BASH_REMATCH[2]`. Optionally require
  `^[0-9]+$` for `pq_version` and `pq_build`.
- Test (tester): with the fake docker, set FAKE_LIBPQ5_VERSION to
  `0+PPID[$(touch <marker>)]`; smoke must fail and the marker must be absent.

### L-1 (low): apt trust path and unpinned transitive packages
- Trust path: `/etc/apt/sources.list.d/debian.sources` in the pinned base names
  `deb.debian.org` (bookworm, bookworm-updates, bookworm-security) with
  `Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg`, which is pinned
  by the base digest. The transport is http, and integrity comes from the
  signed InRelease and the hashes in the signed Packages index, which is sound.
  `libpq5` and `libpq-dev` are exact (`=15.19-0+deb12u1`, served from
  bookworm-security, green-verify-full lines 189, 278-280).
- Residual: apt resolves the new transitive packages (libldap-2.5-0,
  libsasl2-2, libsasl2-modules-db) and the builder and gates `gcc` and
  `libc6-dev` from whatever signed index it gets. Someone who can replay an
  older signed index can hold those back, but cannot inject unsigned content.
  This is accepted by N0. The planned control is the U3/U4 SBOM and the
  coverage check (N5). No change for U0.

### L-2 (low, process): the one unpinned `python:3.12-slim-bookworm` pull
- Local cache: `python:3.12-slim-bookworm` is `sha256:6a0e06f5...`, created
  2026-10-21, which is not the pinned `34386ef0...` (`security-image-inspect.txt`).
- Nothing derives from it:
  - Every `FROM` is digest-pinned, so a local tag cannot stand in for one.
  - A repo grep finds no reference to the image without a digest outside docs.
  - The green build fetched every locked artifact and uv verified it against
    the `uv.lock` hashes, so the lock matches what PyPI serves, wherever
    `uv lock` ran.
  - apt on the pinned base re-validated the libpq pin.
- Record: no repo file says the pull happened or what it was used for. The
  developer adds one line to the developer U0 handoff section or `u0/size.md`.
  Clean: `docker image rm python:3.12-slim-bookworm`. That is hygiene: an
  ad-hoc `docker run python:3.12-slim-bookworm` would otherwise read a newer
  base than the pinned one. Neither blocks.

### I-1 (info): supply chain of the psycopg-c build: confirmed
- `uv.lock`: psycopg-binary gone, with no marker or extra keeping it.
  `psycopg-c` 3.3.6 has an sdist only, sha256 `29c56842...19ff8`, and no wheels.
  setuptools 83.0.0, wheel 0.48.0 and packaging 26.3 (a dependency of wheel)
  are new, each with sdist and wheel sha256.
- `[tool.uv] no-build-isolation-package = ["psycopg-c"]`: the build runs in
  `/opt/venv` with only the hash-locked `pq-build` packages. The build log shows
  `Resolved 54 packages`, `Building psycopg-c==3.3.6`, `Prepared 1 package`: no
  build-environment download and nothing unpinned (green-verify-full lines
  ~490-505). `--no-binary-package psycopg-c` guards against a future wheel.
- The shipped venv has no setuptools, wheel or packaging, because the exact
  final sync dropped `pq-build` (`security-image-inspect.txt`).
- The ke-gates sync layer was CACHED in the green run, so its build log is not
  in this evidence. The same lock and flags apply, and
  `test_gates_psycopg_is_c_impl_on_debian_libpq` is ok.

### I-2 (info): images
- The shipped stage has no compiler and no `-dev` package. No gcc, cc, c++,
  pg_config, make, ld or as is on PATH. The only `gcc*` package is
  `gcc-12-base`, the base runtime package that `libgcc-s1` needs. It runs as
  uid 10001.
- ke-gates gains gcc, libc6-dev and libpq-dev. This does not widen the gate
  services:
  - Gates already run arbitrary repo Python as uid 10001, with no network
    (`gates`) or only the internal `backend` network (`gates-it`).
  - A compiler adds no capability that Python and ctypes lack.
  - No mount, capability, socket or network changed.
  - The image is neither shipped nor bundled.
  - It grows 1.46 to 1.79 GB.

### I-3 (info): scan, and the L-13 ruling: **L-13 CLOSED**
- Scan: green-verify-full lines 1978-2295. The policy is unchanged
  (`docker-compose.scan.yml` and `docker/scan-ignore.yaml` are not in the diff;
  `--only-fixed --fail-on high --show-suppressed`). `ignore: []` means no new
  ignore entry. Unsuppressed rows are Medium/Low (python, pip) only, so there
  is no fixed High/Critical, and `verify full: PASS`.
- Why L-13 (the psycopg-binary vendored-libraries residual, PSC-7 and
  platform-supply-chain security-u4) is closed:
  - The shipped image has no `psycopg_binary*` and no `*.libs` directory
    anywhere (`find / -xdev`).
  - `libpq.so.5` is owned by dpkg package `libpq5` 15.19-0+deb12u1 (`ii`).
  - The libpq5 dependency chain is in the dpkg status DB that grype reads. The
    scan shows deb-type rows for libldap-2.5-0, libsasl2-2,
    libsasl2-modules-db, libgssapi-krb5-2, libkrb5-3, libk5crypto3 and
    libkrb5support0.
  - libpq5 itself has no row only because the DB holds no matching
    vulnerability for 15.19-0+deb12u1. The same status file and the same
    cataloguer list its transaction siblings.
  - The smoke step proves the live api loads that file, from the `c`
    implementation (lines 1919 and 2453, the offline client included).
- Residual, visible and no longer hidden. Each is reported under policy and
  fails the run once Debian ships a fix (bump the pin or the base, never an
  ignore):
  - New to the image: libsasl2 CVE-2026-107161 (High, no fix) and libldap
    CVE-2023-2953 (High, Debian will not fix). libpq reaches libldap only for
    an `ldap://` lookup in `pg_service.conf`, which the engine does not use.
  - Already in the base before U0, so not new: krb5 1.20.1-2+deb12u5
    CVE-2026-107778 (High, Debian will not fix). See A66.
- Scope: the identifier L-13 is reused by a different record, platform-offline
  security L-13 ("no empty target left when mkdir -m fails",
  `tests/test_offline_bundle.py:1554`). That one is not affected.

### I-4 (info): gssencmode and PS-2.5
`engine/` is not in the diff. `engine/readiness.py:91` keeps
`gssencmode="disable"`. `test_postgres_probe_disables_gss_encryption` and
`test_every_postgres_connect_in_engine_disables_gss_encryption` are unchanged
and ok (green-verify-full lines 1640-1641). Keep the control. Its written
rationale is now stale (documenter): `docs/requirements.md` PS-2.5 (~line
578, "psycopg-binary vendors old Kerberos/SASL libraries") and the comment at
`tests/test_stack_readiness.py:480`. New rationale: defence in depth, so the
client never negotiates GSS encryption and keeps krb5 off that path.

### I-5 (info): evidence accuracy
`u0/size.md` and `u0-psycopg-c.md` list the krb5 libraries and libkeyutils1 as
pulled in by libpq5. apt installed only four new packages: libpq5,
libldap-2.5-0, libsasl2-2 and libsasl2-modules-db (green-verify-full lines
177-184). krb5 1.20.1-2+deb12u5 and libkeyutils1 1.6.3-2 are already in the
pinned base (`security-image-inspect.txt`). This matters for the PSC-14 list of
"packages the last stage adds" (U1). Documenter.

## A66: re-rating the `require_auth=scram-sha-256` follow-up
- As written it cannot be done: Debian 12 libpq 15 has no `require_auth`,
  which arrived in libpq 16. Its stated reason, the vendored el7 krb5, is gone.
- What remains: libpq 15 still answers a server `AuthenticationGSS` request by
  calling into krb5 (`gssencmode=disable` stops GSS *encryption*, not GSS
  *auth*). That krb5 is now the patched and scanned Debian 1.20.1-2+deb12u5,
  but it has an unfixed High that Debian will not fix (CVE-2026-107778). The
  precondition is a malicious or compromised postgres on the internal
  `backend` network, which already holds the data.
- **Re-rated: low, re-scoped (not retired), stays with `auth-audit`,
  non-blocking.** Replace the bullet with:
  1. Server side, now: pin `password_encryption=scram-sha-256` and a
     TCP `pg_hba` that is `scram-sha-256` only (no trust, md5 or password),
     proved by a live `full` check (`SHOW password_encryption`,
     `pg_hba_file_rules`). This protects the credential from a downgrade by an
     honest server. It does not stop a malicious server.
  2. Client side on libpq 15: the only refusal of non-SCRAM requests is
     `channel_binding=require`. libpq 13+ then rejects any non-SASL auth
     request before a GSS call (auth-audit confirms this in its RED). It needs
     TLS to postgres, which the stack does not have today, so it applies only
     if auth-audit adds backend TLS.
  3. Trigger: when the base moves to libpq 16 or later (Debian 13 trixie
     ships 17), add `require_auth=scram-sha-256` at every connect site and
     extend the PS-2.5 pair, as first planned.
  4. Compensating control meanwhile: Debian security updates through the
     `LIBPQ_VERSION` and base bumps, and the dpkg-visible scan above.

## Secret and redaction sweep
`docs/evidence/platform-sbom/**`, `docs/handoffs/platform-sbom.md`,
`docs/handoffs/archive/platform-sbom-part1.md` and `tests/test_psycopg_c.py`
were checked for:
- profile paths (`X:\Users\`, `/c/Users/`, `AppData`, `/home/`) and SIDs
  (`S-1-5-..`): none; `windows-run.txt` uses `<scratch>` and `<sid>`;
- tokens and keys (gh*_/github_pat_, AKIA, sk-, xox, JWT, Bearer, AIza,
  PRIVATE KEY): none;
- connection strings with credentials, and `*PASSWORD=` values: none. Only
  compose "variable is not set" warnings and the placeholder `.env.example`
  notes appear.

The new tests add no shell=True or pickle. `tests/fake_docker.py` runs the
smoke python program from the repo under `python -I -S -B`, which is test-only.

Tracing: U0 adds no agent step, model call, retrieval or span, so no trace
export changes.

## Re-check after rework round 1 (2026-10-23, security)

Scope: the same `git diff 737750d` plus untracked files, with round-1 changes
in `scripts/smoke.sh`, `tests/fake_docker.py`, `tests/test_psycopg_c.py`,
`tests/test_offline_bundle.py`, `tests/test_stack_readiness.py` (a comment
only), README/requirements/ADR/N0 and the new `u0/` evidence. New evidence:
`u0/security-recheck-m1-poc.txt`.

### Verdict: PASS
No critical, high or medium finding. M-1 is fixed and L-2 is done. L-1 is
unchanged and accepted by N0. I-6 to I-9 are new and info only.

### M-1: FIXED (verified)
The psycopg block of `scripts/smoke.sh` (lines ~131-193) is byte-identical to
`u0/r1-target-smoke-block.sh`. Each value from the api:
- `pq_out` (impl, version, build, ext, binary list): split by `read -r`.
  - `pq_impl` must equal `c`.
  - `pq_bin` must be `-`, so extra words in any field land there and fail.
  - `pq_version` and `pq_build` are used only in a quoted `!=` against `$want`.
    `$want` contains only digits, so an exact string match is the validation.
    Neither value reaches `$(( ))`.
- `$deb`: checked first against
  `^([0-9]+)\.([0-9]+)-[0-9A-Za-z.+~]+$`, and the step fails closed naming the
  value. Only the digit-only `BASH_REMATCH[1]`/`[2]` reach `$((10#...))`.
  Without REG_NEWLINE, `$` anchors at the end of the string, so an embedded
  newline fails the match. An empty value or a failed dpkg-query gives a
  named FAIL.
- `$pq_ext`: used only as a quoted argument of `ldd` inside the api. ldd
  failure gives a named FAIL.
- `$libpq` (sed of the ldd output): must match
  `^(/usr)?/lib/(x86_64|aarch64)-linux-gnu/libpq\.so\.5(\.[0-9]+)*$`, and
  `*psycopg_binary*` in the ldd output fails.
- `$libpq_real`: quoted argument to `dpkg-query -S` in the api. A realpath
  failure gives a named FAIL.
- `$libpq_owner`: must match `^libpq5(:[a-z0-9]+)?:\ (.+)$`, and
  `BASH_REMATCH[2]` must equal `$libpq_real` exactly. Multi-line or diverted
  output fails.
- Nothing is passed to `eval`, `sh -c` or an unquoted expansion. `compose exec`
  stops parsing its own flags at the service name, so a value starting with
  `-` cannot become a compose option.

PoC re-run (`u0/security-recheck-m1-poc.txt`): a stub `compose()` plus the
extracted block, with a `$(touch <marker>)` payload in each container value:
- 18 hostile cases, all exit 1 with a named FAIL and no marker:
  - `$deb`: PPID / BASH_VERSINFO / `a[...]` subscripts, a valid prefix with a
    subscript suffix, an embedded newline, a leading subscript, an empty
    value, a dpkg-query failure, and a 23-digit major (wraps; mismatch FAIL);
  - `pq_out`: version, build, ext and impl;
  - ldd x2, realpath, owner x2.
- The baseline passes.
- Positive control: the round-0 lines in the same harness create the marker,
  so the harness detects host execution.

Tests: `test_smoke_never_evaluates_the_libpq5_version` (PPID and
BASH_VERSINFO payloads, marker absent, plus `x.y`) and
`test_smoke_fails_closed_on_dpkg_query_errors` are ok in
`r1-green-verify-fast.txt` (lines 962-964) and in the full run (782 tests, OK).

### L-2: DONE
- `u0/u0-lock-regen.md` records the pull of `python:3.12-slim-bookworm`
  (id 6a0e06f5ba0b, used once for `uv lock`), no container using it, and the
  `docker image rm` output (`Untagged` and `Deleted: sha256:6a0e06f5...`).
- The pinned `sha256:34386ef0cb08...` is kept and is the digest in every
  `FROM` of both Dockerfiles.
- Host check today: `docker image inspect python:3.12-slim-bookworm` fails
  (the tag is absent), and the pinned image is present.
- No non-doc repo file names the image without a digest.

### Docs: accurate
- README (line ~184): L-13 closed on 2026-10-23, citing this file, with the
  correct reason (the vendored libraries the scan could not see).
- requirements.md:
  - PSC-7 (~2965) and the follow-up (~3211-3222) mark L-13 CLOSED by security.
  - The A66 text matches this audit: low, re-scoped and not retired,
    auth-audit, non-blocking.
  - The libpq 15 and krb5 GSS-auth caveat is stated correctly.
  - The three steps are server scram-only plus `password_encryption`, then
    `channel_binding=require` only with backend TLS, then `require_auth`
    once libpq is 16 or later.
- ADR-KE-016 (*Proof* and *Effects*, ~6577-6586) states the round-1 proof
  (merged-usr path, realpath plus `dpkg-query -S` libpq5, no psycopg_binary*,
  strict fail-closed regex for M-1, L-13 closed). Line 6715 cites A66.
- The PS-2.5 rationale (requirements ~499-502, `test_stack_readiness.py:480`
  comment) is now defence in depth. Security I-4 is resolved.
- `size.md` and `u0-psycopg-c.md` list the four packages apt added. I-5 is
  resolved.

### New code: nothing unsafe
- `tests/fake_docker.py`:
  - runs the smoke's own literal python program through
    `subprocess.run([sys.executable, "-I", "-S", "-B", ...])` (a list, no
    shell) against a stub site in `mkdtemp`, removed in `finally`;
  - embeds the Dockerfile pin with `repr`;
  - has no network, socket, pickle, yaml or eval of external data.
- `tests/test_psycopg_c.py`:
  - its PEP 508 evaluator is a tokenizer and does not call `eval`;
  - the lock fixtures are inline strings;
  - the gates test reads only `/proc/self/maps` and skips outside `KE_IN_GATES`.
- `test_offline_bundle.py` and `test_stack_readiness.py`: data or comment
  changes only.
- The fast run is in `gates`, which has no network. Compose files,
  `verify.sh`, CI and `docker/scan-ignore.yaml` are not in the diff. The
  round-1 scan policy is unchanged: `ignore: []`, unsuppressed rows
  Medium/Low only.

### New findings (info, non-blocking)
- **I-6:** smoke does not shape-check `$pq_ext` and `$libpq_real` on the
  host.
  - Each reaches only a quoted argv in the api and a message, so there is no
    host sink.
  - A compromised image can fake any self-report, so this is outside the
    check's purpose.
  - Optional hardening: anchor `$libpq_real` to
    `^/usr/lib/(x86_64|aarch64)-linux-gnu/libpq\.so\.5(\.[0-9]+)*$`.
- **I-7:** FAIL messages and the success line echo container text raw. A
  hostile image could put terminal escape sequences into CI logs. This is
  log cosmetics only, and other smoke steps already do the same.
- **I-8 (reviewer nit, not security):** `scripts/smoke.sh:133` still says
  "(tester scratch target, not production)" in production code.
- **I-9 (analyst):**
  - `docs/open-questions.md` Q66 still says "Security re-rates ... at U0
    review", and its "Recommended" line says the risk is "removed by the
    switch itself".
  - Add a one-line outcome pointer to requirements ~3211 (re-rated low,
    re-scoped, GSS auth still reaches krb5).
  - The A66 text there leaves out this audit's point 4 (compensating
    control: Debian security updates through the pin and base bumps, and the
    dpkg-visible scan). Add it if wanted.

### Evidence sweep (round-1 files)
Files checked: `r1-green-verify-fast.txt`, `r1-green-verify-full.txt`,
`r1-red-verify-fast.txt`, `r1-red-mutants.txt`, `r1-target-smoke-block.sh`,
`r1_smoke_check.py`, `size.md`, `q65-windows-uv-run.txt`, `u0-lock-regen.md`
and `security-recheck-m1-poc.txt`. Results:
- Profile paths (`X:\Users\`, `/c/Users/`, `AppData`, `/home/`) and SIDs: none.
  The PoC file uses `<scratch>`.
- Tokens and keys (gh*_, github_pat_, AKIA, sk-, xox, JWT, Bearer, AIza, hf_,
  PRIVATE KEY): none.
- Credentialed connection strings and `PASSWORD=` values: none. `passwd`
  appears only as the Debian package name in the scan.
- `KE_*` values: none. The model keys are unset in the full run.
- The only IPs are private Docker bridge addresses from the network probe.
