# ci-speed CS-7 close-out: security audit

Date: 2026-10-21. Role: security. Branch `agent/ci-speed`, HEAD `24b6839`,
working tree diff (`git diff HEAD`) plus untracked `docs/evidence/ci-speed/cs7/`
and `docs/evidence/ci-speed/ci/`.

## Verdict: PASS

No critical, high or medium findings. One informational note (I-CS7-1).

## 1. ci.yml diff

`git diff HEAD -- .github/workflows/ci.yml`: one changed line (17),
`timeout-minutes: 29` -> `32` plus its comment. A full-file diff against
`HEAD:.github/workflows/ci.yml` shows only line 17 differs. Unchanged and confirmed:

- `permissions: contents: read` (workflow level). The CI logs confirm the
  GITHUB_TOKEN got `Contents: read`, `Metadata: read` only.
- `runs-on: ubuntu-24.04`.
- `actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5.1.0`, with
  `persist-credentials: false`.
- One run step, `./scripts/verify.sh full`.
- No `env:`, no `secrets.*`, no new step, action or trigger. Triggers are still
  `push` and `pull_request`; there is no `pull_request_target`.
  `concurrency` with `cancel-in-progress: true` is unchanged.

Other diff files: `tests/test_stack_ready_docs.py` changes the constant
`CI_TIMEOUT_MINUTES` 29 -> 32, plus the docstring, comment and assertion
message. The assertion logic is unchanged and no test is weakened.
`docs/requirements.md`, `docs/handoffs/ci-speed.md` and `docs/log.md` are docs
or logs only.

## 2. Timeout increase: abuse path

I-CS7-1 (info, not a finding). The job's worst-case runtime goes up by
3 minutes (29 -> 32, about +10%). That is the most runner time a hung job can
use. On a private repo it can cost at most 3 extra billed minutes per hung
run. `cancel-in-progress` per ref limits overlap. The timeout is a hang guard,
not a security control: anyone who can push a branch, or open a PR that runs
CI, can edit `timeout-minutes` in their own change anyway. Fork PRs run with
the read-only token and no secrets. The value is evidence-based (slower green
run 21.1 min x 1.5 = 31.65 -> 32) and stays well under the 360-minute default.
No abuse path opens that was not already there.

## 3. Evidence scan

Scope: `docs/evidence/ci-speed/cs7/` (ci-timeout.md, doc-verify-fast.txt,
red-verify-fast.txt, green-verify-fast.txt, green-verify-full.txt,
orchestrator-verify-full.txt) and `docs/evidence/ci-speed/ci/`
(ci-39530356210.log, ci-39530367383.log, ci-39559700392.log,
ci-39559708963.log, permodule-39499437202-vs-39559700392.txt).

| Check | Pattern (grep -E) | Result |
|---|---|---|
| Windows SIDs | `S-1-5-[0-9]+(-[0-9]+)+` | 0 |
| Windows profile paths | `([A-Za-z]:[\/]+\|/[a-z]/\|/mnt/[a-z]/)Users[\/]+...`, `AppData`, `USERPROFILE`, `HOMEPATH` | 0 |
| Unix home paths | `/(home\|Users)/<name>` | only `/home/runner` (36 hits: the GitHub runner account, not a profile; kept) |
| Token shapes | `gh[pousr]_`, `github_pat_`, `AKIA`/`ASIA`, `sk-`, `sk-ant-`, `xox?-`, `AIza`, `-----BEGIN ... PRIVATE KEY`, JWT `eyJ..`, `scheme://user:pass@`, `Bearer <20+>` | 0 |
| Assigned secrets | `(PASSWORD\|_KEY\|SECRET\|TOKEN)[A-Z_]*=<value>`, `NEO4J_AUTH=` | 0 |
| Keyword hits | password/secret/token/credential/authorization | test names; compose warnings that `KE_STORES__*__PASSWORD` is unset (names only, no value); GitHub-masked `token: ***` and `AUTHORIZATION: basic ***` from checkout. No values. |
| Model-host keys | `KE_MODEL_UPSTREAM`, `KE_EGRESS_ALLOWLIST` | names only: "is empty" skip messages, no host or URL values |
| IPs | IPv4 | 127.0.0.1 and docker bridge addresses (172.18-20.0.2, 192.168.144.2) on throwaway stacks; not sensitive |
| High-entropy strings (40+ chars, non-hex) | `[A-Za-z0-9+/_-]{40,}` | paths, URLs, runner temp UUIDs only |

Result: 0 secrets, 0 profile paths, 0 SIDs. Nothing to redact.
`C:/repos/Knowledge-engine` paths are not under a user profile and are kept.

Out of scope (not audited): the untracked `docs/knowledge-engine-claude-code-prompt.md`.
Per the earlier orchestrator rulings it is excluded from commits.

## 4. Findings by severity

- critical: none
- high: none
- medium: none
- low: none
- info: I-CS7-1 (timeout +3 min raises the worst-case runner minutes per hung job; no new abuse path)
