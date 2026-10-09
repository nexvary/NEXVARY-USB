[CmdletBinding()]
param([switch]$SelfTest)
$ErrorActionPreference = 'Stop'

# Offline Windows driver recovery. No modem commands, firmware or SIM access.
function Test-HuaweiId([string]$Id) {
    return $Id -match '^USB\\VID_12D1&PID_[0-9A-F]{4}(&|\\|$)'
}
function Test-InfMatch([string]$Text, [string[]]$Ids) {
    foreach ($line in ($Text -split '\r?\n')) {
        $model = ($line -split ';', 2)[0]
        if ($model -notmatch '=') { continue }
        foreach ($token in (($model -split '=', 2)[1] -split ',' | Select-Object -Skip 1)) {
            $hardware = $token.Trim().Trim('"')
            if ((Test-HuaweiId $hardware) -and ($Ids -contains $hardware)) { return $true }
        }
    }
    return $false
}
function Get-IdentityHash([string]$Value) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value))) -replace '-', '').Substring(0,16) }
    finally { $sha.Dispose() }
}
function Get-ModemInventory {
    @(Get-PnpDevice -PresentOnly | Where-Object { Test-HuaweiId $_.InstanceId } | ForEach-Object {
        $p = @(Get-PnpDeviceProperty -InstanceId $_.InstanceId -ErrorAction SilentlyContinue)
        [pscustomobject]@{
            Id = [string]$_.InstanceId
            HardwareIds = @($p | Where-Object KeyName -eq 'DEVPKEY_Device_HardwareIds' | ForEach-Object { $_.Data })
            Name = [string]$_.FriendlyName
            Class = [string]$_.Class
            Status = [string]$_.Status
            Code = [int](($p | Where-Object KeyName -eq 'DEVPKEY_Device_ProblemCode').Data)
            Inf = [string](($p | Where-Object KeyName -eq 'DEVPKEY_Device_DriverInfPath').Data)
            Version = [string](($p | Where-Object KeyName -eq 'DEVPKEY_Device_DriverVersion').Data)
        }
    })
}
function Save-Inventory($Devices, [string]$Path) {
    $safe = @($Devices | ForEach-Object {
        [pscustomobject]@{ Device = Get-IdentityHash $_.Id; Class = $_.Class; Status = $_.Status;
            Code = $_.Code; Inf = $_.Inf; Version = $_.Version;
            Usb = [regex]::Match($_.Id, 'VID_[0-9A-F]{4}&PID_[0-9A-F]{4}(?:&MI_[0-9A-F]{2})?', 'IgnoreCase').Value }
    })
    ConvertTo-Json -InputObject $safe -Depth 4 | Set-Content -LiteralPath $Path -Encoding UTF8
}
function Invoke-Pnp([string[]]$Arguments) {
    # Full instance IDs stay in process memory, never in the public report.
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = Join-Path $env:SystemRoot 'System32\pnputil.exe'
    foreach ($arg in $Arguments) { if ($arg.Contains('"') -or $arg.Contains("`n")) { throw 'Invalid argument.' } }
    $start.Arguments = ($Arguments | ForEach-Object { '"' + $_.TrimEnd('\') + '"' }) -join ' '
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = [Diagnostics.Process]::Start($start)
    try {
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(60000)) {
            # Do not kill a driver installation mid-operation or retry it.
            throw 'Windows driver operation exceeded 60 seconds. Do not retry; restart Windows after it completes.'
        }
        $null = $stdout.GetAwaiter().GetResult(); $null = $stderr.GetAwaiter().GetResult()
        if ($process.ExitCode -notin @(0,3010)) { throw "PnPUtil failed, exit code $($process.ExitCode)." }
        return $process.ExitCode
    } finally { $process.Dispose() }
}
function Get-VerifiedInf([string]$Folder, [string[]]$HardwareIds) {
    $files = @(Get-ChildItem -LiteralPath $Folder -Filter '*.inf' -File -Recurse -ErrorAction SilentlyContinue)
    if ($files.Count -gt 512) { throw 'Too many INF files. Choose the modem driver folder only.' }
    foreach ($inf in $files) {
        if ($inf.Length -gt 2MB) { continue }
        if (-not (Test-InfMatch ([IO.File]::ReadAllText($inf.FullName)) $HardwareIds)) { continue }
        # Trust applies to the catalog; Windows subsequently verifies catalog membership.
        $catalogs = @([regex]::Matches([IO.File]::ReadAllText($inf.FullName), '(?im)^\s*CatalogFile(?:\.[\w.]+)?\s*=\s*([^;\r\n]+)') | ForEach-Object { $_.Groups[1].Value.Trim().Trim('"') })
        $trusted = $false
        foreach ($catalog in $catalogs) {
            if ([IO.Path]::GetFileName($catalog) -ne $catalog) { continue }
            $cat = Join-Path $inf.DirectoryName $catalog
            if ((Test-Path -LiteralPath $cat -PathType Leaf) -and ((Get-AuthenticodeSignature -LiteralPath $cat).Status -eq 'Valid')) { $trusted = $true }
        }
        if ($trusted) { $inf }
    }
}
function Backup-Drivers($Devices, [string]$Destination) {
    $infs = @($Devices | ForEach-Object { $_.Inf } | Where-Object { $_ -match '^oem\d+\.inf$' } | Sort-Object -Unique)
    foreach ($inf in $infs) { $null = Invoke-Pnp @('/export-driver', $inf, $Destination) }
    return $infs.Count
}
function Backup-ModemCD([string]$Destination) {
    $disks = @(Get-CimInstance Win32_CDROMDrive | Where-Object { $_.Name -match 'Vodafone|Huawei' -and $_.Drive })
    foreach ($disk in $disks) {
        $root = $disk.Drive + '\'
        $files = @(Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction Stop)
        if (($files | Measure-Object Length -Sum).Sum -gt 512MB) { throw 'Modem CD exceeds 512 MB; backup stopped.' }
        $dest = Join-Path $Destination ($disk.Drive.TrimEnd(':'))
        $null = New-Item -ItemType Directory -Path $dest -Force
        foreach ($file in $files) {
            if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'CD contains a reparse point.' }
            $relative = $file.FullName.Substring($root.Length)
            $target = Join-Path $dest $relative
            $null = New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)) -Force
            Copy-Item -LiteralPath $file.FullName -Destination $target
            if ((Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath $target).Hash) { throw 'CD copy checksum mismatch.' }
        }
    }
    return $disks.Count
}
function Invoke-Recovery {
    if ($env:OS -ne 'Windows_NT') { throw 'Windows only.' }
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) { throw 'Run Start-Recovery.cmd as administrator.' }
    Write-Host 'NEXVARY Modem Recovery 1.0 - OFFLINE - NO FIRMWARE/SIM CHANGES' -ForegroundColor Cyan
    Write-Host 'Stage 1/3: inspect Windows. Close USB Studio and Vodafone first.'
    $null = Read-Host 'Press Enter when both programs are closed'
    $before = @(Get-ModemInventory)
    if (-not $before.Count) { throw 'No present Huawei USB device. Reconnect the modem; no repair performed.' }
    $before | Select-Object Name, Class, Code, Inf, Version | Format-Table -AutoSize | Out-Host
    $base = Join-Path ([Environment]::GetFolderPath('MyDocuments')) ('NEXVARY-Recovery-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,6))
    $drivers = Join-Path $base 'drivers'; $cd = Join-Path $base 'modem-cd'
    $null = New-Item -ItemType Directory -Path $drivers, $cd
    Save-Inventory $before (Join-Path $base 'before.json')
    Write-Host 'Stage 2/3: back up installed modem driver packages and virtual CD files.'
    $count = Backup-Drivers $before $drivers
    $cdCount = Backup-ModemCD $cd
    Write-Host "Saved $count driver packages and $cdCount virtual CD copies to: $base"
    Write-Host 'This is NOT an internal firmware or SIM backup.' -ForegroundColor Yellow
    Write-Host 'Stage 3/3: local signed driver repair. No download, forced driver, deletion or automatic reboot.'
    $bad = @($before | Where-Object { $_.Code -ne 0 })
    if (-not $bad.Count) { Write-Host 'No reported Windows driver problem. Nothing changed.'; return }
    $ids = @($bad | ForEach-Object { $_.HardwareIds } | Sort-Object -Unique)
    $candidates = @(Get-VerifiedInf $drivers $ids) + @(Get-VerifiedInf $cd $ids)
    foreach ($folder in @('C:\Program Files (x86)\Vodafone','C:\Program Files\Vodafone')) {
        if (Test-Path -LiteralPath $folder -PathType Container) { $candidates += @(Get-VerifiedInf $folder $ids) }
    }
    if (-not $candidates.Count) {
        $folder = Read-Host 'No trusted matching INF found. Optional local Huawei/Vodafone DRIVER folder (Enter to stop)'
        if ($folder -and (Test-Path -LiteralPath $folder -PathType Container)) { $candidates = @(Get-VerifiedInf $folder $ids) }
    }
    $candidates = @($candidates | Sort-Object FullName -Unique)
    if (-not $candidates.Count) { throw "No trusted matching local driver. Backup is saved at $base. Official compatible driver package is needed; no repair performed." }
    # Stage immutable copies of complete packages before consent/install.
    $stage = Join-Path $base 'repair-packages'; $null = New-Item -ItemType Directory -Path $stage
    $staged = @(); $i = 0
    foreach ($inf in $candidates) {
        $dest = Join-Path $stage ([string]$i); $i++
        Copy-Item -LiteralPath $inf.DirectoryName -Destination $dest -Recurse
        $path = Join-Path $dest $inf.Name
        if (@(Get-VerifiedInf $dest $ids | Where-Object FullName -eq $path).Count -ne 1) { throw 'Staged package validation failed.' }
        $staged += $path
    }
    Write-Host "Ready to register $($staged.Count) matching signed driver packages. Windows chooses compatible/ranked drivers."
    Write-Host 'Other connected Huawei devices matching the same INF may also receive this driver. Unplug those devices first.' -ForegroundColor Yellow
    if ((Read-Host 'Type REPAIR to approve; Enter cancels') -cne 'REPAIR') { Write-Host 'Cancelled. Backup retained.'; return }
    $reboot = $false
    foreach ($path in $staged) { if ((Invoke-Pnp @('/add-driver', $path, '/install')) -eq 3010) { $reboot = $true } }
    $after = @(Get-ModemInventory)
    Save-Inventory $after (Join-Path $base 'after.json')
    $after | Select-Object Name, Class, Code, Inf, Version | Format-Table -AutoSize | Out-Host
    $ports = @($after | Where-Object { $_.Class -in @('Ports','Modem') -and $_.Code -eq 0 })
    if (@($after | Where-Object Code -ne 0).Count -or -not $ports.Count) {
        Write-Host 'Driver operations finished, but usable modem ports are NOT confirmed. Do not repeat; share before.json/after.json.' -ForegroundColor Yellow
    } else { Write-Host 'Windows reports modem/serial interfaces without problem codes. AT/SIM operation still needs USB Studio verification.' -ForegroundColor Green }
    if ($reboot) { Write-Host 'Windows requested a restart. Save your work and restart manually.' -ForegroundColor Yellow }
    Get-ChildItem -LiteralPath $base -Recurse -File | Where-Object Name -ne 'SHA256SUMS.txt' | ForEach-Object {
        '{0}  {1}' -f (Get-FileHash -LiteralPath $_.FullName).Hash.ToLower(), $_.FullName.Substring($base.Length + 1)
    } | Set-Content -LiteralPath (Join-Path $base 'SHA256SUMS.txt') -Encoding UTF8
    Write-Host "Results: $base"
}
if (-not $SelfTest) {
    try { Invoke-Recovery } catch { Write-Host $_.Exception.Message -ForegroundColor Red }
    $null = Read-Host 'Press Enter to close'
}
