# Security confirmation: platform-offline unit 2, round 5/5 (scoped)

Date 2026-10-19. Auditor: security. Scope, as set by the orchestrator: confirm
M-7, L-18/RB7, L-19/I-14 and that no new by-name deletion path was added. No
new design questions. Probed byte copies of the working tree (install.sh
sha256 `4bbd875b...676d`, install.ps1 `3c201955...e891`) with a fake docker
(`DOCKER_HOST=tcp://127.0.0.1:1`), cwd in the session scratch `final/r5`.
Raw output: `security-u2-r5-probes.txt` (A = WSL ext4, C = pwsh 7.6.7 on
Windows 11, D = pwsh 7.4.21 + bash off Windows in a throwaway
`docker run --rm --network none --read-only` of the existing `ke-gates` image,
uid 10001; no image was built or changed).

**Verdict: PASS** (0 critical, 0 high, 0 medium open). All four items are confirmed.

## Confirmations

| Item | Status | Evidence |
|---|---|---|
| M-7 sh, sibling renamed into staging name | **Closed.** The run refuses ("not empty"), exit 1. `rmdir` fails on the non-empty dir, so the 0700 and 0755 victims are intact (`keep1 .hidden sub/k`). | A2r, A2r-0755 |
| M-7 sh, ancestor racer (r4 A10) | **Closed.** G is 0777 and the racer moves `adam` to `G/.ke-install.X` and links `adam -> G`. The installer exits 1 at publish. `notes/keep` survives ("precious") under the name the racer gave it. In r4 it was GONE. | A10 |
| M-7 ps1, sibling renamed in before or after the kind check | **Closed.** The run is refused ("does not have the private ACL"), exit 1. `Directory.Delete(path, $false)` leaves the victim intact. | W1r-A, W1r-B |
| M-7 ps1, finally window (new probe) | **Closed.** The pinned run fails at docker load. After the cwd is released and after Close-Claim, the racer renames a non-empty sibling into the staging name just before the Delete. The victim is intact and the real staging was already emptied from inside. | W1c |
| M-7 ps1, ancestor (r4 W11) | Unchanged and safe. Windows blocks the rename of `adam` while the run holds it (Permission denied). Install ok, `notes/keep` intact. | W11 |
| H-2 regression (junction) | Still closed. The victim is intact and the link is removed as a link. | W1j |
| L-18 / RB7 | **Closed.** Off Windows, install.ps1 refuses 1757, 1703, 1777, 0757, 0703, 1775 and 0775 with exit 1, no target, no staging and 0 docker calls. It installs under 0755, 1755, 0750 and 0700. The results match install.sh in every case. The code is at install.ps1:327-331, where the `-not $sticky` clause is gone. | D |
| L-19 / I-14 | **Closed.** quickstart.md:115-126 says the installer *refuses* a parent others can write to or own, sticky `/tmp` and `C:\` included, and that it refuses a parent it cannot check. It says the parent must be owned by you, keeps the ancestor advice and warns against synced or shared targets (OneDrive, Dropbox, network share). No "warns" wording is left. The install.sh:164-165 comment is corrected. | read |
| No new by-name deletion | **Confirmed.** Diffing the r4 snapshot against now: install.sh only changes `rm -rf -- "$staging"` to `rmdir -- "$staging"`, and removes the duplicate `-ef .` line and a comment. install.ps1 only changes `Remove-Item -Recurse` to `[IO.Directory]::Delete($script:Staging, $false)`, renames `Assert-SafeParent` and drops the sticky clause. Across the full `git diff 1fe81dd` plus install.ps1, the only new deletion-capable code lines are these two non-recursive calls. | diff |

## Non-blocking observations (no new design asked)
- **O-1 (info).** An EMPTY operator-owned 0700 directory renamed into the
  staging name passes every pin check and is used as staging. It is then
  removed by `rmdir` at the end, and the real staging is left behind as
  `.moved` (A2r-empty, exit 0). The racer needs rename rights in the parent,
  which the parent rule refuses, and the only loss is an empty directory.
  This is the same as round 4.
- **O-2 (info).** After an ancestor-racer abort (A10), leftovers stay where the
  racer moved the folder: the claimed `t` with its `.ke-claim.*` marker and an
  empty nested staging. Leaving them is the intended cost of non-recursive
  removal. The error names the target, so the operator can clean up by hand.
- L-16 (claim `rm -rf` by name after the marker check) and L-17 (publish
  `mv` by name) are unchanged, and both stay accepted per ADR-KE-012.

## Checked and clean
- **Secret grep.** The round-5 tree (`git diff 1fe81dd`, excluding evidence,
  plus install.ps1) was searched for AWS, GitHub, Slack and OpenAI keys,
  private keys, JWTs, credentialed URLs and quoted
  password/secret/token/api_key values. There were no hits.
- **Tracing.** No tracing surface changed.
- **Repo root.** `git status --short` shows only this file and
  `security-u2-r5-probes.txt` as new entries from this audit. The handoff and
  `docs/log.md` were updated through the documented paths.
