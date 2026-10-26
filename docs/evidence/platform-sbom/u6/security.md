# platform-sbom U6: security gate audit (`hosts`, `exempt`, `exempt_matches`, segment rule)

Date: 2026-10-25. Auditor: security. Tree: HEAD d8ffa2d (U5) plus the U6 working tree:
`git diff HEAD -- scripts/sbom_check.py docker/source-policy.json tests/test_sbom_classifier.py
tests/test_sbom_obligations.py`. `scripts/sbom_check.py` equals `u6/target-sbom_check.py`, and
`docker/source-policy.json` equals `u6/target-source-policy.json`. Probes:
`u6/security-probes.txt` (script `u6/security_probes.py`; gates image, `python -I`). Entry
review: `u6/security-exempt.md`. verify.sh not run.

## Verdict: PASS

No critical, high or medium finding. Two low and three informational notes, all non-blocking.
Both lows are about how U9's `index` must call this code; neither changes a real row today.

| ID | Severity | Finding |
|---|---|---|
| L-1 | low | An `exempt` entry clears every package at its purl; two packages with jna's purl are both cleared, with no problem |
| L-2 | low | `classify_document` keys rows by SPDXID: a package that reuses an exempted package's SPDXID is cleared too (only `validate()` catches it) |
| I-1 | info | `reviewed` accepts a future date (`security 2099-01-01`) |
| I-2 | info | The host regex alone accepts `evil.github.com` and punycode; the exact-set test is the control |
| I-3 | info | Carried from the entry review: the GitHub hosts are multi-tenant; the libffi notice is missing (L-1 there); a base-digest bump re-triggers the entry review |

## 1. `exempt_matches` cannot be widened (probe U6-1)
- The match is exact string equality between the entry's `package` and the SBOM purl with
  `?...` and `#...` removed. Against the real jna entry, only the exact purl and its
  qualifier/subpath forms clear the package (`?type=jar&classifier=x`, `#com/sun/jna`).
- Not cleared, each reported "matches nothing" (fail closed):
  - version prefix or suffix (`@5.15`, `@5.15.0.1`, `-SNAPSHOT`)
  - percent-encoding (`5.15%2E0`, `j%6Ea`)
  - case (`com.sun.JNA`, `pkg:MAVEN`)
  - `@` in the namespace, an extra namespace segment, `pkg:generic`, no namespace
  - leading or trailing space or newline, a NUL, `?` before `@`, `jna-platform`
