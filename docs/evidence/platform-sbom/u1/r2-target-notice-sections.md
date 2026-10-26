# U1 round 2: TARGET NOTICE.md sections and licence-file header (tester)

Tester, 2026-10-23. For the developer: the text between the `notice` markers
replaces NOTICE.md from `## Base of `ke-app`` to the end of the file (the
psycopg, vendor and gateway sections above it are unchanged). The text
between the `header` markers is the first five lines of
`licenses/CPython-3.12-incorporated.txt` (four header lines and a blank);
the extract follows, from the line `Licenses and Acknowledgements for
Incorporated Software` to the end of `Doc/license.rst` at `v3.12.15`, bytes
unchanged (N10a). The sha256 is the architect's probe fetch
(`u1/r2-pip-probe.txt`); the maintainer's fetch must reproduce it or record
its own, and security's second fetch confirms it (Q48). The analyst owns
the wording; the tests pin only the facts. Spliced into a scratch copy of
NOTICE.md with a stand-in extract, this passes all five NOTICE checks
(`u1_controls.py --reach`, recorded in `r2-red-mutants.txt`).

<!-- notice:start -->
## Base of `ke-app`

The shipped stage of `docker/app.Dockerfile` is `runtime`, which the last
stage copies whole (`FROM scratch`, then `COPY --from=runtime / /`). It
builds on
`python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258`.
Besides `/opt/venv` and `/app` it holds:

- CPython 3.12 under `/usr/local`, under the Python License 2.0 (SPDX
  `Python-2.0`: the PSF licence stacked on the BeOpen, CNRI and CWI
  licences). `/usr/local/lib/python3.12/LICENSE.txt` inside the image holds
  that licence stack only. CPython also builds in third-party code under
  its own licences (among them expat and libmpdec), whose texts are in
  `licenses/CPython-3.12-incorporated.txt`.
- The Debian 12 (bookworm) packages of the base image, each under its own
  licence in `/usr/share/doc/*/copyright` inside the image and, where the
  bundle carries one, in the image's SBOM.
- The Debian packages the shipped stage adds: `libpq5` 15.19-0+deb12u1 (the
  `LIBPQ_VERSION` pin), under the PostgreSQL licence, and what apt pulls in
  for it: `libldap-2.5-0`, `libsasl2-2` and `libsasl2-modules-db`, with their
  licences in `/usr/share/doc/*/copyright` (and the SBOM where the bundle
  carries one).

pip is not shipped: the shipped stage removes the base's pip and
`ensurepip`'s bundled pip wheel, so the image carries neither pip nor the
packages pip vendors.

uv is not shipped: it runs only in the `builder` stage, which does not ship.

## Source code

`THIRD_PARTY_NOTICES.md` says, in its "Source code" section, for each
GPL-family component whether its source is in `sources/` of this bundle.
A bundle whose `THIRD_PARTY_NOTICES.md` has no "Source code" section has
no `sources/`, so it does not itself provide the source that a
GPL-family licence requires.

## Licence texts

`licenses/GPL-3.0.txt` and `licenses/LGPL-3.0.txt` are the GNU texts,
unmodified, fetched over HTTPS from https://www.gnu.org/licenses/gpl-3.0.txt
and https://www.gnu.org/licenses/lgpl-3.0.txt.

`licenses/BSD-3-Clause-valkey.txt` is the upstream Valkey `COPYING` at tag 8.1.10,
unmodified, fetched over HTTPS from
https://raw.githubusercontent.com/valkey-io/valkey/8.1.10/COPYING.

`licenses/CPython-3.12-incorporated.txt` is the "Licenses and
Acknowledgements for Incorporated Software" section of CPython 3.12.15's
`Doc/license.rst`, unmodified, fetched over HTTPS from
https://raw.githubusercontent.com/python/cpython/v3.12.15/Doc/license.rst;
its header gives the fetched file's sha256.
<!-- notice:end -->

<!-- header:start -->
CPython 3.12.15: "Licenses and Acknowledgements for Incorporated Software"
Source: https://raw.githubusercontent.com/python/cpython/v3.12.15/Doc/license.rst
Source sha256: 341832873fd316a37927e79385093fbbfd40a467428480835fe435a80cadf4e5
Extract: from that heading line to the end of the file, unmodified.

<!-- header:end -->
