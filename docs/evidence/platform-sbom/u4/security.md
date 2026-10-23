# platform-sbom U4: security audit (2026-10-23)

Scope: `git diff 464fa11` plus untracked `docker/source-policy.json`, `tests/test_sbom_obligations.py`,
`tests/sbom_support.py`, `docs/evidence/platform-sbom/u4/`. Probes: `u4/security-probes.txt`.

## Verdict: FAIL (1 high)

| Id | Sev | Finding |
|---|---|---|
| H-1 | high | Hash-only licences escape the unlicensed report |
| M-1 | medium | GCC runtime (GPL-3.0-or-later WITH GCC-exception-3.1) in every Debian image is not in `always` |
| M-2 | medium | neo4j `jrt-fs` (JDK jar, GPL-2.0 WITH Classpath-exception-2.0) is not tied to the Temurin entry |
| M-3 | medium | neo4j ships a commercially licensed jar (fleet-management plugin) |
| L-1 | low | `always` exact names miss `busybox-binsh` and `libapk` |
| L-2 | low | `XDG_CACHE_HOME: /tmp/cache` is a no-op |
| L-3 | low | Report lines echo generator text unescaped |

### H-1 (high, merge-blocking): hash-only licences escape the unlicensed report
- syft writes `LicenseRef-<64 hex>` (a hash of licence text it could not identify) as the only id on
  59 rows: ke-app 18, neo4j 9, phoenix 10, postgres 22. No row mixes a hash with a real id (probe 1).
- `_missing()` counts only absent, `""`, `NONE` and `NOASSERTION`, so these rows are "licensed" and are
  not in the report. N8 (U5) does not flag them either: the hash matches neither the pattern nor the
  token rule, and it has no `http`. Under the design as written they would need no source and would
  never reach security. PSC-22 exists to prevent this.
- GPL-family by the image's own copyright files: **wget** (GPL-3, a shipped executable, neo4j); the GCC
  runtime (libgcc-s1, libstdc++6, gcc-*-base; ke-app, postgres, neo4j); libgnutls30, libgcrypt20,
  libtasn1-6, libksba8, libcrypt1, libsemanage2, base-files and debian-archive-keyring. glibc rows are
  covered by `always`. krb5, libselinux1, libxslt1.1, python3.13 and pandas are not GPL-family.
- Fix (U4, `sbom_check.py` and test): treat an expression whose every id is `LicenseRef-[0-9a-f]{64}`
  as missing (or list it in its own "unidentified licence text" section with counts). Add a test row
  declared `LicenseRef-<64 hex>`. Amend N8 so U5 treats such ids as unknown and lists them for security,
  or reads `hasExtractedLicensingInfos` text under the token rule. Expected counts: ke-app 19,
  ke-gateway 0, neo4j 28, phoenix 35, postgres 25, valkey 1. Security re-reviews the added rows.

### M-1: GCC runtime (all Debian images)
ke-app and postgres ship gcc-12, neo4j and phoenix gcc-14. The phoenix rows are in the report; the
others are hidden by H-1. Each is GPL-family by N8's own pattern. Add `upstream=gcc-12` (ke-app,
postgres) and `upstream=gcc-14` (neo4j, phoenix) to `always`, then give them source entries (U7) or a
reviewed exemption (U6). Non-blocking at U4: nothing ships sources before U9.

### M-2: neo4j `jrt-fs@21.0.12.1`
This is the Temurin JDK's own jar (`/opt/java/openjdk/lib/jrt-fs.jar`), so it is GPL-family. The
openjdk `always` entry does not match it. Add `{"image":"neo4j","match":"pkg:maven/jrt-fs/jrt-fs"}`,
or a U6 exemption whose reason names the Temurin source entry.

