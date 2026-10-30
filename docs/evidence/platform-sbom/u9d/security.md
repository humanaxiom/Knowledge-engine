# platform-sbom U9d: security audit (security, 2026-10-30)

**Verdict: PASS** (no critical or high finding; 2 low, 4 informational; none merge-blocking).

Scope: `git diff HEAD -- scripts/offline_check.sh tests/test_offline_check.py tests/fake_docker.py`
(140+/3-, 155+/5-, 612+/0-) against U9d-1 (never printed), U9d-3, U9d-4, design "N9 amendment, U9d"
items 7, 10, 11, 12 and O-22. Probes: `docs/evidence/platform-sbom/u9d/security-probes.txt`
(ke-gates, `--network none`, uid 10001; one real-Docker template render on two throwaway containers,
removed after).

## Checks

1. **Template (U9d-1, item 10): pass.** `diag_tpl` (offline_check.sh:114-122) reads only `.State.Status`,
   `.State.ExitCode`, `.State.OOMKilled`, `.State.Health` (presence), `.State.Health.Status` and per Health.Log
   entry `.End`, `.ExitCode`, `{{json .Output}}`. No `.Config`, `.Args`, `.Path`, `.Mounts`, `.HostConfig`,
   `.NetworkSettings`, `{{json .}}`. The only client inspect (l.138) always has `--format "$diag_tpl"`; the listing
   (l.126) prints `.ID` (not printed), `.Names` and the service label value only. `docker system df` is
   `--format`ed summary, never `-v` (l.90). Real Docker render (probes D): five State lines; the label, mount,
   health command and entrypoint sentinels: 0 hits. The fake's U9D_SECRET (Config.Env, Args, Mounts, label):
   0 hits (probes A, P1).
2. **Log injection (item 10): pass for content, gap for labels (L-1, L-2).** Probe output and compose log
   lines through `diag_print`: every line prefixed; CR, LF, ESC, DEL, VT, FF and, under the client's C.UTF-8,
   U+0085, U+2028/9 and 8-bit CSI become `?`; Health.Log output is one JSON-quoted line; 5000-char line cut to
   2000 + ` [cut]`. No line can start `::` (probes A P1, C, D). Remaining: U+202E passes (I-2) and `##[` passes
   mid-line (L-2). Names and service labels bypass the sanitiser (L-1).
3. **Measurement lines (U9d-3): pass.** Real lines (`measure-lines.txt`): `df` filesystem names (`overlay`,
   `tmpfs`), mount points `/` and `/install`, KiB figures, MemAvailable/SwapFree only, `docker system df` rows.
   No hostname, IP, user, env value or profile path. awk keeps only `MemAvailable:`/`SwapFree:` rows with
   `kB`, digits enforced by regex (l.42-53); a crafted file with a `root:SECRETHASH` row printed only the two
   numbers (P3). No CI/GITHUB/RUNNER branch (grep: none).
4. **Timeouts (U9d-4): pass.** Every new docker call: `timeout 10` (system df, ps, inspect) or `timeout 20`
   (compose logs), all `< /dev/null`; the loop's here-string is never read by a docker call. H2 (l.488) is
   bounded by one 5 s read of the kernel's `/proc/meminfo`; the FAIL line is byte-identical on stderr with H2
   measured (P5: `offline_check: FAIL (the offline client failed (see its output above))`).
5. **KE_OFFLINE_MEMINFO (O-22 (3)): pass.** Read only in the client branch (l.80); the host half ignores it
   (P4: host measured `/proc/meminfo`, planted path never mentioned). `/etc/shadow` as uid 10001, a FIFO with
   no writer, `/dev/zero`: named "not measured" line, numeric-only otherwise, run continues exit 0. The seam is
   not settable in the real client (compose fixes its environment). Processing is unbounded (I-1).
6. **No gate weakened: pass.** test_offline_check.py: 0 lines removed; the five fake_docker edits route the
   `State` string through `_u9d_state`, identical for strings; new fake paths act only when
   FAKE_DOCKER_CONTAINERS has dict States, FAKE_COMPOSE_LOGS or FAKE_DF_FAIL is set (`system df` is new and
   no earlier caller runs it). The output-unchanged control row
   (`test_offline_check_output_unchanged_but_for_measure_lines`) is present; the 28 class methods re-ran ok
   under the probe harness.
