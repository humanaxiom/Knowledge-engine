# platform-sbom U7e developer GREEN (2026-10-27)

Downloads (own empty dirs under the scratchpad, never in the repo; extracted with tar -xJf of two named members only):
- license.rst v3.12.16 (raw.githubusercontent.com/python/cpython/v3.12.16/Doc/license.rst): sha256 341832873fd316a37927e79385093fbbfd40a467428480835fe435a80cadf4e5 (equal to the 3.12.15 file's Source sha256)
- Python-3.12.16.tar.xz (www.python.org/ftp/python/3.12.16/): sha256 b5796915dc45ff745cfb4e990a7e7c93d6f546328a102ce31448d69ebc37575c = the ruled value, checked BEFORE extraction.

Body diffs against the 3.12.15 files (header = lines 1-4/5 only changed):
- incorporated: heading-to-end of the fetched license.rst (from line 298) vs the file body (line 6 on): cmp identical.
- HACL (23 lines) vs head of Modules/_hacl/Hacl_Hash_SHA2.c: cmp identical.
- KaRaMeL (2 lines) vs head of Modules/_hacl/include/krml/internal/target.h: cmp identical.
So only headers changed; no new third-party header.

Other: libpq5 pin and ADDED_PACKAGES unchanged (build.sh built ke-app and ke-gates on the new base; developer-build.txt, exit 0).
Fixture: fixture-diff.txt (6 rows, all explained). Lock: lock-run-1.txt (exit 0), key-diff.txt (+openssl~u2, +ca-certificates~u2, -ca-certificates~u1; tzdata has no key, public-domain).
verify fast: developer-verify-fast.txt (FAIL, 1110 tests, failures=9 errors=1, all listed in the handoff).
verify full: developer-verify-full.txt (FAIL at test.sh, same 10; the scan stage is not reached when tests fail, as at RED).
Supplementary, NOT a gate substitute: developer-scan-direct.txt = scripts/scan.sh on the image verify full built (ke-app:wt-33a132fbfdd7, same tree), exit 0; libssl3/openssl 3.0.22-1~deb12u2 only Negligible CVE-2025-27587 (suppressed); no failing finding.
Host note: first full attempt failed on "all predefined address pools have been fully subnetted" (docker network pool exhausted by other projects); removed the stale ke-dev-l5r1_default network (this repo's, unused) and re-ran.
