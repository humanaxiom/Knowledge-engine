<!--
platform-sbom U1 rework round 1: target text for the developer (tester, 2026-10-23).

Replace NOTICE.md's two sections "## Base of `ke-app`" and "## Source code"
(everything from the first heading up to, not including, "## Licence texts")
with the text below this comment, byte for byte. u1_controls.py --reach splices
exactly this text into a scratch copy of today's NOTICE.md and runs all four
U1 checks on it: all return [] (see r1-red-mutants.txt).

Licence texts (test_licenses_carry_texts_for_pip_vendored_licences):
- add licenses/Apache-2.0.txt: the full canonical Apache License 2.0 text
  (https://www.apache.org/licenses/LICENSE-2.0.txt, 11358 bytes), unmodified;
- add licenses/MPL-2.0.txt: the full canonical MPL 2.0 text
  (https://www.mozilla.org/media/MPL/2.0/index.txt, 16726 bytes), unmodified;
- the test checks the markers "Apache License", "Version 2.0, January 2004",
  "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION",
  "9. Accepting Warranty or Additional Liability", "END OF TERMS AND CONDITIONS"
  (>= 10000 chars) and "Mozilla Public License Version 2.0", "1. Definitions",
  "Exhibit A - Source Code Form License Notice",
  'Exhibit B - "Incompatible With Secondary Licenses" Notice' (>= 15000 chars);
- both must be git-tracked (git add) to ship: bundle.sh copies every file
  `git ls-files -- licenses` lists, and test_offline_bundle holds that parity.
- Not tested, suggested for consistency: a line in "## Licence texts" giving
  each file's source URL, as the GNU and Valkey lines do.
-->
## Base of `ke-app`

The shipped (last) stage of `docker/app.Dockerfile` builds on
`python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258`.
Besides `/opt/venv` and `/app` it holds:

- CPython 3.12 under `/usr/local`, under the Python License 2.0 (SPDX
  `Python-2.0`: the PSF licence stacked on the BeOpen, CNRI and CWI
  licences). `/usr/local/lib/python3.12/LICENSE.txt` inside the image holds
  the full licence stack and the licences of the third-party code CPython
  bundles.
- The Debian 12 (bookworm) packages of the base image, each under its own
  licence in `/usr/share/doc/*/copyright` inside the image and, where the
  bundle carries one, in the image's SBOM.
- The Debian packages the last stage adds: `libpq5` 15.19-0+deb12u1 (the
  `LIBPQ_VERSION` pin), under the PostgreSQL licence, and what apt pulls in
  for it: `libldap-2.5-0`, `libsasl2-2` and `libsasl2-modules-db`, with their
  licences in `/usr/share/doc/*/copyright` (and the SBOM where the bundle
  carries one).
- The base's own pip 25.0.1 in the system site-packages (MIT). It is outside
  `uv.lock`, so it is not in the generated table of `THIRD_PARTY_NOTICES.md`.
  The packages pip vendors, listed in `pip/_vendor/vendor.txt`, keep their
  own licences (among them Apache-2.0 and MPL-2.0); pip 25.0.1 ships no
  licence files for them, so the bundle carries those two texts as
  `licenses/Apache-2.0.txt` and `licenses/MPL-2.0.txt`.

uv is not shipped: it runs only in the `builder` stage, which does not ship.

## Source code

`THIRD_PARTY_NOTICES.md` says, in its "Source code" section, for each
GPL-family component whether its source is in `sources/` of this bundle.
A bundle whose `THIRD_PARTY_NOTICES.md` has no "Source code" section has
no `sources/` and carries no third-party source code, so it does not
itself provide the source that any of these licences requires.