### M-3: neo4j `com.neo4j/neo4j-fleet-management-plugin@1.2.0`
The jar sits in `/var/lib/neo4j/products` and is inactive by default. Its notice reads: "Use of this
Software without a proper commercial license with Neo4j, Inc. ... is prohibited". It is not
GPL-family, but redistributing it in our bundle needs a human ruling: either cite Neo4j's terms for
redistributing the image, or delete `products/` in the vendored image.

### L-1: sibling packages missed by `always`
`busybox-binsh` (upstream=busybox) and `libapk` (upstream=apk-tools; apk-tools 3 keeps its library
here) are in valkey and ke-gateway, and the exact-name matches miss them. Today syft reports both as
GPL-2.0-only, so the classifier catches them. Add `upstream=busybox` and `upstream=apk-tools`; keep the
name entries, because busybox and apk-tools carry no upstream qualifier.

### L-2: XDG_CACHE_HOME (item 4) - recommend `/tmp:mode=1777`
- Cause, confirmed: the syft image's `/tmp` is 0755 root. A tmpfs mounted over an image directory takes
  that directory's mode, so uid 1000 cannot write there. `:mode=1777` fixes it (probe 5). The cause is
  the image, not Docker Desktop, so Linux behaves the same. grype works only because it runs as root.
- Security view: a sticky, world-writable `/tmp` is a risk only when a second principal shares the
  mount (symlink races, squatting). Here there is one process, one uid, no network, a read-only root,
  no capabilities, no-new-privileges, a per-container tmpfs, and the defaults nosuid,nodev,noexec
  (verified). A compromised syft can already write `/out`. Adding `mode=1777` gives nobody a new
  capability.
- Recommend adding `- /tmp:mode=1777`. It keeps ruling 5 item 6 and security I-2 ("at or under /tmp")
  and keeps the cache off the host. `_tmpfs_targets` strips options, so the existing pins hold. The repo
  already uses this form (`docker-compose.yml`). Dropping the key is also safe, but then syft probes
  `/.cache` and warns on every run. The current state (a key that does nothing) is the worst of the three.

### L-3: unescaped report lines
`report_lines` prints the SBOM's `name` (no-purl rows) and purl verbatim to stderr. A crafted vendor
package name could carry terminal control sequences into the bundle output. Pass them through
`ascii()` or strip C0/C1 characters.

## Item 1: unlicensed lists per image (as reported)
- **ke-app (1)**: `pkg:generic/python@3.12.15`: Python-2.0, not GPL-family; covered by NOTICE.md and
  `licenses/CPython-3.12-*`. Row cleared. List not accepted until H-1.
- **ke-gateway (0)**: no hash-only rows. **Accepted.**
- **neo4j (19)**:
  - Permissive by upstream licence: argparse4j (MIT), commons-lang3 and commons-text (Apache-2.0),
    ipaddress, magnolia, the 4 bolt-connection jars, cypher-dsl, picocli, scala-collection-contrib,
    zero-allocation-hashing (Apache-2.0), kiama (MPL-2.0), reactive-streams (MIT-0), slf4j-api (MIT).
    Their poms inherit the licence from parent poms that are not in the jars.
  - GPL-family: openjdk (in `always`) and jrt-fs (M-2). Proprietary: fleet plugin (M-3).
  - 20 -> 19 is explained: U3's 20 rows were the same 18 maven rows plus openjdk plus the `pkg:oci` root,
    and U4 excludes the DESCRIBES root by rule (N8a 4). No other row changed.
  - Not accepted until H-1, M-2 and M-3 are resolved.
- **phoenix (25)**:
  - Not GPL-family:
    - pypi: aiosqlite, exceptiongroup, httpx-ws, markdown-it-py, obstore, pyqwest (MIT); jinja2
      (BSD); synchronicity and both daytona clients (Apache-2.0); protobuf-py-ext (bufbuild,
      Apache-2.0; its Rust deps are all permissive).
    - The 8 no-purl rows are setuptools' cli/gui launcher stubs.
    - deno 2.1.4 (MIT), libncursesw6 (X11/BSD), python3.13-venv (PSF).
  - GPL-family: libgcc-s1, libgomp1 and libstdc++6 (gcc-14 with the GCC exception) need a source
    entry or an exemption (M-1).
  - Not accepted until H-1 and M-1 are resolved.
