# platform-sbom U9: expected values before any real bundle run (R-row; orchestrator, 2026-10-29)

Lock at HEAD 1a7a9e2, sha256 `12eebc8cd09e5effc6934a1a3b67decc053cda923720dda07a8909a137fc761b` (unchanged since u8/expected.md). From `fetch_plan` / `sample_keys`, read-only, `python3 -I`.
A real `bundle.sh --sources` run must produce exactly these; a difference is a defect, never a hand edit.

## sample, amd64
- components (lock keys for the arch): 183; shipped keys: 7; not-shipped keys: 176
- `app/sources/files/`: 25 files (one per distinct sha256), 136571547 bytes; plan rows 25
- `fetch.json` lock_sha256: `12eebc8cd09e5effc6934a1a3b67decc053cda923720dda07a8909a137fc761b`; `index.json` lock_sha256 the same; status `shipped` for the 7 keys, `not-shipped` only in a sample bundle

## full, amd64
- components (lock keys for the arch): 183; shipped keys: 183; not-shipped keys: 0
- `app/sources/files/`: 716 files (one per distinct sha256), 1180936586 bytes; plan rows 876
- `fetch.json` lock_sha256: `12eebc8cd09e5effc6934a1a3b67decc053cda923720dda07a8909a137fc761b`; `index.json` lock_sha256 the same; status `shipped` for the 183 keys, `not-shipped` only in a sample bundle

Exempt components in index.json: one per exempt policy entry that matches exactly one package in the bundle's SBOMs (today: the jna entries; the count is read at the run, not pinned here).

## U9c (A81 option 3; orchestrator, 2026-10-30, before any real run; lock unchanged 12eebc8c...fc761b)
Checked read-only against the lock: the apk sample key `apk:alpine-baselayout@3.7.1-r8` keeps its 2 distfiles.alpinelinux.org files (`protocols-6.4` 3144 B, `services-6.4` 12813 B = 15957 B); its 15 GitLab files (17649 B) leave the sample plan. Every one of the 19 apk keys has at least one distfiles file.
- sample, amd64: 7 keys, 10 files (10 distinct sha256), 136553898 bytes; plan rows 10. Index: shipped 6, partial 1 (the apk key; its 2 fetched files have a `path`, its 15 others `path` null), not-shipped 176; exempt read at the run. `files/` holds 10 files.
- full, amd64: unchanged (183 keys, 876 rows, 716 files, 1180936586 bytes; no partial key, ever).
- `verify full` / CI hop lines: no `gitlab.alpinelinux.org`.
