# U0 (PSC-25): psycopg-c on Debian libpq, confirmed by the working build

Written by the documenter, 2026-10-22. Answers the "confirm at GREEN" items of
`design-notes.md` N0. Evidence: `u0/green-verify-full.txt` (PASS, 711 s; line
numbers below are in that file), `u0/size.md`, and the files in the diff.

| N0 item | Result | Evidence |
|---|---|---|
| uv flags: `--no-binary-package psycopg-c`, `[tool.uv] no-build-isolation-package = ["psycopg-c"]`, groups `pq-build` and `pq-c`, three `--locked` syncs | Confirmed. The app builder runs (1) `--no-dev --group pq-build --no-install-project`, (2) `--no-dev --group pq-build --group pq-c --no-binary-package psycopg-c --no-install-project`, (3) `--no-dev --group pq-c --no-binary-package psycopg-c --no-editable`; sync 3 is exact, so setuptools and wheel do not ship. ke-gates runs the same three without `--no-dev`. Default groups stay `["dev"]`, so a host `uv run` installs neither group. | `docker/app.Dockerfile`, `docker/gates.Dockerfile`, `pyproject.toml`; build lines 127, 499-505 (`Building psycopg-c==3.3.6`, `Built`, `+ psycopg-c==3.3.6`), 517 |
| `uv.lock` psycopg-c: 3.3.6, sdist only, sha256 `29c568426ad61c1b702c7d73505c43ca2c9fc5d97a8431d8d9049e731e319ff8` | Confirmed: `[[package]] psycopg-c` 3.3.6 has `sdist = {...}` and no `wheels`. `psycopg[c]` carries it under marker `implementation_name != 'pypy'`. | `uv.lock` (psycopg-c entry); test `test_ke_app_resolves_psycopg_c_not_binary` ok |
| `uv.lock` has no psycopg-binary | Confirmed: `grep psycopg-binary uv.lock` finds nothing. No platform marker keeps it. | `uv.lock`; same test |
| `pq-c` / `pq-build` under `[package.dev-dependencies]` (RED handoff note) | Confirmed: `pq-build` = setuptools, wheel; `pq-c` = `psycopg[c]`. | `uv.lock` `[package.dev-dependencies]` |
| pq-build pins | setuptools 83.0.0 is the version from psycopg-c 3.3.6's sdist build requirements. wheel 0.48.0 is the latest at lock time, because the sdist only says `>=0.37`. Both are `==` in `pyproject.toml` and hash-locked (sdist and wheel hashes) in `uv.lock`. | `pyproject.toml` `pq-build`; `uv.lock` setuptools 83.0.0, wheel 0.48.0 |
| `[[tool.uv.dependency-metadata]]` needed | Not needed: the sdist's PKG-INFO is static, so `uv lock` did not have to compile psycopg-c. No `dependency-metadata` in `pyproject.toml` or `uv.lock`. | developer U0 GREEN section of the handoff; grep of both files |
| libpq5 pin | `LIBPQ_VERSION=15.19-0+deb12u1`, the version `apt` offers at the pinned base digest, installed from `bookworm-security` (builder `libpq-dev=`, runtime `libpq5=`, same pin in gates). Tests `test_libpq_pin_matches_bookworm_base` and `test_app_dockerfile_builds_psycopg_c_on_pinned_libpq` ok. | lines 152-171, 189 (`bookworm-security ... libpq5 amd64 15.19-0+deb12u1`) |
| `ldd` path | N0 said `/usr/lib/<triplet>/`; the build shows the `/lib` alias: `libpq.so.5 => /lib/x86_64-linux-gnu/libpq.so.5` (bookworm is merged-usr; dpkg owns the `/usr` path). `smoke.sh` accepts both. `ldd` ran in the api, so it is present in the slim image. | lines 1918-1919, 2452-2453 (`smoke: psycopg c on Debian libpq5 15.19-0+deb12u1 (/lib/x86_64-linux-gnu/libpq.so.5)`); `u0/size.md` |
| `pq.__impl__ == "c"`, `version()` == `__build_version__` == pin | Confirmed in the api by the smoke step and in ke-gates by `test_gates_psycopg_is_c_impl_on_debian_libpq` and `test_smoke_checks_psycopg_c_impl_in_api` (all ok). | lines 1517-1531, 1918 |
| Smoke step in the offline client on the installed bundle | Confirmed: the second `== smoke: psycopg ==` step, inside the offline client run on the installed bundle, prints the same `psycopg c on Debian libpq5 15.19-0+deb12u1 (/lib/x86_64-linux-gnu/libpq.so.5)` line as the build-host smoke (lines 1918-1919). | `u0/green-verify-full.txt` lines 2452-2453 |
| Packages apt added for libpq5 | Only four: libpq5, libldap-2.5-0 (2.5.13+dfsg-5), libsasl2-2 and libsasl2-modules-db (2.1.28+dfsg-10). The krb5 libraries (libgssapi-krb5-2, libk5crypto3, libkrb5-3, libkrb5support0 1.20.1-2+deb12u5) and libkeyutils1 were already in the base. Corrected per `u0/security.md` I-5; this is the list for PSC-14. | `u0/size.md`; apt output lines 177-184 of `u0/green-verify-full.txt` |
| Image sizes | ke-app 265 MB (`bundle-d6b70355c452`, before) -> 259 MB (`bundle-737750d06839`, after), -6 MB. ke-gates 1.46 GB -> 1.79 GB (gcc, libc6-dev, libpq-dev; not shipped). | `u0/size.md` |
| Windows host: `uv run --locked` log_event works, no compile | Confirmed by the developer's A34 run (`log_event --help`). | developer U0 GREEN section of the handoff |

## Not confirmed

- Bundle tar size: `verify.sh full` prints no size line (`u0/size.md`).
- Scan effect "15 unseen files go, PSC-7/L-13 closes": the run shows only
  Medium/Low findings and no fixed High/Critical, but the closure of L-13 is
  security's call at U0 review, not confirmed here.
- Per-arch (aarch64) ldd path: untested; only x86_64 was built.
- `pypi.org` leaving the source `hosts` is a U7 matter, not checked in U0.
