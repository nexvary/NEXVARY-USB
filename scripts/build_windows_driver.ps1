param([string]$Source = 'windows-driver-source', [string]$Output = 'driver-output')
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$Output = [IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force $Output | Out-Null
$kit = Join-Path $env:RUNNER_TEMP 'nexvary-wdk-26100'
New-Item -ItemType Directory -Force $kit | Out-Null
$archive = Join-Path $kit 'wdk.zip'
Invoke-WebRequest 'https://api.nuget.org/v3-flatcontainer/microsoft.windows.wdk.x64/10.0.26100.1/microsoft.windows.wdk.x64.10.0.26100.1.nupkg' -OutFile $archive
if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLower() -ne '247b2919ae451f65ba5f1cd51c7c39730fb0fc383d607f3e8ab317fddc8a8239') { throw 'WDK package digest differs' }
Expand-Archive $archive -DestinationPath $kit -Force
$vs = & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
& "$vs\Common7\Tools\Launch-VsDevShell.ps1" -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$driver = Join-Path ([IO.Path]::GetFullPath($Source)) 'virtualsmartcard\win32\BixVReader'
& msbuild (Join-Path $driver 'BixVReader.vcxproj') /m /t:Rebuild /p:Configuration=Release /p:Platform=x64 /p:PlatformToolset=v143 "/p:NexvaryWdkRoot=$kit" "/p:OutDir=$Output\" "/p:IntDir=$Output\obj\" /p:SignMode=Off /p:TargetName=NEXVARYVirtualSIMReader "/bl:$Output\build.binlog"
# Generate a catalog, but never generate/import a certificate or auto-sign/install.
& "$kit\c\bin\10.0.26100.0\x86\Inf2Cat.exe" "/driver:$Output" /os:10_X64 /uselocaltime
& dumpbin /headers "$Output\NEXVARYVirtualSIMReader.dll" | Out-File "$Output\PE-HEADERS.txt"
& dumpbin /exports "$Output\NEXVARYVirtualSIMReader.dll" | Out-File "$Output\PE-EXPORTS.txt"
& dumpbin /dependents "$Output\NEXVARYVirtualSIMReader.dll" | Out-File "$Output\PE-DEPENDENCIES.txt"
Copy-Item "$driver\BixVReader.ini" $Output
Copy-Item "$Source\virtualsmartcard\COPYING" "$Output\GPL-3.0.txt"
$manifest = @{ schema='nexvary.windows-driver-build.v1'; commit=$env:GITHUB_SHA; architecture='x64'; upstream='8a411e3672e843f9bb9fd750fc8dc56a26bb3bc8'; wdk='10.0.26100.1'; built=$true; signed=$false; installed=$false; pcsc_enumerated=$false; physical_modem_tested=$false; loopback='127.0.0.1:35963'; atr='3B00 transport emulation'; reset='session reselect only' }
$manifest | ConvertTo-Json | Set-Content "$Output\BUILD-EVIDENCE.json"
Get-ChildItem $Output -File | Where-Object { $_.Extension -in '.dll','.inf','.cat','.ini' } | ForEach-Object { "$((Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower())  $($_.Name)" } | Set-Content "$Output\SHA256SUMS.txt"

# Separate transport harness from the exact C sources linked into the UMDF DLL.
$harness = Join-Path $Output 'harness'
New-Item -ItemType Directory -Force $harness | Out-Null
$wrapper = Join-Path $harness 'release.c'
Set-Content $wrapper '#include <stdlib.h>
__declspec(dllexport) void release_response(void *p) { free(p); }'
& cl /nologo /LD /MD "/Fo:$harness\" "$Source\virtualsmartcard\src\vpcd\vpcd.c" "$Source\virtualsmartcard\src\vpcd\lock.c" $wrapper ws2_32.lib /link "/OUT:$harness\transport.dll" /EXPORT:vicc_init /EXPORT:vicc_exit /EXPORT:vicc_present /EXPORT:vicc_transmit
& python scripts/check_windows_driver_binary.py $Output
if ((Get-AuthenticodeSignature "$Output\NEXVARYVirtualSIMReader.dll").Status -ne 'NotSigned') { throw 'Unexpected driver signing state' }

# Standalone setup uses only Windows APIs; unsigned driver installation is rejected.
& cl /nologo /std:c++17 /EHsc /W4 /WX /MT /utf-8 /DUNICODE /D_UNICODE /D_WIN32_WINNT=0x0602 /Fo:"$Output\reader_setup.obj" windows/reader_setup.cpp /link "/OUT:$Output\NEXVARY-Reader-Setup.exe" setupapi.lib newdev.lib winscard.lib wintrust.lib crypt32.lib shell32.lib advapi32.lib user32.lib
& python scripts/check_windows_reader_setup.py $Output
Copy-Item windows/Check-Reader.cmd,windows/Install-Reader.cmd $Output
Copy-Item windows/reader_setup.cpp "$Output\reader_setup.cpp"

$manifest.setup_helper_built = $true
$manifest.trusted_install_tested = $false
$manifest | ConvertTo-Json | Set-Content "$Output\BUILD-EVIDENCE.json"
Get-ChildItem $Output -File | Where-Object { $_.Extension -in '.dll','.inf','.cat','.ini','.exe','.cmd' } | ForEach-Object { "$((Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower())  $($_.Name)" } | Set-Content "$Output\SHA256SUMS.txt"
