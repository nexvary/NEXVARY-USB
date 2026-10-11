param([string]$Output = 'driver-output')
$ErrorActionPreference = 'Stop'
$Output = [IO.Path]::GetFullPath($Output)
$manifest = Get-Content "$Output\LOCAL-SIGNATURE.json" -Raw | ConvertFrom-Json
$added = @()
$evidence = @{schema='nexvary.local-reader-ci.v1';boot_policy_changed=$false;physical_card_tested=$false;apdu_tested=$false;runner=$env:RUNNER_OS}
try {
    foreach ($store in @('Root','TrustedPublisher')) {
        $path = "Cert:\LocalMachine\$store\$($manifest.thumbprint)"
        if (!(Test-Path $path)) {
            Import-Certificate -FilePath "$Output\NEXVARY-Local-Development.cer" -CertStoreLocation "Cert:\LocalMachine\$store" | Out-Null
            $added += $path
        }
    }
    $before = & "$Output\NEXVARY-Reader-Setup.exe" --check | ConvertFrom-Json
    $evidence.signature_check = $before
    if (!$before.trusted_package) { throw 'Locally trusted signature failed native package validation' }
    $evidence.install_log = (& "$Output\NEXVARY-Reader-Setup.exe" --install 2>&1 | Out-String)
    $evidence.install_exit_code = $LASTEXITCODE
    # Poll boundedly for asynchronous device startup. No service is started/stopped here.
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        $after = & "$Output\NEXVARY-Reader-Setup.exe" --check | ConvertFrom-Json
        if ($after.nexvary_reader_enumerated) { break }
        Start-Sleep -Seconds 1
    }
    $evidence.after = $after
    # Positive and tampering checks exercise real WinVerifyTrust/catalog membership.
    $temp = Join-Path $env:RUNNER_TEMP 'nexvary-local-tamper'
    New-Item -ItemType Directory -Force $temp | Out-Null
    Copy-Item "$Output\NEXVARY-Reader-Setup.exe","$Output\NEXVARYVirtualSIMReader.dll","$Output\NEXVARYVirtualSIMReader.inf","$Output\nexvaryvirtualsimreader.cat" $temp
    Add-Content (Join-Path $temp 'NEXVARYVirtualSIMReader.inf') '; tamper probe'
    $tamper = & "$temp\NEXVARY-Reader-Setup.exe" --check | ConvertFrom-Json
    if ($tamper.trusted_package) { throw 'Changed INF unexpectedly trusted' }
    & "$temp\NEXVARY-Reader-Setup.exe" --install 2>&1 | Out-File "$Output\TAMPER-CHECK.txt"
    if ($LASTEXITCODE -ne 20) { throw 'Tampered package not blocked' }
    $evidence.tamper_blocked = $true
    if ($evidence.install_exit_code -ne 0) { throw 'Windows installation rejected; inspect recorded install log' }
    if (!$after.nexvary_reader_enumerated) { throw 'Installation completed but Windows PC/SC reader enumeration is not proved on this runner' }
    & python scripts/check_windows_installed_pcsc.py $Output
    if ($LASTEXITCODE) { throw 'External Windows PC/SC synthetic card test failed' }
    $evidence.apdu_tested = $true
    $evidence.apdu_provenance = 'synthetic card and modem; external native WinSCard process'
    $evidence.result = 'installed_and_enumerated_without_boot_policy_changes'
} catch {
    $evidence.result = 'failed'
    $evidence.error = $_.Exception.Message
    Write-Host $evidence.error
    throw
} finally {
    foreach ($path in $added) { Remove-Item $path -ErrorAction SilentlyContinue }
    $evidence | ConvertTo-Json -Depth 8 | Set-Content "$Output\LOCAL-CI-EVIDENCE.json" -Encoding UTF8
}
# The last native command intentionally returned 20 for the tampering probe.
# Reset only after every positive and negative assertion has passed.
$global:LASTEXITCODE = 0
