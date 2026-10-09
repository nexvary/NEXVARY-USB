"""User-initiated bounded AT discovery, preferences contain no SIM identifiers."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from .core import LabError, _open_serial, _one_query
from .coordination import lease
from .grouping import candidates, port_role

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
    def observations(self, key):
        return self.load().get('capabilities:'+key, {})
    def record(self, key, port, observation):
        data = self.load()
        entries = data.setdefault('capabilities:'+key, {})
        entries[port] = observation
        self._save(data)
    def verify(self, key, port, capability, source):
        allowed = {'APDU_READY': 'SELECT_MF_9000', 'SIM_ACCESS_READY': 'EF_ICCID_READABLE',
                   'SMS_READY': 'INBOX_READ_COMPLETE', 'DATA_READY': 'DATA_CONNECTED_VERIFIED'}
        if allowed.get(capability) != source:
            raise LabError('Capability requires independent operation evidence.')
        data = self.load(); entry = data.setdefault('capabilities:'+key, {}).setdefault(port, {})
        entry.setdefault('states', {})[capability] = 'VERIFIED'
        entry.setdefault('proofs', {})[capability] = source
        entry['observed_utc'] = datetime.now(timezone.utc).isoformat()
        self._save(data)
    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, sort_keys=True), encoding='utf-8')
        os.replace(temp, self.path)
    def remember(self, key, port):
        data = self.load(); data[key] = port
        self._save(data)


class CapabilityEvidence:
    """Independent observations; syntax probes never establish APDU/SMS/data readiness."""
    def __init__(self):
        self.states = {name: 'UNKNOWN' for name in
                       ('AT_READY','SIM_ACCESS_READY','APDU_READY','SMS_READY','DATA_READY')}
        self.commands = {}
        self.score = 0
    def observe(self, command, state, value):
        # Store only status, not identifiers or network-location data.
        self.commands[command] = state
        if command == 'AT' and state == 'OK': self.states['AT_READY'] = 'VERIFIED'
        if command == 'AT+CPIN?' and state == 'OK' and value == '+CPIN: READY':
            self.states['SIM_ACCESS_READY'] = 'VERIFIED'; self.score += 4
        elif command == 'AT+CPIN?' and state == 'OK' and '+CPIN:' in value:
            self.states['SIM_ACCESS_READY'] = 'NEEDS_USER'; self.score += 3
        if command == 'AT+CSQ' and state == 'OK' and '+CSQ:' in value: self.score += 2
    def public_dict(self, role):
        return dict(states=self.states,commands=self.commands,role=role,
                    observed_utc=datetime.now(timezone.utc).isoformat(),
                    classification='serial-session observation; injected fixtures are synthetic')


def _sim_capability(wire, evidence=None):
    evidence = evidence or CapabilityEvidence()
    for command in ('AT+CPIN?', 'AT+CSQ'):
        state, value = _one_query(wire, command, 2)
        evidence.observe(command, state, value)
        if state in ('TIMEOUT','IO_ERROR','NOISY','SESSION_UNCERTAIN'): break
    return evidence.score


def discover_at(device, preferences=None, factory=None, include_diagnostics=False,
                assess_sim=False):
    pref = preferences or PortPreferences()
    options = candidates(device, pref.get(device.key), include_diagnostics)
    failures = []
    usable = []
    for p in options[:8]:
        try:
            with lease(p.device):
                wire = (factory or _open_serial)(p.device,115200)
                try:
                    evidence = CapabilityEvidence()
                    state, value = _one_query(wire, 'AT', 2)
                    evidence.observe('AT', state, value)
                    score = _sim_capability(wire, evidence) if state == 'OK' and assess_sim else 0
                    observation = evidence.public_dict(port_role(p))
                    observation['classification'] = 'synthetic injected transport' if factory else 'live serial observation'
                    try: pref.record(device.key, p.device, observation)
                    except OSError: pass
                finally:
                    wire.close()
            if state == 'OK':
                usable.append((score, p.device))
                if not assess_sim:
                    try: pref.remember(device.key,p.device)
                    except OSError: pass
                    return p.device, failures
                failures.append((p.device, 'AT OK; SIM checks ' + ('responsive' if score else 'unverified')))
            else:
                failures.append((p.device, state))
        except (LabError, OSError) as exc:
            failures.append((p.device, str(exc) if isinstance(exc, LabError) else 'Port unavailable'))
    if usable:
        # Higher card capability outranks remembered preference; ties respect
        # candidate order (which still uses a previous known-working port).
        best = max(enumerate(usable), key=lambda item: (item[1][0], -item[0]))[1]
        if best[0] > 0:
            try: pref.remember(device.key, best[1])
            except OSError: pass
        return best[1], failures
    if not options:
        raise LabError('لا يوجد منفذ AT مرشح. منافذ Diagnostics تحتاج اختيارًا متقدمًا وموافقة مستقلة.')
    raise LabError('لم ينجح اكتشاف AT: ' + '؛ '.join(f'{p}: {s}' for p,s in failures))
