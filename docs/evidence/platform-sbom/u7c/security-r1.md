# platform-sbom U7c rework round 1: security re-check

Date: 2026-10-25. Auditor: security. Scope: U7c rework round 1 GREEN. `sources_resolve.py` and
`sbom_check.py` equal `u7c/r1-target-*`. Diffs read against `u7c/target-*`. Rulings:
design-notes l.1894-2105, items 1-9. Probes: `u7c/security-r1-probes.txt` (script
`u7c/security_r1_probes.py`; gates image, `python -I`; lock rules on the test good lock, fake
network, pure parsers; no external request). verify.sh not run.

## Verdict: PASS

No critical, high or medium finding. L-1, L-2, L-3 and I-1 are closed. The item-9 exception (the
GitLab API raw form) refused every smuggling input I built. No new finding; three informational
notes.

| ID | Status | Evidence / input |
|---|---|---|
| L-1 | **Closed** | `main%2Freadline%2Fsub%2FAPKBUILD` gives "the APKBUILD is not at <repo>/<origin>/APKBUILD"; another file in a subdirectory through the API form is still accepted |
| L-2 | **Closed** | Refused: U+0085, U+2028, U+2029, VT, FF, 0x1c, DEL, NUL, ESC and a lone CR, in a value, a field name, a continuation line, the armour, the signature block, an ignored line and after the signature. TAB is allowed. Duplicate fields are refused case-blind and across paragraphs. CRLF files parse. A 1 MB field takes 0.004 s, and 400k continuation lines 0.051 s |
| L-3 | **Closed** | A 100-entry page with no `x-next-page`, with `2`, or with a space is refused ("listing may be truncated"). Only an empty header proceeds |
| I-1 | **Closed** | The tree query is `path=main%2Freadline` (`quote(safe='')`) |
| I-5 | info, new | The real challenge id `__goaway_id=e788cf47...` (from the Windows proof) is copied into `tests/test_sources_resolve.py` l.2369 and `u7c/r1-red-verify-fast.txt`. It is a short-lived anti-bot nonce, not a credential. A synthetic value would be cleaner |
| I-6 | info, new | A leading U+FEFF or a U+200B is not in the refused set. They cannot do harm: `﻿Source` leaves `Source` unset, `x<U+200B>` does not equal the key (both fail closed on Source/Version), and file names must pass `safe_name` |
| I-7 | info, new | A relative challenge Location (`?__goaway_challenge=...`) keeps the `%2F` path, so the hop rules refuse it at once ("not a plain path"), instead of following it to a 418. The absolute form GitLab sends (`/.within.website/challenge?...`, a plain path) is followed and ends in `HTTP 418`, as the design says. Both fail closed. A 307 to another path on the same host (`/api/v4/projects/1/...`) is followed; its content must still match the files-API `content_sha256` or the APKBUILD sha512 |

## 1. Item 9: the GitLab API raw form (probe U7c-r1-1)
The baseline equals the canonical form:
`https://gitlab.alpinelinux.org/api/v4/projects/alpine%2Faports/repository/files/main%2Freadline%2FAPKBUILD/raw?ref=<commit>`.
Every variant is refused:
- **Project:** `alpine%2Faports%2F..`, `alpine%2faports`, `alpine%2FAports`, a numeric id,
  `alpine/aports`.
- **Ref:**
  - a second `ref`, `ref=HEAD`, `ref=<c>%00`, an upper-case or another commit
  - no query, `x=1&ref=<c>`, `ref=<c>&x=1`, a fragment
- **Path segment `<P>`:**
  - `%252F` (it decodes to a `%`), `%2F..%2F`, `.%2F`, `%2e%2e`
  - lower-case `%2f`, `%C3%A9`, `%FF`, `%5C`
  - a subdirectory APKBUILD, another origin, another repo, an empty segment
  - a raw `/` inside `<P>`
- **Shape:** the metadata form without `/raw`, `/raw/raw`, the old `/-/raw/` form, userinfo,
  `:443`, an upper-case host, `api/v3`, `HTTPS://`.
- **Other kinds:** the form is refused on a maven entry (query and plain-path rules), and a query
  on a pypi URL is refused.

The exception is scoped to `kind == "apk"` and the exact shape (`_apk_api_shape`). Elsewhere,
the query and `%` rules stand. U8 has not been written yet; it must fetch the lock URL verbatim
and keep the hop rules, which refuse `%` in a redirect path.

## 2. The 307 challenge (probe U7c-r1-2)
- A 307 with no Location gives `HTTP 307`.
- The absolute challenge Location gives `HTTP 418` after 2 requests.
- A relative challenge Location is refused at the hop (I-7).
- A 307 to another host is refused.

## 3. Evidence hygiene (`u7c/r1-*`, `r1_controls.py`, `review-r1.md`, `reviewer-r1-*`, tests)
- No keys, tokens (no `glpat-` or `PRIVATE-TOKEN`), signed query strings, private keys,
  password values, profile paths, SIDs, or model-host name or port.
- The credential-URL hits are synthetic userinfo cases.
- IPs: 127.0.0.1, the stack gateway address in the smoke no-route lines, and a Temurin version.
- I-5: the challenge nonce.