- Other images are skipped (valkey with jna's purl: nothing cleared, no problem).
- Bad entries clear nothing and are reported: versionless, with qualifiers or subpath, empty,
  None, an int, an empty version. An ESC in an entry is printed escaped. Malformed list items
  are skipped, and `exempt=None` raises `TypeError` (nothing cleared). 100k packages take 0.2 s.
- **L-1:** `[jna, jna?type=jar]` clears both SPDXIDs with no problem. My review covered one jar
  (sha256 `a564158d...`). The only one in the image is at `/var/lib/neo4j/lib`, and the real
  fixture has one row per purl, so there is no effect today. A second jar with the same
  coordinates, or a jar named `jna-5.15.0.jar` (jna has no pom, so syft names it from the jar),
  would ride the exemption. Fix at U9 (or now, cheaply): `exempt_matches` reports a problem when
  an entry matches more than one package. U9's `index` should also compare the package's
  checksum in the SBOM with the reviewed jar, where syft records one.
- **L-2:** a GPL package given jna's SPDXID (`SPDXRef-0`) gets `needs: False, exempt: True`. The
  flags are SPDXID sets. `validate()` reports "package SPDXID SPDXRef-0 is not unique", and
  `finish` refuses such a document, so a bundled SBOM cannot carry it. U9's `index` must call
  `validate()` on each document before `classify_document`, or refuse duplicate SPDXIDs itself.
  `always` has the same keying, but there it fails closed.

## 2. Schema test (`u6_policy_problems`, probe U6-2)
- The committed policy passes, with keys exactly `always`, `exempt`, `hosts`, and `hosts` equal
  to the nine I passed (`test_hosts_are_the_fetch_hosts`).
- The tester's 29 bad shapes all fail. My 26 further mutations also fail, except I-1 and I-2:
  - `reviewed`: fullwidth or Arabic-Indic digits, double space, a trailing newline,
    `Security`, `2026-02-30`, a list.
  - `hosts`: a trailing dot or newline, userinfo, `[::1]`, a decimal IP, a non-string, a
    string instead of a list.
  - `package`: a trailing space, `@` in the namespace, upper case.
  - other: image `KE-neo4j`, a qualifier variant posing as a second entry, `exempt` as a dict,
    a list entry, an upper-hex sha256, `unelected`.
- I-1: a future `reviewed` date passes. The date only has to be real, and process (this file)
  is the control.
- I-2: `evil.github.com` and `xn--...` pass the host regex. The exact nine-host set test rejects
  them, so a new host still needs a reviewed test change.

## 3. Segment rule (I-r3-1; probe U6-3)
- Nothing weaker than U5: 150000 seeded random expressions joined by space, nothing, `-`, `.`,
  `+` or `:`. Tokens included NONE/NOASSERTION in all cases, `NONEX`, `NOASSERTIONS`,
  `LicenseRef-`/`licenseref-`, DocumentRef prefixes, hashes and operators. Result: 0 that
  needed source at d8ffa2d and not now, 0 lost listings, and 11763 that need source only now.
  This holds by construction: the rule only adds a way to be unknown.
- The architect's table holds:
  - Unknown: `NOASSERTION.NONE`, `NOASSERTION-2.0`, `MIT-NOASSERTION`, `MIT AND NONE.NONE`,
    `none-mit`, `DocumentRef-x:NONE-1`.
  - Ordinary: `LicenseRef-NONE`, `licenseref-none`, `LicenseRef-NOASSERTION`,
    `DocumentRef-x:LicenseRef-NONE`, `NOASSERTIONS`, `NONEX-1`, `DocumentRef-NONE:MIT`.
  - Flipped pin, as ruled: `see NONE.txt here` now needs source and is unidentified.
  - `MIT WITH x-NONE` and `LicenseRefX-NONE` are unknown (fail closed).
- ReDoS: `_unknown_id` on 1 MB of `.-` or `a.` segments takes at most 0.04 s. `needs_source` on
  200k terms takes 0.52 s, and on 1 MB of junk 0.22 s.
- Real rows: across the six fixtures with the real `always` and `exempt`, exactly two rows change
  from U5. jna and javassist go from needs True to False with `exempt: True`; javassist stays
  `unparsed: True`, and neither is `always`. Needs counts: 102/17/164/33/130/12 (ke-neo4j was 166).
- `unlicensed_report` and its helpers are identical to c300d88. Counts 19/0/28/35/25/1 are equal.

## 4. Entry `reason` texts
The committed `exempt` array is identical to `u6/target-source-policy.json`, which I reviewed
(`u6/security-exempt.md`). Both reasons match what I read in the jars: the jna LICENSE quote and
the AND join, the javassist pom's three alternatives, Apache-2.0 elected, and both sha256s.
`reviewed` is `security 2026-10-25` on both, as I issued.

## 5. Evidence hygiene (`u6/*`, both test files)
No keys, tokens, private keys, JWTs, credential URLs, password values, profile paths, SIDs,
model-host name or port, or `KE_MODEL_UPSTREAM`/`KE_EGRESS_ALLOWLIST` values. IPs: 127.0.0.1,
the stack gateway's internal address in the smoke's no-route lines, and a Temurin version.
`security-exempt-probes.txt` shows JNA's upstream build paths as `<upstream build dir>`.
`u6_controls.py` runs `git show` and harnesses in a `mkdtemp` dir it removes; no network, no
repository write.
