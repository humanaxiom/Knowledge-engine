#!/usr/bin/env bash
# Lint gate (architecture §2.2 Lint), called by scripts/verify.sh before the
# tests: shellcheck over every *.sh under scripts/ and docker/, and
# PSScriptAnalyzer over every scripts/*.ps1. Any finding fails it. Both tools
# live in the gates image, so this runs the same everywhere.
set -euo pipefail
cd "$(dirname "$0")/.."

mapfile -t shell_files < <(find scripts docker -name '*.sh' -type f | LC_ALL=C sort)
mapfile -d '' -t ps_files < <(find scripts -maxdepth 1 -name '*.ps1' -type f -print0 | LC_ALL=C sort -z)

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
