#requires -Version 5.1
<#
.SYNOPSIS
  maistro-engine Windows bootstrapper.

.DESCRIPTION
  install.sh / get.sh need bash; a fresh Windows 10 box has none. This script
  is the native entrypoint: it enables WSL2, installs an Ubuntu distro
  (handling the Windows feature-enable reboot WSL2 sometimes requires), then
  hands off to the existing Linux installer (get.sh -> install.sh) running
  inside that distro. Re-run this script after a requested reboot, or just
  leave it — it registers a one-time logon task and resumes itself.

  Runs the Linux side as root inside WSL to skip the interactive "create a
  UNIX username" first-run prompt and the docker group dance; this distro is
  treated as a single-purpose runtime for the engine, not a general dev box.

.PARAMETER Branch
  maistro-engine branch to install (default: main).

.PARAMETER Repo
  GitHub "owner/repo" to install from (default: BlakeMatthews-dev/maistro-engine).

.PARAMETER Distro
  WSL distro name to install/use (default: Ubuntu).

.PARAMETER AutoInstallDeps
  Skip confirmation prompts (WSL install, reboot) and the runtime-choice
  prompt inside install.sh. Maps to MAISTRO_AUTO_INSTALL_DEPS=1.

.PARAMETER SkipWizard
.PARAMETER NoStart
.PARAMETER NoCli
.PARAMETER NoOpen
  Passed straight through to install.sh as MAISTRO_SKIP_WIZARD / *_START_STACK
  / *_INSTALL_CLI / *_OPEN_BROWSER.

.EXAMPLE
  irm https://raw.githubusercontent.com/BlakeMatthews-dev/maistro-engine/main/get.ps1 | iex

.EXAMPLE
  .\get.ps1 -AutoInstallDeps
#>
[CmdletBinding()]
param(
    [string]$Branch = 'main',
    [string]$Repo = 'BlakeMatthews-dev/maistro-engine',
    [string]$Distro = 'Ubuntu',
    [switch]$AutoInstallDeps,
    [switch]$Resume,
    [switch]$SkipWizard,
    [switch]$NoStart,
    [switch]$NoCli,
    [switch]$NoOpen
)

$ErrorActionPreference = 'Stop'

function Write-InfoMsg { param([string]$Message) Write-Host "[maistro] $Message" -ForegroundColor Cyan }
function Write-OkMsg { param([string]$Message) Write-Host "[ok] $Message" -ForegroundColor Green }
function Write-WarnMsg { param([string]$Message) Write-Host "[warn] $Message" -ForegroundColor Yellow }
function Write-ErrMsg { param([string]$Message) Write-Host "[error] $Message" -ForegroundColor Red }

