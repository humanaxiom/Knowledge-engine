# platform-sbom U8c O-2: security review of the `hosts` change (U8-10)

Security, 2026-10-29. Scope: uncommitted `git diff HEAD` on `agent/platform-sbom`:
`docker/source-policy.json` (one line), `design-notes.md` (three amendment lines),
`tests/test_sbom_obligations.py`, `tests/test_sources_fetch.py`,
`tests/test_sources_lock_committed.py`, `tests/test_sources_resolve.py`; handoff/log appends.
Probe output and probe scripts: `u8/u8c-o2-security-probes.txt`.

## Verdict: PASS

No critical, high or medium findings. Nothing blocks the merge.

## Checks

| # | Check | Result |
|---|---|---|
| C1 | The change only narrows egress | Yes. The only production byte change removes `objects.githubusercontent.com` from `hosts` (10 -> 9). No host is added. `always`/`exempt` are untouched. No script, compose or Dockerfile changes. Repo-wide grep: no non-doc, non-test file names the dropped host. |
| C2 | Every host left in `hosts` is used | Yes. The committed lock's file-URL hosts are exactly 7: snapshot.debian.org 495, apt-archive.postgresql.org 8, gitlab.alpinelinux.org 344, distfiles.alpinelinux.org 21, github.com 2, files.pythonhosted.org 5, repo1.maven.org 1. All are https. `hosts` minus lock hosts = {codeload.github.com, release-assets.githubusercontent.com}. These two are the only redirect targets seen in `full-run.txt` (716 ok lines), `sample-run.txt` and the U8c green run (neo4j github.com->codeload, temurin github.com->release-assets). Lock hosts minus `hosts` = {}. The dropped host appears 0 times in all three runs. |
| C3 | Lock rules still bind each kind to its hosts | Yes. `sbom_check.KIND_HOSTS` is unchanged by the diff. `lock_entry_problems(committed lock, committed policy)` = []. Controls: dropping github.com gives 2 problems, and dropping snapshot.debian.org gives 495, so the policy-host rule is live. The new `test_policy_hosts_are_the_lock_url_hosts_and_their_redirect_targets` pins `hosts` == lock URL hosts plus the two redirect targets, in both directions. |
| C4 | A refused redirect to a host outside `hosts` prints no signed query | Yes. `_fetch_once` refuses a hop with `redirect to <host> refused: not in hosts`, which names only the host and never the URL. `sources_fetch._safe` also strips any `?...`. Probe P3 sent a 302 carrying `X-Amz-Signature`/`X-Amz-Credential` to objects.githubusercontent.com, to the same host in upper case, to the same host with a trailing dot, and to evil.example. All four were refused before being requested (calls = [github.com] only), and no query text reached either the resolver message or the `bundle_fetch: FAIL` line. P4: the real target release-assets.githubusercontent.com is still followed. |
| C5 | Policy file canonical and parseable | Yes. The file is valid JSON (keys always/exempt/hosts) with 9 unique lower-case strings without surrounding whitespace, LF line endings and a trailing newline. It loads through `sbom_check` (P2), and the diff is a single in-place list edit with the existing formatting. |
| C6 | Tests pin the narrowing | The green full run (`u8c-o2-green-verify-full.txt`, 1201 OK, verify full PASS 1107 s) runs all 7 new or re-pinned rows. That includes resolver `U8cDroppedHostTest` and fetch-client `SourceFetchDroppedHostTest`, which check refusal plus "never requested". The real sample fetch has Temurin `hops=github.com,release-assets.githubusercontent.com`. |
| C7 | Secrets / data exposure | Clean. I grepped the diff and the three new u8c evidence files for AWS/GitHub/Slack/OpenAI key shapes, private keys, X-Amz-Signature, Bearer, password/token assignments, connection strings with credentials, model-host values, profile paths and SIDs: no hits. `.env` is absent and untracked. Test fixtures use placeholder URLs only. The change exports no traces. |

## Findings

None at critical, high or medium.

Informational (non-blocking, no action required for U8c):
- I-1: `test_no_lock_problems_without_the_dropped_host` is now tautological (it filters out a host that is no longer in the policy). C3's two-way host test carries the real assertion. This is a test-quality note for the reviewer, not a security issue.
- I-2: If GitHub moves Temurin release-asset redirects back to `objects.githubusercontent.com`, the fetch fails closed by name (U8-10: "a needed host that is not listed fails closed"). That affects availability only. The remedy is another reviewed U8-10 amendment, never a silent re-add, and `REDIRECT_HOSTS` in the lock test enforces that.
- I-3 (pre-existing, not from this diff): `.gitattributes` has no `eol=lf` for `docker/source-policy.json`, so git warns that LF becomes CRLF with autocrlf. The JSON parse is unaffected. No action.
