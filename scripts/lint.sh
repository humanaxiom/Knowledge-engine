#!/usr/bin/env bash
# Lint gate (architecture §2.2 Lint), called by scripts/verify.sh before the
# tests: shellcheck over every *.sh under scripts/ and docker/, and
# PSScriptAnalyzer over every *.ps1 and *.psm1 (any case) under scripts/ at any depth. Any finding fails it. Both tools
# live in the gates image, so this runs the same everywhere.
set -euo pipefail
CDPATH='' cd -- "$(dirname -- "$0")/.."

# A symlink could point a "script" outside the tree or at a file the gate does
# not otherwise see. Refuse ANY symlink under scripts/ and docker/ (files,
# directories, dangling links, any name) before the tools run (security
# L-12, L-15).
mapfile -d '' -t links < <(find scripts docker -type l -print0 | LC_ALL=C sort -z)
if [ "${#links[@]}" -gt 0 ]; then
  for link in "${links[@]}"; do
    echo "lint: FAIL (symlink refused: $link)" >&2
  done
  exit 1
fi

mapfile -t shell_files < <(find scripts docker -iname '*.sh' -type f | LC_ALL=C sort)
mapfile -d '' -t ps_files < <(find scripts \( -iname '*.ps1' -o -iname '*.psm1' \) -type f -print0 | LC_ALL=C sort -z)
status=0

echo "lint: shellcheck on ${#shell_files[@]} files"
# -x follows `source`d files; the severity is left at the default (style).
shellcheck -x "${shell_files[@]}" || status=1

echo "lint: PSScriptAnalyzer on ${#ps_files[@]} files"
# Error and Warning findings fail. PSAvoidUsingWriteHost is excluded: these
# are interactive command-line scripts that talk to the person running them.
# The -Command text is fixed. The paths reach PowerShell only through the
# environment (newline-joined), never inside generated source, so a filename
# cannot run code (security L-7). A path with a newline cannot be joined
# safely and is refused.
ps_list=""
for file in "${ps_files[@]}"; do
  case "$file" in
    *$'\n'*)
      echo "lint: FAIL (a PowerShell script path contains a newline: refused)" >&2
      exit 1
      ;;
    # Invoke-ScriptAnalyzer -Path takes a wildcard pattern and has no
    # -LiteralPath: a name with one of these would be skipped or would match
    # other files, so it is refused before pwsh runs (security L-10).
    *'['*|*']'*|*'*'*|*'?'*)
      echo "lint: FAIL (a PowerShell script path contains a wildcard character [ ] * ?: refused: $file)" >&2
      exit 1
      ;;
  esac
  ps_list+="${file}"$'\n'
done
export KE_LINT_PS1_FILES="$ps_list"
# One line, so logs and process lists stay readable.
analyze="$(cat <<'POWERSHELL'
$ErrorActionPreference = "Stop"; $findings = @(); foreach ($file in ($env:KE_LINT_PS1_FILES -split "`n")) { if ($file) { $findings += Invoke-ScriptAnalyzer -Path $file -Severity Error, Warning -ExcludeRule PSAvoidUsingWriteHost } }; $findings | Format-Table -AutoSize | Out-String -Width 200 | Write-Output; if ($findings.Count -gt 0) { Write-Error "PSScriptAnalyzer findings in scripts/*.ps1"; exit 1 }
POWERSHELL
)"
pwsh -NoProfile -NonInteractive -Command "$analyze" || status=1

if [ "$status" -ne 0 ]; then
  echo "lint: FAIL" >&2
  exit 1
fi
echo "lint: PASS"