- **postgres (3)**: gosu and moby/sys/user (Apache-2.0), golang.org/x/sys (BSD-3-Clause); none
  GPL-family. Rows cleared. Not accepted until H-1 (22 hidden rows).
- **valkey (1)**: valkey 8.1.10 (BSD-3-Clause; bundled jemalloc, lua, hiredis and linenoise are
  permissive). **Accepted.**

## Item 2: base pull (`offline_check.sh`): no finding
- The ERE is anchored and needs `:tag@sha256:<64 hex>`. It refuses a leading `-`, a two-line value,
  `;`, `$()` and host:port (probe 6). The ref is used quoted, and the step dies on failure with no retry.
- No new egress: it is the same Docker Hub ref BuildKit already pulls in `build.sh`. The pull runs in
  the host half, and the gates/gates-it networks are unchanged. CLAUDE.md's "builds and pulls images"
  still holds.
- I-1 (info): the ERE accepts a registry-qualified ref. That is the same trust as the Dockerfile itself.

## Item 3: drift step: no finding
- `mktemp -d dist/.ke-drift.*` gives 0700, and the subdirectories are set to 0700. `set -e` covers the
  unchecked `mkdir`/`chmod`. The work dir is removed on success and by the EXIT trap. `dist/` is in
  `df_paths`, and the tar holds only the public base.
- The syft run uses the same hardened service under the offline project with `--pull never`.
- The checker runs with `--network none --read-only --cap-drop ALL`, no-new-privileges, the caller's
  uid, `-I` and read-only mounts. `ADDED_PACKAGES` is read with `ast.literal_eval`, never imported.
  `app_ref` must start with `ke-app:`, so it cannot be read as an option.
- I-2 (info): the checker runs inside the image it checks, and both the drift and finish steps use the
  image's own `/app/uv.lock`. That makes it a consistency check, not a security control. U10's revision
  label covers staleness.
- I-3 (info): `docker save name:tag@digest` has been confirmed only on the containerd store. It fails
  closed elsewhere; confirm on CI at U11.

## Item 5: `always`
Every entry matches its real image, with no "not catalogued" (probe 2). openldap and cyrus-sasl2 cover
libldap-2.5-0, libsasl2-2 and libsasl2-modules-db in ke-app (I-1 closed for `always`). Missing
components: M-1, M-2, L-1. postgres openldap/cyrus-sasl2: optional, because syft's ids already carry
GPL; I would add them for parity (info).

## Item 6: evidence sweep
No API keys, tokens, private keys, credential URLs, profile paths or SIDs in `u4/`. The only IPs are
Docker-internal (172.19.0.2, 192.168.176.2, 127.0.0.1). The `exec(` in `u4_controls.py` is mutant
source text, not executed on input. No model-host address appears.

## Re-check after rework round 1 (2026-10-23)

Scope: `git diff 464fa11` plus untracked files (round-1 state). Probes: `u4/r1-security-probes.txt` (A-E).

### Verdict: PASS (0 critical, 0 high; 2 low, non-blocking)

