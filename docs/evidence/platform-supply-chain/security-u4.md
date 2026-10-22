# Security audit: platform-supply-chain unit 4 (2026-10-21)

Scope: `git diff 769b507` (uncommitted U4): verify.sh scan wiring (PSC-6), scan.sh L-1, app.Dockerfile I-1,
CLAUDE.md/README D9 wording, PSC-7 result. Raw probe output: `docs/evidence/platform-supply-chain/security-u4-probes.txt`.
All probes ran on scratch copies in containers labelled `ke.audit=security-u4` with `--network none`; no repo file was modified.

## Verdict: PASS

There are 0 critical and 0 high findings, so nothing blocks the merge. There is 1 medium finding (it predates U4, but U4 widens the window), 2 low, and 4 info.

## Findings

### M-1 (medium, non-blocking; predates U4): SIGTERM/SIGHUP exit non-zero but print `verify full: PASS`
- Where: `scripts/verify.sh:93-102` (`cleanup` reads `rc=$?`, and there is no INT/TERM/HUP trap). The test gap is at `tests/test_stack_scripts.py:1343-1346`.
- Probe P2 run B ran the working-tree verify.sh with stubbed stages and the scan hanging:
  - SIGTERM to the process group gives rc=143. SIGTERM to verify.sh alone gives rc=143. SIGHUP gives rc=129.
  - In all three, the **last line printed is `== verify full: PASS (0s) ==`**.
  - Cause: bash runs the EXIT trap for an untrapped fatal signal with `$?` still set by the last finished command (0), then re-raises the signal.
  - The same happens with TERM during smoke (control row), so this predates U4.
  - SIGINT works correctly: group or scan-only gives rc=130 with no PASS.
- Why it matters:
  - The exit status is correct, so CI is red.
  - The output text reads green, though. The evidence contract has agents paste the last ~15 lines, and those would end in PASS.
  - U4 adds ~76 s to `full`, which is now ~631 s. That is longer than a 600 s foreground tool timeout, so a run killed mid-scan or mid-offline-check is a realistic event.
  - Note also that the inner gates-it prints the same `== verify full: PASS ==` (u4-green-verify-full.txt:1514). Only the outer line has `(Ns)`.
- Fix (developer), either:
  - Option (a): add `trap 'exit 130' INT; trap 'exit 143' TERM; trap 'exit 129' HUP` next to `trap cleanup EXIT`, as scan.sh:79-80 does.
  - Option (b), sturdier: set `finished=1` right before `exit 0` at verify.sh:117, and have `cleanup` print PASS only when `rc -eq 0 && finished -eq 1`.
- Test: in the signal subtests at test_stack_scripts.py:1343, add `assertNotIn("verify full: PASS", out)` and a SIGHUP case.

### L-1 (low): the D9 network wording is inaccurate
- Where: `CLAUDE.md:24` ("runs one more one-shot, `scan-db` ... the only verify-only container with a route out") and `README.md:177-178` (same claim).
- Why it is wrong:
  - During `full`, the smoke ci/offline control (`scripts/smoke.sh:174`) runs `docker run --rm ... --network <project>_edge ke-app:<tag> python -m engine.netprobe`.
  - `edge` is `edge: {}` (`docker-compose.yml:205`), a normal bridge with a route out.
  - architecture.md:146 already documents this control.
  - The offline check `dind`/`offline-client` are also one-shots outside the gate services, though on an internal network (`docker-compose.offline.yml:84-88`). So "one more one-shot" undercounts as well.
- What is accurate:
  - The gate-service sentences: `gates` has `network_mode: none`, and `gates-it` is on `backend` (`internal: true`, isolated), with the gateway as its only way out.
  - The scan has `network_mode: none`.
- Exposure of the control probe: small. netprobe imports only the stdlib, and the only `.pth` in the venv is the uv `_virtualenv.pth`. Still, an interpreter from the image under test starts on a network with egress.
- Fix: the text is verbatim D9, which the human approved, so it goes architect -> human. Suggested wording: "scan-db is the only verify-only step that fetches from outside. The smoke ci/offline control also runs a throwaway ke-app container on the stack edge network, which has a route out, to reach the gateway."

### L-2 (low): the L-13 residual is not recorded where PSC-7 says, and README is silent on it
- PSC-7 (`docs/requirements.md:2836-2837`) and D6 (`docs/architecture.md:6062-6065`) name two files: `l13-psycopg-libs.md` and `scan-full.txt`. Neither exists.
  - The result is in `u4-psc7-psycopg-libs.txt`, and the scan output is inside `u4-green-verify-full.txt:1601-1910`. So the requirement pointer dangles.
- No doc claims the scan covers `psycopg_binary.libs` (grep of all `*.md`).
  - But `README.md:176` ("scans the `ke-app` image for known vulnerabilities") reads as full coverage.
  - The Q42 "if not seen" branch (`docs/open-questions.md:346-348`) is not marked as resolved.
- Fix:
  - Rename or point the evidence to the PSC-7/D6 names, or amend PSC-7 to point at the u4 files.
  - Add one README sentence: "The scan does not see the native libraries vendored in psycopg-binary (`psycopg_binary.libs`; L-13, documented residual)."
  - Record the outcome on Q42/PSC-7.

