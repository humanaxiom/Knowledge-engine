# Security re-check: platform-supply-chain unit 4, rework round 1 (2026-10-22)

Scope: uncommitted U4 after rework 1 (`git diff 769b507`). Covers verify.sh M-1 (traps and finished flag), scan.sh N5, the CLAUDE.md/README network text (L-1), and the PSC-7/D6/Q42 L-13 record (L-2).
Raw probe output: `docs/evidence/platform-supply-chain/security-u4-r1-probes.txt`. Probes ran on scratch copies, in containers labelled `ke.audit=security-u4-r1` with `--network none` (bash 5.2, bash 5.0 musl, ubuntu 20.04 bash 5.0 glibc). One reduced run used the host Git Bash 5.3 on a scratch copy with docker stubbed. No repo file was modified apart from this verdict, the probes file, the handoff line and the log line.

## Verdict: PASS

0 critical, 0 high. M-1, L-1 and L-2 are closed. Two new lows (L-3, L-4); neither blocks.

## Closed

### M-1: closed
- Fix: `scripts/verify.sh:88` `finished=0`; `:96-109` cleanup prints PASS only when `rc -eq 0 && finished -eq 1` (`:100`), otherwise a FAIL line (`:102-107`); `:113-115` traps INT, TERM and HUP to `exit 130`, `exit 143` and `exit 129`; `:130` `finished=1` right before `exit 0`.
- Probe Q1: 47 rows on bash 5.2 and on bash 5.0 (identical), plus 15 rows on Git Bash. INT, TERM, HUP, QUIT and USR1 were sent to the process group, to verify.sh alone and to the stage alone, during the scan and during smoke. KILL was sent to the stage and to verify.sh.
  - INT, TERM and HUP to the group, to verify alone or to the stage alone: rc 130/143/129 every time, with no outer `verify full: PASS (`, and the last line is `== verify full: FAIL (exit N) ==`. Teardown ran once and nothing later ran. Git Bash gives the same result.
  - A stage killed by SIGKILL gives rc 137 and FAIL.
  - USR1 (an untrapped fatal signal; the case M-1 described) gives rc 138 and `FAIL (stopped before the last stage; no PASS)`. The finished flag catches every signal bash does not trap.
  - QUIT to the group gives rc 131 and FAIL. QUIT to verify alone or to a stage alone is ignored by bash (the bash manual: "In all cases, Bash ignores SIGQUIT"). The stage ran to completion, so the PASS that follows is truthful.
- Paths where an outer PASS still prints, none of them false:
  - (a) QUIT to verify or to a stage alone: ignored, nothing was interrupted.
  - (b) INT to smoke alone while its child survives: the bash wait-and-cooperative-exit rule lets smoke finish, and it did finish.
  - (c) A stage that traps the signal and exits 0 (the hostile `swallow0` rows). No real stage does this: scan.sh and offline_check.sh exit 130/143, HUP is re-raised as 129, and smoke.sh has no INT/TERM trap.
  - (d) An untrapped signal in the instant after `:130 finished=1`. Every stage has already passed at that point. TERM, INT and HUP there still give FAIL.
- Tests: `tests/test_stack_scripts.py:1325-1335` (INT/TERM/HUP during the scan) and `:1368-1383` (during smoke) assert status 128+n and no `verify full: PASS`. They pass only because the fake docker prints nothing; see L-3.

### L-1: closed
- `CLAUDE.md:23-31` and `README.md:158-161, 176-186` match the topology:
  - `gates` has `network_mode: none` (`docker-compose.yml:184`).
  - `gates-it` is on `backend` only (`:192`), and `backend` is `internal: true`, isolated (`:207-210`).
  - The gateway is the only service on `edge` (`:65`, `:205`).
  - `scan-db` has no `network_mode` (project default bridge, route out; `docker-compose.scan.yml:20-29`). `scan` has `network_mode: none` (`:33`).
- The new sentence is accurate. `scripts/smoke.sh:174` runs `docker run ... --network "${project}_edge" --entrypoint python <ke-app image> -m engine.netprobe <gateway edge ip> <port>`. That is the control probe, on the stack `edge` network, which has a route out.
- README "`scan-db` is not the only container with a route out" is accurate and does not claim to be a full list (the gateway is also on edge).
- Nit: README:159 "The gate services have networking disabled" then gives `gates-it` a network. The sentence qualifies it at once, so it is not a finding.

### L-2: closed
- PSC-7 (`docs/requirements.md:2836-2853`) and D6 (`docs/architecture.md:6076-6105`) now point at `u4-psc7-psycopg-libs.txt` and `u4-green-verify-full.txt` lines 1601-1914. Both exist, and the range runs from `== scan: ignore entries` to `scan: scan took 4s`. No `.md` outside the handoff still names `l13-psycopg-libs.md` or `scan-full.txt`.
- The residual is recorded as recommended in requirements PSC-7 `:2845-2853`, architecture D6 `:6092-6105` and Consequences `:5825-5831`, and open-questions Q42 `:350-360`:
  - It is an accepted residual, rated low.
  - The compensating control is tracking psycopg-binary releases.
  - The mitigation is `gssencmode=disable`.
  - The structural fix is the Q42 switch to Debian libpq.
  - Q42 and PSC-5 for psycopg are MOOT for the scan (`requirements.md:2805-2810`, `architecture.md:6067`).