| Id | Status |
|---|---|
| H-1 | **Closed.** `_hash_only`/`_missing` match N8 (split on whitespace and parens, AND/OR/WITH any case, exception after WITH dropped, at least one id, all `LicenseRef-[0-9a-f]{64}` by fullmatch). Probe A, an independent recount: 59 hash-only rows (ke-app 18, neo4j 9, phoenix 10, postgres 22) and no other row carries a hash, so none stays hidden. No hash mixed with a real id, inside one expression or across fields. No hex `LicenseRef-` of another length. Unlicensed totals 19/0/28/35/25/1 equal `r1-real-run-report.txt` (bundle.sh on fresh SBOMs), each hash row marked. |
| M-1, M-2, L-1 | **Closed.** All 25 `always` entries match real rows (probe B). gcc-12: 3 rows in ke-app and postgres. gcc-14: 3 in neo4j, 4 in phoenix (with libgomp1). jrt-fs: 1. `upstream=busybox`: busybox-binsh and ssl_client. `upstream=apk-tools`: libapk. `always_problems` rejects an image that is not bundled, so a missed `neo4j` -> `ke-neo4j` rename at U4b fails the test and does not drop coverage silently. |
| M-3 | Moved to the human. Q67: ke-neo4j without `products/` (U4b, N16). Not open for U4. |
| L-2 | **Closed.** Probe D runs the real `sbom` service config, overriding only image, entrypoint and command; no syft run. Results: `/tmp` is `rw,nosuid,nodev,noexec`, mode 1777; the caller's uid can create `/tmp/cache`; a copied binary in `/tmp` gets "Permission denied"; the root is read-only; CapEff is 0; NoNewPrivs is 1; the only interface is `lo`. |
| L-3 | **Closed** for report lines. `CONTROL_RE` covers C0, DEL and C1 (`\x00-\x1f\x7f-\x9f`), and the purl, SPDXID and name are all cleaned (probe C: ESC, CSI `\x9b`, NEL `\x85` and DEL are escaped). The image name is checked against `NAME_RE`, and purl types are restricted to `[a-z0-9.+-]`. The residue is L-5. |
| N5 | No finding. `$out` is made absolute before `floor_probe`, so `dirname` never sees a leading `-`. Every expansion is quoted, `df` gets `--`, and `$1` in messages is the operator's own path. The loop ends at `/`. The `.ke-sbom.*` work dir comes from `mktemp -d` (0700, random name), which is safe even when the parent is world-writable. |
| Evidence | Clean: new `u4/r1-*`, `r1_*.py` and `tests/fixtures/sbom-u3/*.tsv` (byte-identical to `u3/sboms/`). No keys, tokens, private keys, credential URLs, profile paths, SIDs or model-host address. The IPs are Docker-internal or version strings. The fixtures hold only purl, version and licence ids, all printable ASCII. The only path is the container-side `/in/<name>.tar` in the `pkg:oci` root, with public config digests. |

### New findings (non-blocking)
- **L-4 (low, U5 design): hash-only as "missing" can open the classifier.**
  - N8 calls a hash-only field *missing*, and its input order reads `licenseDeclared` and then, if that is missing, `licenseConcluded`. So declared `<hash>` with concluded `MIT` classifies as MIT, and the row is not reported either (probe C, row b). That contradicts N8's own "hash ids are unknown, `needs` = true". Zero such rows today.
  - Fix at U5: hash-only counts as missing for report membership only. In the classifier it is a set field with an unknown id, so the both-set rule applies and the row needs source.
  - Add a U5 row: declared `<hash>`, concluded `MIT` gives needs source and is listed as unidentified.
  - Also treat the tokens `NONE` and `NOASSERTION` inside a compound expression as unknown. Today `<hash> OR NOASSERTION` counts as licensed; syft does not emit it.
- **L-5 (low): SBOM text still printed raw outside `report_lines`.**
  - `validate()` l.100/102 print `sid` raw after it fails `SPDXID_RE`, and that regex's `$` accepts a trailing `\n`.
  - `drift_problems` prints the unquoted Debian name `n` and the CPython version raw (offline_check.sh). Both are failure paths on our own pinned generator.
  - Fix: pass them through `_clean` and use `fullmatch`.
- I-4 (info): the hash match is case-sensitive, as specified. Treat a syft digest bump as a PSC-22 re-review trigger, since "a digest changes" should include the generator's.
- I-5 (info): U+2028 and bidi controls are not escaped. They are outside the C0/C1 requirement.

