# platform-sbom part 10

Plan item: platform-sbom. U7 plan and U7a gate detail.
Live handoff: [../platform-sbom.md](../platform-sbom.md).

## 2026-10-25 — architect (U7 plan)
- Asked: an N5 amendment that makes U7 implementable in TDD units. Wrote it at design-notes l.709-1123 (before N6), plus a pointer bullet at the end of ADR-KE-016 in `docs/architecture.md`.
- Split (amd64 only; arm64 at U12):
  - U7a: pure lock functions and `lock-check` in `sbom_check.py`. Loop `fast`, `full` before the gate.
  - U7b: `sources_resolve.py`, `sources_lock.sh` and `sources-resolve` in `docker-compose.sources.yml`, for neo4j, temurin, pypi and maven, plus security's second fetch. Loop `full`.
  - U7c: the deb, apk and pgdg routes. Loop `fast`, `full` before the gate.
  - U7d: the committed lock, the committed-lock test, the sizes, security's lock review and the CLAUDE.md row. Loop `full`.
- Coverage: the rows `classify_document(..., always, exempt)` marks `needs`, mapped by purl (item 2). The fixtures give 182 keys: deb 152, pgdg 3, apk 19, and 1 each for neo4j, temurin and maven, plus pypi 5. Listed only, no entry: 42 ke-neo4j maven rows. The gcc-12 and gcc-14 keys are present (Q69).
- `neo4j` is always `manual`: the tool prints the TOFU candidate (exit 3), security fetches a second time, then the developer writes the entry. Every other kind is `generated`. Files are streamed into the hashers, never stored.
- Open: O1 (human) PGDG sources for the postgres image need a tenth host, `apt-archive.postgresql.org`; O2 phoenix PyPI packages need `pypi.org` JSON at lock time; O3 the fixtures may differ from fresh images (U7d). O1 and O2 must be ruled before U7c.
- Next: the orchestrator rules O1 and O2, then tester RED for U7a (item 6 (a)-(h)).

## 2026-10-25 — analyst (U7)
- Q71 drafted in `docs/open-questions.md` for the human: PGDG sources (postgresql-16, postgresql-18 with its libpq5, postgresql-common). Recommended: a `pgdg` kind and a tenth host, `apt-archive.postgresql.org`. Decide before U7c. In `docs/requirements.md` PSC-23 (with a pointer in PSC-22's hosts bullet): O2 says lock-time resolution calls are not file URLs and `hosts` is unchanged; O3 says U7d stops if the fresh images differ from the U3 fixtures; plus the Q71 pointer. Flag: N5 shows no GitHub release API endpoint, although O2 names one.

## 2026-10-25 — tester (U7a RED)
- Asked: the U7a RED (N5 amendment U7, item 6 (a)-(h); orchestrator U7a rulings 1-4).
- Tests: new `tests/test_sources_lock.py`, 12 methods: LockNeeds (2), LockSchema (4, with 87 bad shapes), LockCoverage (4), SampleKeys (1), LockCheckCli (1). Carry (g) is in `PolicyU6SchemaTest` (future `reviewed` against the UTC date; `today` is a parameter) and carry (h) is in `U6ExemptMatchesTest` (`#sub/path`, `?type=jar#sub`); both are green, as guards.
- Pinned interface (my reading where the amendment names only the function; flag if wrong):
  - `lock_needs(policy, docs) -> (needs, problems)`, with `needs[key] = {kind, packages: [{image, purl, spdxid}]}`;
  - `lock_problems(lock_text, policy, docs, arch)` takes the file text, for the canonical-form rule;
  - `sample_keys(lock_dict, arch)`.
- Pinned facts: the 182 fixture keys are a constant in the test (deb 152, pgdg 3, apk 19, neo4j 1 with 73 packages, temurin 1, maven 1, pypi 5); my run equals the architect's, including Debian sources per image (70/61/21/78 plus 3 pgdg). The exact miss and stale messages are pinned too.
- pgdg (Q71): the tenth host is not added. Tests that need a passing pgdg entry add `apt-archive.postgresql.org` to an in-memory policy copy only; a row checks that the committed hosts refuse it.
- RED: `scripts/verify.sh fast`, 949 ran. 12 methods fail (98 incl. subtests), 0 errors, sentinel ok (`u7a/red-verify-fast.txt`).
- Reach: PASS on attempt 2, 949 OK; repo restored (`u7a/target-reach-verify-fast.txt`).
  - Attempt 1 failed only PS-1.2 rule 2: no `scheme://host` literal is allowed in Python (`...attempt1.txt`). The target checks the snapshot URL via `urlsplit` host and path instead.
  - The developer must keep it so: no URL literals in `sbom_check.py`.
- Controls: `u7a/u7a_controls.py`, 45 rows (40 must fail, 5 must pass), 0 unexpected, gates image. Full output: `u7a/red-mutants.txt`.
  - The asked mutants: a kind's host check dropped (neo4j, pypi; deb's per-kind rule masks it there), http accepted, a stale entry ignored, a miss message with a wrong key, sample picking the largest, the `.pgdg` mapping dropped, raw version, epoch dropped.
  - Plus 19 more: mapping, coverage, sample and CLI.
- Next: developer GREEN, loop `fast`, `full` before the gate.

## 2026-10-25 — developer (U7a GREEN)
- Asked: U7a GREEN (pure half of the source lock). Copied `u7a/target-sbom_check.py` -> `scripts/sbom_check.py` (`lock_needs`, `lock_problems`, `sample_keys`, `lock_text`, `component_key`, `lock-check` subcommand; no URL literals, `urlsplit` checks only); diff against HEAD read, no refactor. `unlicensed_report`, `_missing`, the classifier and `exempt_matches` untouched; no lock file committed.
- `scripts/verify.sh fast`: PASS (`u7a/green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u7a/green-verify-full.txt`). Controls: `u7a/green-controls.txt`.
- Next: reviewer and security. Nothing committed.

## 2026-10-25 — reviewer (U7a)
- Asked: review U7a (`lock_needs`, `lock_problems`, `sample_keys`, `lock_text`, `lock-check`; carry rows g/h) against the N5 amendment U7. Verdict: **CHANGES REQUESTED**. Detail: `u7a/review.md`.
- B1: the neo4j `upstream` is not bound to the file's sha256. `alg: sha1` (or sha512) with any value and the second-fetch `from` passes, and two neo4j files pass. Fix: exactly one file, `alg == "sha256"`.
- B2: `urlsplit` drops tab/CR/LF, so a URL whose host is `files.py<TAB>thon.org` passes as `files.pythonhosted.org`; a space or newline in the path also passes. Fix: refuse a URL that is not printable ASCII without spaces, before `urlsplit`.
- Nits, for the architect where they are design gaps:
  - N1: per-kind URL host and file-name binding (a maven jar on `files.pythonhosted.org` passes).
  - N2: a deb entry with only the `.dsc` passes.
  - N3: pgdg has no per-kind rules (carry to U7c).
  - N4: entry key sets are not exact.
  - N5: non-str `arches` crash.
  - N6: U7d needs `docker/sources.lock.json text eol=lf` (autocrlf=true here).
  - N7: bad-shape rows only assert a non-empty problem list.
- Conformant: the mapping table (my independent derivation gives the same 182 keys), the exact miss/stale/jrt-fs messages, coverage, sample, CLI, PS-1.2 (no URL literal), carry rows. Controls re-run: 45/40/5, 0 unexpected (`u7a/reviewer-controls.txt`). Probes: `u7a/reviewer-probes.txt`.
- Next: developer fixes B1/B2 with tester rows (loop fast); orchestrator routes N1/N2 to the architect before U7b/U7c.

## 2026-10-25 — security (U7a)
- Asked: gate audit of the pure lock half (`lock_needs`, `lock_problems`, `sample_keys`, `lock_text`, `lock-check`). Verdict: **PASS** (no critical/high/medium). Detail: `u7a/security.md`; probes `u7a/security-probes.txt` (script `u7a/security_probes.py`).
- Rejected: userinfo (incl. a backslash before `@`), IDN/punycode/fullwidth dot, trailing dot, ports, upper-case or percent-encoded host, IP literals, non-https (incl. `HTTP`), query/fragment, bad hashes, sizes <= 0/bool/float/str, unsafe names (`../`, absolute, NUL), alg mismatches; the deb `.dsc` is bound to snapshot `/file/<its sha1>`. `lock_needs`: 32 odd purls and 458 real needs rows each give a key or a problem (182 keys, 0 problems). ReDoS worst 0.04 s.
- Low, non-blocking: L-1 URL charset (`https://files.python<TAB>hosted.org/...` passes: `urlsplit` drops tab/CR/LF; require printable ASCII and canonical form). L-2 no kind-to-host/path binding except deb; pgdg has no per-kind rule (one arbitrary file passes). L-3 the miss message and `_kind_problems` print the key raw (SBOM `upstream=ev%1b%5b2Jil%401` gives raw ESC): `_clean(key)`. L-4 `u7a/reviewer-probes.txt` l.2 has a profile path: redact before commit (reviewer).
- Info: I-1 `HTTPS://` accepted; I-2 no size cap, name not tied to URL, `CON` accepted; I-3 uncoverable keys (`deb:x@1`, `temurin:jdk-21`) fail closed as misses; I-4 deep-JSON RecursionError traceback, `sample_keys` only after a clean check; I-5 `from` uncleaned (not printed).
- Next: L-3 and L-4 are cheap to fold into the current rework; L-1/L-2 before the first real lock (U7b/U7c), with security re-check.


