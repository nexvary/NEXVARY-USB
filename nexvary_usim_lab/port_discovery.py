"""User-initiated bounded AT discovery, preferences contain no SIM identifiers."""
import json
import os
from pathlib import Path
from .core import LabError, _open_serial, _one_query
from .coordination import lease
from .grouping import candidates

def preference_path():
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.config')))
    return base / 'NEXVARY' / 'USB-Studio' / 'ports.json'

class PortPreferences:
    def __init__(self, path=None): self.path = Path(path) if path else preference_path()
    def load(self):
        try:
            if self.path.stat().st_size > 65536: return {}
            data = json.loads(self.path.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError): return {}
    def get(self, key): return self.load().get(key)
    def remember(self, key, port):
        data = self.load(); data[key] = port
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, sort_keys=True), encoding='utf-8')
        os.replace(temp, self.path)

def discover_at(device, preferences=None, factory=None, include_diagnostics=False):
    pref = preferences or PortPreferences()
    options = candidates(device, pref.get(device.key), include_diagnostics)
    failures = []
    for p in options[:8]:
        try:
            with lease(p.device):
                wire = (factory or _open_serial)(p.device,115200)
                try: state, _ = _one_query(wire, 'AT', 2)
                finally: wire.close()
            if state == 'OK':
                try: pref.remember(device.key,p.device)
                except OSError: pass
                return p.device, failures
            failures.append((p.device, state))
        except LabError as exc:
            failures.append((p.device,str(exc)))
    if not options:
        raise LabError('لا يوجد منفذ AT مرشح. منافذ Diagnostics تحتاج اختيارًا متقدمًا وموافقة مستقلة.')
    raise LabError('لم ينجح اكتشاف AT: ' + '؛ '.join(f'{p}: {s}' for p,s in failures))