7. **Evidence and secrets: pass.** `docs/evidence/platform-sbom/u9d/*`: no profile path, SID or secret
   pattern; the diff adds no key, token, private key or connection string (only the test sentinel
   `u9d-sentinel-secret-7f3a9c`, a fixture). Stack secrets in the client are `.env.example` placeholders
   (`changeme-*`); the stack's health probes send cypher-shell stdout to /dev/null and print no password.

## Findings

- **L-1 (low) Container name and service label are printed unsanitised; the label is also an unguarded
  argument.** offline_check.sh:136 (`diag "container $name (service ${svc:-<absent>})"`), :149
  (`logs of service $svc`), :152 (`diag_print "  $svc | "`, the label argument skips the `[[:cntrl:]]`
  pass), :151 (`... --tail 50 "$svc"`, no `--`). Probe A P2: a `com.docker.compose.service` label
  `svc<CR>::error::cr-in-label<ESC>[31m` produced three output lines that begin `::error::` once a bare CR
  is read as a line break (the GitHub runner's line reader and Python both do), and raw ESC bytes; a label
  `--follow` became a `compose logs --follow` option (bounded by the 20 s timeout). Contrary to item 10's
  "no container text can begin a workflow command". Exposure is low: Docker validates container names and
  compose validates service names (`[a-zA-Z0-9._-]`), and only the bundle (the PR's own code) or a holder of
  the inner daemon's TLS client key can set labels. Fix: right after `read -r id name svc`, set
  `name="${name//[[:cntrl:]]/?}"` and `svc="${svc//[[:cntrl:]]/?}"`; fetch logs only when
  `[[ $svc =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]` (else a named "not a compose service name, so no logs" line);
  pass `-- "$svc"`. Add one row with a CR/ESC label and a `--follow` label.
- **L-2 (low) `##[` survives the sanitiser.** offline_check.sh:107. Probes A, C, D: `##[add-mask]...` and
  `x ##[warning]...` print after the prefix. Item 10 says the prefix stops `##[`; the runner's legacy
  `##[command]` parser, as I understand actions/runner's `ActionCommand.TryParse`, finds the marker anywhere
  in a line (IndexOf), not only at the start (not verifiable offline here). Source is the stack's own
  container output (same trust as the PR), and other unprefixed streams in the verify log already carry the
  same exposure, so low. Fix: in diag_print after the cntrl pass, `l="${l//'##['/'#?['}"`; same on l.95.
  Add `##[` to the existing control-character row.
- **I-1 `meminfo_line` bounds the read, not the work.** offline_check.sh:44. A 200 MiB one-line file took
  227 s and /dev/urandom 35.9 s (probes B), though `timeout 5` killed `cat`. Unreachable in the real client
  (the seam is unset; `/proc/meminfo` is a few KiB) and on the host (fixed path). Fix, worth taking before
  U10 reuses the helper: `timeout 5 head -c 65536 -- "$1"`.
- **I-2 Bidi and zero-width format characters (U+202E etc.) pass.** l.107. Not `[[:cntrl:]]` in C.UTF-8;
  visual reordering in the log viewer only, cannot form a command. Optional: also replace U+200B-U+200F,
  U+202A-U+202E, U+2066-U+2069.
- **I-3 `timeout` sends TERM only.** l.90, 126, 138, 151. The docker CLI exits on TERM, so the bounds hold;
  `timeout -k 5 N` would make them hold for a CLI that ignores TERM. Optional.
- **I-4 Probe output and log tails are printed verbatim, by design.** The api healthcheck's `Settings()`
  validation error would print pydantic `input_value`s. Harmless in the offline client (placeholders,
  throwaway stack, never an operator launch); re-review if the diagnostic is ever run where real secrets are
  set (U10 or later).

## Next

L-1 and L-2 are non-blocking. The developer may fold them in (a few lines plus a test row each) before the
commit, or the orchestrator may record them for U10. Neither changes the outcome-neutral, CI-same
properties above.
