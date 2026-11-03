# platform-sbom handoff, part 19 (archived 2026-11-02 by the orchestrator): Q82 / U9d detail

Moved verbatim from docs/handoffs/platform-sbom.md.

## Q82 / U9d (A82a: launch diagnostic + runner measurement; plan gate PASS 2026-10-30, O-22; detail: archive/platform-sbom-part18.md)
- Q82: PR #15 CI run 40993359777 failed twice at the offline client's launch; runner disk at 100% at the failure; the client prints nothing from the dead container (`docs/evidence/platform-sbom/ci/`). A82a: U9d = option A + C before U10; D rejected; B/E after the measurement.
- Criteria "U9d precision" U9d-1..U9d-8 (requirements l.4941-5129); design "N9 amendment, U9d" items 1-16 (design-notes l.5302-5746; only `scripts/offline_check.sh` changes; fake_docker knobs); O-22 (Health.Log JSON-quoted one line; 5 s bound when sources answer; client-only seam `KE_OFFLINE_MEMINFO`; launch only).
- RED (tester): 11 new methods / 24 subtests red in `tests/test_offline_check.py`, fake_docker knobs inert, 17/17 mutants killed, prototype proof in gates (`u9d/red-verify-fast.txt`, `controls.txt`); two control rows green by design (output unchanged but for `measure:` lines; no CI-only branch). Next: developer GREEN (`fast`, then `full`), reviewer + security, orchestrator verify full, commit; push + one CI run on the human's word; analyst reads the CI extract (U9d-6).


- GREEN (developer): `scripts/offline_check.sh` +143 (helpers, `measure` C1-C3, `diag_launch`, `measure_host` H1-H3); fast Ran 1354 OK/8, full PASS 1361 s, points 1 s total (`u9d/green-verify-*.txt`, `measure-lines.txt`).
- Rework 1 of 5 (O-23 + precision): reviewer CHANGES REQUESTED (`u9d/review.md` B-1: `restart: unless-stopped` resets ExitCode/OOMKilled, events history unreliable; N-1 `;q`, N-2 wording); security PASS on the first version (`u9d/security.md` L-1 name/label sanitising, L-2 `##[`, I-1 unbounded meminfo read, folded in). Architect "Amendment, rework 1 (O-23)" A1-A11 (design-notes l.5777-6172: +RestartCount/StartedAt/FinishedAt/Error, `docker events` die/oom/kill stream with 100-line cap and 900 s bound); analyst U9d-1/4/6 amended. RED: 5 new methods, 19 subtests red incl. the restarted-neo4j fixture and the L-1/L-2/I-1 rows, 24/24 mutants, prototype proof (`u9d/r1-red-verify-fast.txt`, `controls-r1.txt`). Next: developer GREEN, reviewer re-read, security re-audit, orchestrator verify full, commit, push on the human's word.
- Rework-1 GREEN (developer): `neutralise`, bounded `meminfo_line`, template +4 fields, `events_start`/`events_stop` (`timeout 900`, `--since`, 5 filters, 5-field format, tmpfs file, 100-line cap), sanitised name/label and `-- "$svc"`; fast Ran 1359 OK/8, full PASS 1373 s, nothing printed on a pass (`u9d/r1-green-verify-*.txt`, `measure-lines.txt`). Reviewer APPROVED (`u9d/r1-review.md`; U9d-6 yes: OOM / crash / Docker stop / disk-full / nothing-died distinct; N-1 optional). Security PASS (`u9d/r1-security.md`; L-1/L-2/I-1 closed; L-3 low label shadowing, I-3/I-5/I-6 info). **O-24** defers L-3, I-3, I-5, I-6 and r1 N-1 to U10. Code final. Next: orchestrator verify full (`u9d/orchestrator-verify-full-u9d.txt`), commit, push of 9c3183d + U9d on the human's word, one CI run, analyst reads the launch extract (U9d-6).


## 2026-10-30 developer: U9d committed
- Commit bc5e65e (local, not pushed) on agent/platform-sbom.
