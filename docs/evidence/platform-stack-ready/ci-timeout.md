# CI timeout (PS-3.4, ruling C1/Q36)

- Measured run: commit 42547d0, job `verify`, 2026-10-19T09:41:14Z to 09:47:43Z = 389 s wall (verify full step: 382 s). Log: `ci-run-42547d0.txt`.
- 389 s x 1.5 = 584 s; rounded up to whole minutes: timeout-minutes 10 (was 20).
- Previous baseline (2a, 0f2821c): 274 s.
- Re-measure when a later item adds substantial gate work; the 1 MB hook timing tests passed on this run.
