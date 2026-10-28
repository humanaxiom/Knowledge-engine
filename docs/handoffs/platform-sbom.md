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
- Outcome: psycopg-c built against Debian libpq5; ke-app 265 -> 259 MB. Rework 1 of 5; verify full PASS 694 s.

## U1 (PSC-14; committed 23e3c9b; detail: archive/platform-sbom-part3.md and part4.md)
- Outcome: ke-app flattened and pip dropped; NOTICE gains the Base of ke-app section. Rework 4 of 5; verify full PASS 721 s.
- Still carried: I-3 to U9 (`app/sources/`); standing rule N1: no merge to main and no operator bundle before U9.

## U2 (PSC-20; committed 98b6d27; detail: archive/platform-sbom-part5.md)
- Outcome: syft v1.54.1 pinned by index digest and hardened; `bundle.sh` refuses without it. Rework 0 of 5; verify full PASS 699 s.

## U3 (PSC-13; committed 464fa11; detail: archive/platform-sbom-part5.md)
- Outcome: one SPDX SBOM per bundled image in `app/sboms/`. Rework not recorded in the summary; verify full PASS 856 s.

## U4 (PSC-22; committed 40e2181; detail: archive/platform-sbom-part6.md and part7.md)
- Outcome: obligations the generator could hide are surfaced. Rework 1 of 5; verify full PASS 896 s.

## U4b (PSC-26, Q67; committed c300d88; detail: archive/platform-sbom-part7.md and part8.md)
- Outcome: our own ke-neo4j image without the fleet-management and genai plugins; EXPOSE exemption added to the scanner. Rework 0 of 5; verify full PASS 995 s.

## 2026-10-23 — orchestrator (pushed; human rulings Q69, Q70; detail: archive/platform-sbom-part8.md)
- U4b pushed as DRAFT PR #14 (no merge before U9); Q69 GCC runtime source ships (U7); Q70 no scanning of the other bundled images.

## U5 (PSC-15 classifier; committed d8ffa2d; detail: archive/platform-sbom-part9.md)
- Outcome: pure fail-closed classifier functions in `scripts/sbom_check.py` (N8 amendment U5). Rework 3 of 5; verify full PASS 999 s; CI run 40046377958 PASS 32m32s (feeds U11/Q62). Still carried: security I-4 upper-hex hash (generator digest bump = re-review); watch review N8 smoke flake at U11; no CHANGELOG line until U9.

## U6 (hosts + exempt; committed 66781a9; detail: archive/platform-sbom-part9.md)
- Outcome: `hosts` (nine N4 hosts) and `exempt` (jna, javassist; reviewed `security 2026-10-25`) landed with `exempt_matches` and the segment rule. Rework 0 of 5; verify full PASS 962 s. Still carried to U9: libffi notice in the ke-neo4j NOTICE section; an exempt entry matching more than one package is a problem; `index` runs `validate` first; drop the "no row both always and exempt" assertion and list "always, cleared by exemption"; a base-image digest bump re-triggers the exempt review.

