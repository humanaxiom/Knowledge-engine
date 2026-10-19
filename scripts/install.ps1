# Installs an offline bundle (PS-3.1, architecture 2.5 Install); the
# PowerShell twin of install.sh.
#
#   pwsh -NoProfile -File install.ps1 -Target <dir> [-ExpectManifest <sha256>]
#
# Runs from the bundle root, on its own directory. Everything in the bundle is
# untrusted until the manifest passes, and bundle.json stays untrusted after
# it: every value is matched against a fixed pattern, nothing is evaluated
# (no Invoke-Expression, no string-built commands) and docker is always
# called with an argument array. Until the manifest check passes no `docker`
# command runs.
#
# Order: PATH check, arguments, claim the target (a directory created with a
# protected ACL / mode 0700, plus a random marker file held open until
# publish), private staging copy (in the target's parent; the script then
# works from inside it with relative paths only), manifest (on staging),
# daemon, bundle.json, services, per image (load, tag as `as`, inspect `as`),
# override, publish into the claim. Only the staged bytes are verified, loaded
# and published; a rename of the staging directory cannot reach them (the
# working directory follows the directory, not its name). Staging is removed on
# every exit, and so is the claim unless it was published. Every path
# comparison is ordinal. Image ids are never compared; nothing is removed or
# untagged; `:local` is never touched.
#
# Needs PowerShell 7.3 or newer (not Windows PowerShell 5.1) and FullLanguage
# mode: under ConstrainedLanguage (AppLocker / WDAC script enforcement) the
# Add-Type below is refused before anything is created, and the script exits
# non-zero.
#
# Integrity, not authenticity: this script ships inside the bundle it checks.
# Compare the manifest hash it prints with your release record (the
# `<out>.manifest.sha256` file bundle.sh wrote) or pass -ExpectManifest.
#Requires -Version 7.3
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Target,

    [string]$ExpectManifest
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:Staging = $null
$script:ClaimPath = $null
$script:ClaimMarker = $null
$script:ClaimStream = $null
$script:Claimed = $false
$script:Published = $false
$script:Pinned = $false
$windows = [System.IO.Path]::DirectorySeparatorChar -eq '\'
$sep = [System.IO.Path]::DirectorySeparatorChar
$ordinal = [System.StringComparer]::Ordinal
$originalPath = $env:PATH
$originalLocation = (Get-Location).ProviderPath

# A refusal is an exception; the catch at the bottom prints it, the finally
# removes staging, and only then does the script exit.
function Exit-WithError([string]$Message) {
    throw [System.InvalidOperationException]::new("install: $Message")
}

# A name is printed with every character outside a safe set replaced.
function Format-Safe([string]$Text) {
    return ($Text -replace '[^A-Za-z0-9._/-]', '?')
}

# Security L-9 (twin of install.sh): a relative PATH entry makes a native
# command resolve inside the current directory. Relative entries are refused;
# empty entries are refused on Linux and dropped on Windows (where they are
# stray separators).
function Assert-SafePath {
    $kept = [System.Collections.Generic.List[string]]::new()
    $dropped = $false
    foreach ($entry in @(([string]$env:PATH) -split [System.IO.Path]::PathSeparator, 0)) {
        $bare = $entry.Trim('"')
        if ($bare -eq '') {
            if ($windows) { $dropped = $true; continue }
            throw [System.InvalidOperationException]::new('install: PATH has an empty entry; set PATH to absolute directories only')
        }
        if (-not [System.IO.Path]::IsPathFullyQualified($bare)) {
            throw [System.InvalidOperationException]::new("install: PATH has a relative entry ('$(Format-Safe $bare)'); set PATH to absolute directories only")
        }
        $kept.Add($entry)
    }
    if ($dropped) { $env:PATH = $kept -join [System.IO.Path]::PathSeparator }
}
function Read-BundleLine([string]$Path) {
    $strict = [System.Text.UTF8Encoding]::new($false, $true)
    try {
        $text = $strict.GetString([System.IO.File]::ReadAllBytes($Path))
    } catch {
        Exit-WithError "$(Format-Safe ([System.IO.Path]::GetFileName($Path))) is not valid UTF-8"
    }
    $lines = @($text -split "`n")
    if ($lines.Count -gt 0 -and $lines[$lines.Count - 1] -eq '') {
        $lines = @($lines | Select-Object -First ($lines.Count - 1))
    }
    return , $lines
}

