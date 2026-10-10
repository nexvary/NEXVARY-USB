"""Native setup checks on an isolated runner. Never install any driver/certificate."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

def check(output):
    output=Path(output).resolve();exe=output/'NEXVARY-Reader-Setup.exe'
    def run(path,*args):return subprocess.run([str(path),*args],capture_output=True,text=True,timeout=45)
    before=run(exe,'--check');assert before.returncode==0,before.stderr
    state=json.loads(before.stdout)
    assert state['package_complete'] and state['inf_identity_valid'],state
    assert not state['trusted_package'],state
    rejected=run(exe,'--install');assert rejected.returncode==20 and 'No device created' in rejected.stderr,rejected.stderr
    after=run(exe,'--check');assert after.returncode==0,after.stderr
    later=json.loads(after.stdout);assert later['own_root_devices']==state['own_root_devices']
    with tempfile.TemporaryDirectory() as temp:
        copy=Path(temp)/exe.name;shutil.copyfile(exe,copy)
        missing=run(copy,'--check');assert missing.returncode==0,missing.stderr
        missing_state=json.loads(missing.stdout);assert not missing_state['package_complete'] and not missing_state['trusted_package']
        assert run(copy,'--install').returncode==20
        assert run(copy,'--unknown').returncode==2
    evidence={'schema':'nexvary.reader-setup-native-check.v1','unsigned_install_blocked_before_device_creation':True,
              'missing_package_blocked':True,'invalid_arguments_rejected':True,'root_device_count_unchanged':True,
              'windows_native_pcsc_status':state,'trusted_install_path_executed':False,'physical_card_tested':False}
    (output/'SETUP-CHECKS.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(evidence,indent=2))
if __name__=='__main__':check(sys.argv[1])
