param([string]$Output='local-reader-output')
$ErrorActionPreference='Stop'
$Output=[IO.Path]::GetFullPath($Output)
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class ReaderUi {
 [StructLayout(LayoutKind.Sequential)] public struct Rect { public int L,T,R,B; }
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr FindWindow(string cls,string title);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd,out Rect rect);
 [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr hwnd,uint msg,IntPtr w,IntPtr l);
}
'@
$manifest=Get-Content "$Output\LOCAL-SIGNATURE.json" -Raw | ConvertFrom-Json
$before=@('Root','TrustedPublisher') | ForEach-Object { Test-Path "Cert:\LocalMachine\$_\$($manifest.thumbprint)" }
$p=Start-Process "$Output\NEXVARY-Local-Reader-Setup.exe" -PassThru
try {
    $window=[IntPtr]::Zero
    for($i=0;$i -lt 50;$i++){
        $window=[ReaderUi]::FindWindow('#32770','NEXVARY — موافقة الثقة المحلية')
        if($window -ne [IntPtr]::Zero){break}
        Start-Sleep -Milliseconds 100
    }
    if($window -eq [IntPtr]::Zero){throw 'Native approval dialog not observed'}
    $rect=New-Object ReaderUi+Rect
    if(![ReaderUi]::GetWindowRect($window,[ref]$rect)){throw 'Cannot read approval window bounds'}
    $bitmap=New-Object Drawing.Bitmap ($rect.R-$rect.L),($rect.B-$rect.T)
    $g=[Drawing.Graphics]::FromImage($bitmap)
    try {$g.CopyFromScreen($rect.L,$rect.T,0,0,$bitmap.Size);$bitmap.Save("$Output\LOCAL-APPROVAL-UI.png",[Drawing.Imaging.ImageFormat]::Png)} finally {$g.Dispose();$bitmap.Dispose()}
    [ReaderUi]::SendMessage($window,0x111,[IntPtr]7,[IntPtr]::Zero) | Out-Null
    if(!$p.WaitForExit(10000) -or $p.ExitCode -ne 0){throw 'Cancel did not exit normally'}
    $after=@('Root','TrustedPublisher') | ForEach-Object { Test-Path "Cert:\LocalMachine\$_\$($manifest.thumbprint)" }
    if((Compare-Object $before $after)){throw 'Cancel changed certificate trust'}
    # Explicit Yes on this disposable CI runner exercises the native certificate
    # import and the unchanged helper's integrity gates. Driver installation was
    # separately checked above; no real modem/card is involved.
    $p=Start-Process "$Output\NEXVARY-Local-Reader-Setup.exe" -PassThru
    for($i=0;$i -lt 50;$i++){
        $window=[ReaderUi]::FindWindow('#32770','NEXVARY — موافقة الثقة المحلية')
        if($window -ne [IntPtr]::Zero){break}
        Start-Sleep -Milliseconds 100
    }
    if($window -eq [IntPtr]::Zero){throw 'Positive approval dialog not observed'}
    [ReaderUi]::SendMessage($window,0x111,[IntPtr]6,[IntPtr]::Zero) | Out-Null
    for($i=0;$i -lt 300;$i++){
        $window=[ReaderUi]::FindWindow('#32770','NEXVARY — فحص تعريف القارئ')
        if($window -ne [IntPtr]::Zero){break}
        if($p.HasExited){throw 'Native positive installation exited before result dialog'}
        Start-Sleep -Milliseconds 100
    }
    if($window -eq [IntPtr]::Zero){throw 'Native install result dialog not observed'}
    [ReaderUi]::SendMessage($window,0x111,[IntPtr]1,[IntPtr]::Zero) | Out-Null
    if(!$p.WaitForExit(10000) -or $p.ExitCode -ne 0){throw 'Native positive installation failed'}
    $state=& "$Output\NEXVARY-Reader-Setup.exe" --check | ConvertFrom-Json
    if(!$state.trusted_package -or !$state.nexvary_reader_enumerated){throw 'Native trust/reader validation failed'}
    @{native_arabic_approval_dialog=$true;cancel_preserved_trust=$true;native_trust_install_passed=$true;state=$state;physical_card_tested=$false} | ConvertTo-Json -Depth 6 | Set-Content "$Output\LOCAL-UI-CHECKS.json"
} finally {
    if(!$p.HasExited){Stop-Process -Id $p.Id -Force}
    $stores=@('Root','TrustedPublisher')
    for($i=0;$i -lt 2;$i++){if(!$before[$i]){Remove-Item "Cert:\LocalMachine\$($stores[$i])\$($manifest.thumbprint)" -ErrorAction SilentlyContinue}}
}
