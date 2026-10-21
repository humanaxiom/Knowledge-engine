# Security re-audit: harness-followups rework 5 (2026-10-18)

Scope: changes since rework 4: scripts/verify.sh (sentinel grep), tests/test_harness_followups.py, and the docs
(ADR-KE-001 in docs/architecture.md, CLAUDE.md, AGENTS.md, README.md, docs/requirements.md), plus every file
in docs/evidence/harness-followups/ and docs/evidence/platform-skeleton/. Audited snapshot (sha256):
- scripts/hooks/block-main-commit.sh 4f7d313e64b66b11c3cd75b7bf89d8a84dd3f5b7857db3bd5a897efca5ea3baf
  (UNCHANGED, same as the rework-4 audit, so the hook tables are not repeated)
- scripts/verify.sh 98e55ef27048e20b2615862f54672979e0dd8d52c3e000ed51819a6e60597443 (was ab9ef8b0...)
- scripts/test.sh 057e4682..., .github/workflows/ci.yml b1a3e54c... (unchanged)
- tests/test_harness_followups.py 307dd22b60893f349f5286d3d3687b772e8794507a758155b4b715eaacf657fd

## Verdict: PASS (0 critical, 0 high, 0 medium; 1 low new (L24, docs), L21 stays low, L23 fixed in docs; 3 info)

## 1. verify.sh sentinel grep (`grep -Pq '^...\) \.\.\. ok\r?$' "$log"`)
- Injection: the pattern is a fixed single-quoted literal; "$log" is a mktemp path, quoted. The log content is
  only data to grep. No injection surface.
- ReDoS: the pattern is a literal prefix plus one optional `\r` and anchors. There are no nested or adjacent
  quantifiers, so matching is linear. Measured in the gates image: 48 MB log of filler after the sentinel 253 ms;
  200k near-miss lines (`...ok\r\r\r x`) 178 ms; one 20 MB line of CRs 145 ms. Host Git Bash: 413-570 ms.
- PCRE availability: gates image grep 3.8 supports -P (LANG=C.UTF-8). With a grep that lacks -P (shimmed to exit 2
  with the real GNU message), verify FAILS closed: grep's own stderr line, then the sentinel FAIL message (I2).
- No pipe: SIGPIPE under pipefail is gone. Temp file left in /tmp: 0 in every case.
- I1 forging cases, rerun in the gates image (network none) with a scratch verify.sh copy and a fake test.sh:
  control PASS, CRLF log PASS. FAIL for: sub-package module, module suffix, module prefix, skip with "... ok" in the
  reason, plain skip, expected failure, FAIL result, trailing text, trailing space, leading space, embedded after
  another test's dots, dot-as-wildcard, CR then text after ok, CR-prefixed junk before the line (renders like the
  sentinel on a terminal, grep still fails), ok followed by two CRs, the line split across two lines, no sentinel,
  and a huge CR line before ok. Non-zero test.sh: FAIL (test.sh exited non-zero).
  Binary data (NUL) or invalid UTF-8 earlier in the log does not stop a real sentinel from passing (no false FAIL).
- Residual (info, unchanged): a test that prints the exact full line still passes. It needs a deliberately forged
  line and cannot hide a failing test, because the exit code still gates.

## 2. Docs vs code
- README.md and docs/requirements.md 4 call the hook a guard rail, not a security boundary, with branch
  protection (Q18) as the real control. ADR-KE-001 calls it a fail-safe text rule, not a shell lexer, and lists
  accepted bypasses. That matches the code.
- ADR-KE-001 now lists the off-main form of Table M rows 14/15 (security L23): L23 fixed (doc ask only).
- ADR-KE-001, CLAUDE.md and README sentinel text matches verify.sh (Ran N > 0 and the whole sentinel line). The CI
  claims (ubuntu-24.04, checkout pinned to a SHA, persist-credentials false) match ci.yml.
- L24 (low, docs, new): the on-main accepted bypass lists are incomplete. ADR-KE-001 says "Accepted bypasses on
  main: Table M rows 14 and 15", and requirements 4e lists bypasses only off main. The rework-4 Table A shows
  these silent on main too (also silent on base): a git alias verb (`git ci -m x`), `gh pr merge`, and
  eval/base64-encoded commands. AGENTS.md line 74 (base text, not changed in this diff) still says the hook
  "denies any commit/push attempted while on main". That is an overclaim, though README and requirements qualify it.
  Ask (documenter): extend the on-main bypass list to "words hidden from the text (variables, eval, aliases,
  encodings), gh", as off main, and soften AGENTS.md line 74 to "is a guard rail that denies most...". No code change.
