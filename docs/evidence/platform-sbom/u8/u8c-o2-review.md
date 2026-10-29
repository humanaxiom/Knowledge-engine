# platform-sbom U8c O-2 review (reviewer, 2026-10-29)

Scope: uncommitted `git diff HEAD` on agent/platform-sbom (base 5d4ab46), 8 files.
Read: handoff U8c O-2 RED/GREEN sections; requirements.md U8-10 (l.4269); design-notes
"N4 amendment, U8" O-2 rulings (l.1451, 1468, 1496); u8/hop-hosts.md; u8c-o2-controls.txt;
u8c-o2-red-verify-fast.txt; u8c-o2-green-verify-full.txt.

## Verdict: APPROVED (no blocking findings; 3 nits)

## Checks
- Policy edit: `git diff --word-diff=porcelain` shows one token removed,
  `"objects.githubusercontent.com", `; key order, other hosts and their order, LF endings unchanged;
  valid JSON. No canonical-form rule exists for the policy (only for the lock); no policy digest in
  the lock. `hosts` is the single host source: no other script/compose file names either GitHub
  asset host (grep outside docs/ and tests/).
- Tests: test/class names diffed HEAD vs working tree: additions only (5 tests, 2 classes), none
  removed or renamed; matches u8c-o2-controls.txt. Removed `-` assertion lines are 3, each replaced
  in place: `len(hosts) == 10` -> `len(hosts) == len(U6_HOSTS)` (set equality kept, so still exact);
  two resolver fakes objects. -> release-assets.
- Fakes moved to release-assets.githubusercontent.com are equivalent: it is in ALLOW, so
  "redirect inside the allowlist" still follows; the "redirect to http" row still fails on the scheme
  (an allowed host keeps the row testing the scheme, not the host); the timeout row still names the
  hop's host; the RealOpener 302 Location is passthrough only.
- Redirect refusal pinned at both layers through the committed policy: fetch
  (`SourceFetchDroppedHostTest`, same `fetch_fail` shape as `SourceFetchHostsTest` row 2, never
  requested, nothing placed) and resolver (`U8cDroppedHostTest`, ResolveError, never requested).
  Both were RED for the expected reason (red log l.1779, l.1807) and green in the full run.
- Lock: `test_committed_lock_passes_lock_problems` (existing) and the new narrowed-policy test pass;
  new `test_policy_hosts_are_the_lock_url_hosts_and_their_redirect_targets` pins hosts ==
  lock URL hosts | {codeload, release-assets}, which fails closed on any future unused or missing host.
- Real run: green full l.2528 Temurin `hops=github.com,release-assets.githubusercontent.com`;
  `verify full: PASS (1107s)`, 1201 OK (skipped=8); RED fast 1201, failures=5, exactly the 5 O-2 rows.
- Reviewer re-run (host, targeted): 25 tests across the touched classes, OK.
- No test reads docs/evidence/** (REDIRECT_HOSTS copied as literals; only a comment mentions it).
- No count in a test, class or constant name.
- design-notes.md: 3 `+` lines, 0 `-` lines (additions only), dated, citing u8/hop-hosts.md.
- Handoff 137 lines before this section (< 200). Evidence files: no profile paths or SIDs.
- Requirement U8-10: design note amendment + test change present; security review still required
  before commit (not a reviewer finding, a gate reminder).

## Findings
### Blocking
None.

### Nits
- N-1 `tests/test_sources_lock_committed.py` `test_no_lock_problems_without_the_dropped_host`: now
  that the committed policy lacks the host, the filter is a no-op and the test duplicates
  `test_committed_lock_passes_lock_problems`. It was a useful pre-drop control; keeping it is harmless.
- N-2 `tests/test_sbom_obligations.py` `test_hosts_are_the_fetch_hosts`: the message "exactly nine
  hosts" hardcodes a count while the assertion uses `len(U6_HOSTS)`; after the set-equality check the
  length check only catches duplicates, so a message like "a host is listed twice" would not go stale.
- N-3 Staging: untracked `docs/handoffs/NEXT-SESSION.md` and `docs/knowledge-engine-claude-code-prompt.md`
  are outside this diff; the U8c commit should stage only the 8 modified files, the three
  u8c-o2 evidence files, and this review (plus security's).
