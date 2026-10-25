# Handoff: platform-sbom

Plan item: `platform-sbom` (PSC-13..PSC-16; ADR to be written). Outcome
metric: neither *drafts a human reviewer has acted on* nor *ratified rules*;
it closes the M-NT1 remainder (no GPL source offer, incomplete SBOM). Branch:
`agent/platform-sbom`, cut from main at `737750d` (PR #13 merged).

## 2026-10-22 — orchestrator
- Asked to: open `platform-sbom` (the human said proceed, 2026-10-22).
- Criteria already drafted: `docs/requirements.md` `## Item: platform-sbom`
  (PSC-13 SBOM per image, PSC-14 ke-app notices, PSC-15 GPL source archive,
  PSC-16 CI cost and disk). TDD order PSC-14 -> PSC-13 -> PSC-15 -> PSC-16.
- Opener detail: archive/platform-sbom-part1.md

## Plan phase (detail: docs/handoffs/archive/platform-sbom-part1.md)
- 2026-10-22 analyst: criteria PSC-13..16 confirmed against code; drift fixed (uv gone from ke-app; tar config digest); PSC-19..24 added; Q61-Q63 drafted.
- 2026-10-22 orchestrator, human rulings: Q61 fail closed on a failed or mismatched source fetch (human); Q62 Q60's 3-min CI trigger applies, over 180 s goes to the human (human); Q63 reduced verify set, full set for operator bundles (human).
- 2026-10-22 architect: ADR-KE-016 is at `docs/architecture.md`; detail in `docs/evidence/platform-sbom/design-notes.md` (N0 is U0). Units:
  - U0 PSC-25 psycopg built against Debian libpq (full, A34)
  - U1 PSC-14 ke-app notices (fast)
  - U2 PSC-20 pinned SBOM generator (full, A34)
  - U3 PSC-13 SBOM per image (full)
  - U4 PSC-22 obligations not hidden / drift (full)
  - U5 licence classifier (fast)
  - U6 source policy (fast)
  - U7 generated source lock (full)
  - U8 PSC-23 fetch + CLAUDE.md wording (full, A34)
  - U9 PSC-15/24 source archive and manifest (full; A34 if install.ps1 changes)
  - U10 PSC-19 e2e + `/install` sizing (full, A34)
  - U11 PSC-16 CI cost on CI plus full recorded run
  - U12 PSC-21 per-arch
- Further plan-phase rulings and the final U0 test list: archive/platform-sbom-part1.md

## U0 (committed 31bfed4; detail: docs/handoffs/archive/platform-sbom-part2.md)
- Outcome: psycopg-c on Debian libpq5 15.19-0+deb12u1; ke-app 265 -> 259 MB, bundle tar -2.6%.
- L-13 CLOSED (security).
- A66 re-rated low, re-scoped to auth-audit.
- Rework rounds used: 1 of 5 (B1-B3, M-1).
- Orchestrator verify full PASS 694 s.
- A34 proof at `docs/evidence/platform-sbom/u0/windows-run.txt`.
- Open nits carried: none.

## U1 (PSC-14; detail: archive/platform-sbom-part3.md and part4.md)
- Commit 23e3c9b: ke-app flattened and pip dropped; NOTICE gains the Base of ke-app section (PSC-14).
- Rework rounds used 4 of 5; review APPROVED, security PASS, verify full PASS 721 s.
- Carried: I-1 to U5/U6 (libldap/libsasl2 GPL lines), I-3 to U9 (`app/sources/`); standing rule N1: no merge to main and no operator bundle before U3 and U9 land.

## U2 (committed 98b6d27; detail: archive/platform-sbom-part5.md)
- Commit 98b6d27: syft v1.54.1 pinned by index digest and hardened; `bundle.sh` refuses without it (PSC-20).
- Rework rounds used 0 of 5; review APPROVED, security PASS, verify full PASS 699 s.
- Carried: standing rule (security G5): record provenance BEFORE the first run of a newly pinned image.

## U3 (PSC-13; detail: archive/platform-sbom-part5.md)
- Commit 464fa11: one SPDX SBOM per bundled image in `app/sboms/` (PSC-13).
- Rework rounds used: not recorded in the summary (see archive part5); review APPROVED, security PASS, verify full PASS 856 s.
- Carried: ruling 5 to U5-U7 (jna, javassist Apache-2.0 OR exempt at U6; jaxb-api CDDL branch, maven sources jar at U7; classifier token rule at U5; NOASSERTION to the U4 report). Windows build hosts need jq on PATH, and `jq.exe` needs `-b`.

## U4 (committed 40e2181; detail: archive/platform-sbom-part6.md and part7.md)
- Commit 40e2181: obligations the generator could hide are surfaced (PSC-22).
- Rework rounds used 1 of 5; review APPROVED, security PASS, verify full PASS 896 s.
- Carried: to U5, security L-4, L-5, I-4, review R2 and R3, and a named LicenseRef fixture row.

## U4b (PSC-26, Q67; detail: archive/platform-sbom-part7.md and part8.md)
- Orchestrator rulings: the EXPOSE exemption (the scanner gains a Dockerfile exact-line rule, which security must review); checks in offline_check after drift; the file tree as evidence only; the NOTICE section; labels excluded; installers unchanged; Q68, ke-neo4j not scanned.
- RED: 29 failing, 61 controls, reach PASS.
- GREEN: verify full PASS 990 s; config identical; file tree equal minus products (two jars: the fleet-management and genai plugins); plugin absent from the tar; ke-neo4j unlicensed 27; tar -1.15%.
- Review APPROVED, 0 rework rounds (doc nits N1-N3 fixed; N6/N7 and cosmetic carried to U5).
- Security PASS, M-3 closed (L-1, I-2 carried to U5).
- A34 Windows proof PASS, including install.ps1 from the bundle (`u4b/windows-run.txt`).
- Orchestrator verify full PASS 995 s; committed c300d88.

## 2026-10-23 — orchestrator (pushed; human rulings Q69, Q70)
- U4b committed c300d88. Human approved push: `agent/platform-sbom` pushed, DRAFT PR #14
  (do not merge before U9, rule N1); its pull_request CI run is the first Linux
  classic-store run of the base `docker save name:tag@digest` and the sbom tmpfs mode.
- Human: Q69 GCC runtime SOURCE ships (U7, deb kind, no exemption); Q70 no scanning of
  the other bundled images for now. Analyst records both (uncommitted; ride with U5).
- Next: watch PR #14 CI; then U5 (classifier). Brief: docs/handoffs/NEXT-SESSION.md.

## U5 (PSC-15 classifier; committed d8ffa2d; detail: archive/platform-sbom-part9.md)
- Outcome: pure classifier functions in `scripts/sbom_check.py`, fail-closed rules (N8 amendment U5, design-notes l.940-1171); also escaping, tree size, scanner continuation lines and the smoke prune.
- Rework rounds 3 of 5: r1 B1-B3 + security lows, r2 leaf charset, r3 joiners/hash anywhere.
- Review APPROVED r3, security PASS r3, orchestrator verify full PASS 999 s. CI run 40046377958 PASS 32m32s (feeds U11/Q62).
- Carried to U6: I-r3-1 segment rule (first test row); security I-4 upper-hex hash (generator digest bump = re-review).
- Watch at U11: review N8 smoke flake risk.
- No CHANGELOG line until U9.

## U6 (hosts + exempt; committed 66781a9; detail: archive/platform-sbom-part9.md)
- Outcome: `hosts` holds the nine N4 hosts; `exempt` holds jna and javassist (reviewed `security 2026-10-25`); `exempt_matches`, `classify_document` exempt and the segment rule landed. PSC-22 amended: `always` overrides only the classifier, and an exact-version exempt entry still clears.
- Rework 0 of 5; review APPROVED, security PASS + exempt review PASS, orchestrator verify full PASS 962 s.
- Rulings: libffi notice goes to the ke-neo4j NOTICE section at U9; a base-image digest bump re-triggers the exempt review.
- First test rows carried to U7: a future `reviewed` date is rejected; a `#subpath` purl row.
- First test rows carried to U9: an exempt entry matching more than one package is a problem; `index` runs `validate` first.
- Also U9: drop the "no row both always and exempt" assertion when the first such entry lands; list "always, cleared by exemption".

## U7 (source lock; in progress)
Plan: design-notes N5 amendment U7.

## 2026-10-25 — architect (U7 plan)
- Split U7a-d, 182 keys, O1 -> Q71 human, O2 ruled, CLAUDE.md row draft.
- Detail: archive/platform-sbom-part10.md; evidence design-notes N5 amendment U7

## 2026-10-25 — analyst (U7)
- Q71 drafted; O2/O3 recorded in PSC-23.
- Detail: archive/platform-sbom-part10.md; evidence docs/open-questions.md, docs/requirements.md

## 2026-10-25 — tester (U7a RED)
- U7a RED: 12 failing, reach PASS, controls 45 (0 unexpected).
- Detail: archive/platform-sbom-part10.md; evidence u7a/red-verify-fast.txt, u7a/target-reach-verify-fast.txt, u7a/red-mutants.txt

## 2026-10-25 — developer (U7a GREEN)
- U7a GREEN: verify fast + full PASS 975 s, controls 0 unexpected.
- Detail: archive/platform-sbom-part10.md; evidence u7a/green-verify-fast.txt, u7a/green-verify-full.txt, u7a/green-controls.txt

## 2026-10-25 — reviewer (U7a)
- CHANGES REQUESTED: B1 neo4j second-fetch binding, B2 URL charset, N1-N7.
- Detail: archive/platform-sbom-part10.md; evidence u7a/review.md, u7a/reviewer-controls.txt, u7a/reviewer-probes.txt

## 2026-10-25 — security (U7a)
- PASS: lows L-1 charset, L-2 kind-host binding, L-3 raw key, L-4 profile path (redacted).
- Detail: archive/platform-sbom-part10.md; evidence u7a/security.md, u7a/security-probes.txt

## 2026-10-25 — tester (U7a rework r1 RED)
- r1 RED: 12 failing, reach PASS, controls 84 (0 unexpected).
- Detail: archive/platform-sbom-part10.md; evidence u7a/r1-red-verify-fast.txt, u7a/r1-target-reach-verify-fast.txt, u7a/r1-red-mutants.txt

## 2026-10-25 — developer (U7a rework r1 GREEN)
- r1 GREEN: verify fast + full PASS 969 s, controls 0 unexpected.
- Detail: archive/platform-sbom-part10.md; evidence u7a/r1-green-verify-fast.txt, u7a/r1-green-verify-full.txt, u7a/r1-green-controls.txt

## 2026-10-25 — reviewer (U7a rework r1)
- CHANGES REQUESTED: round-0 closed; new R1-B1 encoded dot-segments, R1-N1 temurin binding, R1-N2 CLI line.
- Detail: archive/platform-sbom-part10.md; evidence u7a/review-r1.md, u7a/reviewer-r1-controls.txt, u7a/reviewer-r1-probes.txt

## 2026-10-25 — security (U7a rework r1)
- PASS: L-1/L-3/L-4/I-2/I-4 closed; lows R1-L1 pypi regex, R1-L2 temurin binding.
- Detail: archive/platform-sbom-part10.md; evidence u7a/security-r1.md, u7a/security-r1-probes.txt

## 2026-10-25 — tester (U7a rework r2 RED)
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

## 2026-10-25 — developer (U7a rework r2 GREEN)
- Asked: U7a rework r2 GREEN (review R1-B1 + nits, security R1-L1; design-notes "Rework round 2"). Only `scripts/sbom_check.py` changed: copied `u7a/r2-target-sbom_check.py`; diff against the r1 target read, no refactor (`_plain_path` rule, exact temurin tag/asset binding, `lock-check: FAIL (<Class>: <msg>)` line, linear pypi name check via `_pypi_parts`, pypi path layout). Classifier, `exempt_matches`, `unlicensed_report` untouched; no URL literals.
- `scripts/verify.sh fast`: PASS (`u7a/r2-green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u7a/r2-green-verify-full.txt`). Controls: `u7a/r2-green-controls.txt`.
- Next: reviewer and security re-check. Nothing committed.

## 2026-10-25 — reviewer (U7a rework r2)
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

## 2026-10-25 — security (U7a rework r2)
- Asked: re-check U7a rework round 2 (linear pypi name check, exact temurin binding, plain paths, pypi Warehouse layout, CLI FAIL line). Verdict: **PASS** (no critical/high/medium; no new finding). Detail: `u7a/security-r2.md`; probes `u7a/security-r2-probes.txt` (script `u7a/security_r2_probes.py`).
- Closed: R1-L1 (`a-` x 50000 name 0.002 s, 255-char names 0.001 s; `psycopg_c-3.3.6.tar.gz` still good) and R1-L2 (temurin exact: feature, tag, asset, `%2B` forms, JRE/JDK binary, `from` all bound; the baseline equals the design form `/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz`).
- Plain-path rule holds for `%2e%2e`/`.%2e`/`%2E.`/`..%5c`/backslash/`%2f`/`//`/`/./`/trailing `/`/`%25`/`%252e`/`%c0%ae`/`%00`; Unicode forms stop at the ASCII rule. pypi layout rejects upper-case/59/61 hex, extra/missing segments, legacy paths. CLI: one `lock-check: FAIL (...)` line for missing/invalid/deep/bad-UTF-8. `lock_needs` = r1 (182 keys); ReDoS worst 0.035 s; r2 evidence clean.
- Info: I-7 the FAIL line echoes the operator's `--lock` path (redact profile paths in evidence); I-6 carried.
- Next: nothing from security for U7a; U7b to confirm the temurin asset form against the release page.

## 2026-10-25 — orchestrator (U7a commit gate)
- Rework rounds used: 2 of 5 (r1: B1 neo4j second-fetch binding, B2 URL charset + security L-1..L-3, per-kind host/name binding, exact keys, no tracebacks; r2: R1-B1 plain URL paths, exact temurin tag/asset, CLI line, linear pypi check, pypi path layout). Rulings: design-notes N5 amendment U7 l.709-1382.
- Review APPROVED (r2; no further shape), security PASS (r2; no new finding; I-7 operator path in the missing-file line: evidence redaction rule applies).
- Orchestrator verify full PASS 968 s (966 unit + 15 integration, sentinel ok; `u7a/orchestrator-verify-full.txt`). Diff read: component_key, lock_needs, lock_problems (_url_problems, _plain_path, _binding_problems, _pypi_parts), sample_keys, lock_text, lock-check. Sentinel untouched. No lock file committed (U7d).
- Also rides: ADR-KE-016 pointer (architecture.md), Q71 (PGDG, for the human) and O2/O3 records, N5 amendment U7 and its rounds, handoff archive part9 (U6 close) and new part10.
- Open for the human: Q71 (PGDG host/kind) before U7c; the CLAUDE.md "Generated artifacts" row for `docker/sources.lock.json` lands at U7d (draft in N5 amendment U7 item 7).
- Commit APPROVED. Next: U7b (`scripts/sources_resolve.py`, `scripts/sources_lock.sh`, `docker-compose.sources.yml` `sources-resolve`; neo4j/temurin/pypi/maven; security second fetch of the Neo4j tarball into sources-provenance.md; U7b confirms the real temurin asset name).
