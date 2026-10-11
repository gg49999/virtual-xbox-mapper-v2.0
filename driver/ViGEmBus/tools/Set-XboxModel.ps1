<#
.SYNOPSIS
    Shows or changes how the ViGEm bus driver presents Xbox targets.

.DESCRIPTION
    Sets the XusbDefaultModel value below the Parameters key of the ViGEmBus
    service. It applies to every Xbox 360 target a client plugs in without
    asking for specific vendor/product IDs, which is what unmodified
    applications do. See XBOX-MODELS.md for details.

    The driver reads the value whenever a controller gets plugged in. Neither
    a reboot nor a driver restart is needed, but controllers that are already
    plugged in keep their current presentation: restart the application that
    creates them.

    Requires a ViGEmBus build that contains the model selection. On the
    original driver the value is ignored.

.PARAMETER Model
    The model to present. Omit to display the current setting.

.EXAMPLE
    .\Set-XboxModel.ps1 XboxSeries

.EXAMPLE
    .\Set-XboxModel.ps1 Xbox360
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('Xbox360', 'XboxOne', 'XboxOneS', 'XboxEliteSeries2', 'XboxSeries', 'XboxSeriesBluetooth')]
    [string]$Model
)

$ErrorActionPreference = 'Stop'

# Keep in sync with XBOX_PRESENTATION_MODEL in sys\XboxModels.hpp
$models = [ordered]@{
    Xbox360             = 0
    XboxOne             = 1
    XboxOneS            = 2
    XboxEliteSeries2    = 3
    XboxSeries          = 4
    XboxSeriesBluetooth = 5
}

$serviceKey = 'HKLM:\SYSTEM\CurrentControlSet\Services\ViGEmBus'
$parametersKey = Join-Path $serviceKey 'Parameters'
$valueName = 'XusbDefaultModel'

if (-not (Test-Path $serviceKey)) {
    throw 'The ViGEmBus service is not installed on this machine.'
}

if (-not $Model) {
    $current = 0
    $item = Get-ItemProperty -Path $parametersKey -Name $valueName -ErrorAction SilentlyContinue
    if ($null -ne $item) {
        $current = [uint32]$item.$valueName
    }

    $name = ($models.GetEnumerator() | Where-Object { $_.Value -eq $current } | Select-Object -First 1).Key
    if (-not $name) {
        $name = 'Xbox360 (the stored value is not a known model and is ignored by the driver)'
    }

    Write-Output "Current default model: $name [$current]"
    Write-Output ('Available models: ' + ($models.Keys -join ', '))
    return
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Changing the model requires an elevated (Run as administrator) PowerShell session.'
}

if (-not (Test-Path $parametersKey)) {
    New-Item -Path $parametersKey -Force | Out-Null
}

New-ItemProperty -Path $parametersKey -Name $valueName -PropertyType DWord -Value $models[$Model] -Force | Out-Null

Write-Output "Default model set to $Model [$($models[$Model])]."
Write-Output 'It applies to the next virtual controller that gets plugged in; restart the application that creates it.'
