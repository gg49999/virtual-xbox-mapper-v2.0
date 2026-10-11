<#
.SYNOPSIS
    Installs the virtual-gamepad driver build that ships with Virtual Xbox Mapper.

.DESCRIPTION
    Installs (or updates to) the driver package found next to this script:
    ViGEmBus.inf, ViGEmBus.sys and ViGEmBus.cat, built from driver\ViGEmBus in
    the Virtual Xbox Mapper repository. That build can present the virtual
    controller as an Xbox One or Xbox Series X|S controller.

    The work is done by devcon.exe (part of the Windows Driver Kit), because
    the driver's bus device is root-enumerated and Windows has no inbox tool
    to create such a device. devcon is looked for in -DevconPath, next to this
    script, and in an installed Windows Driver Kit.

    NOT YET RUN ON A REAL MACHINE. See driver\README.md in the repository before relying on it.

.PARAMETER PackageDir
    Directory containing the driver package. Defaults to this script's directory.

.PARAMETER DevconPath
    Full path of devcon.exe.

.PARAMETER Force
    Install even if the same driver file is already in place.
#>
[CmdletBinding()]
param(
    [string]$PackageDir = $PSScriptRoot,
    [string]$DevconPath,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$hardwareId = 'Nefarius\ViGEmBus\Gen1'   # from ViGEmBus.inf

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Installing a driver requires an elevated (Run as administrator) PowerShell session.'
}

$inf = Join-Path $PackageDir 'ViGEmBus.inf'
$sys = Join-Path $PackageDir 'ViGEmBus.sys'
$cat = Join-Path $PackageDir 'ViGEmBus.cat'
foreach ($file in @($inf, $sys, $cat)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Driver package is incomplete, missing: $file"
    }
}

$installed = Join-Path $env:SystemRoot 'System32\drivers\ViGEmBus.sys'
if (-not $Force -and (Test-Path -LiteralPath $installed)) {
    if ((Get-FileHash -LiteralPath $installed).Hash -eq (Get-FileHash -LiteralPath $sys).Hash) {
        Write-Output 'This driver build is already installed. Nothing to do.'
        exit 0
    }
}

$signature = Get-AuthenticodeSignature -LiteralPath $cat
if ($signature.Status -eq 'NotSigned') {
    throw 'The driver package is not signed. 64-bit Windows does not load unsigned kernel drivers.'
}
if ($signature.Status -ne 'Valid') {
    Write-Warning ("The driver package's signature is not trusted on this machine (" + $signature.Status + '). ' +
        'A test-signed driver only loads while Windows is in test-signing mode.')
}

$candidates = @()
if ($DevconPath) { $candidates += $DevconPath }
$candidates += (Join-Path $PackageDir 'devcon.exe')
$kits = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\Tools'
if (Test-Path -LiteralPath $kits) {
    $candidates += Get-ChildItem -Path (Join-Path $kits '*\x64\devcon.exe') -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | ForEach-Object { $_.FullName }
}
$devcon = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
if (-not $devcon) {
    throw 'devcon.exe was not found. Pass -DevconPath, put it next to this script, or install the Windows Driver Kit.'
}

$existing = (& $devcon find $hardwareId 2>&1 | Out-String)
if ($existing -match 'No matching devices') {
    Write-Output 'Creating the virtual gamepad bus device and installing the driver...'
    & $devcon install $inf $hardwareId
} else {
    Write-Output 'Updating the driver of the existing virtual gamepad bus device...'
    & $devcon update $inf $hardwareId
}

# devcon: 0 = success, 1 = success but a restart is required, 2 = failure, 3 = syntax error
switch ($LASTEXITCODE) {
    0 { Write-Output 'Driver installed.' }
    1 { Write-Output 'Driver installed. Restart Windows to finish.' }
    default { throw "devcon failed with exit code $LASTEXITCODE." }
}
exit 0
