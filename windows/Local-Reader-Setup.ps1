# Explicit local trust, no boot-policy changes or signature-check bypass.
param([switch]$Elevated)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$manifest = Get-Content (Join-Path $PSScriptRoot 'LOCAL-SIGNATURE.json') -Raw | ConvertFrom-Json
function Check-Package {
    foreach ($file in $manifest.files.PSObject.Properties) {
        if ($file.Name -notin @('NEXVARYVirtualSIMReader.dll','NEXVARYVirtualSIMReader.inf','nexvaryvirtualsimreader.cat','NEXVARY-Reader-Setup.exe','NEXVARY-Local-Development.cer')) { throw 'Unexpected manifest member' }
        if ((Get-FileHash (Join-Path $PSScriptRoot $file.Name) -Algorithm SHA256).Hash -ne $file.Value) { throw "Changed file: $($file.Name)" }
    }
    if ($manifest.files.PSObject.Properties.Name.Count -ne 5) { throw 'Incomplete manifest' }
    $script:cert = New-Object Security.Cryptography.X509Certificates.X509Certificate2 (Join-Path $PSScriptRoot 'NEXVARY-Local-Development.cer')
    if ($cert.Thumbprint -ne $manifest.thumbprint -or $cert.HasPrivateKey -or $cert.NotAfter -lt (Get-Date)) { throw 'Certificate mismatch or expiry' }
    foreach ($file in @('NEXVARYVirtualSIMReader.dll','nexvaryvirtualsimreader.cat')) {
        $sig = Get-AuthenticodeSignature (Join-Path $PSScriptRoot $file)
        if (!$sig.SignerCertificate -or $sig.SignerCertificate.Thumbprint -ne $cert.Thumbprint -or $sig.Status -notin @('Valid','NotTrusted','UnknownError')) { throw 'Signature identity mismatch' }
    }
}
try {
    Check-Package
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (!$admin) {
        Start-Process powershell.exe -Verb RunAs -ArgumentList @('-NoProfile','-File',('"'+$PSCommandPath+'"'),'-Elevated') -Wait
        exit
    }
    $text = "حزمة تطوير محلية، وليست شهادة عامة أو اعتماد Microsoft.`nسيُضاف هذا المفتاح العام إلى Root وTrustedPublisher على هذا الكمبيوتر.`nبصمة الشهادة: $($cert.Thumbprint)`nلن تتغير إعدادات Secure Boot أو حماية التعريفات.`nهل تريد تجربة التثبيت؟"
    if ([Windows.Forms.MessageBox]::Show($text,'NEXVARY — موافقة الثقة المحلية','YesNo','Warning',0,'RightAlign,RtlReading') -ne 'Yes') { exit }
    $added = @()
    try {
        foreach ($store in @('Root','TrustedPublisher')) {
            $path = "Cert:\LocalMachine\$store\$($cert.Thumbprint)"
            if (!(Test-Path $path)) {
                Import-Certificate -FilePath (Join-Path $PSScriptRoot 'NEXVARY-Local-Development.cer') -CertStoreLocation "Cert:\LocalMachine\$store" | Out-Null
                $added += $path
            }
        }
        Check-Package
        $exe = Join-Path $PSScriptRoot 'NEXVARY-Reader-Setup.exe'
        $check = & $exe --check | ConvertFrom-Json
        if (!$check.trusted_package) { throw 'Windows signature/catalog validation failed after local trust' }
        $log = & $exe --install 2>&1 | Out-String
        $code = $LASTEXITCODE
        $state = & $exe --check | ConvertFrom-Json
        $report = @{schema='nexvary.local-reader-install.v1';exit_code=$code;install_log=$log;state=$state;certificate_thumbprint=$cert.Thumbprint;added_certificate_paths=$added;boot_policy_changed=$false;physical_card_tested=$false}
        $reportPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'NEXVARY-Local-Reader-Report.json'
        $report | ConvertTo-Json -Depth 6 | Set-Content $reportPath -Encoding UTF8
        if ($code -ne 0) { throw "فشل التثبيت برمز $code. التقرير: $reportPath" }
        $status = if ($state.nexvary_reader_enumerated) { 'ظهر قارئ NEXVARY عبر PC/SC' } else { 'لم يثبت تعداد القارئ بعد' }
        [Windows.Forms.MessageBox]::Show("$status`nلم تُختبر الشريحة أو APDU.`nالتقرير: $reportPath",'NEXVARY') | Out-Null
    } catch {
        foreach ($path in $added) { Remove-Item $path -ErrorAction SilentlyContinue }
        throw
    }
} catch {
    [Windows.Forms.MessageBox]::Show($_.Exception.Message,'NEXVARY — نتيجة التجربة','OK','Error') | Out-Null
    exit 1
}
