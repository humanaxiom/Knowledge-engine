# Q74: CI verify-job timing, stage by stage (orchestrator, 2026-10-28)

Source: `gh run view <id> --log`, the `== <stage>: PASS (<s>) ==` markers and the unittest summary
lines. CI timeout: `.github/workflows/ci.yml` `timeout-minutes: 37` (derived at PS-3.4 from runs
of 24.5 and 23.0 min + 50%). Runner: private 2-vCPU runner (one job at a time).

| Run | Head | Units | Unit stage | Integration | offline_check | verify full | Job wall |
|---|---|---|---|---|---|---|---|
| 40244299450 (2026-10-25) | 86f7831 | U0-U7c | Ran 1047 tests in 912.573s | 15 in 3.9s | PASS (195s) | PASS (1388s) | 23m13s |
| 40628987168 (2026-10-28) | 0630586 | +U7d, U7e | Ran 1110 tests in 1566.982s | 15 in 5.2s | PASS (230s) | PASS (2146s) | 35m53s |

Delta: verify full +758 s, of which the unit stage is +654 s (+63 tests, the U7d/U7e lock tests:
`tests/test_sources_lock*.py`, `tests/test_sources_resolve.py`), offline_check +35 s, and the
remainder (~70 s) sits before the unit stage (image build/pull on the new base, the scan-db fetch).
Headroom at 0630586: 37 min - 35m53s = 67 s. U8 adds a fetch stage to offline_check (sample set:
7 keys, 25 files, 136.6 MB) and more tests.

The per-test profile is in `test-profile-q74.md` (tester). Proposal to the human follows in the
handoff once the profile names the causes.

## Correction (orchestrator, 2026-10-28, after the tester's profile `test-profile-q74.md`)

The attribution above ("the unit stage +654 s for +63 tests") is WRONG. The profile ran both
trees in the gates image with the gate's settings: 86f7831 (1047 tests) 731.4 s wall / 645.5 CPU-s;
0630586 (1110 tests) 736.3 s wall / 646.4 CPU-s. The new tests cost 12.1 s in total; coverage and
the 3.12.16 base change nothing measurable. On CI every unchanged module ran 1.6-1.9x slower
between the two runs (test_offline_bundle 338 -> 574 s, test_stack_scripts 192 -> 315 s), the
gates-it resource probe shows the same work costing 1442 CPU-s instead of 844, `cpu_steal_ticks`
0 both times and `psi_cpu_some` 189 -> 458 s: the runner host was under CPU pressure from
something outside the job. CI wall = ~735 s x a runner factor that moved from 1.24x to 2.13x.
A timeout sized from one run will fail intermittently as that factor moves; size it on the
factor's spread or on a CPU-time budget (the probe's `cg_cpu_usage_us`, already printed).
Cheap test savings exist (InstallPs1 tamper pair ~14 s, LintScriptTest minimal project ~30 s,
shared bundle.sh runs up to ~45 s locally) but they are a separate item and do not explain Q74.

## The runner (orchestrator, 2026-10-28; `gh run view 40628987168 --log`, job setup group)

Runner version 2.338.0; "Runner Image Provisioner: Hosted Compute Agent, Version 20261021.618,
Region southcentralus, Cloud Azure"; Operating System Ubuntu 24.04.5 LTS; Runner Image
ubuntu-24.04, Version 20261012.334.1. So the runner is GitHub-hosted on Azure, not a machine of
the project's: the outside CPU pressure in the second run is a noisy-neighbour effect of the
hosted pool, and the CI sample fetch's egress is independent of the dev box and of SFU
(U8-11's third-fetch independence holds). Q74 option 3 ("remove the outside load") is therefore
not available; options 1 and 2 stand.
