# architect: per-arch bundles, code-first docs, Q50 (2026-10-19)

Docs only. Files: `docs/architecture.md` (§2.5 *Arch* (new), Bundle
preconditions, step 5 `bundle.json`, Install portability, step 5 arch
check, step 9 publish without `mv -T`, offline_check host step 3;
ADR-KE-012; §2.6 item 5b), `docs/requirements.md` (PS-2.9 OS note, PS-3.1
"per-arch bundles" block and the macOS criteria, PS-3.2 *Which arch*, PS-3.2
*Docs*, PS-Q10), `docs/open-questions.md` (Q20 note, Q49–Q53).

Rulings applied, latest first, so later ones override earlier ones:
1. Native arm64 on `aria-gb10` through a docker context. The arch comes
   from the target daemon, `--arch` is only an assertion, and there is no
   `--platform` anywhere. Q51 is resolved by a recorded run on `aria-gb10`.
2. The buildx cross-build ruling. It was designed first and then withdrawn
   by ruling 1. Cross-build with emulation is kept as an optional
   alternative, through an emulated arm64 `dind` used as the target daemon.
3. Q50 in scope: `install.sh` must run on bash 3.2 with BSD tools. Q52
   holds the pointer to MLX.
4. "Build it for both": code-first is the primary path.

Proposed tests (PS-3.1): `test_arch_normalisation`,
`test_install_refuses_arch_mismatch`, `test_bundle_arch_comes_from_daemon`,
`test_bundle_refuses_image_of_other_arch`, `test_bundle_json_records_arch`,
`test_bundle_out_name_carries_arch`,
`test_install_sh_uses_no_gnu_or_bash4_constructs`,
`test_install_sh_runs_with_bsd_tool_shims`,
`test_quickstart_code_first_comes_first`.

Flagged: Q53 (do the launch, teardown and smoke scripts on the Mac fall
under Q50?), and the residual risk of publishing without `mv -T` (for
security to judge).

Verify: `COMPOSE_PROJECT_NAME=ke-arch-arch scripts/verify.sh fast` → PASS,
488 tests OK. Full output: `architect-arch-verify-fast.txt`.