### Per-image review of the unlicensed rows (PSC-22)
How each is met. `always` = the source check whatever syft says. `hash` = N8/U5 makes `<hash>` need source, U7 locks the Debian source by the `deb` kind, and an `exempt` is allowed only where marked. Licences read from the image's own `/usr/share/doc/<pkg>/copyright` (probe E).
- **ke-app (19): accepted.**
  - python: cleared at the first audit.
  - `always`: libc-bin, libc6 (glibc); gcc-12-base, libgcc-s1, libstdc++6 (gcc-12).
  - GPL-family, `hash` -> U7 deb, no exemption: base-files (GPL-2+), debian-archive-keyring (GPL-2+ support files), libcrypt1 (LGPL-2.1+), libgcrypt20 (LGPL-2.1+/GPL-2+), libgnutls30 (LGPL-2.1+, GPLv3+), libtasn1-6 (LGPL-2.1+), libsemanage2 and libsemanage-common (LGPL-2.1+).
  - libselinux1: the library is public domain, but its copyright file carries GPL-2 lines (avcstat.c and the Debian changes). By the libldap convention it is GPL-family, so it ships source (corrects my first note).
  - Not GPL-family: libgssapi-krb5-2, libk5crypto3, libkrb5-3, libkrb5support0 (MIT-style; the one dual file is BSD OR GPL-2+, BSD elected). A U6 `exempt` is acceptable.
- **ke-gateway (0): accepted.**
- **neo4j (28): accepted for U4.**
  - `always`: gcc-14-base, libgcc-s1, libstdc++6, openjdk, jrt-fs.
  - GPL-family, `hash` -> U7 deb: wget (GPL-3 with the OpenSSL exception, `/usr/bin/wget`), libgnutls30t64, libtasn1-6, libcrypt1, libcrypt-dev, debian-archive-keyring.
  - 16 permissive maven rows: as at the first audit.
  - fleet plugin: Q67, gone in ke-neo4j. At U4b, check that the row has left the report.
- **phoenix (35): accepted.**
  - `always`: gcc-14-base, libgcc-s1, libgomp1, libstdc++6.
  - GPL-family, `hash` -> U7 deb: libcrypt1.
  - python3.13-minimal, libpython3.13-minimal, libpython3.13-stdlib: PSF, but the copyright file carries GPL-2+ text (readline note, Documentation block). Source by default; any exemption must show those files are not in these packages. readline itself (libreadline8t64) is flagged by its GPL ids.
  - Not GPL-family, U6 `exempt` acceptable: the 4 krb5 rows; pandas 2.3.3 (BSD-3-Clause; its GPL mentions are only the bundled PSF history table).
  - The other 21 rows: as at the first audit.
- **postgres (25): accepted.**
  - `always`: libc-bin, libc-l10n, libc6, locales (glibc); gcc-12-base, libgcc-s1, libstdc++6.
  - GPL-family, `hash` -> U7 deb: base-files, debian-archive-keyring, libcrypt1, libgcrypt20, libgnutls30, libksba8 (LGPL-2.1+/GPL-2+), libselinux1, libsemanage2, libsemanage-common, libtasn1-6.
  - Not GPL-family, `exempt` acceptable: the 4 krb5 rows, libxslt1.1 (MIT).
  - The 3 golang rows: as at the first audit.
- **valkey (1): accepted** (as at the first audit).
- **New `always` entries now: none.** `always` covers what the generator hides. After H-1, no hash row is hidden: each is reported and marked, and N8 fails closed on it. Everything GPL-family in Debian reaches its source by the `deb` kind at U7, and this list backs that up if U5 slips. Optional, not required: `{"image":"neo4j","match":"pkg:deb/debian/wget","why":"PSC-22: wget (GPL-3), a shipped executable"}`, renamed `ke-neo4j` at U4b.