- `require_auth="scram-sha-256"` is a follow-up (`requirements.md:2992-3006`, `architecture.md:6103-6105`).
- No overclaim:
  - README:181-183 says the scan does not see `psycopg_binary.libs`.
  - Grep of README, CLAUDE.md, AGENTS.md, CHANGELOG, requirements, architecture and open-questions finds no claim that the scan covers them.
  - CHANGELOG has no scan entry yet. When the marketer writes one, it must keep the L-13 caveat.

### N5: confirmed
- The `scripts/scan.sh:36-40` regex `^ke-scan-[0123456789]+$` has no `LC_ALL`, and it still rejects every value tested except ASCII digits. Probe Q3: real scan.sh, caller-set SRANDOM on bash 5.0, with:
  - musl in the default locale and in C.UTF-8;
  - glibc in C.UTF-8, in LANG/LC_COLLATE/LC_CTYPE=C.UTF-8, and in C with real UTF-8 bytes.
- Rejected with rc 1, 0 docker calls and no dist entry: Arabic-Indic, Devanagari, Thai, superscript, fullwidth and mathematical-bold (4-byte) digits; mixed ASCII and Arabic-Indic; Arabic-Indic zero; trailing or embedded newline; space; sign; `1a`; `../1`; `1;id`; `1*`; empty; unset.
- Accepted: `0`, `123`, `4294967295`. A bracket list of explicit characters does not depend on collation, unlike a `[0-9]` range.
- On bash 5.2, a caller-set SRANDOM is ignored.

## New findings (non-blocking)

### L-3 (low): the inner half prints the same `== verify full: PASS ==`
- `scripts/verify.sh:156` (the gates-it half, `mode=full`) prints `== verify full: PASS ==` in every `full` run that gets past the integration tests. That includes runs that later fail in smoke, scan or offline_check, and runs that are interrupted.
- Example: `u4-rework1-green-verify-full.txt:1513`. In probe Q1 this line is in all 47 rows, and in the KILL-to-verify rows it is the **last line** printed.
- Exposure: the outer line differs (`(Ns)`), and since M-1 every catchable end prints FAIL last. Two cases can still mislead:
  - A run that ends with no trap: SIGKILL, the OOM killer, or a Windows tool timeout (TerminateProcess). Full now takes about 625 s.
  - Any reader that greps for `verify full: PASS`.
- Also, the M-1 tests (`assertNotIn("verify full: PASS", out)`) hold only because the fake docker is silent.
- Fix (developer):
  - Give the inner line its own wording, for example `== verify full (gates-it half): PASS ==` when `KE_IN_GATES=1`. Check first that no test or doc pins the old text.
  - Make the fake gates-it echo that line, so the tests can tell the two apart.

### L-4 (low; predates U4; offline_check.sh unchanged): the M-1 shape in offline_check.sh
- `scripts/offline_check.sh:151-167` traps only INT and TERM.
- A HUP (or USR1, or any other untrapped fatal signal) during the offline check runs cleanup with a last status of 0. Cleanup prints `== offline_check: PASS (Ns) ==` and the script then dies 129/138 (probe Q2).
- verify.sh still exits 129 and prints `FAIL (exit 129)` last. So this is misleading text only.
- Fix: trap HUP to `exit 129` (and add HUP to the trap reset at `:154`), or use a finished flag as in verify.sh.
- scan.sh also leaves HUP untrapped (`:79-80`), but its cleanup prints no PASS, so it gives 129 with no misleading text. Adding HUP there is optional, for symmetry.

### Info
- I-8: SIGKILL to verify.sh leaves the verify project and the orphaned stage running. An untrapped USR1 to verify alone runs the EXIT-trap teardown while the orphaned smoke stage keeps running (probe row "USR1 to verify in smoke"). Both fail closed. Nothing more is possible for KILL.
- I-9: the M-1 guarantee assumes each stage reports a signal as non-zero. All four real stages do today. Keep that in mind for any future stage script.

## Evidence sweep
- All 19 untracked files under `docs/evidence/platform-supply-chain/` (u4-rework1-*, review-u4*, security-u4*), and the added lines of `git diff 769b507`, contain:
  - no profile paths or SIDs;
  - no keys or tokens (AKIA, gh*_, github_pat_, sk-, xox, PRIVATE KEY, JWT, AIza, glpat-);
  - no credentialed connection strings and no e-mail addresses.
- Addresses are loopback and docker bridge only. The model keys were unset in the rework-1 full run.
