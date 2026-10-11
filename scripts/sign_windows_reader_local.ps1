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
    # Windows PowerShell 5.1 needs a BOM to decode the Arabic UI reliably.
    Get-Content windows/Local-Reader-Setup.ps1 -Raw | Set-Content "$Output\Local-Reader-Setup.ps1" -Encoding utf8BOM
    Copy-Item windows/Local-Reader-Setup.cmd $Output
    $build = Get-Content "$Output\BUILD-EVIDENCE.json" -Raw | ConvertFrom-Json
    $build.signed = $true
    $build | Add-Member -NotePropertyName signing_scope -NotePropertyValue 'local-development-only' -Force
    $build | ConvertTo-Json | Set-Content "$Output\BUILD-EVIDENCE.json" -Encoding UTF8
    Get-ChildItem $Output -File | Where-Object { $_.Extension -in '.dll','.inf','.cat','.ini','.exe','.cmd','.ps1','.cer' } | ForEach-Object { "$((Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower())  $($_.Name)" } | Set-Content "$Output\SHA256SUMS.txt"
    Copy-Item docs/WINDOWS-LOCAL-READER-AR.md "$Output\LOCAL-README-AR.md"
} finally {
    Remove-Item "Cert:\CurrentUser\My\$($cert.Thumbprint)" -DeleteKey -ErrorAction Stop
}
