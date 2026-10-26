# platform-sbom U5: security audit (PSC-15, PSC-22; N8, N8a, "N8 amendment, U5")

Date: 2026-10-24. Auditor: security. Tree: `agent/platform-sbom` HEAD c300d88 plus the
uncommitted U5 working tree (`git diff HEAD -- scripts/sbom_check.py scripts/smoke.sh
scripts/offline_check.sh tests/hardcoded_scan.py tests/test_engine_hardcoded.py
tests/test_neo4j_image.py` and the new `tests/test_sbom_classifier.py`).
Probes: `u5/security-probes.txt` (script `u5/security_probes.py`, gates image, `python -I`;
own containers only, `--rm`, `--network none`, label `ke.security.u5=1`). verify.sh not run
(the orchestrator runs `full`).

## Verdict: PASS

No critical, high or medium finding. Carried U4 L-4, U4b I-2 (continuation half) and U4b L-1 are
closed. U4 L-5 is closed except one residual print (L-5a, low; the reviewer's B3, confirmed).
Five low and four informational notes, all non-blocking. None of the classifier shapes occurs in
the 1015 real U3 rows, and the classifier has no caller until U9's `index`.

| ID | Severity | Status | Finding |
|---|---|---|---|
| U4 L-4 | low | **Closed** | Hash-only declared + permissive concluded, and NONE/NOASSERTION/hash leaves in expressions, now need source and are unidentified |
| U4 L-5 / review R2 | low | **Closed but L-5a** | `validate`, `drift_problems`, `psycopg_problems` strings are `_clean`ed; every `$`-anchored regex uses `fullmatch` |
| L-5a | low | New (residual of L-5) | `scripts/sbom_check.py:587`, drift's ok line, prints SBOM CPython versions raw on stdout (reviewer B3) |
| U4b I-2 (continuation half) | info | **Closed** | A Dockerfile line after a trailing backslash is never exempt; the heredoc half stays as rated |
| U4b L-1 | low | **Closed** | Smoke `find` drops `-xdev`, prunes /proc /sys /dev, and sees /data and /logs |
| U4 I-4 | info | Carried | Hash rule is case-sensitive (upper-hex or 63-hex hash = known, no source); amendment item 3 makes a syft digest bump a PSC-22 re-review trigger |
| L-1 | low | New | Token rule misses GPL-family names spelled out without a `gpl` token |
| L-2 | low | New | `none`/`noassertion` in other case, or NONE/NOASSERTION inside unparseable text, is not unknown |
| L-3 | low | New | Non-ASCII look-alike ids (Cyrillic, fullwidth, ZWJ) classify as known, no source, not listed |
| L-4 | low | New | The WITH exception slot is never read: `MIT WITH GPL-3.0-only` needs no source |
| I-1 | info | New | Wrong-type declared falls to concluded; `licenseInfoFromFiles` is ignored when declared is set (both as ruled) |
| I-2 | info | New | Smoke prune of /dev also hides /dev/shm; a `cap_drop: ALL` on neo4j would turn the step red (fail closed) |
| I-3 | info | New | Smoke echoes the raw `find` output to stderr on failure (pre-existing M-1 pattern) |
| I-4b | info | New | Expressions nested deeper than about 199 parentheses take the unparseable path (RecursionError caught; fail closed via the token and hash rules) |

## 1. L-4 closure (probe section A)
- Closed cases: declared `<hash>` + concluded `MIT` gives `(<hash>) AND (MIT)`, needs, unidentified,
  not unlicensed (A1; A2 the mirror); `<hash> OR NOASSERTION`, `MIT AND NOASSERTION`, `(NOASSERTION)`,
  `<hash> WITH Classpath-exception-2.0`, `MIT AND (<hash> WITH x)` all need source, unidentified
  (A4-A6, A8, A10); `MIT OR NONE` and `MIT OR (<hash> WITH x)` need none but are unidentified, as
  ruled (A7, A9). Junk holding a hash needs source (A31, A32: orchestrator correction).
- Precedence and case: `MIT oR GPL-2.0-only aNd Apache-2.0` = MIT elected (A16); `gPl-2.0-OnLy`
  needs (A15). Unbalanced parentheses, a comma or slash join, NEL or NUL separators all fall to the
  token rule and need source when a `gpl` token is present (A28, A34, A35, A47, A48).
- Real rows (A-d): 1015 rows, 555 need no source. The 17 no-source rows with GPL-ish words are 2 OR
  elections (`FTL OR GPL-2.0-or-later`, `BSD-3-Clause OR GPL-2.0-or-later`), 14 EPL/EDL or
  EPL-2.0 plus gnu.org classpath URL-folded ids (all `unparsed`, listed, as in N8a item 4), and
  libpsl's `LicenseRef-gnulib`, which is the FSF all-permissive notice (probe part 3).
- Robustness (A-c): `needs_source` never raised: depth 100000, width 200k operators, a 100k WITH
  chain, 1 MB leaves, and None/list/bytes inputs. Worst time 0.31 s (200k operators). No ReDoS:
  `GPL_ID_RE`, `GPL_TOKEN_RE`, `HASH_ID_RE`, `CONTROL_RE` and the five anchored regexes take at most
  0.06 s on 0.4-1.1 MB adversarial inputs.
- `unlicensed_report` unchanged (section F): `unlicensed_report`, `_missing`, `_hash_only`,
  `report_lines`, `_clean`, `MISSING`, `HASH_ID_RE` and `CONTROL_RE` are source-identical to HEAD,
  and the reports and printed lines are equal for all six images (19/0/28/35/25/1) and the 53
  crafted rows.

### Residual fail-open shapes (non-blocking; inputs from probe section A)
- **L-1** `LicenseRef-GNU-General-Public-License-v2`, `LicenseRef-GNU-Affero-General-Public-License`
  (needs=False, unparsed=False: silent), `GNU General Public License v2` and
  `LicenseRef-https---www.gnu.org-copyleft-lesser.html` (needs=False, listed unparsed). Also
  `GPLv2orlater`. syft maps licence names to SPDX ids, so none occurs today. Fix (cheap, fail
  closed): extend the token rule with `general` plus `public`, `lesser`, `affero` or `copyleft`
  (alongside `gnu`), or make every leaf that only spells a licence name `unparsed`. Before U9
  consumes the classifier.
- **L-2** `noassertion`, `NoAssertion AND MIT` (needs=False, not unidentified); `MIT AND AND
  NOASSERTION` (junk: needs=False, unidentified=False, though listed unparsed). Fix: compare the
  keyword leaves case-insensitively, and have the unparseable path treat a NONE/NOASSERTION token
  like a hash id (needs, unidentified).
- **L-3** `G` + Cyrillic ER + `L-3.0-only`, fullwidth `GPL-3.0`, `G` + ZWJ + `PL-2.0`: needs=False,
  not listed. SPDX ids are ASCII (`idstring`). Fix: a leaf with a character outside
  `[A-Za-z0-9.+:-]` is `unparsed` and needs source unless its NFKC form clears the rules. Also
  `w` + dotless-i + `th` upper-cases to `WITH` and is parsed as the operator (A24, A-b).
- **L-4** `MIT WITH GPL-3.0-only` needs no source (A25), by the amendment's "the exception id is not
  read". Fix: flag `unparsed`, and need source, when the token rule hits the exception id.
- I-1 (as ruled, N8 type rule and input order): declared `["GPL-2.0"]`, a dict or `123` with
  concluded `MIT` gives MIT (A36-A38); declared `MIT` with `licenseInfoFromFiles` `["GPL-2.0-only"]`
  gives MIT (A45). syft writes neither today.

## 2. L-5 / R2 closure (sections B, B2)
- `validate`: SPDXID, spdxVersion, dataLicense, documentNamespace, created and relationship ends
  carrying a trailing newline, ESC (0x1b) with a CSI sequence, CSI (0x9b), NEL (0x85) and DEL
  (0x7f) are all rejected and printed escaped: 35 cases, 0 raw control lines. A list-typed SPDXID
  prints escaped.
- `drift_problems` / `psycopg_problems`: purl-encoded ESC, CSI, NEL, DEL and LF in Debian names,
  CPython versions, pip, libpq5, psycopg-c and psycopg-binary versions: 0 raw control lines.
- CLI end to end (subprocess, `python -I`): `drift` with a hostile SBOM (rc 1, 6 lines, 0 raw;
  a `%0aFAKE-LINE` version cannot start a line); `finish` failing validate (rc 1, 0 raw);
  `finish` ok with report rows holding an OSC title sequence and C1 bytes (rc 0, 0 raw).
- `finish` argv: `--name`/`--git-sha` with a trailing newline, ESC or NEL fail (rc 2) and print
  via repr. No `.match`/`.search` remains on `SPDXID_RE`, `NAMESPACE_RE`, `RFC3339_UTC`,
  `NAME_RE`, `SHA_RE`, the only end-anchored patterns. Prefix patterns keep `match`, as ruled.
- **L-5a (low; reviewer B3, confirmed, probe part 5).** `drift`'s ok line
  (`scripts/sbom_check.py:587`) joins `_named(app, "generic")["python"]` raw. `_named` ignores the
  purl namespace, so `pkg:generic/x/python@3.12.15%1b%5d0%3bOWNED%07%1b%5b2J` beside the real
  `pkg:generic/python@3.12.15` passes the check (rc 0) and prints an OSC title and a clear-screen
  sequence to stdout (the offline_check log). Fix: `_clean` the joined versions (and take `py` from
  the same non-namespaced set `drift_problems` checks). Our own pinned generator's output, so low.
- U4 I-5 (U+2028, bidi controls) stands as info; it is outside the C0/C1 requirement.

## 3. PS-1.2 scanner (section C)
- The change only removes exemptions (`not continued and ...`), so nothing new can become exempt.
  The real `docker/neo4j.Dockerfile` still scans clean for 7687.
- A line after `RUN x` and a trailing backslash, with trailing blanks, or with CRLF is flagged; a
  first line, leading/trailing spaces, or a line after a backslash inside text is exempt. A
  comment line ending in a backslash also flags the next line (false positive, fail closed).
  Other paths (`docker/neo4j.dockerfile`, `docker/gateway.Dockerfile`) and `EXPOSE ... 8080` stay
  flagged. Python exemptions after a backslash line are unchanged.
- Still exempt, the same literal only, not actionable (I-2 as rated): a heredoc body line, a
  continuation broken by a comment or empty line, and a `# escape=` backtick directive.

## 4. U4b L-1 closure (probe part 2)
- In ke-neo4j (default caps, root, as `compose exec`): clean gives exactly
  `/var/lib/neo4j/LICENSE.txt`, rc 0. Fleet jars planted in the `/data` and `/logs` volumes and in
  a tmpfs at `/plugins` are printed, so the whole-output compare fails. The old `-xdev` form
  missed the /data and /logs jars (P5). Nothing under /proc, /sys or /dev is printed (P6).
- Fail closed: a non-zero `find` exit fails the step (P7: under `cap_drop: ALL`, a permission
  error gives rc 1). Injection-safe: the argv is fixed literals; the output is only compared with
  `[ = ]` and echoed, never evaluated (U4b test `test_smoke_never_evaluates_the_neo4j_output`).
- I-2: /dev/shm is pruned with /dev; neo4j loads no plugin from it. I-3: on failure the raw output
  is echoed to stderr (U4b M-1 pattern, accepted then).
- I-4b: about 199 nested parentheses exhaust the recursive parser; the RecursionError is caught and
  the text takes the token/hash path (`unparsed`), so a GPL or hash id still needs source.

## 5. Other changes
- `tree_listing`/`neo4j_tree_problems` (evidence-only): size added; a hard link resolves to its
  target's size only when the target is a regular file in the same listing, otherwise it stays
  `hardlink` and differs (fail closed). No extraction; names cleaned.
- `offline_check.sh`: one comment line. `u4/u4_controls.py`, `u4b/u4b_controls.py`: docstrings.

## 6. Evidence hygiene (probe part 4)
`u5/*` and `tests/test_sbom_classifier.py`: no keys, tokens, private keys, JWTs, credential URLs,
profile paths, SIDs, model-host name or port, or `KE_MODEL_UPSTREAM`/`KE_EGRESS_ALLOWLIST`
values. IPs are 127.0.0.1, the stack gateway's internal address in the smoke's no-route lines,
and a Temurin version string. The test file's fixtures are synthetic hashes and real U3 ids.