## U7 (source lock; U7a 9b1754f, U7b 6d8fa4d, U7c 86f7831 committed, U7d gate passed (commit this session); detail: archive/platform-sbom-part10.md and part11.md)
- Plan: the architect's split U7a-d; 182 keys = deb 152 / pgdg 3 / apk 19 / neo4j 1 / temurin 1 / maven 1 / pypi 5. The CLAUDE.md row draft is in N5 amendment U7 item 7, for the human at U7d.
- U7a outcome: `lock_needs`, `lock_problems`, `sample_keys`, `lock_text` and `lock-check`; fail-closed URL, path and per-kind binding rules; no lock committed.
- Rework 2 of 5; review APPROVED, security PASS, orchestrator verify full PASS 968 s.
- Rulings: O2 lock-time resolution endpoints are listed in N5 and `hosts` is file URLs only; O3 fresh-image drift stops U7d.
- Open for the human: Q71 PGDG host/kind before U7c.
- Carried: security I-7 operator path in the FAIL line (evidence redaction); U7b confirms the real temurin asset form (exact amendment, never looser); U7d adds `.gitattributes` eol=lf for the lock.
- U7b outcome: `sources_resolve.py` for neo4j/temurin/pypi/maven (hop-by-hop https, deadline and cap, fail-closed lines); `sources_lock.sh` maintainer tool; `sources-resolve` service; `lock-needs`; `lock-check --pending-neo4j`. Provenance recorded: Neo4j sha256 `182ae2e5...91e3`, commit `27f24499...`.
- U7b rework 1 of 5; review APPROVED, security PASS, A34 PASS, verify full PASS 1042 s.
- U7b rulings: KE_IN_GATES accepted; second fetch stands, U7d adds a third fetch from another network; U7d compares key sets.
- Carried to U7c first test rows: server-supplied URLs pass the hop rules; deadline within one read; six-image list derived.
- Notes: host `ke-app:local` is stale, so U7d runs build.sh first; a tester driver bug caused 3 unintended real-network resolver runs, all failed closed, nothing written.
- U7c outcome: deb route via the snapshot `.dsc`; apk route via the GitLab API raw form after the raw endpoint's bot challenge; strict deb822 and APKBUILD parsers; every aports file locked, distfiles streamed. Real `bash` and `pax-utils` resolve on Windows.
- U7c rework 1 of 5; review APPROVED, security PASS, A34 PASS, verify full PASS 1004 s.
- U7c rulings: R-1 stream distfiles; R-2 compose as source; gap rulings; item 9 URL form; two U7a apk rule changes.
- Carried to U7d first rows: R1-N1 middle segments, R1-N2 non-field `.dsc` line, I-5 synthetic nonce.
- U7d: Q71/Q72 ruled by the human 2026-10-25; CI run 40244299450 on 86f7831 PASS (verify 23 min); see the U7d block below.

