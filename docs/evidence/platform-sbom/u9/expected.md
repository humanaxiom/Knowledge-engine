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
