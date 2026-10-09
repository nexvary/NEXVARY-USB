$ErrorActionPreference = 'Stop'
function Get-TextAssociations {
    $keys = @('Registry::HKEY_CURRENT_USER\Software\Classes\.txt', 'Registry::HKEY_CLASSES_ROOT\.txt', 'Registry::HKEY_CLASSES_ROOT\txtfile\shell\open\command')
    $values = foreach ($key in $keys) {
        if (Test-Path -LiteralPath $key) { (Get-Item -LiteralPath $key).GetValue('') } else { '<missing>' }
    }
    return ($values | ConvertTo-Json -Compress)
}
$associations = Get-TextAssociations
$version = (& python -c 'from nexvary_usim_lab import __version__; print(__version__)').Trim()
if ($version -notmatch '^\d+\.\d+\.\d+
$target = Join-Path $env:TEMP 'nexvary-usb-package-test'
$settings = Join-Path $env:LOCALAPPDATA 'NEXVARY/USB-Studio'
New-Item -ItemType Directory -Force -Path $settings | Out-Null
$sentinel = Join-Path $settings 'ci-preserve-sentinel.txt'
Set-Content -LiteralPath $sentinel -Value 'preserve-user-settings'
$args = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',"/DIR=$target",'/TASKS=')
# Verify a real upgrade from the previously built 0.3.1 installer.
$previous = (Resolve-Path 'previous-installer/NEXVARY-USB-Studio-Setup-v0.3.1.exe').Path
$old = Start-Process -FilePath $previous -ArgumentList $args -Wait -PassThru
if ($old.ExitCode -ne 0) { throw 'Previous-version install failed' }
$process = Start-Process -FilePath $installer -ArgumentList $args -Wait -PassThru
if ($process.ExitCode -ne 0) { throw 'Installer failed' }
$exe = Join-Path $target 'NEXVARY-USB-Studio.exe'
if (!(Test-Path $exe)) { throw 'Installed executable missing' }
# Exercise packaged UI navigation; absence of a marker is a failure.
$env:NEXVARY_PACKAGE_SMOKE = Join-Path $env:TEMP 'nexvary-packaged-ui.json'
Remove-Item $env:NEXVARY_PACKAGE_SMOKE -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $exe -PassThru
if (!$p.WaitForExit(120000)) { Stop-Process -Id $p.Id; throw 'Packaged app timed out' }
if ($p.ExitCode -ne 0 -or !(Test-Path $env:NEXVARY_PACKAGE_SMOKE)) {
    $errorFile = $env:NEXVARY_PACKAGE_SMOKE + '.error'
    if (Test-Path $errorFile) { Get-Content $errorFile | Write-Output }
    throw 'Packaged GUI failed to open all pages'
}
if ((Get-TextAssociations) -ne $associations) { throw 'Text file associations changed' }
$marker = Get-Content -Raw $env:NEXVARY_PACKAGE_SMOKE | ConvertFrom-Json
if ($marker.version -ne $version -or $marker.pages.Count -ne 8) { throw 'Packaged version/page marker invalid' }
if ($marker.esim_contract -ne 'synthetic QR and CSV passed') { throw 'Packaged eSIM contract failed' }
# Upgrade using identical AppId, then uninstall; no outside directory is removed.
$p = Start-Process -FilePath $installer -ArgumentList $args -Wait -PassThru
if ($p.ExitCode -ne 0) { throw 'Upgrade failed' }
$uninstaller = Join-Path $target 'unins000.exe'
$p = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -Wait -PassThru
if ($p.ExitCode -ne 0 -or (Test-Path $exe)) { throw 'Uninstall failed' }
if ((Get-TextAssociations) -ne $associations) { throw 'Uninstall altered text associations' }
if (!(Test-Path $sentinel)) { throw 'User settings removed' }
Remove-Item $env:NEXVARY_PACKAGE_SMOKE
Remove-Item $sentinel
Remove-Item Env:NEXVARY_PACKAGE_SMOKE
Write-Output "Packaging PASS: 0.3.1 install, $version upgrade, packaged GUI, repeat upgrade, uninstall, settings and file associations preserved"
) { throw 'Invalid project version for installer smoke test' }
$installer = (Resolve-Path "installer-output/NEXVARY-USB-Studio-Setup-v$version.exe").Path
$target = Join-Path $env:TEMP 'nexvary-usb-package-test'
$settings = Join-Path $env:LOCALAPPDATA 'NEXVARY/USB-Studio'
New-Item -ItemType Directory -Force -Path $settings | Out-Null
$sentinel = Join-Path $settings 'ci-preserve-sentinel.txt'
Set-Content -LiteralPath $sentinel -Value 'preserve-user-settings'
$args = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',"/DIR=$target",'/TASKS=')
# Verify a real upgrade from the previously built 0.3.1 installer.
$previous = (Resolve-Path 'previous-installer/NEXVARY-USB-Studio-Setup-v0.3.1.exe').Path
$old = Start-Process -FilePath $previous -ArgumentList $args -Wait -PassThru
if ($old.ExitCode -ne 0) { throw 'Previous-version install failed' }
$process = Start-Process -FilePath $installer -ArgumentList $args -Wait -PassThru
if ($process.ExitCode -ne 0) { throw 'Installer failed' }
$exe = Join-Path $target 'NEXVARY-USB-Studio.exe'
if (!(Test-Path $exe)) { throw 'Installed executable missing' }
# Exercise packaged UI navigation; absence of a marker is a failure.
$env:NEXVARY_PACKAGE_SMOKE = Join-Path $env:TEMP 'nexvary-packaged-ui.json'
Remove-Item $env:NEXVARY_PACKAGE_SMOKE -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $exe -PassThru
if (!$p.WaitForExit(120000)) { Stop-Process -Id $p.Id; throw 'Packaged app timed out' }
if ($p.ExitCode -ne 0 -or !(Test-Path $env:NEXVARY_PACKAGE_SMOKE)) {
    $errorFile = $env:NEXVARY_PACKAGE_SMOKE + '.error'
    if (Test-Path $errorFile) { Get-Content $errorFile | Write-Output }
    throw 'Packaged GUI failed to open all pages'
}
if ((Get-TextAssociations) -ne $associations) { throw 'Text file associations changed' }
$marker = Get-Content -Raw $env:NEXVARY_PACKAGE_SMOKE | ConvertFrom-Json
if ($marker.version -ne '0.7.1' -or $marker.pages.Count -ne 8) { throw 'Packaged version/page marker invalid' }
if ($marker.esim_contract -ne 'synthetic QR and CSV passed') { throw 'Packaged eSIM contract failed' }
# Upgrade using identical AppId, then uninstall; no outside directory is removed.
$p = Start-Process -FilePath $installer -ArgumentList $args -Wait -PassThru
if ($p.ExitCode -ne 0) { throw 'Upgrade failed' }
$uninstaller = Join-Path $target 'unins000.exe'
$p = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -Wait -PassThru
if ($p.ExitCode -ne 0 -or (Test-Path $exe)) { throw 'Uninstall failed' }
if ((Get-TextAssociations) -ne $associations) { throw 'Uninstall altered text associations' }
if (!(Test-Path $sentinel)) { throw 'User settings removed' }
Remove-Item $env:NEXVARY_PACKAGE_SMOKE
Remove-Item $sentinel
Remove-Item Env:NEXVARY_PACKAGE_SMOKE
Write-Output 'Packaging PASS: 0.3.1 install, 0.7.1 upgrade, packaged GUI, repeat upgrade, uninstall, settings and file associations preserved'