# 'none', 'link' (symlink, junction or reparse point; never followed), 'dir'
# or 'file', for the entry itself.
function Get-EntryKind([string]$Path) {
    try {
        $attr = [System.IO.File]::GetAttributes($Path)
    } catch [System.IO.IOException] {
        return 'none'
    }
    if (($attr -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { return 'link' }
    if (($attr -band [System.IO.FileAttributes]::Directory) -ne 0) { return 'dir' }
    return 'file'
}

# Every entry under $Dir, directories before their contents, as objects with
# Rel (bundle-relative, '/'), Kind, Full and Length. A link is refused before
# it can be followed; on Linux a first `find` pass refuses fifos, devices and
# sockets before any file is opened (opening a fifo would block).
function Get-BundleEntry([string]$Base) {
    if (-not $windows) {
        $odd = @(& find $Base -mindepth 1 '!' -type f '!' -type d -print)
        if ($LASTEXITCODE -ne 0) { Exit-WithError "cannot scan $Base" }
        if ($odd.Count -gt 0) {
            $oddPath = [string]$odd[0]
            $oddRel = Format-Safe ($oddPath.Substring($Base.Length + 1))
            if ((Get-EntryKind $oddPath) -eq 'link') {
                Exit-WithError "refused (rule: a symlink or link is not allowed): $oddRel"
            }
            Exit-WithError "refused (rule: a fifo / named pipe, device or socket is not allowed): $oddRel"
        }
    }
    Get-BundleEntryUnder ([System.IO.DirectoryInfo]::new($Base)) ''
}

function Get-BundleEntryUnder([System.IO.DirectoryInfo]$Dir, [string]$Prefix) {
    foreach ($info in $Dir.EnumerateFileSystemInfos()) {
        $rel = $Prefix + $info.Name
        if ($null -ne $info.LinkTarget -or (($info.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) {
            Exit-WithError "refused (rule: a symlink, junction or reparse point is not allowed): $(Format-Safe $rel)"
        }
        if ($info -is [System.IO.DirectoryInfo]) {
            [pscustomobject]@{ Rel = $rel; Kind = 'dir'; Full = $info.FullName; Length = [long]0 }
            Get-BundleEntryUnder $info ($rel + '/')
        } else {
            [pscustomobject]@{ Rel = $rel; Kind = 'file'; Full = $info.FullName; Length = [long]$info.Length }
        }
    }
}

# Free KiB under $Path. Linux reads `df -Pk` by shape (the Available column is
# the number before the NN% field, so names with spaces cannot shift it).
function Get-FreeKb([string]$Path) {
    if ($windows) {
        try {
            $drive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($Path))
            return [long][Math]::Floor($drive.AvailableFreeSpace / 1024)
        } catch {
            Exit-WithError "cannot read the free space on $Path"
        }
    }
    $text = @(& df -Pk -- $Path)
    if ($LASTEXITCODE -ne 0) { Exit-WithError "cannot read the free space on $Path" }
    foreach ($line in ($text | Select-Object -Skip 1)) {
        $m = [regex]::Match([string]$line, '(?<total>\d+)\s+(?<used>\d+)\s+(?<avail>\d+)\s+\d+%(\s|$)')
        if ($m.Success) { return [long]$m.Groups['avail'].Value }
    }
    Exit-WithError "cannot read the free space on $Path"
}
# The current user's SID, as the owner and the one principal of a private
# directory on Windows.
function Get-MeSid {
    return [System.Security.Principal.WindowsIdentity]::GetCurrent().User
}

# Security H-1: a directory only the current user can use, created with that
# protection in one call, never created first and protected afterwards.
# Windows: a DACL (owner = me, protected, one FullControl ACE) goes in with
# FileSystemAclExtensions.Create. Linux: mode 0700. The name must not exist
# (Create / CreateDirectory do nothing for an existing directory, so
# Assert-PrivateDirectory checks the result).
function Initialize-PrivateDirectory([string]$Path) {
    if ((Get-EntryKind $Path) -ne 'none') {
        Exit-WithError "cannot create $Path (something is already there)"
    }
    if ($windows) {
        $me = Get-MeSid
        $security = [System.Security.AccessControl.DirectorySecurity]::new()
        $security.SetOwner($me)
        $security.SetAccessRuleProtection($true, $false)
        $rule = [System.Security.AccessControl.FileSystemAccessRule]::new($me, 'FullControl',
            'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $security.AddAccessRule($rule)
        [void][System.IO.FileSystemAclExtensions]::Create([System.IO.DirectoryInfo]::new($Path), $security)
    } else {
        $mode = [System.IO.UnixFileMode]::UserRead -bor [System.IO.UnixFileMode]::UserWrite -bor [System.IO.UnixFileMode]::UserExecute
        [void][System.IO.Directory]::CreateDirectory($Path, $mode)
    }
}

# $Path is a real directory only this user can use: Windows, owner = me and a
# protected DACL that is exactly one non-inherited FullControl ACE for me;
# Linux, a directory (not a link) with mode 0700.
function Assert-PrivateDirectory([string]$Path) {
    if ((Get-EntryKind $Path) -ne 'dir') { Exit-WithError "$Path is not the private directory this install created" }
    if ($windows) {
        $me = Get-MeSid
        $acl = [System.IO.FileSystemAclExtensions]::GetAccessControl([System.IO.DirectoryInfo]::new($Path))
        $rules = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
        $full = [System.Security.AccessControl.FileSystemRights]::FullControl
        $ok = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]) -eq $me -and
            $acl.AreAccessRulesProtected -and $rules.Count -eq 1 -and
            $rules[0].IdentityReference -eq $me -and -not $rules[0].IsInherited -and
            $rules[0].AccessControlType -eq 'Allow' -and
            (($rules[0].FileSystemRights -band $full) -eq $full)
        if (-not $ok) { Exit-WithError "$Path does not have the private ACL this install gave it (something else created it first)" }
    } else {
        $expected = [System.IO.UnixFileMode]::UserRead -bor [System.IO.UnixFileMode]::UserWrite -bor [System.IO.UnixFileMode]::UserExecute
        if ([System.IO.File]::GetUnixFileMode($Path) -ne $expected) {
            Exit-WithError "$Path does not have mode 0700 (something else created it first)"
        }
    }
}

function Get-RandomHex {
    $bytes = [byte[]]::new(8)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [System.BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
}

# The owner uid of $Path off Windows, from `ls -ldn` (field 3), the same read
# install.sh uses. Any failure is a refusal (fail closed).
function Get-OwnerUid([string]$Path) {
    $listing = @(& ls -ldn -- $Path)
    if ($LASTEXITCODE -ne 0 -or $listing.Count -ne 1) { Exit-WithError "cannot check $Path (reading its owner failed)" }
    $m = [regex]::Match([string]$listing[0], '^\S+\s+\d+\s+(\d+)\s')
    if (-not $m.Success) { Exit-WithError "cannot check $Path (its owner could not be read)" }
    return [long]$m.Groups[1].Value
}

function Get-OperatorUid {
    $text = @(& id -u)
    if ($LASTEXITCODE -ne 0 -or $text.Count -ne 1 -or ([string]$text[0]) -notmatch '\A[0-9]+\z') {
        Exit-WithError "cannot check the operator's uid (id -u failed)"
    }
    return [long]$text[0]
}

# Private staging beside the target; the process works from inside it from
# here on (both working directories), so a rename of the directory cannot
# redirect the relative paths used below. Security H-2 / review RB6: staging
# counts as pinned (and cleanup may empty it) only after the directory we are
# in has passed the private-directory assert, is not a link, is empty and, off
# Windows, is ours.
function Initialize-Staging([string]$Parent) {
    for ($attempt = 0; $attempt -lt 5; $attempt++) {
        $path = Join-Path $Parent ".ke-install.$(Get-RandomHex)"
        if ((Get-EntryKind $path) -ne 'none') { continue }
        Initialize-PrivateDirectory $path
        $script:Staging = $path
        if ((Get-EntryKind $path) -ne 'dir') {
            Exit-WithError "the staging directory is not the one this install created (its name leads elsewhere): $path"
        }
        Set-Location -LiteralPath $path
        [System.Environment]::CurrentDirectory = $path
        Assert-PrivateDirectory '.'
        if ($null -ne ([System.IO.Directory]::EnumerateFileSystemEntries('.') | Select-Object -First 1)) {
            Exit-WithError "the staging directory is not empty (something was put there after creation): $path"
        }
        if (-not $windows -and (Get-OwnerUid '.') -ne (Get-OperatorUid)) {
            Exit-WithError "the staging directory is not owned by you: $path"
        }
        $script:Pinned = $true
        return $path
    }
    Exit-WithError "cannot create a staging directory in $Parent"
}

# Security H-1 fix 3, hardened by the round-4 ruling: whoever can write the
# parent can replace the target (or race the staging name), so a parent that
# anyone but the operator can write, or that anyone but the operator (or root,
# or on Windows SYSTEM / Administrators) owns, is refused. Any failure reading
# the owner, the mode or the ACL refuses too (fail closed).
function Assert-SafeParent([string]$Parent) {
    $reason = $null
    if ($windows) {
        $me = Get-MeSid
        $trusted = @($me,
            [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18'),
            [System.Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'),
            [System.Security.Principal.SecurityIdentifier]::new('S-1-3-4'),    # OWNER RIGHTS: applies to the owner, checked above
            [System.Security.Principal.SecurityIdentifier]::new('S-1-3-0'))   # CREATOR OWNER
        # Integer masks (security M-6): GenericWrite and GenericAll are not
        # defined FileSystemRights values, so they are never cast to the enum.
        # WriteData/CreateFiles, AppendData/CreateDirectories, WriteExtendedAttributes,
        # DeleteSubdirectoriesAndFiles, WriteAttributes, Delete, ChangePermissions,
        # TakeOwnership, GenericWrite, GenericAll.
        [long]$writeMask = 0x2 + 0x4 + 0x10 + 0x40 + 0x100 + 0x10000 + 0x40000 + 0x80000 + 0x40000000 + 0x10000000
        try {
            $acl = [System.IO.FileSystemAclExtensions]::GetAccessControl([System.IO.DirectoryInfo]::new($Parent))
            $owner = $acl.GetOwner([System.Security.Principal.SecurityIdentifier])
            $rules = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
        } catch {
            Exit-WithError "cannot check the target's parent $Parent (reading its ACL failed); use a directory only you can write"
        }
        if ($null -eq $owner -or @($trusted[0..2]) -notcontains $owner) {
            $reason = "refused (rule: the target's parent must be owned by you, SYSTEM or Administrators): $Parent is owned by another account; its owner can replace the installed target; use a directory you own"
        }
        foreach ($rule in $rules) {
            if ($rule.AccessControlType -ne 'Allow') { continue }
            if (($rule.PropagationFlags -band [System.Security.AccessControl.PropagationFlags]::InheritOnly) -ne 0) { continue }
            if (([long][int]$rule.FileSystemRights -band $writeMask) -eq 0) { continue }
            if ($trusted -contains $rule.IdentityReference) { continue }
            $reason = "refused (rule: the target's parent must not be writable by others): $Parent is writable by another account ($($rule.IdentityReference)); anyone who can write it can replace the installed target; use a directory only you can write"
            break
        }
    } else {
        try {
            $mode = [System.IO.File]::GetUnixFileMode($Parent)
        } catch {
            Exit-WithError "cannot check the target's parent $Parent (reading its mode failed); use a directory only you can write"
        }
        $ownerUid = Get-OwnerUid $Parent
        $meUid = Get-OperatorUid
        if ($ownerUid -ne $meUid -and $ownerUid -ne 0) {
            $reason = "refused (rule: the target's parent must be owned by you or root): $Parent is owned by another user (uid $ownerUid); its owner can replace the installed target; use a directory you own"
        }
        # The sticky bit is no exemption (a 1777 parent lets anyone create entries in it).
        if (($mode -band [System.IO.UnixFileMode]::GroupWrite) -ne 0 -or
            ($mode -band [System.IO.UnixFileMode]::OtherWrite) -ne 0) {
            $reason = "refused (rule: the target's parent must not be writable by others): $Parent is writable by others (group or world); anyone who can write it can replace the installed target; use a directory only you can write"
        }
    }
    if ($null -ne $reason) { Exit-WithError $reason }
}

# An interrupt (SIGINT, SIGTERM, SIGHUP, SIGQUIT; Ctrl+C / Ctrl+Break on
# Windows) is recorded and cancelled, so the script reaches its finally and
# removes staging; it then exits non-zero. Assert-NotInterrupted is called
# after every docker call, on each loop iteration and before publish: the
# handler only sets a flag, and nothing else would stop the run. The handler
# is compiled C# because a PowerShell scriptblock cannot run on the runtime's
# signal thread. Install() resets the flag (an in-process run may follow an
# interrupted one) and Dispose() removes the registrations, so the session
# gets its own signal behaviour back. The signals reach a running docker child
# too when sent to the process group, which fails the step in progress.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class KeInterrupt {
    public static volatile bool Fired;
    static PosixSignalRegistration[] regs;
    public static void Install() {
        Dispose();
        Fired = false;
        PosixSignalRegistration[] r = new PosixSignalRegistration[4];
        r[0] = PosixSignalRegistration.Create(PosixSignal.SIGINT, Handle);
        r[1] = PosixSignalRegistration.Create(PosixSignal.SIGTERM, Handle);
        r[2] = PosixSignalRegistration.Create(PosixSignal.SIGHUP, Handle);
        r[3] = PosixSignalRegistration.Create(PosixSignal.SIGQUIT, Handle);
        regs = r;
    }
    public static void Dispose() {
        PosixSignalRegistration[] r = regs;
        regs = null;
        if (r == null) { return; }
        foreach (PosixSignalRegistration p in r) { if (p != null) { p.Dispose(); } }
    }
    static void Handle(PosixSignalContext context) { Fired = true; context.Cancel = true; }
}
'@

# PowerShell starts a native command in its own location *by name*; after a
# rename of the pinned directory that name leads elsewhere. The process's real
# working directory still follows the directory, so PowerShell's location is
# re-pointed at it before each native command (Windows cannot rename it).
function Sync-Pin {
    Set-Location -LiteralPath ([System.Environment]::CurrentDirectory)
}

function Assert-NotInterrupted {
    if ([KeInterrupt]::Fired) { throw [System.InvalidOperationException]::new('install: interrupted') }
}

$script:RestoreEmpty = $false

# Removes the claimed target, but only while it is still the claim: a real
# directory (no link) that still holds the marker. An empty directory that
# was there before the run is put back.
function Close-Claim {
    if ($null -ne $script:ClaimStream) {
        try { $script:ClaimStream.Dispose() } catch { $null = $_ }
        $script:ClaimStream = $null
    }
    if (-not $script:Claimed -or $script:Published -or $null -eq $script:ClaimPath) { return }
    $path = $script:ClaimPath
    if ((Get-EntryKind $path) -eq 'dir' -and (Get-EntryKind (Join-Path $path $script:ClaimMarker)) -eq 'file') {
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
        if ($script:RestoreEmpty) { [void][System.IO.Directory]::CreateDirectory($path) }
    }
}

[KeInterrupt]::Install()

$exitCode = 0
$finished = $false
try {
    Assert-SafePath
    $root = $PSScriptRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    $pathComparison = if ($windows) { [System.StringComparison]::OrdinalIgnoreCase } else { [System.StringComparison]::Ordinal }

    # --- 1. arguments ------------------------------------------------------
    $expect = ''
    if ($PSBoundParameters.ContainsKey('ExpectManifest')) {
        if ($ExpectManifest -cnotmatch '\A[0-9a-fA-F]{64}\z') {
            Exit-WithError '-ExpectManifest must be 64 hex characters'
        }
        $expect = $ExpectManifest.ToLowerInvariant()
    }
    if ($Target -eq '') { Exit-WithError 'the target is empty' }
    $targetPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Target)
    $targetRoot = [System.IO.Path]::GetPathRoot($targetPath)
    if ($targetPath.Length -gt $targetRoot.Length) {
        $targetPath = $targetPath.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    }
    $parent = [System.IO.Path]::GetDirectoryName($targetPath)
    if ([string]::IsNullOrEmpty($parent)) { Exit-WithError "the target has no parent directory: $targetPath" }
    switch (Get-EntryKind $parent) {
        'link' { Exit-WithError "the target's parent is a link: $parent" }
        'dir' { }
        default { Exit-WithError "the target's parent is not a directory: $parent" }
    }
    if (($parent + $sep).StartsWith($root + $sep, $pathComparison)) {
        Exit-WithError "the target must be outside the bundle directory: $targetPath"
    }
    Assert-SafeParent $parent
    switch (Get-EntryKind $targetPath) {
        'link' { Exit-WithError "the target is a link: $targetPath" }
        'file' { Exit-WithError "the target exists and is not a directory: $targetPath" }
        'dir' {
            if ($null -ne ([System.IO.Directory]::EnumerateFileSystemEntries($targetPath) | Select-Object -First 1)) {
                Exit-WithError "the target is not empty: $targetPath (install into a new directory)"
            }
            [System.IO.Directory]::Delete($targetPath)
            $script:RestoreEmpty = $true
        }
        default { }
    }
    # Claim the target: created with its protection, never over something that
    # exists (Initialize-PrivateDirectory refuses, Assert-PrivateDirectory re-checks),
    # with a random marker file held open (no sharing) until publish.
    $script:ClaimPath = $targetPath
    Initialize-PrivateDirectory $targetPath
    $script:Claimed = $true
    Assert-PrivateDirectory $targetPath
    $script:ClaimMarker = ".ke-claim.$(Get-RandomHex)"
    $script:ClaimStream = [System.IO.File]::Open((Join-Path $targetPath $script:ClaimMarker),
        [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    Assert-NotInterrupted

    # --- 2. staging --------------------------------------------------------
    $staging = Initialize-Staging $parent
    $source = @(Get-BundleEntry $root)
    $needBytes = [long]0
    foreach ($entry in $source) { $needBytes += $entry.Length }
    $needKb = [long][Math]::Ceiling($needBytes / 1024)
    $needGib = [long][Math]::Ceiling($needKb / 1048576)
    $availKb = Get-FreeKb $parent
    if ($availKb -lt $needKb) {
        Exit-WithError "need $needGib GiB free on $parent, found $([long][Math]::Floor($availKb / 1048576)) GiB"
    }
    foreach ($entry in $source) {
        Assert-NotInterrupted
        $destination = $entry.Rel.Replace('/', [string]$sep)
        if ($entry.Kind -eq 'dir') {
            if ((Get-EntryKind $destination) -ne 'none') {
                Exit-WithError "paths differ only by case: $(Format-Safe $entry.Rel)"
            }
            [void][System.IO.Directory]::CreateDirectory($destination)
        } else {
            try {
                [System.IO.File]::Copy($entry.Full, $destination, $false)
            } catch [System.IO.IOException] {
                if ((Get-EntryKind $destination) -ne 'none') {
                    Exit-WithError "paths differ only by case: $(Format-Safe $entry.Rel)"
                }
                throw
            }
        }
    }
    $staged = @(Get-BundleEntry '.')

    # --- 3. manifest (staged) ----------------------------------------------
    $manifestPath = 'MANIFEST.sha256'
    if ((Get-EntryKind $manifestPath) -ne 'file') {
        Exit-WithError 'manifest: MANIFEST.sha256 is missing or not a regular file'
    }
    $manifestSize = ([System.IO.FileInfo]::new($manifestPath)).Length
    if ($manifestSize -gt 1048576) {
        Exit-WithError "manifest: MANIFEST.sha256 is too large ($manifestSize bytes; the size cap is 1 MiB)"
    }
    $manifestSha = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expect -ne '' -and $expect -cne $manifestSha) {
        Exit-WithError "manifest: the manifest sha256 is $manifestSha, not the value given to -ExpectManifest ($expect)"
    }

    $manifestRe = '\A([0-9a-f]{64})  (.+)\z'
    $listed = [System.Collections.Generic.Dictionary[string, string]]::new($ordinal)
    $lowerSeen = [System.Collections.Generic.Dictionary[string, string]]::new($ordinal)
    $listedOrder = [System.Collections.Generic.List[string]]::new()
    $reservedRe = '\A(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])\z'
    $n = 0
    foreach ($line in (Read-BundleLine $manifestPath)) {
        $n++
        if (-not ($line -cmatch $manifestRe)) {
            Exit-WithError "manifest: line $n is malformed, not '<64 hex>  <path>': $(Format-Safe $line)"
        }
        $want = $Matches[1]
        $path = $Matches[2]
        $shown = Format-Safe $path
        if ($path.StartsWith('/', [System.StringComparison]::Ordinal)) {
            Exit-WithError "manifest: line ${n}: path is absolute (leading '/'): $shown"
        }
        if ($path.Contains('\')) {
            Exit-WithError "manifest: line ${n}: path has a backslash: $shown"
        }
        if ($path -cmatch '[^A-Za-z0-9._/-]') {
            Exit-WithError "manifest: line ${n}: path has a character outside [A-Za-z0-9._/-]: $shown"
        }
        if ($path.EndsWith('/', [System.StringComparison]::Ordinal) -or $path.Contains('//')) {
            Exit-WithError "manifest: line ${n}: path has an empty segment: $shown"
        }
        foreach ($segment in $path.Split('/')) {
            if ($segment -ceq '.' -or $segment -ceq '..') {
                Exit-WithError "manifest: line ${n}: path has a '.' or '..' segment: $shown"
            }
            if ($segment.EndsWith('.', [System.StringComparison]::Ordinal)) {
                Exit-WithError "manifest: line ${n}: path has a segment with a trailing dot: $shown"
            }
            $stem = $segment.Split('.')[0].ToUpperInvariant()
            if ($stem -cmatch $reservedRe) {
                Exit-WithError "manifest: line ${n}: path has a Windows reserved name: $shown"
            }
        }
        if ($listed.ContainsKey($path)) {
            Exit-WithError "manifest: duplicate path: $shown"
        }
        $lower = $path.ToLowerInvariant()
        if ($lowerSeen.ContainsKey($lower)) {
            Exit-WithError "manifest: paths differ only by case: $(Format-Safe $lowerSeen[$lower]) and $shown"
        }
        $lowerSeen[$lower] = $path
        $listed[$path] = $want
        $listedOrder.Add($path)
    }

    $present = [System.Collections.Generic.HashSet[string]]::new($ordinal)
    foreach ($entry in $staged) {
        if ($entry.Kind -ne 'file' -or $entry.Rel -ceq 'MANIFEST.sha256') { continue }
        [void]$present.Add($entry.Rel)
        if (-not $listed.ContainsKey($entry.Rel)) {
            Exit-WithError "manifest: file is not listed: $(Format-Safe $entry.Rel)"
        }
    }
    foreach ($path in $listedOrder) {
        if (-not $present.Contains($path)) {
            Exit-WithError "manifest: listed file is missing: $path"
        }
        Assert-NotInterrupted
        $actual = (Get-FileHash -LiteralPath $path.Replace('/', [string]$sep) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -cne $listed[$path]) {
            Exit-WithError "manifest: hash mismatch: $path"
        }
    }
    if ($expect -ne '') {
        Write-Host "manifest sha256: $manifestSha (matches -ExpectManifest)"
    } else {
        Write-Host "manifest sha256: $manifestSha (not checked: compare it with the value from your release record)"
    }

    # --- 4. daemon ---------------------------------------------------------
    Sync-Pin
    $daemonArchRaw = (& docker info --format '{{.Architecture}}' 2> $null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        Exit-WithError 'the Docker daemon does not answer (docker info failed)'
    }
    Assert-NotInterrupted
    if ($daemonArchRaw -ceq 'x86_64' -or $daemonArchRaw -ceq 'amd64') {
        $daemonArch = 'amd64'
    } elseif ($daemonArchRaw -ceq 'aarch64' -or $daemonArchRaw -ceq 'arm64') {
        $daemonArch = 'arm64'
    } else {
        Exit-WithError "the Docker daemon reports an unsupported architecture: $(Format-Safe $daemonArchRaw) (supported: amd64, arm64)"
    }

    # --- 5. bundle.json (staged) -------------------------------------------
    $refRe = '[a-z0-9._/-]+(:[A-Za-z0-9._-]+)?(@sha256:[0-9a-f]{64})?'
    $asRe = '(ke-[a-z0-9._-]+:bundle-[0-9a-f]{12}|ke-vendor/[a-z0-9._-]+:[0-9a-f]{12})'
    $headerRe = '\A\{"format": 1, "git_sha": "(?<sha>[0-9a-f]{40})", "dirty": (true|false), "created": "[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", "arch": "(?<arch>amd64|arm64)", "images": \[\z'
    $entryRe = '\A\{"file": "(?<file>images/[A-Za-z0-9._-]+\.tar)", "ref": "(?<ref>' + $refRe + ')", "as": "(?<as>' + $asRe + ')", "services": "(?<services>[a-z0-9_-]+( [a-z0-9_-]+)*)"\}(?<comma>,?)\z'

    $bundleJson = 'bundle.json'
    if ((Get-EntryKind $bundleJson) -ne 'file') {
        Exit-WithError 'bundle.json is missing'
    }
    $entries = [System.Collections.Generic.List[hashtable]]::new()
    $gitSha = ''
    $n = 0
    $state = 'header'
    foreach ($line in (Read-BundleLine $bundleJson)) {
        $n++
        if ($state -eq 'header') {
            if (-not ($line -cmatch $headerRe)) { Exit-WithError "bundle.json: line $n does not match the header pattern" }
            $gitSha = $Matches['sha']
            $bundleArch = $Matches['arch']
            if ($bundleArch -cne $daemonArch) {
                Exit-WithError "arch mismatch: this bundle is $bundleArch but the Docker daemon is $daemonArch (reported as $daemonArchRaw); use the $daemonArch bundle"
            }
            $state = 'images'
        } elseif ($state -eq 'images') {
            if ($line -ceq ']}') { $state = 'done'; continue }
            if (-not ($line -cmatch $entryRe)) {
                Exit-WithError "bundle.json: line $n does not match the image entry pattern (file, ref, as, services)"
            }
            $entries.Add(@{
                    file     = $Matches['file']
                    as       = $Matches['as']
                    services = $Matches['services']
                    comma    = $Matches['comma']
                })
        } else {
            Exit-WithError "bundle.json: line $n follows the closing line"
        }
    }
    if ($state -ne 'done') { Exit-WithError 'bundle.json: the closing line ]} is missing' }
    if ($entries.Count -eq 0) { Exit-WithError 'bundle.json: no images' }

    $entryFile = [System.Collections.Generic.HashSet[string]]::new($ordinal)
    $entryAs = [System.Collections.Generic.HashSet[string]]::new($ordinal)
    $svcOwner = [System.Collections.Generic.HashSet[string]]::new($ordinal)
    for ($i = 0; $i -lt $entries.Count; $i++) {
        $e = $entries[$i]
        $isLast = $i -eq ($entries.Count - 1)
        if (-not $isLast -and $e.comma -eq '') { Exit-WithError "bundle.json: image entry $($i + 1) lacks its trailing comma" }
        if ($isLast -and $e.comma -ne '') { Exit-WithError 'bundle.json: the last image entry has a trailing comma' }
        if (-not $entryFile.Add($e.file)) { Exit-WithError "bundle.json: duplicate file $($e.file)" }
        if (-not $entryAs.Add($e.as)) { Exit-WithError "bundle.json: duplicate as $($e.as)" }
        if ($e.as -cmatch '\Ake-[a-z0-9._-]+:bundle-(?<sha12>[0-9a-f]{12})\z' -and $Matches['sha12'] -cne $gitSha.Substring(0, 12)) {
            Exit-WithError "bundle.json: first-party as $($e.as) does not carry the header git_sha ($($gitSha.Substring(0, 12)))"
        }
        if (-not $listed.ContainsKey($e.file)) { Exit-WithError "bundle.json: $($e.file.Split('/')[-1]) is not in the bundle" }
        foreach ($s in $e.services.Split(' ')) {
            if (-not $svcOwner.Add($s)) { Exit-WithError "bundle.json: service $s is in more than one entry" }
        }
    }
    foreach ($path in $listedOrder) {
        if ($path.StartsWith('images/', [System.StringComparison]::Ordinal) -and -not $entryFile.Contains($path)) {
            Exit-WithError "bundle.json does not list $($path.Split('/')[-1]) (every image tar must be listed)"
        }
    }

    # --- 6. services: every stack service has exactly one entry ------------
    $appDir = 'app'
    $composeFile = Join-Path $appDir 'docker-compose.yml'
    $envExample = Join-Path $appDir '.env.example'
    foreach ($required in @($composeFile, $envExample)) {
        if ((Get-EntryKind $required) -ne 'file') {
            Exit-WithError "app/$([System.IO.Path]::GetFileName($required)) is missing"
        }
    }
    $env:COMPOSE_PROFILES = $null
    $env:COMPOSE_FILE = $null
    Sync-Pin
    $configOut = @(& docker compose --project-directory $appDir -f $composeFile --env-file $envExample config --services)
    if ($LASTEXITCODE -ne 0) { Exit-WithError 'docker compose config --services failed' }
    Assert-NotInterrupted
    $stackServices = @($configOut | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ -ne '' })
    if ($stackServices.Count -eq 0) { Exit-WithError 'docker compose config lists no services' }
    $isStack = [System.Collections.Generic.HashSet[string]]::new($ordinal)
    foreach ($s in $stackServices) {
        if ($s -cnotmatch '\A[a-z0-9_-]+\z') {
            Exit-WithError 'docker compose config printed a service name that fails its pattern'
        }
        if (-not $svcOwner.Contains($s)) { Exit-WithError "stack service $s has no bundle.json entry" }
        [void]$isStack.Add($s)
    }
    foreach ($s in $svcOwner) {
        if (-not $isStack.Contains($s)) { Exit-WithError "bundle.json names service $s, which the stack does not have" }
    }

    # --- 7. load (from staging), tag as `as`, inspect `as` -----------------
    foreach ($e in $entries) {
        Assert-NotInterrupted
        $tarName = $e.file.Split('/')[-1]
        Sync-Pin
        $output = @(& docker load -i $e.file.Replace('/', [string]$sep))
        $loadExit = $LASTEXITCODE
        Assert-NotInterrupted
        if ($loadExit -ne 0) { Exit-WithError "docker load failed for $tarName" }
        $found = [System.Collections.Generic.List[string]]::new()
        $named = $false
        foreach ($l in $output) {
            $text = ([string]$l).TrimEnd("`r")
            if ($text -cmatch '\ALoaded image: (.+)\z') {
                $found.Add($Matches[1])
                $named = $true
            } elseif ($text -cmatch '\ALoaded image ID: (sha256:[0-9a-f]{64})\z') {
                $found.Add($Matches[1])
                $named = $false
            }
        }
        if ($found.Count -ne 1) {
            Exit-WithError "docker load of $tarName printed $($found.Count) 'Loaded image' lines; exactly one is required"
        }
        if ($found[0].StartsWith('-', [System.StringComparison]::Ordinal)) {
            Exit-WithError "docker load of $tarName named an image starting with '-'"
        }
        if ($named -and $found[0] -cne $e.as) {
            Exit-WithError "docker load of $tarName named an image other than its as ($($e.as))"
        }
        Sync-Pin
        & docker tag $found[0] $e.as
        $tagExit = $LASTEXITCODE
        Assert-NotInterrupted
        if ($tagExit -ne 0) { Exit-WithError "docker tag failed for $tarName" }
        Sync-Pin
        & docker image inspect $e.as *> $null
        $inspectExit = $LASTEXITCODE
        Assert-NotInterrupted
        if ($inspectExit -ne 0) { Exit-WithError "image $($e.as) is not present after loading $tarName" }
        Write-Host "loaded $tarName as $($e.as)"
    }

    # --- 8. compose override (staged app/) ---------------------------------
    $override = [System.Text.StringBuilder]::new()
    [void]$override.Append("services:`n")
    foreach ($e in $entries) {
        foreach ($s in $e.services.Split(' ')) {
            [void]$override.Append("  ${s}:`n    image: `"$($e.as)`"`n    pull_policy: never`n")
        }
    }
    $overridePath = Join-Path $appDir 'docker-compose.override.yml'
    [System.IO.File]::WriteAllText($overridePath, $override.ToString(), [System.Text.UTF8Encoding]::new($false))
    if (-not $windows) {
        [System.IO.File]::SetUnixFileMode($overridePath,
            [System.IO.UnixFileMode]::UserRead -bor [System.IO.UnixFileMode]::UserWrite -bor
            [System.IO.UnixFileMode]::GroupRead -bor [System.IO.UnixFileMode]::OtherRead)

        # F6: the published modes come from this installer, not from the build
        # host or the umask. Relative paths inside the pinned staging only;
        # Get-BundleEntry refuses links, so none is followed. Directories and
        # everything under scripts/ are 0755, every other file 0644.
        $exec755 = [System.IO.UnixFileMode]::UserRead -bor [System.IO.UnixFileMode]::UserWrite -bor [System.IO.UnixFileMode]::UserExecute -bor
            [System.IO.UnixFileMode]::GroupRead -bor [System.IO.UnixFileMode]::GroupExecute -bor
            [System.IO.UnixFileMode]::OtherRead -bor [System.IO.UnixFileMode]::OtherExecute
        $plain644 = [System.IO.UnixFileMode]::UserRead -bor [System.IO.UnixFileMode]::UserWrite -bor
            [System.IO.UnixFileMode]::GroupRead -bor [System.IO.UnixFileMode]::OtherRead
        foreach ($modeEntry in @(Get-BundleEntry $appDir)) {
            $modePath = "$appDir/$($modeEntry.Rel)"
            if ($modeEntry.Kind -eq 'dir' -or $modeEntry.Rel.StartsWith('scripts/')) {
                [System.IO.File]::SetUnixFileMode($modePath, $exec755)
            } else {
                [System.IO.File]::SetUnixFileMode($modePath, $plain644)
            }
        }
    }

    # --- 9. publish into the claim -----------------------------------------
    # The target must still be the directory this run claimed: a real
    # directory (no link) that holds exactly the marker. Each top-level entry
    # of the staged app/ is renamed into it, the marker is removed and, on
    # Linux, 0755 is set last.
    Assert-NotInterrupted
    $markerPath = Join-Path $targetPath $script:ClaimMarker
    if ((Get-EntryKind $targetPath) -ne 'dir' -or (Get-EntryKind $markerPath) -ne 'file') {
        Exit-WithError "the target is no longer the directory this install claimed (something replaced it during install): $targetPath"
    }
    $held = @([System.IO.Directory]::EnumerateFileSystemEntries($targetPath))
    if ($held.Count -ne 1) {
        Exit-WithError "the claimed target holds something besides the install's marker: $targetPath"
    }
    foreach ($info in @([System.IO.DirectoryInfo]::new($appDir).EnumerateFileSystemInfos())) {
        $dest = Join-Path $targetPath $info.Name
        $from = Join-Path $appDir $info.Name
        try {
            if ($info -is [System.IO.DirectoryInfo]) {
                [System.IO.Directory]::Move($from, $dest)
            } else {
                [System.IO.File]::Move($from, $dest)
            }
        } catch [System.IO.IOException] {
            Exit-WithError "cannot publish to the target (something appeared there): $targetPath"
        }
    }
    $script:ClaimStream.Dispose()
    $script:ClaimStream = $null
    # Security I-7: staging may have been renamed away; empty it from inside
    # while it is still the verified pin, then leave the pin (cleanup must not
    # empty the target).
    if ($script:Pinned) {
        Get-ChildItem -LiteralPath . -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
    $script:Pinned = $false
    # Security M-5: step into the target and require this run's marker there.
    Set-Location -LiteralPath $targetPath
    [System.Environment]::CurrentDirectory = $targetPath
    if ((Get-EntryKind '.') -ne 'dir' -or (Get-EntryKind $script:ClaimMarker) -ne 'file') {
        Exit-WithError "the claim marker is gone (something replaced the target during install): $targetPath"
    }
    if ((Get-EntryKind $targetPath) -ne 'dir' -or (Get-EntryKind $markerPath) -ne 'file') {
        Exit-WithError "the claim marker is gone (something replaced the target during install): $targetPath"
    }
    try {
        [System.IO.File]::Delete($markerPath)
    } catch [System.IO.IOException] {
        Exit-WithError "the claim marker could not be removed: $targetPath"
    }
    if (-not $windows) {
        if ((Get-EntryKind $targetPath) -ne 'dir') {
            Exit-WithError "the target is no longer a real directory (something replaced it during install): $targetPath"
        }
        [System.IO.File]::SetUnixFileMode($targetPath,
            [System.IO.UnixFileMode]::UserRead -bor [System.IO.UnixFileMode]::UserWrite -bor [System.IO.UnixFileMode]::UserExecute -bor
            [System.IO.UnixFileMode]::GroupRead -bor [System.IO.UnixFileMode]::GroupExecute -bor
            [System.IO.UnixFileMode]::OtherRead -bor [System.IO.UnixFileMode]::OtherExecute)
    }
    # The name must still lead to a real directory (not a link swapped in).
    if ((Get-EntryKind $targetPath) -ne 'dir') {
        Exit-WithError "the target's name no longer leads to the directory this install published (something replaced it during install): $targetPath"
    }
    $script:Published = $true

    Write-Host "manifest sha256: $manifestSha"
    Write-Host "installed to $targetPath"
    Write-Host "next: cd '$targetPath'; Copy-Item .env.example .env (set real secrets in it); $(Join-Path 'scripts' 'launch.ps1')"
    $finished = $true
} catch {
    $finished = $true
    $message = $_.Exception.Message
    if (-not $message.StartsWith('install:', [System.StringComparison]::Ordinal)) { $message = "install: $message" }
    if ([KeInterrupt]::Fired) { $message = 'install: interrupted' }
    [Console]::Error.WriteLine($message)
    $exitCode = 1
} finally {
    # Security I-7: if staging was renamed away, the pinned working directory is
    # still the original; empty it from inside before leaving it.
    try {
        $pin = [System.Environment]::CurrentDirectory
        if ($script:Pinned -and $null -ne $script:Staging -and (Get-EntryKind $pin) -eq 'dir' -and [System.IO.Path]::GetFileName($pin).StartsWith('.ke-install.', [System.StringComparison]::Ordinal)) {
            Get-ChildItem -LiteralPath $pin -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        }
    } catch { $null = $_ }
    # Leave the pinned directory first: Windows will not delete a working directory.
    try {
        [System.Environment]::CurrentDirectory = $originalLocation
        Set-Location -LiteralPath $originalLocation
    } catch { $null = $_ }
    Close-Claim
    if ($null -ne $script:Staging -and [System.IO.Path]::GetFileName($script:Staging).StartsWith('.ke-install.', [System.StringComparison]::Ordinal)) {
        if ((Get-EntryKind $script:Staging) -eq 'link') {
            # A link planted under the staging name: remove the link only, never what it leads to.
            try { [System.IO.Directory]::Delete($script:Staging) } catch { $null = $_ }
        } else {
            # Security M-7: the pinned staging was emptied from inside above; the name is
            # removed non-recursively, so a directory swapped in under it is never deleted.
            try { [System.IO.Directory]::Delete($script:Staging, $false) } catch { $null = $_ }
        }
    }
    $env:PATH = $originalPath
    [KeInterrupt]::Dispose()
    # A stopped pipeline (Ctrl+C / SIGINT handled by pwsh itself) skips both the
    # catch and the exit below, and pwsh would then exit 0: force a failure.
    if (-not $finished) { [System.Environment]::Exit(1) }
}
if ([KeInterrupt]::Fired) { $exitCode = 1 }
exit $exitCode
