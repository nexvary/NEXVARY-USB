"""Bounded independent OS client; never owns a modem port or installs a driver."""
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from . import __version__
from .core import Reading, Report, LabError


def external_report(timeout=30):
    with tempfile.TemporaryDirectory(prefix='nexvary-pcsc-') as directory:
        target = Path(directory) / 'report.json'
        command = ([sys.executable] if getattr(sys, 'frozen', False) else
                   [sys.executable, '-m', 'nexvary_usim_lab'])
        command += ['pcsc-check', '--consent', '--export', str(target)]
        try:
            completed = subprocess.run(command, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       timeout=timeout, check=False,
                                       cwd=None if getattr(sys, 'frozen', False) else str(Path(__file__).resolve().parents[1]),
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired:
            # subprocess.run kills and waits for the child. Never retry APDUs.
            return _report([Reading('PC/SC APDU transfer', 'TIMEOUT',
                            'External client exceeded deadline; no retry.', '')])
        if completed.returncode not in (0, 2) or not target.is_file() or target.stat().st_size > 32768:
            raise LabError('External PC/SC client unavailable; no automatic retry.')
        result = json.loads(target.read_text(encoding='utf-8'))
        return from_result(result)


def _report(readings):
    return Report('NEXVARY USB Studio', __version__, datetime.now(timezone.utc).isoformat(),
                  'Independent PC/SC client', False, readings)


def from_result(result):
    if result.get('schema') != 'nexvary.field-pcsc.v1':
        raise LabError('External PC/SC report schema invalid.')
    rows = [Reading('PC/SC enumeration', 'OK' if result.get('enumeration') else 'UNVERIFIED',
                    str(result['reader_count']) + ' readers' if 'reader_count' in result else 'Reader count not established', ''),
            Reading('PC/SC connection', 'OK' if result.get('connected') else 'UNVERIFIED',
                    result.get('runtime', 'Native PC/SC'), '')]
    for key, name in [('select_mf', 'PC/SC SELECT MF'), ('ef_dir_read', 'PC/SC EF_DIR'),
                      ('usim_selected', 'PC/SC SELECT USIM')]:
        rows.append(Reading(name, 'OK' if result.get(key) else 'UNVERIFIED',
                            'Independent process / native SCard', ''))
    if result.get('error'):
        rows.append(Reading('PC/SC diagnostic', 'NEEDS_USER', result['error'], ''))
    for step in result.get('steps', []):
        rows.append(Reading(step['operation'], 'OK' if step['sw']=='9000' else 'CARD_STATUS',
                            'SW='+step['sw']+'; bytes='+str(step['data_bytes']), 'Native SCard response.'))
    rows.extend([Reading('USIM AKA', 'UNVERIFIED', 'Not performed', ''),
                 Reading('ePDG / IMS / Calls', 'UNVERIFIED', 'Not performed', '')])
    # Native OS use does not identify the physical/synthetic upstream card.
    rows.append(Reading('PC/SC provenance', 'OBSERVED',
                        'Physical modem provenance requires the separate Direct CSIM report.', ''))
    return _report(rows)
