"""Explicit foreground bridge lifetime. Provision certificates independently."""
import json,os,stat,time,re,subprocess
from pathlib import Path
from .core import LabError
from .usim_backend import Authorization,ModemUsimBackend
from .secure_bridge import PrivateUsimBridge

def _private(path):
    path=Path(path)
    if not path.is_absolute() or path.is_symlink():raise LabError('Private files must be absolute regular paths.')
    info=path.stat()
    if not stat.S_ISREG(info.st_mode):raise LabError('Private file unavailable.')
    if os.name!='nt':
        if stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=os.geteuid():raise LabError('Private file must be owned mode 0600.')
    else:
        # Fail closed on permissive inherited ACLs, regardless of OS display language.
        exe=os.path.join(os.environ.get('SystemRoot',r'C:\Windows'),'System32','WindowsPowerShell','v1.0','powershell.exe')
        script="$p=$env:NEXVARY_PRIVATE_CHECK; $a=Get-Acl -LiteralPath $p; $s=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; $ok=$true; foreach($r in $a.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier])) {if($r.AccessControlType -eq 'Allow' -and $r.IdentityReference.Value -notin @($s,'S-1-5-18','S-1-5-32-544')){$ok=$false}}; if($ok){exit 0}else{exit 1}"
        env=dict(os.environ,NEXVARY_PRIVATE_CHECK=str(path))
        try:result=subprocess.run([exe,'-NoProfile','-NonInteractive','-Command',script],env=env,capture_output=True,timeout=8)
        except (OSError,subprocess.TimeoutExpired):raise LabError('Private ACL verification unavailable.') from None
        if result.returncode:raise LabError('Restrict configuration/key ACL to the owner, SYSTEM and Administrators.')
    return path

def serve(path,consent=False):
    if not consent:raise LabError('Bridge requires explicit current owner --consent.')
    path=_private(path)
    if path.stat().st_size>8192:raise LabError('Invalid bridge configuration.')
    config=json.loads(path.read_text(encoding='utf-8'))
    fields={'serial_port','device_key','aid','token','server_cert','server_key','client_ca','client_pin','port'}
    if not isinstance(config,dict) or set(config)!=fields:raise LabError('Invalid bridge configuration.')
    if type(config['port']) is not int or not 1<=config['port']<=65535 or not isinstance(config['device_key'],str) or not 1<=len(config['device_key'])<=128:
        raise LabError('Invalid scoped bridge device/port.')
    if not isinstance(config['token'],str) or not re.fullmatch('[A-Za-z0-9_-]{32,128}',config['token']):raise LabError('Invalid scoped token.')
    _private(config['server_key'])
    auth=Authorization(config['device_key'],config['token'],time.monotonic()+300)
    backend=ModemUsimBackend(config['serial_port'],config['device_key'],config['aid'],auth,config['token'],consent=True)
    bridge=PrivateUsimBridge(backend,config['server_cert'],config['server_key'],config['client_ca'],config['client_pin'],config['port'])
    print('Private loopback bridge active for at most 300 seconds. Ctrl+C revokes consent.')
    try:bridge.serve_forever()
    except KeyboardInterrupt:pass
    finally:bridge.stop()
