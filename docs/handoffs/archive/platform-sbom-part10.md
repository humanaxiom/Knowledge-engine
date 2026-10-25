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

