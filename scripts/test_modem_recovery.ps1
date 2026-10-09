$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/../recovery/NEXVARY-Modem-Recovery.ps1" -SelfTest
function Assert($Condition, $Message) { if (-not $Condition) { throw $Message } }
Assert (Test-HuaweiId 'USB\VID_12D1&PID_14C9&MI_00\private') 'Huawei interface rejected'
Assert (-not (Test-HuaweiId 'USB\VID_8086&PID_14C9\private')) 'Unrelated device accepted'
Assert (-not (Test-HuaweiId 'ROOT\Huawei')) 'Name-only device accepted'
$ids = @('USB\VID_12D1&PID_14C9&MI_00')
Assert (Test-InfMatch '%Modem%=Install, USB\VID_12D1&PID_14C9&MI_00' $ids) 'Exact hardware match rejected'
Assert (-not (Test-InfMatch ';%Modem%=Install, USB\VID_12D1&PID_14C9&MI_00' $ids)) 'Comment accepted'
Assert (-not (Test-InfMatch '%Modem%=Install, USB\VID_12D1&PID_14C9&MI_01' $ids)) 'Different interface accepted'
Assert (-not (Test-InfMatch '%Modem%=Install, USB\VID_12D1&PID_14C9' $ids)) 'VID/PID-only inference accepted'
$temp = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $temp
try {
    $devices = @([pscustomobject]@{ Id='USB\VID_12D1&PID_14C9&MI_00\SECRET-SERIAL'; Class='Unknown'; Status='Error'; Code=31; Inf='oem42.inf'; Version='1.0' })
    Save-Inventory $devices "$temp/report.json"
    $json = Get-Content "$temp/report.json" -Raw
    Assert (-not $json.Contains('SECRET-SERIAL')) 'Serial leaked'
    Assert ($json.Contains('31')) 'Code 31 omitted'
    $calls = New-Object Collections.Generic.List[string]
    function Invoke-Pnp([string[]]$Arguments) { $calls.Add(($Arguments -join '|')); return 0 }
    $devices += [pscustomobject]@{ Inf='oem42.inf' }, [pscustomobject]@{ Inf='../bad.inf' }, [pscustomobject]@{ Inf='usb.inf' }
    $count = Backup-Drivers $devices $temp
    Assert ($count -eq 1 -and $calls.Count -eq 1) 'Driver export not deduplicated/restricted'
    Assert ($calls[0].StartsWith('/export-driver|oem42.inf|')) 'Unexpected command'
    '%M%=Install,USB\VID_12D1&PID_14C9&MI_00' | Set-Content "$temp/unsigned.inf"
    Assert (@(Get-VerifiedInf $temp $ids).Count -eq 0) 'Unsigned package accepted'
    "CatalogFile=model.cat`n%M%=Install,USB\VID_12D1&PID_14C9&MI_00" | Set-Content "$temp/model.inf"
    'Synthetic catalog fixture; not a real signed driver' | Set-Content "$temp/model.cat"
    function Get-AuthenticodeSignature { param($LiteralPath) [pscustomobject]@{ Status='Valid' } }
    Assert (@(Get-VerifiedInf $temp $ids).Count -eq 1) 'Matching trusted synthetic catalog rejected'
    function Get-AuthenticodeSignature { param($LiteralPath) [pscustomobject]@{ Status='HashMismatch' } }
    Assert (@(Get-VerifiedInf $temp $ids).Count -eq 0) 'Invalid synthetic signature accepted'
    "CatalogFile=..\outside.cat`n%M%=Install,USB\VID_12D1&PID_14C9&MI_00" | Set-Content "$temp/model.inf"
    function Get-AuthenticodeSignature { param($LiteralPath) throw 'Traversal reached signature API' }
    Assert (@(Get-VerifiedInf $temp $ids).Count -eq 0) 'Catalog path traversal accepted'
    # Real host inventory is read-only; no devices or drivers are changed in CI.
    if ($env:OS -eq 'Windows_NT') { $null = @(Get-ModemInventory) }
    Write-Host 'PASS: synthetic matching, privacy, backup scope, unsigned rejection and read-only inventory'
} finally { Remove-Item -LiteralPath $temp -Recurse -Force }
