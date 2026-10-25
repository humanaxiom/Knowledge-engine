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

## U6 (hosts + exempt; in progress)
Rulings: design-notes N10 amendment U6.

## 2026-10-25 — analyst (U6)
- Asked: PSC-22 wording for the generator-digest trigger and U5's landing; U6 `exempt`/`hosts` criteria; status line. Only `docs/requirements.md` changed (all marked "Amended 2026-10-25, analyst, U6").
- Already recorded, confirmed by quote: PSC-22 "A new syft image digest in `docker-compose.sbom.yml` triggers a PSC-22 re-review by security" (U4 R1). Added the reason (exact, case-sensitive `LicenseRef-<64 hex>`; I-r3-2) and a pointer saying U5 landed (N8 amendment U5).
- Not there before; added as PSC-22 bullets (no new PSC number): exactly three keys; a versioned purl, with no duplicate image+purl; an entry not catalogued at that exact version fails the bundle (pure check at U6, wired at U9); the reason gives the text read and where, the artifact's SHA-256 and, for an OR correction, the elected branch; `reviewed` is `^security \d{4}-\d{2}-\d{2}$`, written only after security's audit. On `hosts`: lower-case, no wildcard; U8 refuses any unlisted host on every hop, failing closed (Q61); every lock host is listed. First test row: I-r3-1. PSC-15 gained a pointer: an exemption means a PSC-22 `exempt` entry.
- Status line: "U0-U5 committed (U5 d8ffa2d, not yet pushed) ... U6 in progress". In the table, PSC-15's row now names U5.
- OPEN (for the orchestrator): "`always` beats `exempt`" conflicts with the recorded text. PSC-22 bullet 1 and its "`always` additions" ("Each needs a `sources/` entry (U7) or an exemption whose reason security has reviewed (U6)"), the libldap/libsasl2 bullet, and N10's human-call GCC fallback ("one `exempt` entry per versioned purl and image") all let a reviewed exemption clear an `always` package. Not written as a criterion; the requirements mark it open. Rule one of these: (a) `always` beats the classifier only (the recorded reading); (b) `exempt` can never clear `always`, which needs PSC-22 amended and closes off the GCC fallback.
- Interpretation to confirm: I-r3-1's "ruled boundary" was written as "the cases stay ordinary, as `MIT-NOASSERTION` does".
- Not changed (outside the brief): the status table's PSC-26 row still says PENDING/U4b, although U4b is committed as c300d88.
- Next: architect (N10 amendment U6, not yet in design-notes when I read it), then tester RED.
- Rulings recorded (orchestrator, 2026-10-25) in `docs/requirements.md` PSC-22: (1) option (a). `always` overrides only the classifier, and a reviewed exact-purl `exempt` entry still clears the package; the U9 index lists such rows as "always, cleared by exemption <reviewed>" (the open marker is closed). (2) I-r3-1 closes the boundary. If the bare id is not `licenseref-`, a `.`/`-` segment of NONE/NOASSERTION (case-fold) makes it unknown. `MIT-NOASSERTION`'s round-3 pin flips; the `LicenseRef-NONE` forms stay ordinary. (3) The PSC-26 row now reads MET, U4b (c300d88).

## 2026-10-25 — architect (U6)
- Wrote design-notes "N10 amendment, U6" (l.1530-1731; it ends before N11), with a dated correction for `always`+`exempt` (l.1691 on).
- API: `exempt_matches(image, doc, exempt) -> (flagged, problems)`. The match drops the purl's `?`/`#` and compares the string exactly; an entry with no match, or one that is not a versioned purl, is a problem. `classify_document(..., exempt=())`: an exempt row gets `needs=False`, also when `always` matches (correction).
- `hosts`: the nine N4 names (item 2). Schema test (item 3) maps fixture `neo4j.pkgs.tsv` to image `ke-neo4j` (the reverse of `U4B_POLICY_NAME`). The lock-host check moves to U7.
- Entries: `pkg:maven/com.sun.jna/jna@5.15.0` and `pkg:maven/org.javassist/javassist@3.30.2-GA`. `reviewed` is set only after a separate security review of the entries, recorded in `u6/security-exempt.md`.
- I-r3-1 also flips `see NONE.txt here` (run `NONE.txt`) to needs source; to be confirmed. Simulated real-row effect: 1015 rows, 0 changed.
- Next: orchestrator confirms the `see NONE.txt here` flip; tester RED in item order (a)-(e); loop `fast`, then full before the gate.