## 2026-10-25 — tester (U7a rework r1 RED)
- Asked: round-1 RED for review B1, B2, N1-N7 and security L-1..L-3, I-1, I-2, I-4 (orchestrator rulings 1-9; design-notes N5 amendment U7, "Rework round 1", l.1163 on).
- Tests: `tests/test_sources_lock.py` gains 7 `ReworkR1*` classes (12 methods): Neo4jBinding, Charset, Binding (incl. pgdg until Q71), CompletenessAndKeys, Types, CleanAndSize, Cli.
- Changes to U7a tests (superseded by round 1, CLAUDE.md *Contradictions*), plus N7:
  - The 87 old bad-shape rows each assert a targeted substring (`BAD_SHAPE_SUBSTRINGS`, the target's wording); this is ruling 8, review N7.
  - pgdg: the tests no longer add the PGDG host. The small set swaps pgdg for `pypi:psycopg-c`, and the full lock's only problems are its pgdg files (`pgdg_free`).
  - The neo4j file name is now `<ver>.tar.gz`.
- RED: `scripts/verify.sh fast`, 961 ran. 12 methods fail (89 incl. subtests): the 11 new methods plus `test_bad_shapes` (16 rows whose wording is new). 0 errors; sentinel ok (`u7a/r1-red-verify-fast.txt`). `test_good_names` (`psycopg_c-3.3.6.tar.gz` etc.) is green, as a guard.
- Reach: the r1 target overlaid, verify fast PASS, 961 OK; repo restored (`u7a/r1-target-reach-verify-fast.txt`). Target: `u7a/r1-target-sbom_check.py`, still with no URL literal.
- Controls: `u7a/r1_controls.py`, which supersedes u7a_controls.py. 84 rows (78 must fail, 6 must pass), 0 unexpected, gates image. Full output: `u7a/r1-red-mutants.txt`.
  - Mutants asked for: urlsplit before the charset check, the round-trip dropped, the host binding dropped (one per kind: deb, apk, neo4j, temurin, pypi, maven), neo4j sha1 accepted, two neo4j files, a `.dsc`-only deb, an extra key, upper-case HTTPS, the size cap dropped, the key printed raw.
  - Plus: pgdg allowed, the last-segment and `..` rules, PEP 503, apk commit binding, the types guard, and lock-check's catches.
- Added to kill two mutants: lock-check also gets a malformed policy (`hosts: 5`, raises inside the check) and a deeply nested SBOM (RecursionError while reading). The nested lock alone is caught inside `lock_problems`, so it could not show the outer catch. Each gives exit 1, one line, no traceback.
- Flags: substrings pin the target's message wording; the developer keeps it. I-4 "`sample_keys` only after a clean check" is a docstring note (no caller until U8). Security L-4 (redaction of `u7a/reviewer-probes.txt`) is not mine.
- Next: developer GREEN, loop `fast`, `full` before the gate.

## 2026-10-25 — developer (U7a rework r1 GREEN)
- Asked: U7a rework r1 GREEN (review B1/B2 + nits, security lows; design-notes "Rework round 1"). Only `scripts/sbom_check.py` changed: copied `u7a/r1-target-sbom_check.py`; diff against the U7a GREEN read, no refactor (printable-ASCII fields, round-trip URL check, per-kind host/path binding, neo4j one file with sha256 upstream, size cap, type-safe `lock_problems`, fail-closed `lock-check`). Classifier, `exempt_matches`, `unlicensed_report` untouched; no URL literals.
- `scripts/verify.sh fast`: PASS (`u7a/r1-green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u7a/r1-green-verify-full.txt`). Controls: `u7a/r1-green-controls.txt`.
- Next: reviewer and security re-check. Nothing committed.

## 2026-10-25 — reviewer (U7a rework r1)
- Asked: re-check U7a rework round 1 (rulings l.1163-1298). Verdict: **CHANGES REQUESTED**. Detail: `u7a/review-r1.md`.
- Closed: B1 (neo4j one file, sha256 bound), B2 (printable ASCII before parsing, round-trip, lower-case https), N1 (per-kind host/path/name), N2, N4, N5 (no traceback), N7, L-3, the 4 GiB cap. 182 keys unchanged. r1 controls re-run: 84/78/6, 0 unexpected (`u7a/reviewer-r1-controls.txt`).
- R1-B1: encoded or backslash dot-segments bypass the "no `..` segment" rule (sbom_check.py l.1170). Temurin is only prefix-bound and pypi only suffix-bound, so `.../releases/download/%2e%2e/%2e%2e/%2e%2e/%2e%2e/attacker/repo/.../OpenJDK21U-...tar.gz` passes, as do `%2E%2E`, `..%2F` and `x\..\..\` (backslash is printable). On pypi, `/%2e%2e/psycopg_c-3.3.6.tar.gz` passes. Fix: refuse `\`, `%2e`, `%2f` and `%5c` (any case) and `.`/`..` segments in every url path. Probes: `u7a/reviewer-r1-probes.txt`.
- Nits: R1-N1, bind the temurin tag and asset version exactly at U7b (item 4's form). R1-N2, the CLI exception line is not ruling 11's `lock-check: FAIL (<class>: <msg>)` text.
- Next: orchestrator/architect confirm the R1-B1 rule; tester rows; developer GREEN; re-check.

## 2026-10-25 — security (U7a rework r1)
- Asked: re-check the U7a rework round 1 (charset and round-trip, per-kind binding, `_clean`, size cap, no-traceback CLI). Verdict: **PASS** (no critical/high/medium). Detail: `u7a/security-r1.md`; probes `u7a/security-r1-probes.txt` (script `u7a/security_r1_probes.py`).
- Closed: L-1 (tab/LF/CR/space/NUL/non-ASCII, `HTTP(S)://` upper, `../`), L-2 except temurin (maven, apk, pypi, deb, neo4j bindings hold for every probe; pgdg fails closed until Q71), L-3 (0 raw control lines), L-4 (reviewer-probes redacted), I-2 (4 GiB cap), I-4 (wrong types are problems; CLI one line, no traceback). `lock_needs` = GREEN (182 keys); `unlicensed_report` identical; r1 evidence clean.
- New low, non-blocking: R1-L1 `PYPI_DIST_RE` quadratic on over-long names (`a-` x 50000: 7.2 s; binding runs even when the name check failed) — skip binding on a failed name. R1-L2 temurin: tag, asset version and feature in the name are not bound (`OpenJDK17U-...` in temurin21, `Evil-jdk-sources_x.tar.gz`, extra segments pass) — bind the exact path at U7b.
- Info: I-6 printable non-RFC-3986 path chars (`%2e%2e`, backslash, quotes, `<>`, `//`) pass; host and kind binding still hold.


## U7a region as it stood at commit 9b1754f (verbatim from the live doc)

### U7 (source lock; in progress)
Plan: design-notes N5 amendment U7.

### 2026-10-25 — architect (U7 plan)
- Split U7a-d, 182 keys, O1 -> Q71 human, O2 ruled, CLAUDE.md row draft.
- Detail: archive/platform-sbom-part10.md; evidence design-notes N5 amendment U7

### 2026-10-25 — analyst (U7)
- Q71 drafted; O2/O3 recorded in PSC-23.
- Detail: archive/platform-sbom-part10.md; evidence docs/open-questions.md, docs/requirements.md

### 2026-10-25 — tester (U7a RED)
- U7a RED: 12 failing, reach PASS, controls 45 (0 unexpected).
- Detail: archive/platform-sbom-part10.md; evidence u7a/red-verify-fast.txt, u7a/target-reach-verify-fast.txt, u7a/red-mutants.txt

### 2026-10-25 — developer (U7a GREEN)
- U7a GREEN: verify fast + full PASS 975 s, controls 0 unexpected.
- Detail: archive/platform-sbom-part10.md; evidence u7a/green-verify-fast.txt, u7a/green-verify-full.txt, u7a/green-controls.txt

### 2026-10-25 — reviewer (U7a)
- CHANGES REQUESTED: B1 neo4j second-fetch binding, B2 URL charset, N1-N7.
- Detail: archive/platform-sbom-part10.md; evidence u7a/review.md, u7a/reviewer-controls.txt, u7a/reviewer-probes.txt

### 2026-10-25 — security (U7a)
- PASS: lows L-1 charset, L-2 kind-host binding, L-3 raw key, L-4 profile path (redacted).
- Detail: archive/platform-sbom-part10.md; evidence u7a/security.md, u7a/security-probes.txt

### 2026-10-25 — tester (U7a rework r1 RED)
- r1 RED: 12 failing, reach PASS, controls 84 (0 unexpected).
- Detail: archive/platform-sbom-part10.md; evidence u7a/r1-red-verify-fast.txt, u7a/r1-target-reach-verify-fast.txt, u7a/r1-red-mutants.txt

### 2026-10-25 — developer (U7a rework r1 GREEN)
- r1 GREEN: verify fast + full PASS 969 s, controls 0 unexpected.
- Detail: archive/platform-sbom-part10.md; evidence u7a/r1-green-verify-fast.txt, u7a/r1-green-verify-full.txt, u7a/r1-green-controls.txt

### 2026-10-25 — reviewer (U7a rework r1)
- CHANGES REQUESTED: round-0 closed; new R1-B1 encoded dot-segments, R1-N1 temurin binding, R1-N2 CLI line.
- Detail: archive/platform-sbom-part10.md; evidence u7a/review-r1.md, u7a/reviewer-r1-controls.txt, u7a/reviewer-r1-probes.txt

### 2026-10-25 — security (U7a rework r1)
- PASS: L-1/L-3/L-4/I-2/I-4 closed; lows R1-L1 pypi regex, R1-L2 temurin binding.
- Detail: archive/platform-sbom-part10.md; evidence u7a/security-r1.md, u7a/security-r1-probes.txt

### 2026-10-25 — tester (U7a rework r2 RED)
- Asked: round-2 RED, orchestrator rulings 1-5: plain paths (review R1-B1), the exact temurin binding (R1-N1), the CLI FAIL line (R1-N2), linear name checks (security R1-L1), and the pypi path layout. Design-notes l.1300 on.
- Tests: `tests/test_sources_lock.py` gains 5 `ReworkR2*` classes (5 methods): PlainPath (the reviewer's five inputs plus 13 more spellings), TemurinBinding (10 rows), PypiPath (7 rows plus the `psycopg_c` good row), Redos (timed), and CliLine (exact `lock-check: FAIL (<Class>: ...)` for 6 cases).
- Superseded in the test file (CLAUDE.md *Contradictions*): the good pypi url is now `/packages/<2>/<2>/<60 hex>/<name>` (ruling 5). The round-1 `../..` row now expects "url path is not a plain path" (ruling 1).
- RED: `scripts/verify.sh fast`, 966 ran. 6 methods fail (40 incl. subtests): the 5 new methods plus ReworkR1Binding's `../..` row. 0 errors; sentinel ok (`u7a/r2-red-verify-fast.txt`).
- Reach: the r2 target overlaid, verify fast PASS, 966 OK; repo restored (`u7a/r2-target-reach-verify-fast.txt`). Target: `u7a/r2-target-sbom_check.py`, with no URL literal.
  - `lock-check` now parses the lock in its read block, so the 100000-deep lock is a FAIL line, as the architect's item 3 pins.
  - The pypi dist part is split at its last `-` (no backtracking).
- Controls: `u7a/r2_controls.py`, which supersedes r1_controls.py. 106 rows (100 must fail, 6 must pass), 0 unexpected, gates image. Full output: `u7a/r2-red-mutants.txt`.
  - Mutants asked for: the `%` check dropped, `%2B` allowed anywhere, backslash allowed, `.` segment allowed, temurin tag not bound, asset version not bound, CLI wording changed (both paths).
  - Plus: `%2b` in the tag, an empty segment, the lock not parsed in the read block, the pypi path binding dropped, hex case, segment length, and the old regex with the skip dropped.
- Equivalent mutants, not rows:
  - "the old regex" alone: under the 255-character name cap with the skip in place, it is linear in practice. The row kept is the round-1 path (old regex with the skip dropped).
  - "the FAIL message not `_clean`ed": every caught exception's text already escapes control characters, since OSError shows the file name by repr.
- Flag: ESC in a file name raises `OSError` on Windows and `FileNotFoundError` on Linux; that row accepts any `*Error` class, and the plain missing file pins `FileNotFoundError`.
- Next: developer GREEN, loop `fast`, `full` before the gate.

### 2026-10-25 — developer (U7a rework r2 GREEN)
- Asked: U7a rework r2 GREEN (review R1-B1 + nits, security R1-L1; design-notes "Rework round 2"). Only `scripts/sbom_check.py` changed: copied `u7a/r2-target-sbom_check.py`; diff against the r1 target read, no refactor (`_plain_path` rule, exact temurin tag/asset binding, `lock-check: FAIL (<Class>: <msg>)` line, linear pypi name check via `_pypi_parts`, pypi path layout). Classifier, `exempt_matches`, `unlicensed_report` untouched; no URL literals.
- `scripts/verify.sh fast`: PASS (`u7a/r2-green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u7a/r2-green-verify-full.txt`). Controls: `u7a/r2-green-controls.txt`.
- Next: reviewer and security re-check. Nothing committed.

### 2026-10-25 — reviewer (U7a rework r2)
- Asked: re-check U7a rework round 2 (rulings l.1300-1382). Verdict: **APPROVED**. Detail: `u7a/review-r2.md`.
- Closed:
  - R1-B1: `_plain_path` refuses all five inputs, plus `/./`, `%2F`, trailing `/` and `//`.
  - R1-N1: the temurin tag and asset are bound exactly.
  - R1-N2: `lock-check: FAIL (<Class>: <msg>)` on a missing file, invalid JSON, 100000-deep nesting and an in-check exception.
  - Security R1-L1: linear; 0.001 s on 255- and 50008-character names.
  - pypi `/packages/<2>/<2>/<60>/<name>`.
- Every kind's path is now exact or a full match on validated fields. I found no remaining path or binding fail-open (`..;`, `;x`, a trailing-dot host and an empty path are all refused).
- 182 keys unchanged. r2 controls re-run: 106/100/6, 0 unexpected (`u7a/reviewer-r2-controls.txt`). Probes: `u7a/reviewer-r2-probes.txt` (temp path redacted).
- Next: security's re-check; orchestrator commit gate. U7b confirms the temurin asset and tag form (exact amendment only).

### 2026-10-25 — security (U7a rework r2)
- Asked: re-check U7a rework round 2 (linear pypi name check, exact temurin binding, plain paths, pypi Warehouse layout, CLI FAIL line). Verdict: **PASS** (no critical/high/medium; no new finding). Detail: `u7a/security-r2.md`; probes `u7a/security-r2-probes.txt` (script `u7a/security_r2_probes.py`).
- Closed: R1-L1 (`a-` x 50000 name 0.002 s, 255-char names 0.001 s; `psycopg_c-3.3.6.tar.gz` still good) and R1-L2 (temurin exact: feature, tag, asset, `%2B` forms, JRE/JDK binary, `from` all bound; the baseline equals the design form `/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz`).
- Plain-path rule holds for `%2e%2e`/`.%2e`/`%2E.`/`..%5c`/backslash/`%2f`/`//`/`/./`/trailing `/`/`%25`/`%252e`/`%c0%ae`/`%00`; Unicode forms stop at the ASCII rule. pypi layout rejects upper-case/59/61 hex, extra/missing segments, legacy paths. CLI: one `lock-check: FAIL (...)` line for missing/invalid/deep/bad-UTF-8. `lock_needs` = r1 (182 keys); ReDoS worst 0.035 s; r2 evidence clean.
- Info: I-7 the FAIL line echoes the operator's `--lock` path (redact profile paths in evidence); I-6 carried.
- Next: nothing from security for U7a; U7b to confirm the temurin asset form against the release page.

### 2026-10-25 — orchestrator (U7a commit gate)
- Rework rounds used: 2 of 5 (r1: B1 neo4j second-fetch binding, B2 URL charset + security L-1..L-3, per-kind host/name binding, exact keys, no tracebacks; r2: R1-B1 plain URL paths, exact temurin tag/asset, CLI line, linear pypi check, pypi path layout). Rulings: design-notes N5 amendment U7 l.709-1382.
- Review APPROVED (r2; no further shape), security PASS (r2; no new finding; I-7 operator path in the missing-file line: evidence redaction rule applies).
- Orchestrator verify full PASS 968 s (966 unit + 15 integration, sentinel ok; `u7a/orchestrator-verify-full.txt`). Diff read: component_key, lock_needs, lock_problems (_url_problems, _plain_path, _binding_problems, _pypi_parts), sample_keys, lock_text, lock-check. Sentinel untouched. No lock file committed (U7d).
- Also rides: ADR-KE-016 pointer (architecture.md), Q71 (PGDG, for the human) and O2/O3 records, N5 amendment U7 and its rounds, handoff archive part9 (U6 close) and new part10.
- Open for the human: Q71 (PGDG host/kind) before U7c; the CLAUDE.md "Generated artifacts" row for `docker/sources.lock.json` lands at U7d (draft in N5 amendment U7 item 7).
- Commit APPROVED. Next: U7b (`scripts/sources_resolve.py`, `scripts/sources_lock.sh`, `docker-compose.sources.yml` `sources-resolve`; neo4j/temurin/pypi/maven; security second fetch of the Neo4j tarball into sources-provenance.md; U7b confirms the real temurin asset name).

## 2026-10-25 — security (U7b second fetch)
- Asked: independent second fetch of the Neo4j 5.26.32 tag tarball, the tag commit, and the Temurin sidecar for U7b comparison. Recorded in `docs/evidence/platform-sbom/sources-provenance.md` (commands, UTC times, hop hosts, hashes; nothing unpacked or run).
- Neo4j (image confirms 5.26.32): hops `github.com` 302 then `codeload.github.com` 200. **sha256 `182ae2e5c3807bc3d7a09770dbf450d2e8667080bde93b3b6c829125db0f91e3`, size 20907800.** Tag `5.26.32` = annotated `d766af19...` pointing to commit `27f24499b751708815d42c8cf26bfb6597b3516c`, which the tarball pax comment names. `upstream.from` = `second fetch: security 2026-10-25, docs/evidence/platform-sbom/sources-provenance.md`.
- Temurin (image confirms 21.0.12.1+1): hops `github.com` 302 then `release-assets.githubusercontent.com` 200 (no `objects.` host). Sidecar: `573057d03584ae793fb7ec9a14c76d826d9187a53efeefd99da47403a5308234  OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz` (one line), so the asset and tag form exist.
- Flags: the lock check proves byte identity with this reviewed fetch, not Neo4j authorship; GitHub tarballs are not byte-stable (a mismatch fails closed, then a re-TOFU). The fetch ran on the same dev box and network as the developer: process-independent, not network-independent (N5 says "another host or network"); orchestrator to decide whether a third fetch from another network is needed.
- Next: developer compares the resolver candidate with these values; any disagreement goes to the orchestrator.

## 2026-10-25 — tester (U7b RED)
- Asked: the U7b RED with a fake network (orchestrator rulings 1-4; design-notes N5 amendment U7, items 1, 3, 4 and "Resolution endpoints").
- Tests: new `tests/test_sources_resolve.py`, 22 methods. It covers:
  - the hop rules with item 4's messages, and the parsers;
  - the temurin, maven and pypi (uv.lock and pypi.org JSON) routes, whose entries pass U7a's `lock_problems`;
  - the neo4j candidate (printed, never written, exit 3), the merge rules and the resolver CLI (0/1/2/3, writes only `out/lock.new.json`);
  - `sbom_check.py lock-needs` (`lock_needs_doc`, `tar_file_text`);
  - `docker-compose.sources.yml` hardening, plus an oracle with 14 bad shapes;
  - `sources_lock.sh`, statically and with fake docker: a missing image, bad arguments, the 7 GiB floor; never called by verify or CI.
- Pinned interface (my reading, flag if wrong):
  - the hook is the module-level `OPENER(url, timeout)`, which tests patch after importing by path; no `--fake-net` flag;
  - the functions are `fetch`, `stream`, `parse_sha256_txt`, `parse_sha1`, `uv_lock_sdist`, `pypi_json_sdist`, `temurin_tag`, `resolve`, `main`;
  - needs.json is `{"format": 1, "needs": {key: {kind, packages, route}}}`.
- Design gaps resolved as follows (flag):
  1. **Tag source:** ruling 1 says the resolver derives the Temurin tag from the saved tar, but its service mounts no tar, while the architect's item 3.3 gives the tar to `lock-needs --tar`. So `lock-needs` reads `/opt/java/openjdk/release` into the temurin route as text, and the resolver derives and cross-checks the tag from it.
  2. **deb/apk/pgdg keys in U7b:** they are skipped and named on stderr. lock-check then fails the run.
  3. **`--prune` is not in U7b.**
- Contradiction resolved (CLAUDE.md): `tests/test_stack_compose.py`'s bind-mount rule gains a `sources-resolve` exemption, as for `sbom`, citing N5 amendment U7 item 3.4. `SourcesComposeTest` pins the mounts.
- RED: `scripts/verify.sh fast`, 988 ran. 20 methods fail (22 incl. subtests), 0 errors, sentinel ok; the 2 oracle/guard tests pass (`u7b/red-verify-fast.txt`; attempt 1 predates a rename).
- Reach: the u7b targets overlaid (`sources_resolve.py`, `sources_lock.sh`, `docker-compose.sources.yml`, `sbom_check.py` with `lock-needs`), verify fast PASS, 988 OK; restored (`u7b/target-reach-verify-fast.txt`).
  - Attempts 1-3 are kept: shellcheck SC2317 on the trap function; the bind-mount exemption; and a pass before a test rename.
  - The targets have no URL literal.
- Controls: `u7b/u7b_controls.py`, 62 rows (58 must fail, 4 must pass), 0 unexpected, gates image. Full output: `u7b/red-mutants.txt`. The 37 mutants cover the resolver, lock-needs, compose and the script, plus HEAD.
- Not covered by fake-docker tests in U7b: the full `sources_lock.sh` happy path (save, sbom, lock-needs, resolve, lock-check, move); it is static only. GREEN needs `full` and the A34 Windows proof for the compose file, and the real run is U7b evidence.
- Next: developer GREEN.

## 2026-10-25 — developer (U7b GREEN)
- Asked: U7b GREEN (resolver tool for the singleton kinds). Copied `u7b/target-sources_resolve.py` -> `scripts/sources_resolve.py` (new, +x), `target-sources_lock.sh` -> `scripts/sources_lock.sh` (new, +x), `target-docker-compose.sources.yml` -> `docker-compose.sources.yml` (new), `target-sbom_check.py` -> `scripts/sbom_check.py` (adds `lock-needs`, `tar_file_text`, `lock_needs_doc`). Diff against HEAD read, no refactor; existing classifier/exempt/lock functions untouched. `scripts/sources_lock.sh` NOT run against the network (U7d is the real run).
- `scripts/verify.sh fast`: PASS (`u7b/green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u7b/green-verify-full.txt`). Controls: `u7b/green-controls.txt`.
- Commit note: the two new scripts need `git add --chmod=+x`. Next: reviewer and security. Nothing committed.

## 2026-10-25 — reviewer (U7b)
- Asked: review U7b (resolver, sources_lock.sh, docker-compose.sources.yml, lock-needs) against the N5 amendment U7 and the U7b pins. Verdict: **CHANGES REQUESTED**. Detail: `u7b/review.md`.
- B1 (`sources_resolve.py` fetch/stream/text):
  - Mid-body TimeoutError, IncompleteRead and ConnectionResetError, plus OPENER raising InvalidURL or BadStatusLine, escape as tracebacks; none gives the item 4 why-text or the pin 4 FAIL line (nothing is written).
  - There is no overall byte deadline (item 3.5) and no size cap (the probe streamed 1.22 GiB).
  - Fix: map the errors to ResolveError and add a deadline and a 4 GiB cap, with rows.
- B2 (`sources_lock.sh` l.139-148): the "only neo4j misses" grep sees only the first 20 lock-check lines.
  - Input: the fixture lock without neo4j, pandas and pgdg gives 79 problems, 6 not neo4j; the first 20 are all neo4j, so the script writes the lock and exits 3.
  - This is the first real U7c run (pgdg waits on Q71).
  - Fix: decide in Python (for example `lock-check --pending-neo4j`, exit 3), with a row.
- Nits:
  - N1: hops allow a port or userinfo on an allowed host.
  - N2: jq is required with no check (absent on this Git Bash host).
  - N3: the temp file in `docker/` is not in the trap.
  - N4: no six-image check.
  - N5: tar_file_text ignores whiteouts.
  - N6: write and type errors in main are tracebacks.
- Conformant: hop rules and messages, the four routes (entries pass lock_problems), merge semantics, writes only out/lock.new.json, lock-needs, compose hardening, script quoting/trap/no KE_* to containers, PS-1.2. Controls re-run: 62/58/4, 0 unexpected (`u7b/reviewer-controls.txt`). Probes: `u7b/reviewer-probes.txt`.
- Next: tester rows for B1/B2; developer GREEN; re-check.

## 2026-10-25 — security (U7b)
- Asked: gate audit of the resolver (`sources_resolve.py`), `sources_lock.sh`, `docker-compose.sources.yml` and `lock-needs`. Verdict: **PASS** (no critical/high). Detail: `u7b/security.md`; probes `u7b/security-probes.txt` (fake network).
- Holds: no redirect reaches a non-listed host (scheme-relative, http, `@evil`, IDN, trailing dot, data/file/javascript, tab tricks all refused; max 5 hops); hashes over exact bytes, no decoding, nothing stored; TOFU prints only, manual entries never touched; script quoting, traps, `.env.example` only, no KE_* into the container; compose matches `sbom` but for the default bridge; tar read without extraction.
- **M-1 (medium, fix before U7c writes a real lock):** the pending rule greps the first 20 `lock-check` lines; with the real fixtures (73 neo4j misses) 5 pgdg misses are hidden and the lock is written with exit 3 "neo4j pending". Decide pending over the full problem list in Python.
- Low: L-1 port/userinfo accepted on allowed hosts in `fetch()` (apply U7a `_url_problems` per hop); L-2 `pypi.org` allowed for every route; L-3 no size cap/total deadline in `stream()` (3 GiB streamed); L-4 body-read errors escape as tracebacks (still nothing written); L-5 the lock lands 0600 (unreadable to the gates uid on Linux; chmod 0644). Info I-1..I-4 in the file.

## 2026-10-25 — tester (U7b Windows proof)
- Asked: the A34 Windows proof of `docker-compose.sources.yml`, `sources_lock.sh`, `sources_resolve.py` and `lock-needs` on the U7b GREEN tree. Own project `ke-tester-u7bwin`; Git Bash and PowerShell 7.6.7; Docker Desktop 29.5.2.
- Verdict: **A34 FAIL**, because of one defect the proof found; every other check passes (`u7b/windows-run.txt`, redacted).
  1. compose config resolves from Git Bash (`MSYS_NO_PATHCONV`, `cygpath -m`) and from PowerShell, and refuses when the required keys are missing.
  2. `sources-resolve` runs hardened. A bad argument exits 2; a dry run (empty needs) exits 0 and writes only `/out/lock.new.json` as the caller. Root, `/opt/ke` and `/in` are read-only; CapEff is 0; NoNewPrivs is 1; `docker inspect` matches.
  3. The `sources_lock.sh` refusals pass: bad arguments exit 2; a missing image gives the exact FAIL line; the floor check (df shim) refuses; no lock or temp file is written, and the work dir is removed.
  4. **DEFECT:** `docker-compose.sbom.yml` sets `TMPDIR=/out/tmp`, and `bundle.sh` creates `out/tmp`, but `sources_lock.sh` does not create `$work/sboms/tmp`. So syft fails ("could not determine source") and a real run fails at step 2 (fail closed). The fix is one `mkdir` plus a test; no fake-docker happy-path test covers step 2, the gap I flagged in the U7b RED. My target had the same omission.
     - With `tmp/` created, `lock-needs --tar` on a real saved `ke-neo4j:local` gives 182 keys, the same set as the fixtures, with the real Temurin release text.
     - O3: the neo4j key has 72 packages against the fixture's 73 (`neo4j-genai-plugin`, removed with `products/` at U4b).
  5. Teardown: nothing is left for either project and no `ke-sources-*` project; the hashes of the 20 files are identical start to end.
- Flags:
  - the gates image's own ENV puts `KE_IN_GATES` into the resolver's environment (the compose environment is literal only). Ruling 3: accept, or unset it.
  - an unmarked repo-root `.env`, from another role at 09:32Z, was present; this run never read or touched it.
- Next: developer fixes the `sboms/tmp` defect (with a test), with security's M-1/L-*; then the A34 item 4 path is re-run.

## 2026-10-25 — tester (U7b rework r1 RED)
- Asked: the round-1 RED for review B1, B2, N1-N6, security M-1, L-1..L-5, I-1, I-3 and the A34 finding (design-notes "U7b rework round 1", items 1-13). Project `ke-tester-u7br1`.
- Tests: 25 methods fail, all in the new classes; 2 guards already pass on U7b GREEN.
  - `tests/test_sources_resolve.py`:
    - ReworkR1TransportTest (item 1): errors at open and mid-body give the exact texts. `DEADLINE` is 600 with `<host>: deadline <n> s passed: <url>`. `MAX_BYTES` is 4294967296 with `<host>: more than <n> bytes: <url>`, and the read stops at the chunk that passes the cap.
    - ReworkR1MainTest (N6): a body error, an OSError writing /out and wrong-typed needs each give one FAIL line, exit 1 and no lock.new.json.
    - ReworkR1RealOpenerTest (item 10): `ERROR_BODY_LIMIT` is 1048576. The default OPENER reads at most 1 MiB of a 302/404 body (urllib `build_opener` patched, no network).
    - ReworkR1HopRulesTest (item 3): 14 bad hop shapes are refused and never requested; a hop query is allowed; first-URL rules keep the `%` exemption.
    - ReworkR1PypiScopeTest (item 8): pypi.org only for the JSON request, never on a hop.
    - ReworkR1KeysTest (item 11): 12 bad keys give `<key>: not a valid lock key`, no request and the one FAIL line.
    - ReworkR1LockScriptRunTest (items 2, 4, 5, 6, 9, 12), the script end to end on fake docker:
      - exit 0 and exit 3, in order: save/sbom x6, lock-needs (`--tar ke-neo4j=/tars/ke-neo4j.tar`), resolve, `lock-check --pending-neo4j`; the lock 0644, no temp file left, `git diff --stat` printed;
      - B2 end to end: 25 neo4j misses hide a later pgdg miss; exit 1, lock untouched;
      - tools first (jq, git, docker), each with the exact FAIL line and no docker call;
      - exactly six images (extra redis / missing valkey);
      - the trap removes the temp file when chmod or mv fails;
      - no `ke-neo4j.tar` literal.
  - `tests/test_sources_lock.py` ReworkR1PendingNeo4jCliTest (item 2):
    - exit 3 only for a non-empty list of neo4j misses only;
    - the reviewer's 79-problem lock (6 non-neo4j) exits 1;
    - clean exits 0;
    - stale-neo4j, neo4j-shape and non-canonical rows exit 1;
    - the 20-line print cut is unchanged.
- `tests/fake_docker.py`:
  - models `compose -f docker-compose.sources.yml run sources-resolve`: the real resolver read from its compose bind, binds interpolated, OPENER = FAKE_RESOLVE_NET, URLs logged to FAKE_RESOLVE_LOG;
  - `run ... sbom_check.py` now remaps `IMAGE=<path>` arguments (`--sbom`, `--tar`). The U7b script never reached this, so it was unmodelled.
- Interface pinned: `DEADLINE`, `MAX_BYTES` and `ERROR_BODY_LIMIT` are module constants read at use (tests patch them); `lock-check --pending-neo4j`.
- Targets (reach-proven; compose unchanged): u7b/r1-target-sources_resolve.py, u7b/r1-target-sources_lock.sh, u7b/r1-target-sbom_check.py.
- Evidence:
  - RED `u7b/r1-red-verify-fast.txt`: verify fast FAIL, 1016 run, failures=64 / errors=8 by subtest, all in the new classes; lint PASS.
  - Reach `u7b/r1-target-reach-verify-fast.txt`: verify fast PASS, 1016 OK.
  - Controls `u7b/r1_controls.py` + `u7b/r1-red-mutants.txt`: 71 rows (66 must-fail, 5 must-pass), 0 unexpected. Attempt 1 is `u7b/r1-red-mutants-attempt1.txt`; its 2 unexpected rows were harness gaps, fixed.
- Ruling recorded (item 13): `KE_IN_GATES` is the gates image's own ENV marker and is accepted. The no-`KE_*` rule covers only the compose `environment:` block and pass-through from the caller or `.env`.
- A34 after the round-1 GREEN: re-run step 4 (the script's SBOM + lock-needs path) and step 3 (the refusals, now including tools and six images) on Windows. Steps 1, 2 and 5 are unchanged (compose unchanged).
- For the developer:
  - Keep `mv -f -- "$tmp" docker/sources.lock.json` alone on its line: the U7b static check counts writes by line end. A failed mv exits through set -e and the trap.
  - `urljoin` drops tabs and lower-cases a scheme, so check the raw Location (printable, literal `https://`) as well as the joined URL.
- No repo-root `.env` was present during these runs; I created none.

## 2026-10-25 — tester (U7b r1 controls + A34 re-run)
- Asked: fix the `r1_controls.py --base repo` baseline, re-run it, then re-run A34 steps 3 and 4 on Windows against the round-1 GREEN.
- Controls:
  - The harness read its U7b GREEN baseline from the repository, which now holds round 1, so 25 rows could not fail. It now reads the saved `u7b/target-sources_resolve.py`, `target-sources_lock.sh` and `target-sbom_check.py`; these were byte-equal to the U7b GREEN tree when I checked at the r1 RED.
  - Re-run in the gates image (`ke-tester-u7br1`): 71 rows, 66 must-fail, 5 must-pass, **0 unexpected**. Every mutant anchor applied to the developer's code.
  - Evidence: `u7b/r1-green-controls.txt`; the developer's run is kept as `u7b/r1-green-controls-attempt1.txt`.
- A34 steps 3 and 4: **PASS** (`u7b/windows-run.txt`, addendum 2026-10-25).
  - 3a-3e all refuse before any save, and nothing is left behind: bad arguments (exit 2), missing image, the floor, tools first (jq, git, docker), six images (extra redis, missing valkey).
  - 4: the script saved and SBOM'd the six real images with `sboms/tmp` in place, and lock-needs produced 181 keys with the real Temurin release text. A shim stopped the run before the network; the script failed closed with the lock unchanged.
  - Teardown is clean; the 21 hashed files are identical at start and end.
- O3 drift (for the orchestrator, not a script defect):
  - The fresh key set is fixtures minus `pypi:psycopg-c@3.3.6` and `deb:postgresql-15@15.19-0+deb12u1`, plus `pypi:psycopg-binary@3.3.6`.
  - Cause: `ke-app:local` here was built on 2026-10-20, before the psycopg-c Dockerfile (23e3c9b), so it is stale.
  - A real lock run needs `scripts/build.sh` first; U7d's key-set check would stop on this.
- Unintended real-network resolves, from my driver's bugs: attempts 1-2 (the PATH shims did not apply, then the case pattern was wrong) ran the real resolver three times (redacted logs: `u7b/windows-run-r1-attempts.txt`).
  - Each fetched maven, then neo4j (the github tarball).
  - Each then failed closed on `pypi:psycopg-binary@3.3.6: ... 0 sdists, want 1`, which comes from the stale image.
  - One FAIL line each, exit 1, nothing written, no leftovers.
- `.env`: a repo-root `.env` (mtime 04:09 local, not mine) was present throughout. The script reads only `.env.example`, and I did not touch the `.env`.

## U7b region as it stood at commit 6d8fa4d (verbatim from the live doc)

### 2026-10-25 — security (U7b second fetch)
- Neo4j 5.26.32 sha256 `182ae2e5...91e3`, 20907800 B, commit `27f24499...`; Temurin sidecar `573057d0...8234`; hops github.com -> codeload / release-assets.
- Detail: archive/platform-sbom-part10.md; evidence docs/evidence/platform-sbom/sources-provenance.md

### 2026-10-25 — tester (U7b RED)
- U7b RED: 20 failing, reach PASS, controls 62 (0 unexpected), OPENER hook.
- Detail: archive/platform-sbom-part10.md; evidence u7b/red-verify-fast.txt, u7b/target-reach-verify-fast.txt, u7b/red-mutants.txt

### 2026-10-25 — developer (U7b GREEN)
- U7b GREEN: verify fast + full PASS 983 s, controls 0 unexpected.
- Detail: archive/platform-sbom-part10.md; evidence u7b/green-verify-fast.txt, u7b/green-verify-full.txt, u7b/green-controls.txt

### 2026-10-25 — reviewer (U7b)
- CHANGES REQUESTED: B1 body errors/deadline/cap, B2 pending-neo4j from truncated output, N1-N6.
- Detail: archive/platform-sbom-part10.md; evidence u7b/review.md, u7b/reviewer-controls.txt, u7b/reviewer-probes.txt

### 2026-10-25 — security (U7b)
- PASS: M-1 = B2, L-1..L-5, I-1..I-4.
- Detail: archive/platform-sbom-part10.md; evidence u7b/security.md, u7b/security-probes.txt

### 2026-10-25 — tester (U7b Windows proof)
- A34 FAIL on one defect: `sources_lock.sh` lacks `$work/sboms/tmp`; all other checks PASS. O3: fresh ke-neo4j 72 vs 73 Neo4j packages (genai plugin), keys unchanged.
- Detail: archive/platform-sbom-part10.md; evidence u7b/windows-run.txt

### 2026-10-25 — tester (U7b rework r1 RED)
- U7b r1 RED: 25 failing as expected (new classes only), reach PASS (1016 OK), controls 71 rows 0 unexpected; fake docker runs the real resolver for the script happy path.
- KE_IN_GATES accepted (item 13). After GREEN: re-run A34 steps 3 and 4 on Windows.
- Detail: archive/platform-sbom-part10.md; evidence u7b/r1-red-verify-fast.txt, u7b/r1-target-reach-verify-fast.txt, u7b/r1-red-mutants.txt

### 2026-10-25 — developer (U7b rework r1 GREEN)
- Asked: U7b rework r1 GREEN (review B1/B2/N1-N6, security M-1/L-1..L-5, A34 `$work/sboms/tmp`; design-notes "U7b rework round 1"). Copied `u7b/r1-target-sources_resolve.py`, `r1-target-sources_lock.sh`, `r1-target-sbom_check.py` (adds `lock-check --pending-neo4j`, exit 3, `_coverage_misses`, `only_neo4j_misses`) over the scripts; diffs against the U7b GREEN read, no refactor. `mv -f -- "$tmp" docker/sources.lock.json` stays alone on its line. Compose unchanged. `sources_lock.sh` NOT run against the network.
- `scripts/verify.sh fast`: PASS (`u7b/r1-green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u7b/r1-green-verify-full.txt`). Controls: `u7b/r1-green-controls.txt`.
- Next: reviewer and security re-check. Nothing committed.
- Controls note (U7b rework r1): `r1-green-controls.txt` reports 71 rows, 25 "unexpected". All 25 are the "U7b GREEN: ... must fail" baseline rows, which read the repo's own scripts as the old U7b GREEN tree (`GREEN_U7B` in `r1_controls.py`); with the repo now at r1 they pass, so they cannot fail. Every target and mutant row is ok. Not a code defect; the tester should confirm or fix the control's baseline (use the saved U7b target files).

### 2026-10-25 — reviewer (U7b rework r1)
- Asked: re-check U7b rework round 1 (rulings l.1444-1563). Verdict: **APPROVED**. Detail: `u7b/review-r1.md`.
- Closed:
  - B1: mid-body timeout, IncompleteRead and ConnectionResetError, plus OPENER InvalidURL and BadStatusLine, now give one FAIL line with the item 4 text and no lock.new.json. The 600 s deadline, the 4 GiB cap before hashing and the catch-all in main are in.
  - B2: `--pending-neo4j` decides on the full list; my 79-problem input gives exit 1, and the end-to-end test keeps the lock byte-identical.
  - N1: port, userinfo, tab, `%` and non-literal https hops are refused.
  - N2-N4, L-2, L-5, I-1, I-3 and the sbom tmp dir.
- The happy-path fake-docker test runs the real resolver and pins step order, chmod 0644, no temp left, `git diff --stat`, and exits 0 and 3.
- r1 controls re-run after the harness fix: 71/66/5, 0 unexpected (`u7b/reviewer-r1-controls.txt`). Probes: `u7b/reviewer-r1-probes.txt`.
- Nits, as U7c first rows:
  - R1-N1: the pypi JSON sdist url (server-supplied) is fetched as a first request, so it is exempt from the path-% rule. `.../packages/33/01/%2e%2e/%2e%2e/<60>/pandas-2.3.3.tar.gz` is requested; the U7a lock check then refuses the entry, so it fails closed.
  - R1-N2: the `six=(...)` literal beside the compose list.
- Next: security re-check; orchestrator commit gate.

### 2026-10-25 — security (U7b rework r1)
- Asked: re-check U7b rework round 1 (pending decided by `lock-check --pending-neo4j`, per-hop URL rules, pypi.org JSON-only, deadline and cap, ResolveError everywhere, 0644, key grammar first). Verdict: **PASS** (no critical/high/medium). Detail: `u7b/security-r1.md`; probes `u7b/security-r1-probes.txt` (fake network plus one loopback server).
- Closed: M-1 (the real-fixture lock without neo4j and pgdg now rc 1, not 3; no grep in step 5), L-1 (port/userinfo/fragment/non-plain path/raw-Location tricks refused on the first URL and every hop; query only on hops to allowed hosts), L-2, L-4, L-5, I-1, I-3. L-3: the cap and the slow-chunk deadline hold.
- New R1-L1 (low): the deadline is checked only between chunks, and the real opener `read(65536)` blocks until 64 KiB: a 1-byte/50 ms drip held one read past 12 s against a 2 s deadline. Use `read1` or a per-read socket timeout = remaining deadline. Listed hosts only; a stalled maintainer run at worst.
- Script: tools first (`tools: docker not on PATH`), six images exactly, trap removes the temp file. r1 evidence clean.

### 2026-10-25 — tester (U7b r1 controls + A34 re-run)
- Controls baseline fixed (saved u7b/target-*): `--base repo` 71 rows, 0 unexpected. A34 steps 3 and 4 PASS on Windows (refusals incl. tools and six images; the script's own SBOM + lock-needs path with sboms/tmp).
- O3: the fresh key set differs (psycopg-binary in, psycopg-c and postgresql-15 out) because ke-app:local here is stale (pre-23e3c9b); rebuild before a real lock run.
- Detail: archive/platform-sbom-part10.md; evidence u7b/r1-green-controls.txt, u7b/windows-run.txt (addendum), u7b/windows-run-r1-attempts.txt

### 2026-10-25 — orchestrator (U7b commit gate)
- Rework rounds used: 1 of 5 (B1 body errors/deadline/byte cap, B2/M-1 pending-neo4j on the full list, hop rules, tools check, trap, six images, pypi.org JSON-only, chmod 0644, error-body limit, key validation, A34 defect `$work/sboms/tmp`). Rulings: design-notes N5 amendment U7 "U7b interface pins" l.1384-1442 and "U7b rework round 1" l.1444-1563.
- Review APPROVED (r1), security PASS (r1), A34 PASS (steps 1-5; 3-4 re-run after r1), controls 71 rows 0 unexpected after the harness baseline fix (saved targets, not the repo).
- Orchestrator verify full PASS 1042 s (1016 unit + 15 integration, sentinel ok; `u7b/orchestrator-verify-full.txt`). Diff read: sources_resolve.py (fetch/stream/hop rules), sources_lock.sh (round-1 diff), compose service, lock-needs. Sentinel untouched. No lock file committed.
- Rulings: KE_IN_GATES accepted (image ENV marker); the second fetch stands for U7b, U7d adds a third fetch from another network path; U7d compares KEY SETS (fresh ke-neo4j 72 vs 73 Neo4j packages is information).
- Carried to U7c first test rows: review R1-N1 (a server-supplied pypi sdist URL is checked by the hop/path rules before streaming), security R1-L1 (deadline enforced within one read: `read1` or per-read socket timeout = remaining deadline), review R1-N2 (the six-image list is a literal beside bundle.sh's).
- Notes: the host's `ke-app:local` is stale (built 2026-10-20, carries psycopg-binary): U7d runs build.sh first. The tester's A34 driver bug caused 3 unintended real-network resolver runs (maven jar + Neo4j tarball fetched, then failed closed at pypi psycopg-binary; nothing written; `u7b/windows-run-r1-attempts.txt`).
- Commit APPROVED (`git add --chmod=+x` for the two new scripts). Next: U7c (deb/apk routes against a fake network; pgdg waits for Q71).

## 2026-10-25 — architect (U7c)
- Asked: make U7c implementable. Wrote "U7c precision" at design-notes l.1565-1789, before N6.
- deb (D1-D7): snapshot `srcfiles` gives a name->sha1 map, and only the `.dsc` is streamed (sha1 + sha256). Then `Checksums-Sha256`/`Files` are parsed and every name must be in the map. orig/debian files are not streamed. Requests are 1 s apart, with exact why-texts.
- apk (A1-A5): `lock-needs` reads `lib/apk/db/installed` (`o:`, `c:`) and `etc/alpine-release` from the saved tar; syft-json is not used. `--tar` goes to every image. Then the GitLab tree (`x-next-page` rule) picks main or community; the APKBUILD is checked by `content_sha256`; `sha512sums` is parsed as literal text (its names are the local `::` names); each file is streamed from GitLab raw or distfiles.
- Carried rows: server-supplied URLs pass the hop rules first; `read1` bounds a drip at 660 s; six-image list per R-2.
- Rulings needed: R-1 (stream distfiles tarballs at lock time; recommend yes, about 250-300 MB per full run); R-2 (six-image list; recommend a fast test pinning `six` == `bundled_names()`, with no bundle.sh change).
- Also: `sources_lock.sh` changes, so A34 applies. U7d cannot finish while Q71 is open (3 pgdg keys).


## 2026-10-25 — tester (U7c RED)
- Asked: the U7c RED against the "U7c precision" (D1-D7, A1-A5, C1-C3) and rulings R-1 (a), R-2 (c). Project `ke-tester-u7c`. Fake network only.
- **17 tests fail**, as the RED intends: 16 new methods (U7c* classes in `tests/test_sources_resolve.py`) plus 2 changed LockNeedsTest methods, less 1 guard.
  - The deb route: entry, `.dsc` forms (epoch, native, `+`/`~`, plain, dash-escaped), 19 failure rows with exact texts, `parse_dsc`.
  - The apk route: entry for main and community, 18 failure rows.
  - The 152 deb and 19 apk fixture keys: all resolve, and every entry passes `lock_problems`.
  - Carried rows: C1 (`%2e%2e` sdist URL never requested), C2 (`read1` pin via a patched `build_opener`), `SNAPSHOT_PAUSE` 1.0 (0.3 s spacing measured), and the pgdg skip text `until Q71`.
  - lock-needs A1 (installed-db stanzas, origin, commit, branch, 16 MiB fail, release 1 MiB fail, top layer wins).
  - The script: `--tar` for every image; R-2 guard `six` == `bundled_names()`.
- **Changed U7b tests** (each cites the U7c precision):
  - ResolverMergeTest: the no-route key is now pgdg, since deb has a route.
  - LockNeedsTest fixtures and CLI: the apk route gains commit/branch from the tar (`apk_inputs` helper).
  - ReworkR1LockScriptRunTest `_run` now gives the Alpine tars their db via the new fake-docker knob `FAKE_IMAGE_TAR_FILES`.
- Targets (reach-proven): `u7c/target-sources_resolve.py`, `target-sbom_check.py`, `target-sources_lock.sh`.
- **Interface pins:**
  - `SNAPSHOT_PAUSE`;
  - `parse_dsc(text) -> {field: value}`;
  - `lock_needs_doc(policy, docs, releases, apk)`, where `apk` maps an image to `{installed, release}`;
  - `tar_file_text(tar, member, limit)`.
- **Evidence:**
  - RED `u7c/red-verify-fast.txt`: FAIL, 1032 run, failures=54 / errors=11 by subtest, all in the U7c rows; lint PASS.
  - Reach `u7c/target-reach-verify-fast.txt`: PASS, 1032 OK.
  - Controls `u7c/u7c_controls.py` + `u7c/red-mutants.txt`: 59 rows (55 must-fail, 4 must-pass), 0 unexpected. The baseline is the saved `u7b/r1-target-*`, which equals 6d8fa4d. Attempt 1 is `red-mutants-attempt1.txt`.
- **Design notes for the architect:**
  - (1) Tree subdirectories: a patch in a `tree` subdirectory is not in the blob set, so it would go to distfiles.
  - (2) Missing paths: GitLab may answer a missing path with 200 `[]`, not 404; A2 counts any list as "here", so this risks a false "in both".
  - (3) Install scripts: aports files outside `sha512sums` (for example `*.post-install`) get no entry.
  - (4) Texts not in the design: a missing `Files` and a bad apk route have no listed text, and the target uses its own.
  - (5) The `pkgver` literal check never decides on its own, because the version compare already catches a non-literal.
- After GREEN, A34: the U7b real-run path through lock-needs, plus one real deb and one real apk component.
- Note (tester, 2026-10-25, U7c gap rulings, design-notes l.1806-1892): RED amended, now **19 failing**.
  - Recursive tree; mode 100644/100755 only; flat basenames from subdirectories; two blobs with one basename fail.
  - `200 []` counts as not here.
  - Every package-directory file is locked; files outside `sha512sums` go by the files API `content_sha256`.
  - Texts pinned: `.dsc has no Files`, `apk <key>: route is malformed (<field>)`, `gitlab files API says`.
  - `parse_dsc` is checked by content only.
  - The U7a apk lock rule changes (i) and (ii) are pinned in `tests/test_sources_lock.py` U7cApkLockRulesTest; `good_entry`'s APKBUILD `from` now uses the new text.
  - Evidence: `u7c/red-verify-fast.txt` (1034 run, failures=70 / errors=12 by subtest), `u7c/target-reach-verify-fast.txt` PASS 1034 OK, `u7c/red-mutants.txt` 79 rows, 0 unexpected. Earlier runs are kept as `*-attempt1/2`.

## 2026-10-25 — developer (U7c GREEN)
- Asked: U7c GREEN (deb and apk resolver routes; pgdg stays skipped until Q71). Copied `u7c/target-sources_resolve.py`, `target-sbom_check.py`, `target-sources_lock.sh` over `scripts/`; diffs against HEAD read (ignoring EOL), no refactor. `sources_lock.sh` NOT run against the network. New scripts keep +x in the working tree.
- `scripts/verify.sh fast`: PASS, 1034 ran (`u7c/green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u7c/green-verify-full.txt`). Controls: 79 rows, 0 unexpected (`u7c/green-controls.txt`).
- Next: reviewer and security. Nothing committed.

## 2026-10-25 — reviewer (U7c)
- Asked: review U7c (deb and apk routes, lock-needs apk inputs, the two apk lock-rule changes) against the U7c precision and gap rulings. Verdict: **CHANGES REQUESTED**. Detail: `u7c/review.md`.
- B1: rule change (i) also lets the APKBUILD come from a subdirectory.
  - Input: the fixture apk entry with the APKBUILD url at `.../main/readline/tests/APKBUILD` passes `lock_problems` (sbom_check.py l.1280-1293).
  - Fix: pin the APKBUILD path to `<commit>/<repo>/<origin>/APKBUILD`, plus a row.
- Nits:
  - N1: `parse_dsc` keeps the last of a duplicated field; it should fail. CRLF, leading blank and armour are fine.
  - N2: `parse_apkbuild` takes the first `pkgver=` or `sha512sums=` and ignores later reassignments.
  - N3 (U8 carry): check the apk `sha512sums` names against the entry.
  - N4: a listing with no blobs counts as not here.
- Conformant: D1-D7, A1-A5, gap rulings 1-4, rule (ii), C1/C2/six. Coverage of 152 deb + 19 apk keys passes lock_problems. Controls re-run: 79/75/4, 0 unexpected (`u7c/reviewer-controls.txt`). Probes: `u7c/reviewer-probes.txt`.
- Next: tester row for B1; developer GREEN; re-check.

## 2026-10-25 — security (U7c)
- Asked: gate audit of the deb and apk routes, the two apk lock-rule changes, the installed-db/alpine-release tar reads and `read1`. Verdict: **PASS** (no critical/high/medium). Detail: `u7c/security.md`; probes `u7c/security-probes.txt` (no external request).
- Closed: U7b R1-L1 (a 1-byte/50 ms drip now stops at the 2 s patched deadline).
- Holds: `.dsc` names (slash, `..`, NUL, not in srcfiles), Files vs Checksums agreement, sha1 vs snapshot, two sha1s per name refused; GitLab symlink/submodule/`..`/percent/prefix/collision refused before any URL; sha256-only files bound to GitLab raw at the entry commit with the files-API `from`; tar member limits fail closed.
- Low, non-blocking: **L-1** `lock-check` accepts the APKBUILD from a subdirectory (`.../raw/<commit>/main/readline/sub/APKBUILD`): exclude APKBUILD from the subdirectory form. **L-2** `parse_dsc` splits on U+2028/U+0085 etc. (`Homepage: a<U+2028>Source: evil` sets Source) and lets a repeated field win: split on newline only, refuse duplicates. **L-3** a 100-entry tree listing without `x-next-page` passes as complete.
- Info: I-1 the tree path query is unencoded (plus-sign origins fail closed); I-2 a sums-listed file in the tree may be recorded sha256; I-3 `.dsc` sizes unchecked until `lock-check`; I-4 tar whiteouts/hard links (carried).

## 2026-10-25 — tester (U7c Windows proof)
- **A34 FAIL**, on the real Alpine component; every other check passes (`u7c/windows-run.txt`, redacted).
  - Step 3 refusals pass, including tools and six images.
  - Step 4 passes: save, sbom (sboms/tmp present), lock-needs with `--tar` for all six. It gave 181 keys; all 19 apk keys carry commit and branch (ke-gateway v3.23, valkey v3.24). The drift is the recorded stale-ke-app one.
  - Real deb `deb:bash@5.2.15-2` passes: 2 snapshot requests, 2.7 s, `lock-check: ok`.
  - Teardown is clean, hashes are unchanged, and there is no `docker/sources.lock.json`.
- **Gap for the architect:** gitlab.alpinelinux.org's `/-/raw/` URLs answer 307 to an anti-bot challenge (`__goaway_challenge`), then 418.
  - The API raw endpoint `.../repository/files/<path>/raw?ref=<commit>` answers 200.
  - Every apk lock URL is GitLab raw (A3, A5, U7a binding), so neither the resolver nor U8 can fetch aports files. The API form needs a query, which U7a forbids in lock URLs.

## 2026-10-25 — tester (U7c rework r1 RED)
- 11 failing as expected: 8 new ReworkR1U7c* methods plus 3 U7c apk tests. The 3 fail because the fixture's tree URL now percent-encodes `path=` (ruling 8, security I-1), which the U7c code does not yet do.
  - Rows: APKBUILD path exact (lock side) and top-level only (resolver); `<dsc>: duplicate field <name>` (case-blind); CRLF folded (guard); `<dsc>: control character in field <name>`; `<origin>: APKBUILD assigns <name> more than once` (an indented one ignored); `<origin>: listing may be truncated at <commit>` (100 entries without an empty `x-next-page`); `path=main%2Flibsigc%2B%2B`.
  - Interface: `parse_dsc(text, name=".dsc")`; `parse_apkbuild(..., origin)`.
- Targets `u7c/r1-target-sources_resolve.py` and `r1-target-sbom_check.py` reach PASS, 1043 OK (`u7c/r1-target-reach-verify-fast.txt`). RED: `u7c/r1-red-verify-fast.txt`.
- Controls: `u7c/r1_controls.py` + `u7c/r1-red-mutants.txt`, 25 rows, 0 unexpected; the baseline is the saved `u7c/target-*`.
- Open for the architect (from the A34 above): GitLab raw is behind a bot challenge.
- Note (tester, item 9, the apk GitLab URL form): RED amended, now **39 failing**.
  - The 39 are 13 round-1 methods, and 26 U7a/U7b/U7c tests whose fixture lock (`good_entry`) now uses the API raw URL, which the GREEN lock rule still refuses.
  - Rows: lock good/bad per the item-9 list (in ReworkR1U7cApiUrlTest); resolver requests at the API raw form; a challenge.
  - Gap for the architect: the challenge row's 418 text only appears when the challenge redirects to a plain path. A same-path challenge on the API form (`%2F`) is refused by the hop rules (`redirect to <url> refused: not a plain path`). Both fail closed.
  - Reach PASS, 1047 OK, after a PS-1.2 fix in the target (no URL literal). Controls: 34 rows, 0 unexpected. Earlier runs are kept as `-attempt1/2`.

## 2026-10-25 — developer (U7c rework r1 GREEN)
- Asked: U7c rework r1 GREEN (review B1/N1/N2, security L-2/L-3/I-1, A34 GitLab bot challenge; design-notes "U7c rework round 1" items 1-9). Copied `u7c/r1-target-sources_resolve.py` and `r1-target-sbom_check.py` over `scripts/` (sources_lock.sh unchanged); diffs against the U7c GREEN files read, no refactor. Every apk GitLab file url is now the API raw form (`_apk_api_shape`, `_apk_api_problem`); no URL literals. `sources_lock.sh` NOT run against the network.
- `scripts/verify.sh fast`: PASS (`u7c/r1-green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u7c/r1-green-verify-full.txt`). Controls: `u7c/r1-green-controls.txt`.
- Next: reviewer and security re-check. Nothing committed.

## 2026-10-25 — tester (U7c r1 Windows re-run)
- **A34 PASS** (`u7c/windows-run.txt`, addendum).
  - `apk:pax-utils@1.3.8-r2`: tree, metadata, API raw and distfiles calls answer 200 (community's 404 means not here). 3 files, 129375 B, 5.2 s, `lock-check: ok`.
  - `deb:bash@5.2.15-2`: snapshot answered 503 once (failed closed, no retry). The re-run passed in 32.4 s, and its entry is byte-identical to the U7c GREEN run's.
  - Teardown is clean, hashes are unchanged, and there is no `docker/sources.lock.json`.


## 2026-10-25 — security (U7c rework r1)
- Asked: re-check U7c rework round 1 (APKBUILD path pinned, parse_dsc separators/duplicates, truncation rule, encoded tree path, item 9 GitLab API raw form). Verdict: **PASS** (no critical/high/medium; no new finding). Detail: `u7c/security-r1.md`; probes `u7c/security-r1-probes.txt`.
- Closed: L-1, L-2 (every separator in values, names, continuation, armour and trailer refused; duplicates case-blind), L-3 (100 entries need an empty `x-next-page`), I-1.
- Item 9 holds: project, ref, `<P>` (`%252F`, `%2F..%2F`, `.%2F`, `%2e%2e`, lower hex, unicode, `%5C`, subdir APKBUILD, other origin/repo), metadata or `/-/raw/` forms, userinfo/port/case all refused; the form is apk-only. Challenge: no Location gives 307, the absolute challenge gives 418, a relative one is refused at the hop.
- Info: I-5 a real `__goaway_id` nonce copied into a test and RED output (not a credential); I-6 U+FEFF/U+200B not refused but fail closed; I-7 relative challenge refused at the hop rather than reaching 418.