- I2 (info): the grep -P (PCRE) dependency is not recorded in ADR-KE-001 (only in the developer's handoff note).
  It fails closed, but the FAIL message blames the sentinel. Optional: note it in the ADR.

## 3. Secrets, profile paths, usernames
Searched docs/evidence/harness-followups, docs/evidence/platform-skeleton, both handoffs, the prompt doc,
CLAUDE.md, AGENTS.md, README.md, architecture/requirements/open-questions/log.md, tests/, scripts/, .github/ for:
the host username and email; Windows profile paths in plain, JSON-escaped (doubled backslash), forward-slash, MSYS
(/c/Users) and URL-encoded forms; AppData; the Claude projects dir; /home/ and /Users/; the repo's absolute path in
the same forms; session UUIDs; cloud keys (AKIA/ASIA), GitHub/OpenAI/Anthropic/Slack/Google tokens, private-key
blocks, JWTs, credentialed connection strings (postgres, mysql, mongodb, redis, amqp, bolt, neo4j), and
key/secret/token/password assignments; private IPs and default hostnames.
Result: clean. The only hits are the word "scratchpad" in prose (no path), and README's upstream
github.com/<owner>/harness link, which was already in base a11842d (a public repo URL, not a secret).

## 4. Tests
tests/test_harness_followups.py: subprocess uses argv lists (no shell=True), temp dirs come from mkdtemp with an
rmtree cleanup, and there is no network. The N21 test compiles a regex read from the repo's own verify.sh (trusted
source) with Python re.

## 5. Carried over
- L21 (low): hook host timing headroom with a backslash-newline (6.8 s against a 10 s timeout). The hook is
  unchanged, so this is still open, non-blocking.
- I3 (info): host Git Bash grep 3.0 also accepts `ok` followed by two CRs (the gates image rejects it). That only
  matters when KE_IN_GATES=1 is set by hand on the host. Harmless.

## Raw output
### Gates image (knowledge-engine-gates, --network none)
```
grep (GNU grep) 3.8
badutf8_before: == verify fast: PASS == | 18ms | tmpdelta 0
big_after: == verify fast: PASS == | 253ms | tmpdelta 0
big_nearmiss: == verify fast: PASS == | 178ms | tmpdelta 0
control: == verify fast: PASS == | 21ms | tmpdelta 0
cr_mid: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 22ms | tmpdelta 0
cr_prefix: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 20ms | tmpdelta 0
crlf: == verify fast: PASS == | 23ms | tmpdelta 0
dotwild: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 24ms | tmpdelta 0
double_cr: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 31ms | tmpdelta 0
huge_line_cr: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 145ms | tmpdelta 0
huge_line_cr_ok: == verify fast: PASS == | 137ms | tmpdelta 0
lead: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 20ms | tmpdelta 0
lf_cr_split: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 18ms | tmpdelta 0
modprefix: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 17ms | tmpdelta 0
modsuffix: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 18ms | tmpdelta 0
none: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 18ms | tmpdelta 0
notok: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 19ms | tmpdelta 0
nul_before: == verify fast: PASS == | 18ms | tmpdelta 0
okplus: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 20ms | tmpdelta 0
okspace: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 20ms | tmpdelta 0
prefix: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 19ms | tmpdelta 0
printed: == verify fast: PASS == | 17ms | tmpdelta 0
skipok: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 17ms | tmpdelta 0
skipped: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 17ms | tmpdelta 0
subpkg: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 17ms | tmpdelta 0
xfail: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 16ms | tmpdelta 0
failafter(rc=1): verify fast: FAIL (test.sh exited non-zero)
LANG=C.UTF-8 LC_ALL=
nopcre control: grep: support for the -P option is not compiled into this --disable-perl-regexp binary verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run) 
nopcre crlf: grep: support for the -P option is not compiled into this --disable-perl-regexp binary verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suite did not run) 
C.UTF-8 control: == verify fast: PASS ==
C.UTF-8 crlf: == verify fast: PASS ==
C.UTF-8 nul_before: == verify fast: PASS ==
C.UTF-8 badutf8_before: == verify fast: PASS ==
```
### Host Git Bash (grep 3.0), same harness
```
badutf8_before: == verify fast: PASS == | 244ms | tmpdelta 0
big_after: == verify fast: PASS == | 570ms | tmpdelta 0
big_nearmiss: == verify fast: PASS == | 454ms | tmpdelta 0
control: == verify fast: PASS == | 246ms | tmpdelta 0
cr_mid: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 226ms | tmpdelta 0
cr_prefix: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 226ms | tmpdelta 0
crlf: == verify fast: PASS == | 228ms | tmpdelta 0
dotwild: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 234ms | tmpdelta 0
double_cr: == verify fast: PASS == | 239ms | tmpdelta 0
huge_line_cr: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 413ms | tmpdelta 0
huge_line_cr_ok: == verify fast: PASS == | 436ms | tmpdelta 0
lead: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 226ms | tmpdelta 0
lf_cr_split: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 235ms | tmpdelta 0
modprefix: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 257ms | tmpdelta 0
modsuffix: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 231ms | tmpdelta 0
none: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 225ms | tmpdelta 0
notok: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 233ms | tmpdelta 0
nul_before: == verify fast: PASS == | 231ms | tmpdelta 0
okplus: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 229ms | tmpdelta 0
okspace: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 231ms | tmpdelta 0
prefix: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 240ms | tmpdelta 0
printed: == verify fast: PASS == | 242ms | tmpdelta 0
skipok: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 234ms | tmpdelta 0
skipped: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 228ms | tmpdelta 0
subpkg: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 224ms | tmpdelta 0
xfail: verify fast: FAIL (sentinel test_top_level_unit_suite_ran did not report ok: the top-level unit suit | 222ms | tmpdelta 0
failafter(rc=1): verify fast: FAIL (test.sh exited non-zero)
```
