param([string]$Output = 'driver-output')
$ErrorActionPreference = 'Stop'
$Output = [IO.Path]::GetFullPath($Output)
$tool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" | Sort-Object FullName -Descending | Select-Object -First 1
if (!$tool) { throw 'Windows SDK SignTool is required on the build machine' }
$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=NEXVARY Local Development $env:GITHUB_RUN_ID" -CertStoreLocation Cert:\CurrentUser\My -KeyAlgorithm RSA -KeyLength 3072 -HashAlgorithm SHA256 -KeyExportPolicy NonExportable -NotAfter (Get-Date).AddMonths(3)
try {
    & $tool.FullName sign /fd SHA256 /sha1 $cert.Thumbprint "$Output\NEXVARYVirtualSIMReader.dll"
    if ($LASTEXITCODE) { throw 'DLL signing failed' }
    # Signing changes the DLL: regenerate its catalog before signing the catalog.
    $inf2cat = Join-Path $env:RUNNER_TEMP 'nexvary-wdk-26100\c\bin\10.0.26100.0\x86\Inf2Cat.exe'
    & $inf2cat "/driver:$Output" /os:10_X64 /uselocaltime
    if ($LASTEXITCODE) { throw 'Catalog regeneration failed' }
    & $tool.FullName sign /fd SHA256 /sha1 $cert.Thumbprint "$Output\nexvaryvirtualsimreader.cat"
    if ($LASTEXITCODE) { throw 'Catalog signing failed' }
    Export-Certificate -Cert $cert -FilePath "$Output\NEXVARY-Local-Development.cer" | Out-Null
    $files = @{}
    foreach ($name in @('NEXVARYVirtualSIMReader.dll','NEXVARYVirtualSIMReader.inf','nexvaryvirtualsimreader.cat','NEXVARY-Reader-Setup.exe','NEXVARY-Local-Development.cer')) {
        $files[$name] = (Get-FileHash (Join-Path $Output $name) -Algorithm SHA256).Hash
    }
    @{schema='nexvary.local-development-signature.v1';thumbprint=$cert.Thumbprint;files=$files;publicly_trusted=$false;private_key_exported=$false;expires=$cert.NotAfter.ToUniversalTime().ToString('o')} | ConvertTo-Json -Depth 5 | Set-Content "$Output\LOCAL-SIGNATURE.json" -Encoding UTF8
    Copy-Item windows/Local-Reader-Setup.ps1,windows/Local-Reader-Setup.cmd $Output
    Copy-Item docs/WINDOWS-LOCAL-READER-AR.md "$Output\LOCAL-README-AR.md"
} finally {
    Remove-Item "Cert:\CurrentUser\My\$($cert.Thumbprint)" -DeleteKey -ErrorAction Stop
}
