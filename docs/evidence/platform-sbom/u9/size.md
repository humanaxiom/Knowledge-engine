# platform-sbom U9b: size and time of the bundle with sources (tester, 2026-10-29; replaces the developer's GREEN version)

Host: aria-alien1, the Windows 11 dev box (Docker Desktop 29.5.2, linux/amd64 daemon, 24 CPUs), Git Bash.
Code: HEAD 1a7a9e2 plus the uncommitted U9b rework-1 GREEN edits. All timings are local. They are informational and
never a CI figure: CI's numbers come from U11, and B-sources-bundle (30 s on CI) is measured at R16, not asserted here.

## Full set, amd64: the Q79 recorded run (R10/R11), 2026-10-29
Sources: `full-fetch-run.txt` (fetch) and `full-bundle-run.txt` (bundle; it compares every item against `expected.md`).

| Item | Value |
|---|---|
| fetch (`bundle_fetch.sh --set full`) | 394 s stage (`fetched ... in 392.8 s`), wall 6m36.1s, 21:33:38Z-21:40:15Z |
| source set | 716 files, 1180936586 B, 183 components (full, amd64); fetched dir 1181080083 B with fetch.json |
| bundle wall time (`time bash scripts/bundle.sh ... --sources-set full`) | 2m37.9s (real), 23:24:01Z-23:26:39Z, exit 0 |
| stage seconds (O-15 marker) | `bundle: sources: check 7 s, copy 12 s, index 2 s, notices 0 s` (21 s total; whole-second `SECONDS` deltas) |
| bundle bytes (`du -sb`) | 2147272340 B (2.00 GiB) |
| `app/sources/` bytes | 1181831173 B (1180936586 B of files + 894587 B for `index.json`) |
| bundle bytes without `app/sources/` | 965441167 B (920.7 MiB) |
| `app/sources/index.json` | 894587 B; 185 components: 183 `shipped`, 0 `not-shipped`, 2 `exempt` (jna, javassist); 876 file rows |
| `MANIFEST.sha256` | 111025 B, 764 lines (716 of them under `app/sources/files/`); 10.6% of the 1048576 B cap |
| release record | 102 B, one line, beside `--out` |

Rework-2 re-run (O-17 (5)), 2026-10-30T01:08:17Z-01:10:48Z, on the rework-2 GREEN `bundle.sh`: every byte and count row above
is unchanged (bundle 2147272340 B, `app/sources/` 1181831173 B, without 965441167 B, index 894587 B, MANIFEST 111025 B / 764
lines). Only the timings moved: wall 2m31.2s; marker `bundle: sources: check 6 s, copy 12 s, index 1 s, notices 1 s` (20 s).
Source: the "2026-10-30 rework 2 re-run" section of `full-bundle-run.txt`.

## Sample set, amd64: the verify-full bundle, 2026-10-29
Source: `sample-bundle-run.txt` (an extract of `u9b-r1-green-verify-full.txt`, verify full PASS 1422 s, offline_check PASS 249 s).
The sample bundle is removed by offline_check's EXIT trap, so that run did not record its bundle bytes or manifest size.

| Item | Value |
|---|---|
| fetch (`bundle_fetch.sh --set sample`) | 23.8 s (`fetched 25 files, 136571547 bytes, 7 components (sample, amd64) in 23.8 s`) |
| source set | 25 files, 136571547 B, 7 components (sample, amd64) |
| stage seconds (O-15 marker) | `bundle: sources: check 1 s, copy 1 s, index 1 s, notices 1 s` |
| bundle bytes, with and without `app/sources/` | not measured. Estimate: 965441167 B (the full run's size without sources, same images) + 136571547 B of files + the index, about 1.03 GiB. The earlier GREEN run's `df` delta was +1093400 KiB (about 1.04 GiB). |
| `MANIFEST.sha256` | not measured (the bundle was removed first). Estimate: 73 lines (the full run's 48 lines outside `app/sources/files/` plus 25). The full run's 111025 B is the upper bound that matters for the cap. |

Measured at A34 (2026-10-30, `a34-windows-run.txt` step 2; Git Bash, a sample bundle written to the session scratch dir and
removed after): bundle 1102759214 B (1.03 GiB), `app/sources/` 137402164 B (136571547 B of files + 830617 B for `index.json`),
without `app/sources/` 965357050 B; `MANIFEST.sha256` 8066 B, 73 lines (25 under `app/sources/files/`), so the 73-line estimate
above holds; wall 1m57.9s; marker `bundle: sources: check 1 s, copy 1 s, index 1 s, notices 0 s`.

## Notes
- Design item 12 gave "941 MiB today, about 2.0 GiB after" for the full bundle. This run measures 920.7 MiB without
  sources and 2.00 GiB with them. The images in the bundle are not pinned by `expected.md`, so the difference is
  recorded here and is not a defect.
- U10's N14 tmpfs sizing: the `/install` staging adds the source bytes: about 0.13 GiB for the sample and 1.10 GiB
  for the full set.