## U7d (source lock real run; gate passed 2026-10-26; commit pending in this session; detail: archive/platform-sbom-part11.md)
- Outcome: pgdg route via the apt-archive InRelease-bound Sources; bounded retry 3x (10/30/60 s) on 5xx and timeouts plus a run budget (20 / 3 h); real-data rules: aports symlink skip, leading `_`, size-0 GitLab apk files, scanner skips the lock. The lock: 182 keys, 872 files, 1.327 GB full, 137 MB sample, 1 manual neo4j entry == second fetch. CLAUDE.md row added with the human's approval.
- Gates: review APPROVED, security PASS + gpgv lock review PASS, A34 PASS, controls 0 unexpected, verify full PASS 1018 s (plus a final run after the CLAUDE.md row). Rework 1 of 5.
- Rulings: A71 (pgdg kind + tenth host), A72 (lock-tool retry only), P-R1 (no signature verification in the tool), P-R2 (mid-body timeouts retried), item 14 (third Neo4j fetch deferred to U8's CI sample fetch; the ARM one-liner is still preferred before the first operator bundle).
- Lessons: a change found during a real run goes back through RED; controls baselines come from SAVED copies.
- Forward U8: keep the run's SBOMs in `--evidence-dir`; name checks of `.dsc` Files and APKBUILD sha512sums; cite the CI fetch in sources-provenance.md.
- Forward U11: full operator bundle ~8 GiB staged > 7 GiB floor; CI verify 23 min. Forward U9: the U6 carried rows.


## 2026-10-27 — analyst (plan update U7d)
- requirements.md: new status line (U7d gate passed, next U8); table rows PSC-15/16/22/23 updated; PSC-23 says U8's first CI sample fetch is the third Neo4j fetch (sources-provenance.md). open-questions.md: Q61-Q72 all resolved, plus the third-fetch refinement with the architect's caveat (ARM one-liner still preferred).

## 2026-10-27 — marketer (CHANGELOG U5-U7d)
- CHANGELOG "platform-sbom (in progress)" rewritten to U0-U7d in six bullets (U0-U4b merged in, U5-U7d added); no README change (no operator-facing shift until U9); no evidence file.

## 2026-10-27 — orchestrator (U7d commit BLOCKED by a fresh scan High; U7e opened)
- After the docs/CLAUDE.md row, the orchestrator's `verify.sh full` FAILED at the scan stage (`u7d/orchestrator-verify-full-after-claude-row.txt` l.2075-2372): ke-app's base carries openssl/libssl3 3.0.22-1~deb12u1, fixed in 3.0.22-1~deb12u2, CVE-2026-84782 High (+ Mediums/Lows in the same fix; CPython Mediums with no 3.12 fix). Unit + integration tests were green. Never commit on red: the U7d commit waits for U7e.
- U7e (openssl 3.0.22-1~deb12u2 pinned in ke-app's runtime stage like libpq5; scan green; the lock regenerated with the new `deb:openssl@...deb12u2` key; the U3 fixtures refreshed and real-row tests re-pinned; NOTICE true; A34): analyst criteria, architect design (N0 amendment U7e) and security advisory confirmation dispatched 2026-10-27; next session runs tester RED -> GREEN (incl. the lock re-run) -> reviews -> one commit for U7d+U7e or two (architect recommends).

## 2026-10-27 — architect (U7e)
- Design: design-notes "N0 amendment, U7e" l.248-420. Pin `ARG OPENSSL_VERSION=3.0.22-1~deb12u2` and install `libssl3`/`openssl` beside libpq5 in the runtime stage only (not builder, not gates); no base-digest bump. Tests: static `test_openssl_pin_in_runtime_stage` + image-side `deb_pin_problems`; the scan is the proof; drift is unchanged (it compares names) and a NOTICE change is optional (analyst).
- Lock: new key `deb:openssl@3.0.22-1~deb12u2` (ke-app); `~deb12u1` stays for postgres, so 183 keys. Refresh only `ke-app.pkgs.tsv`, and its diff must be exactly the two openssl rows, else stop. Incremental real lock run. A34 yes.
- Recommend ONE commit for U7d+U7e: verify gates the whole tree and neither unit goes green alone. Flag for the human: the pinned postgres image carries the same vulnerable openssl, but Q70 means it is not scanned.

## 2026-10-27 — analyst (U7e)
- New PSC-27 in requirements.md (U7e, before U7d's commit). Pin libssl3/openssl 3.0.22-1~deb12u2 in the runtime apt RUN. The static and NOTICE tests split upgraded from added packages. Drift check on versions; scan clean with a fresh DB; lock gains deb:openssl@...u2 (tool-generated, security-reviewed); all six U3 fixtures refreshed (O3) and real rows re-pinned; the NOTICE base section names the upgrade; A34; gate full; metric neither. Status line and table updated.
- Flag: postgres carries the same libssl3 u1 and is unscanned (A70), so deb:openssl@u1 stays in the lock for it.

## 2026-10-28 — security (openssl advisory)
- **Confirmed:** CVE-2026-84782 (OpenSSL High, DTLS only) plus five Low/Medium, fixed for bookworm in `3.0.22-1~deb12u2` (DLA-4859-1), on deb.debian.org debian-security and snapshot (`.dsc` sha1 `eb6d0239...`, first_seen 20261026T032458Z); CPython Mediums have no 3.12 fix in grype and do not fail the `--only-fixed --fail-on high` policy. Detail: `u7e/security-openssl.md`.
- **Prefer:** pin `libssl3=3.0.22-1~deb12u2 openssl=3.0.22-1~deb12u2` in the app runtime stage now; bump the base to `python:3.12-slim-bookworm@sha256:6dd8b6da...` (3.12.16 plus deb12u2, already published) as its own item with the CPython licence refresh. Either way the lock gains `deb:openssl@3.0.22-1~deb12u2` and the U3 ke-app fixture must move.
- Other images: postgres also has deb12u1 (vulnerable, not scanned, Q70); phoenix and ke-neo4j have trixie `3.5.7-1~deb13u3` (fixed); FYI the Alpine gateway (3.5.5-r0) and valkey (3.5.8-r0) are below upstream 3.5.9 (backport not checked).