### PSC-7 / L-13 residual: my view
- Vendored versions (probe P5):
  - OpenSSL 3.5.8 (25 Aug 2026): current.
  - libpq 18.0.6: current.
  - pcre 8.32 (2012): EOL, with many known CVEs.
  - cyrus-sasl 2.1.26: known CVEs fixed in 2.1.28.
  - krb5 (el7 1.15.1, per the platform-stack-ready L-13 audit), ldap, keyutils, selinux.
- Reachability is narrow:
  - libpq talks only to the stack postgres on the internal backend network.
  - `gssencmode="disable"` is set (`engine/readiness.py:89-91`).
  - ldap/sasl are reached only through an LDAP service lookup, and there is no pg_service.conf.
  - pcre is reached only through libselinux label lookups, which libpq does not use.
  - One server-reachable path remains: a compromised postgres answering `AuthenticationGSS` drives libpq into the krb5 code.
- Residual risk: **low**. Record it as an accepted residual on Q42/PSC-7 with three parts:
  - (i) The scan cannot detect new CVEs in these 15 files.
  - (ii) The compensating control is tracking psycopg-binary releases, since the wheel libraries move with it.
  - (iii) The structural fix stays the Q42 switch to psycopg-c on the Debian libpq.
- Cheap hardening (recommendation, not a finding): add `require_auth="scram-sha-256"` to the connect at `engine/readiness.py:89`. libpq 18 supports it. libpq then refuses GSS/SSPI/md5/cleartext before any krb5 call, so the remaining krb5 path is closed.

### Info
- I-1: Under bash 5.0, an all-digit `SRANDOM` set by the caller is accepted (`ke-scan-424242`, P1 control). Two runs given the same value would collide, and the cleanup of the losing run could remove the containers and directory of the other. Only the caller can set it, and the caller already controls the environment.
- I-2: scan.sh saves `ke-app:<tag>` by tag, not by image ID (`scripts/scan.sh:92`). A second `full` from the **same checkout** (same `wt-` tag) that rebuilds between build and scan could swap the image. Optional fix: pass the image ID from after build.
- I-3: SIGINT sent to verify.sh alone (not its group) during the scan is absorbed by bash, because the child exited normally. The scan completes and the run continues. The resulting rc=0 is truthful.
- I-4: The ke-app image keeps the Debian base setuid binaries (su, mount, passwd, ...). It runs as `ke`. This predates U4 and is out of scope.

## Focus checks (all hold, except the printed text in M-1)
1. **Red cannot read as green (exit status).**
   - A scan that exits 1, is SIGKILLed or is not executable gives verify rc 1/137/126, with no PASS and no offline_check.
   - Offline failing after a passing scan gives rc=1.
   - INT gives 130. TERM/HUP give 143/129, but see M-1.
   - `scripts/scan.sh` at verify.sh:113 is a plain command under `set -euo pipefail`.
   - `torn_down=1`, so the trap does not tear down twice.
2. **Caller environment.**
   - With hostile values for COMPOSE_FILE/PROJECT_NAME/PATH_SEPARATOR/PROFILES/ENV_FILES, KE_ENV_FILE, KE_SCAN_IN, SCAN_DB_URL, GRYPE_DB_UPDATE_URL and DOCKER_DEFAULT_PLATFORM, every docker call saw the values scan.sh sets itself (P3).
   - Host GRYPE_* values reach the CLI but not the containers: their environment blocks are fixed, and the flags are pinned.
   - KE_SMOKE_OWNS_PROJECT leaks through but is unused by scan.sh and teardown.sh.
   - The tag is the one verify built and tested: ke-app:wt-33a132fbfdd7 at u4-green-verify-full.txt:3-224 is the tag scan saved. Malformed tags make 0 docker calls.
3. **L-1 is closed.**
   - Tested on bash 5.0.18 (musl) and 5.0.17 (glibc, both C and C.UTF-8).
   - SRANDOM unset or empty, and 12 hostile values (path, newline, `;`, glob, sign, Arabic-Indic/superscript/fullwidth digits): all give rc=1 with 0 docker calls and no dist entry.
   - The check runs before the trap, mkdir and docker.
   - bash 5.2 ignores an SRANDOM set by the caller.
4. **I-1 is closed** (P4).
   - `/opt/venv/.lock` is absent from the image built after the edit.
   - `find / -xdev -perm -0002 -type f` (excluding /proc, /sys, /dev, /tmp, /var/tmp) finds nothing.
   - There are no non-sticky world-writable dirs. /tmp, /var/tmp and /run/lock are sticky and empty.
   - /opt/venv and /app are all root-owned, with nothing group-writable, and there is no uv.
5. **Network wording:** see L-1.
6. **PSC-7:** the grype catalogue has 0 components for the 15 files. No doc overclaims coverage, but see L-2.
7. **Evidence sweep (u4-*).**
   - No profile paths, SIDs, tokens, keys or connection strings.
   - The "passwd" hits are the Debian package. The 127.0.0.1 and 172/192.168 addresses are loopback and ephemeral bridge addresses.
   - The secret-pattern grep of the added lines in the diff found nothing.