## 2026-10-25 — security (U6 exempt review)
- Asked: review the two `ke-neo4j` `exempt` entries (jna 5.15.0, javassist 3.30.2-GA) and the nine `hosts`, between RED and GREEN. Verdict: **exempt review PASS** for both entries; hosts PASS. Detail: `u6/security-exempt.md`; probes `u6/security-exempt-probes.txt` (jars `docker cp`'d from `ke-neo4j:bundle-c300d881cd94`, nothing run).
- **Developer writes `"reviewed": "security 2026-10-25"` on both entries.** Reason texts in `u6/target-source-policy.json` are accurate as written.
- jna: sha256 matches; `META-INF/LICENSE` is a genuine OR ("LGPL 2.1 or later, or ... Apache 2.0. You can freely decide"); all 28 `libjnidispatch` builds have no GPL strings and are JNA's own (dual) code plus libffi (MIT-style). javassist: sha256 matches; pom `<licenses>` MPL 1.1 / LGPL 2.1 / Apache 2.0 (any one, Maven), no shaded or native code. Neo4j's own LICENSES.txt/NOTICE.txt list both under Apache-2.0.
- Hosts: all public source hosts, fetch-time only (not runtime egress). Info I-1: the GitHub hosts are multi-tenant, so provenance rests on N4's hop rules and U7's per-file sha256 lock.
- L-1 (low, non-blocking, not an exempt issue): libffi's MIT notice is absent from Neo4j's NOTICE/LICENSES and from the jar; route to ke-neo4j NOTICE work. I-2: a base-digest bump re-triggers this review.
- Next: developer GREEN with the value above; security's U6 gate audit on the integrated diff.

## 2026-10-25 — tester (U6 RED)
- Asked: the U6 RED per orchestrator rulings 1-5 (with the correction that exempt clears `always` too), and the "N10 amendment, U6" (l.1530 on).
- Tests:
  - `tests/test_sbom_obligations.py` PolicyU6SchemaTest (4 methods) holds the schema oracle, the nine N4 hosts, the jna/javassist entries, and the oracle's own bad-shape controls.
  - `tests/test_sbom_classifier.py`: U6ExemptMatchesTest (2), U6ClassifyDocumentExemptTest (2, real rows of all six images), U6SegmentRuleTest (2).
  - Fixture mapping: `ke-neo4j` reads `neo4j.pkgs.tsv` (the reverse of `U4B_POLICY_NAME`).
- Pins flipped by ruling 5, recorded in the test file: `MIT-NOASSERTION` and `see NONE.txt here` (in two places) are now unknown.
- RED: `scripts/verify.sh fast`, 936 ran. 9 methods fail (19 incl. subtests), 0 errors, sentinel ok (`u6/red-verify-fast.txt`). The oracle's bad-shapes test is green, as a guard.
- Reach: u6 targets overlaid (checker + policy), verify fast PASS, 936 OK; repo restored (`u6/target-reach-verify-fast.txt`). Targets: `u6/target-sbom_check.py`, `u6/target-source-policy.json`. The target `reviewed` value equals security's (`security 2026-10-25`). The real-row snapshot is unchanged.
- Controls: `u6/u6_controls.py`, 44 rows (40 must fail, 4 must pass), 0 unexpected, gates image. Full output: `u6/red-mutants.txt`.
  - Checker mutants: version ignored or prefix-matched, case fold, void problem silenced, other images' entries applied, `always` beating `exempt`, exempt not clearing needs, `always` not forcing needs, and the segment rule dropped, inside LicenseRef, `-` only, case-sensitive, or on leaves only.
  - Policy mutants: a host with a scheme, path or wildcard; a tenth or a missing host; a fourth key; `reviewed` loosened or impossible; jna bumped; a reason without the sha256; javassist dropped; jaxb-api or openjdk exempted; image `neo4j`.
  - One equivalent mutant, not a row: accepting a qualifier-bearing entry. It never equals a stripped purl, so it still matches nothing and is a problem.
- Followed over the architect's text where they differ:
  - both-match gives `needs: False` (your correction; amendment item 1 still says True);
  - literal purl compare, and an entry with qualifiers is a problem (amendment item 1; the brief said qualifiers are ignored).
- Not pinned: the exact problem message texts.
- Next: developer GREEN, loop `fast`, `full` before the gate (scripts/ touched).

## 2026-10-25 — developer (U6 GREEN)
- Asked: U6 GREEN (`hosts` + `exempt` in `docker/source-policy.json`, `exempt_matches`, `classify_document(..., exempt=())`, I-r3-1 segment rule). Copied `u6/target-sbom_check.py` -> `scripts/sbom_check.py` and `u6/target-source-policy.json` -> `docker/source-policy.json`; diff against HEAD read, no refactor. `always` entries unchanged; both exempt entries carry `reviewed: "security 2026-10-25"`; `unlicensed_report`/`_missing` untouched; row matched by both gets always True, exempt True, needs False.
- `scripts/verify.sh fast`: PASS (`u6/green-verify-fast.txt`). `scripts/verify.sh full`: PASS (`u6/green-verify-full.txt`). Controls: `u6/green-controls.txt`.
- Next: reviewer and security. Nothing committed.

## 2026-10-25 — reviewer (U6)
- Asked: review the U6 diff (`hosts`, `exempt`, `exempt_matches`, `classify_document(..., exempt=())`, segment rule) against N10 amendment U6 and its correction (l.1691). Verdict: **APPROVED**. Detail: `u6/review.md`.
- Conformant:
  - Match: exact string compare after stripping qualifiers/subpath on the package side only; no case fold; a bump or a non-versioned entry is a problem (void).
  - Flags: exempt clears needs, also under `always` (both flags set); `always` alone forces needs; the default adds `exempt: False` only.
  - Policy: nine hosts; jna/javassist entries with `reviewed: security 2026-10-25`.
  - `unlicensed_report` is untouched.
- Segment rule: only adds unknowns. 200k random expressions against U5: 0 lost needs, 0 lost listings.
- Real rows: identical row by row to U5 with `exempt=()`. With the committed `exempt`, only ke-neo4j jna and javassist change (`needs`, `exempt`).
- Controls re-run in the gates image: 44/40/4, 0 unexpected (`u6/reviewer-controls.txt`).
- Nits:
  - N1 (U9 precondition): a duplicate SPDXID shared with an exempt package clears it too. `validate` refuses such docs; U9's `index` must validate first. Carry it as a U9 test row.
  - N2: the real-row test still asserts "never always+exempt" (withdrawn bullet).
  - N3: a future `reviewed` date is accepted.
  - N4: there are 29 bad shapes, not 31.
  - N5: no test has a `#subpath` package purl.
- Next: security's U6 gate audit; orchestrator commit gate.

## 2026-10-25 — security (U6)
- Asked: gate audit of U6 (`hosts`, `exempt`, `exempt_matches`, `_purl_base`, `classify_document(..., exempt)`, segment rule). Verdict: **PASS** (no critical/high/medium). Detail: `u6/security.md`; probes `u6/security-probes.txt` (script `u6/security_probes.py`).
- `exempt_matches` is exact: only jna's purl plus qualifiers/subpath clears it; version prefix/suffix, percent-encoding, case, `@` in namespace, other type, whitespace, NUL do not (each "matches nothing"). Schema oracle rejects the tester's 29 shapes and 24 of my 26 more. Segment rule: 150000 random expressions, 0 weaker than U5; ReDoS worst 0.52 s; real rows change only for jna and javassist (needs False, exempt True). `unlicensed_report` identical. Reasons equal what I reviewed; evidence clean.
- L-1 (low, for U9 or now): an entry clears every package at its purl (`[jna, jna?type=jar]` both cleared, no problem); report >1 match, and compare the SBOM checksum at U9. L-2 (low, U9): rows keyed by SPDXID, so a duplicate of an exempted SPDXID is cleared; U9's `index` must `validate()` first (finish already refuses duplicates).
- Info: I-1 future `reviewed` date accepted; I-2 the host regex accepts `evil.github.com`/punycode (the exact-set test rejects them); I-3 carried from the entry review.
- Next: orchestrator commit gate.

## 2026-10-25 — orchestrator (U6 commit gate)
- Rework rounds used: 0 of 5. Review APPROVED (nits N1-N5), security PASS (lows L-1, L-2), security exempt review PASS (`u6/security-exempt.md`; `reviewed: security 2026-10-25`).
- Orchestrator verify full PASS 962 s (936 unit + 15 integration, sentinel ok; `u6/orchestrator-verify-full.txt`). Diff read: source-policy.json (hosts, exempt), sbom_check.py (exempt_matches, classify_document exempt, segment rule), tests. Sentinel untouched.
- Rulings recorded here: (a) `always` overrides only the classifier; an exact-version `exempt` still clears (PSC-22 amended; GCC fallback stays open); (b) libffi notice (security exempt L-1) goes to the ke-neo4j NOTICE section at U9; (c) a base-image digest bump re-triggers the exempt review (security I-2).
- Carried as first test rows: U7: reviewer N3 / security I-1 future `reviewed` date rejected; N5 a `#subpath` purl row. U9: security L-1 an exempt entry matching more than one package is a problem; security L-2 / reviewer N1 `index` runs `validate` before `classify_document`; reviewer N2 drop the "no row both always and exempt" assertion when the first such entry lands; `index` lists "always, cleared by exemption <reviewed>".
- Commit APPROVED. Next: U7 (source lock: `docker/sources.lock.json`, `scripts/sources_lock.sh`, `maven` kind for jaxb-api, `deb` gcc-12/gcc-14 per Q69; security second fetch for provenance).