function Confirm-Action {
    param([string]$Prompt)
    if ($AutoInstallDeps) {
        Write-InfoMsg "$Prompt -> auto-confirmed (-AutoInstallDeps)"
        return $true
    }
    $reply = Read-Host "$Prompt [y/N]"
    return $reply -match '^[Yy]'
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Guarantees a copy of this script exists on disk: needed both for the
# elevation relaunch and for the post-reboot RunOnce hook, since a script
# fetched via `irm | iex` has no $PSCommandPath to point those at.
function Save-StableCopy {
    $destDir = Join-Path $env:LOCALAPPDATA 'maistro'
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    $dest = Join-Path $destDir 'get.ps1'
    if ($PSCommandPath -and (Test-Path -LiteralPath $PSCommandPath)) {
        Copy-Item -LiteralPath $PSCommandPath -Destination $dest -Force
    } else {
        $url = "https://raw.githubusercontent.com/$Repo/$Branch/get.ps1"
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    }
    return $dest
}

function Get-PassthroughArgs {
    param([switch]$IncludeResume)
    $argList = @()
    if ($Branch -ne 'main') { $argList += @('-Branch', $Branch) }
    if ($Repo -ne 'BlakeMatthews-dev/maistro-engine') { $argList += @('-Repo', $Repo) }
    if ($Distro -ne 'Ubuntu') { $argList += @('-Distro', $Distro) }
    if ($AutoInstallDeps) { $argList += '-AutoInstallDeps' }
    if ($SkipWizard) { $argList += '-SkipWizard' }
    if ($NoStart) { $argList += '-NoStart' }
    if ($NoCli) { $argList += '-NoCli' }
    if ($NoOpen) { $argList += '-NoOpen' }
    if ($IncludeResume) { $argList += '-Resume' }
    return $argList
}

function Invoke-Elevated {
    $scriptPath = Save-StableCopy
    $passthrough = Get-PassthroughArgs
    $quoted = $passthrough | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
    $fullArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$scriptPath`"") + $quoted
    Write-InfoMsg "Elevation is required to enable WSL2. Requesting an admin prompt..."
    Start-Process -FilePath 'powershell.exe' -ArgumentList $fullArgs -Verb RunAs
}

# RunOnce fires once at the next interactive logon, with the logged-on user's
# normal (non-elevated) token — fine here, since only the initial Windows
# feature-enable step needs admin, not resuming into an already-enabled WSL2.
function Register-Resume {
    param([string]$ScriptPath)
    $passthrough = Get-PassthroughArgs -IncludeResume
    $quoted = $passthrough | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
    $argStr = ($quoted -join ' ')
    $cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" $argStr"
    New-Item -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Force | Out-Null
    New-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' `
        -Name 'MaistroInstallResume' -Value $cmd -PropertyType String -Force | Out-Null
}

function Test-WindowsBuild {
    $build = [System.Environment]::OSVersion.Version.Build
    if ($build -lt 19041) {
        Write-ErrMsg "Windows build $build detected; WSL2 needs build 19041 (Windows 10 version 2004) or newer."
        Write-ErrMsg "Open Settings > Update & Security > Windows Update, install all updates, reboot, then re-run this script."
        return $false
    }
    Write-OkMsg "Windows build $build supports WSL2."
    return $true
}

# Advisory only, like the macOS arm64 manifest check: VirtualizationFirmwareEnabled
# is unreliable on some builds/VMs, so an inconclusive read does not block setup —
# `wsl --install` will fail with a clear message if virtualization is really off.
function Test-Virtualization {
    try {
        $cpu = Get-CimInstance -ClassName Win32_Processor -ErrorAction Stop | Select-Object -First 1
        if ($null -eq $cpu.VirtualizationFirmwareEnabled) {
            Write-WarnMsg "Could not determine virtualization firmware state; continuing."
            return
        }
        if ($cpu.VirtualizationFirmwareEnabled) {
            Write-OkMsg "Virtualization is enabled in firmware."
        } else {
            Write-WarnMsg "Virtualization (Intel VT-x / AMD-V) appears disabled in BIOS/UEFI firmware."
            Write-WarnMsg "If WSL2 install fails below, reboot into BIOS/UEFI setup and enable it, then re-run."
        }
    } catch {
        Write-WarnMsg "Could not query virtualization state; continuing."
    }
}

function Test-WslInstalled {
    return [bool](Get-Command wsl.exe -ErrorAction SilentlyContinue)
}

# `wsl -l -v` rows are UTF-16 and sometimes carry embedded NUL bytes when
# captured through the pipeline; strip them before matching.
function Get-WslDistroState {
    param([string]$Name)
    if (-not (Test-WslInstalled)) { return $null }
    $raw = & wsl.exe -l -v 2>$null
    if (-not $raw) { return $null }
    foreach ($line in $raw) {
        $clean = ($line -replace "`0", '').Trim()
        if ($clean -like "$Name*") { return $clean }
    }
    return $null
}

function Test-DistroUsable {
    param([string]$Name)
    if (-not (Get-WslDistroState -Name $Name)) { return $false }
    try {
        & wsl.exe -d $Name -u root -- true 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

# `wsl --install -d <distro>` can spend a couple of minutes downloading the
# rootfs on a fresh box; poll rather than judging "needs a reboot" off one
# early check, which would otherwise reboot machines that just needed longer.
function Wait-DistroUsable {
    param([string]$Name, [int]$TimeoutSeconds = 180)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-DistroUsable -Name $Name) { return $true }
        Start-Sleep -Seconds 5
    }
    return $false
}

# Runs get.sh (the existing, already-supported Linux/macOS installer) inside
# the WSL distro as root. Env-var assignments must be `export`ed inside the
# command string rather than prefixed before `curl`, since a leading
# `VAR=val cmd1 | cmd2` only scopes VAR to cmd1 in POSIX shells — and it's
# cmd2 (the piped-in get.sh) that needs to see these.
function Invoke-LinuxInstall {
    Write-InfoMsg "Bootstrapping $Distro (curl/git) and running the engine installer as root..."
    & wsl.exe -d $Distro -u root -- bash -lc 'apt-get update -qq && apt-get install -y -qq curl ca-certificates git'

    $envAssignments = @("MAISTRO_REPO=$Repo", "MAISTRO_BRANCH=$Branch")
    if ($AutoInstallDeps) { $envAssignments += 'MAISTRO_AUTO_INSTALL_DEPS=1' }
    if ($SkipWizard) { $envAssignments += 'MAISTRO_SKIP_WIZARD=1' }
    if ($NoStart) { $envAssignments += 'MAISTRO_START_STACK=0' }
    if ($NoCli) { $envAssignments += 'MAISTRO_INSTALL_CLI=0' }
    if ($NoOpen) { $envAssignments += 'MAISTRO_OPEN_BROWSER=0' }
    $exports = ($envAssignments | ForEach-Object { "export $_;" }) -join ' '

    $getShUrl = "https://raw.githubusercontent.com/$Repo/$Branch/get.sh"
    $innerCmd = "$exports curl -fsSL $getShUrl | bash"

    & wsl.exe -d $Distro -u root -- bash -lc $innerCmd
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-ErrMsg "The installer exited with code $exitCode inside $Distro."
        Write-ErrMsg "Re-run manually: wsl -d $Distro -u root -- bash -lc `"$innerCmd`""
        exit $exitCode
    }

    Write-OkMsg "Done. The Conductor UI should have opened automatically."
    Write-Host ""
    Write-Host "If it didn't, open: http://localhost:8101" -ForegroundColor Cyan
}

function Invoke-Main {
    Write-Host ""
    Write-Host "maistro-engine Windows installer" -ForegroundColor Cyan
    Write-Host "bootstraps WSL2, then hands off to the Linux installer" -ForegroundColor Cyan
    Write-Host ""

    if (Test-DistroUsable -Name $Distro) {
        Write-OkMsg "$Distro is ready."
        Invoke-LinuxInstall
        return
    }

    if (-not (Test-Admin)) {
        Invoke-Elevated
        return
    }

    if (-not (Test-WindowsBuild)) { exit 1 }
    Test-Virtualization

    if (-not $Resume) {
        if (-not (Confirm-Action "Install WSL2 + $Distro now (required for Docker on Windows)?")) {
            Write-ErrMsg "WSL2 is required. Re-run this script when ready, or pass -AutoInstallDeps."
            exit 1
        }
    }

    $scriptPath = Save-StableCopy
    Register-Resume -ScriptPath $scriptPath

    Write-InfoMsg "Running: wsl --install -d $Distro (this can take a few minutes)..."
    & wsl.exe --install -d $Distro

    if (Wait-DistroUsable -Name $Distro) {
        Write-OkMsg "$Distro is ready (no reboot needed)."
        Invoke-LinuxInstall
        return
    }

    Write-WarnMsg "WSL2 needs a restart to finish enabling."
    Write-WarnMsg "Setup will resume automatically the next time you log in (registered via RunOnce)."
    if (-not $AutoInstallDeps) {
        if (-not (Confirm-Action "Reboot now?")) {
            Write-InfoMsg "Reboot manually when ready; setup resumes automatically at your next logon."
            exit 0
        }
    }
    Restart-Computer -Force
}

Invoke-Main
