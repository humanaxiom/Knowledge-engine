# platform-sbom U6: security review of the two `exempt` entries and `hosts`

Date: 2026-10-25. Auditor: security. Scope: the two `ke-neo4j` entries and the nine hosts in
`u6/target-source-policy.json` (design-notes N10 amendment U6 items 2 and 4, correction at
l.1691; N8a items 1 and 3; requirements PSC-22 `exempt` bullets). This is the entry review that
gates the `reviewed` value. The U6 gate audit of the integrated diff follows separately.
Probes: `u6/security-exempt-probes.txt`. The jars were taken out of
`ke-neo4j:bundle-c300d881cd94` (sha256:d4c9e9b6...7a24) with `docker create --network none` and
`docker cp`, with nothing run, and read with `python -I` zipfile.

## Verdict: exempt review PASS (both entries)

**The developer writes exactly `"reviewed": "security 2026-10-25"` on both entries.**

| Entry (image `ke-neo4j`) | Verdict | `reviewed` |
|---|---|---|
| `pkg:maven/com.sun.jna/jna@5.15.0` | PASS | `security 2026-10-25` |
| `pkg:maven/org.javassist/javassist@3.30.2-GA` | PASS | `security 2026-10-25` |
| `hosts` (9) | PASS, no host to remove | n/a |

## 1. jna 5.15.0
- sha256 of `/var/lib/neo4j/lib/jna-5.15.0.jar`:
  `a564158d28ab5127fc6a958028ed54279fe0999662c46425b6a3b09a2a52094d`, equal to the reason's value.
  It is the only jna jar in the image.
- `META-INF/LICENSE` (read in full): `SPDX-License-Identifier: Apache-2.0 OR LGPL-2.1`; "JNA is
  licensed under the LGPL, version 2.1 or later, or (from version 4.0 onward) the Apache License,
  version 2.0. You can freely decide which license you want to apply to the project." This is a
  genuine disjunction. 5.15.0 is at least 4.0, so Apache-2.0 is available. `META-INF/AL2.0` (the
  Apache License 2.0 text) and `META-INF/LGPL2.1` are the two texts syft joined with AND. The
  jar has no pom and no NOTICE file. The manifest names the vendor "JNA Development Team".
- Electing Apache-2.0 carries no source obligation, only licence text and notices. Apache-2.0's
  text ships in the jar and in Neo4j's `LICENSES.txt`, which lists "Java Native Access" in its
  Apache Software License 2.0 section (l.91). Neo4j made the same election upstream.
- Native code: there are 28 `libjnidispatch` builds (`.so`, `.a`, `.jnilib`, `.dll`). The
  jar's own LICENSE covers JNA as a project, so JNA's native dispatch is under the same dual
  licence. The jar's files do not name a separate licence for the native libraries. Their
  strings hold no `gpl`, "general public", "free software", copyright or licence text. All 28
  link libffi (`ffi_call`/`ffi_prep_cif`, `LIBFFI_TMPDIR`, `native/libffi/src/*` paths). libffi is
  under its own MIT-style licence; that comes from upstream, not from the jar. That is a notice
  obligation, not a source one (see L-1). No GPL-only code was found. All classes are under
  `com/sun/jna`, with nothing shaded from another project.
- The reason text is accurate: the quote (with its ellipsis), the AND join, the election and
  the sha256. It contains `sha256 <64 hex>` and `elected`, as the schema requires.

## 2. javassist 3.30.2-GA
- sha256 of `/var/lib/neo4j/lib/javassist-3.30.2-GA.jar`:
  `eba37290994b5e4868f3af98ff113f6244a6b099385d9ad46881307d3cb01aaf`, equal to the reason's value.
- `META-INF/maven/org.javassist/javassist/pom.xml` (`groupId` org.javassist, `artifactId`
  javassist, `version` 3.30.2-GA, no `<parent>`; `pom.properties` agrees). Its `<licenses>`
  block lists MPL 1.1, LGPL 2.1 and Apache License 2.0, with upstream's comments: "the license
  under which javassist is usually distributed", "... when it is bundled with JBoss", "... under
  which javassist can be distributed". The manifest's `Bundle-License` lists the same three URLs.
  By Maven's POM reference, several `<license>` entries mean any one may be selected, so this is
  a tri-licence with Apache-2.0 electable. Neo4j's `LICENSES.txt` (l.92) and `NOTICE.txt`
  (l.114) list "Javassist" under Apache Software License 2.0.
- Electing Apache-2.0 carries no source obligation. The jar has no LICENSE or NOTICE file, and
  the Apache-2.0 text ships in Neo4j's `LICENSES.txt`. All 426 classes are under `javassist/`
  (no shaded code); there is no native code.
- The reason text is accurate: three alternatives, syft's URL fold, the election and the sha256.
  The classifier still lists the row unparsed (N10 amendment item 4), which is expected.

## 3. `hosts` (nine)
`snapshot.debian.org`, `gitlab.alpinelinux.org`, `distfiles.alpinelinux.org`, `github.com`,
`codeload.github.com`, `objects.githubusercontent.com`, `release-assets.githubusercontent.com`,
`files.pythonhosted.org`, `repo1.maven.org`.
- Every one is a public, upstream or distribution source host for a named kind. There is no
  model host, no internal or private name, no IP literal, no wildcard, no scheme or port.
- The list is fetch-time only. `docker/source-policy.json` is read by tests only today (probe
  part 4), and by `bundle_fetch.sh` at U8. It never feeds the gateway's `KE_EGRESS_ALLOWLIST` or
  any runtime service, so the stack's egress is unchanged.
- I-1 (info): `github.com`, `codeload.github.com` and the two `*.githubusercontent.com` hosts
  are multi-tenant: anyone can publish there. The host list is not a provenance control. The
  real controls are N4's fetch rules (https only on every hop, no `-L`, every hop's host in
  `hosts`, at most 5 hops) and the reviewed lock's per-file sha256 (N5, U7). U7/U8 must keep
  both; security re-checks them at U7/U8. `objects.githubusercontent.com` and
  `release-assets.githubusercontent.com` stay *confirm at GREEN* of U8 (N4); drop whichever real
  fetches never use.

## Findings (non-blocking)
- **L-1 (low, outside the exempt decision): the libffi notice is missing.** Every
  `libjnidispatch` build embeds libffi. Its MIT-style licence asks for its copyright and
  permission notice in all copies. Neo4j's `LICENSES.txt` and `NOTICE.txt` have no libffi
  entry (`grep -ci libffi`: 0 and 0), and the jna jar carries no libffi text. This is a notice
  gap that Neo4j already has upstream, not a source obligation, so it does not change either
  verdict. Owner: the NOTICE work for ke-neo4j (its "Base image of `ke-neo4j`" section or the
  register). Add libffi's notice, or record a ruling that upstream's omission is accepted.
- I-1 (info): above, host provenance.
- I-2 (info): `exempt` voids on a version bump (match by exact versioned purl, N10 item 1).
  Jar sha256s are recorded in `reason` but not checked by code. A rebuilt jar at the same
  version would keep the exemption. That is acceptable while the base image is pinned by digest
  (`docker/neo4j.Dockerfile`). A base digest bump is a re-review trigger for both entries.
