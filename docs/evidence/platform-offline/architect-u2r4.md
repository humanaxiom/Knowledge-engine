# Architect: unit-2 rework round 4/5 (2026-10-19)

Docs only. Inputs: handoff "orchestrator: unit-2 rework round 4/5",
security-u2-r3.md (H-2, M-5, M-6, L-15), review-u2-r3.md (RB6, N6, N7).

## Edited
- docs/architecture.md §2.5 Install: amendment note; step 1 parent rule now
  REFUSES (owner or writer other than operator/root/SYSTEM/Administrators;
  fail closed; messages; POSIX `ls -ldn` + `id -u`, sticky no longer exempt,
  macOS `ls -lde` allow-entry branch; pwsh off Windows `GetUnixFileMode` +
  `stat -c %u`; Windows owner + Allow ACE check with an integer write mask);
  step 2 pin-only-when-proven (no chmod by name; `pwd -P`, empty, `-O`, 0700;
  ps1 Pinned after assert + emptiness; never empty a reparse point); cleanup
  note; step 9 publish by cd + marker/owner check + `rm ./marker` +
  `chmod 0755 .` + `[ "$target" -ef . ]` + `cd /`; N6 `bash scripts/launch.sh`;
  trust-anchor (a,e) line; offline-client installs under `/install/op/ke`.
- ADR-KE-012: status amendment, Decision items 1/2/7, round-4 alternatives
  (warn rejected: three rounds of race fixes each opened a new race; the
  parent policy removes the attacker's precondition; sticky exemption,
  defences-only, all-ancestors, pwsh 7.4 UnixStat), Consequences.
- §2.6: 5c item 4 marked superseded; new 5d with the tester's names.
- docs/requirements.md PS-3.1: parent bullet rewritten (refuse, fail closed,
  rejected alternative), new "Defence in depth kept (round 4)" bullet;
  PS-3.2 Docs: parent must be owned and writable only by you, installer
  refuses otherwise.

## Flags for the orchestrator
1. TrustedInstaller is no longer exempt on Windows (ruling names only
   SYSTEM/Administrators). One-SID change if wanted back.
2. Sticky 1777 parent is refused (ruling: "writable by"); tester's docstring
   still says "without the sticky bit"; no 1777 case. `offline_check.sh`
   (not yet built) must install under an operator-owned `/install/op`.
3. `test_install_sh_refuses_staging_loosened_before_cd` depends on a chmod of
   staging by name, which the design removes; it will need re-seating.
4. Ancestors above the parent are not checked (recorded as a consequence).

## Verify
`COMPOSE_PROJECT_NAME=ke-arch-r4 scripts/verify.sh fast`: FAIL, 555 tests,
87 failures, all in tests/test_offline_bundle.py (tester RED + developer's
in-flight install.sh, "line 219: syntax error"). No failure outside that
module. Lint PASS. Raw: architect-u2r4-verify-fast.txt.
