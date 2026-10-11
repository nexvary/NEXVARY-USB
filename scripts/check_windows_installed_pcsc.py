"""External WinSCard client against installed reader; synthetic modem/card only."""
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from nexvary_usim_lab.virtual_reader import VirtualReaderService
from test_reader_diagnostics import FieldModem

def verify(output):
    output = Path(output)
    evidence = {'schema': 'nexvary.installed-windows-pcsc.v1',
                'transport': 'external process using system winscard.dll',
                'modem': 'synthetic FieldModem', 'physical_card_tested': False}
    def client():
        p = subprocess.run([sys.executable, 'scripts/check_field_pcsc.py', '--consent'],
                           capture_output=True, text=True, timeout=40)
        return json.loads(p.stdout)
    service = VirtualReaderService('COM9', 35963, True, True, True, FieldModem)
    try:
        service.start()
        for _ in range(12):
            result = client()
            if result['connected']:
                break
            time.sleep(1)
        evidence['card_read'] = result
        assert result['connected'] and result['select_mf'] and result['ef_dir_read'] and result['usim_selected'], result
        service.stop()
        for _ in range(12):
            removed = client()
            if not removed['connected']:
                break
            time.sleep(1)
        evidence['after_host_stop'] = removed
        assert not removed['connected'], removed
        # A fresh host instance grants a new synthetic local approval.
        service = VirtualReaderService('COM9', 35963, True, True, True, FieldModem)
        service.start()
        for _ in range(12):
            restarted = client()
            if restarted['ef_dir_read']:
                break
            time.sleep(1)
        evidence['fresh_consent_restart'] = restarted
        assert restarted['ef_dir_read'], restarted
        evidence['result'] = 'passed'
    except BaseException as exc:
        evidence['result'] = 'failed'
        evidence['error'] = str(exc)
        raise
    finally:
        service.stop()
        (output / 'INSTALLED-PCSC-CHECKS.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')

if __name__ == '__main__':
    verify(sys.argv[1])
