"""Physical-device grouping using PnP evidence, never VID/PID alone."""
from dataclasses import dataclass, field
import hashlib
import re
from .catalog import model_from_text
from .core import Port

_PHYSICAL = re.compile(r'^usb\\vid_[0-9a-f]{4}&pid_[0-9a-f]{4}\\[^\\]+$', re.I)
_ZERO = '00000000-0000-0000-0000-000000000000'

def evidence_keys(interface):
    keys = set()
    c = interface.container.strip('{}').lower()
    if re.fullmatch(r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}', c) and c != _ZERO:
        keys.add('container:' + c)
    for path in (interface.identity, *interface.ancestors):
        if _PHYSICAL.fullmatch(path):
            keys.add('physical:' + path.lower())
    return keys

@dataclass
class ModemDevice:
    key: str
    title: str
    interfaces: list = field(default_factory=list)
    ports: list[Port] = field(default_factory=list)
    evidence: str = 'unresolved'

    @property
    def driver_status(self):
        return 'تحتاج مراجعة التعريف' if any(x.mode == 'DRIVER_PROBLEM' for x in self.interfaces) else 'Windows يتعرف على الواجهات' if self.interfaces else 'منفذ Serial فقط'

def group_devices(inventory):
    clusters = []
    for interface in inventory.devices:
        keys = evidence_keys(interface)
        roots={k for k in keys if k.startswith('physical:')}
        related = [c for c in clusters if keys and c[0] & keys and
                   not (roots and (other_roots:={k for k in c[0] if k.startswith('physical:')}) and not roots & other_roots)]
        if not related:
            clusters.append([keys, [interface]])
        else:
            first = related[0]
            first[0].update(keys); first[1].append(interface)
            for other in related[1:]:
                first[0].update(other[0]); first[1].extend(other[1]); clusters.remove(other)
    result = []
    serial = {p.device.upper(): p for p in inventory.serial_ports}
    assigned = set()
    for index, (keys, interfaces) in enumerate(clusters):
        text = ' '.join(x.name for x in interfaces)
        model = model_from_text(text)
        vendor = interfaces[0].family
        title = f'{model.brand} {model.model}' if model else vendor + ' — الموديل غير مفحوص'
        if 'vodafone' in text.lower(): title += ' — Vodafone'
        ps = []
        for x in interfaces:
            if x.com_port and x.com_port.upper() not in assigned:
                ps.append(serial.get(x.com_port.upper(), Port(x.com_port, x.name, x.family, *x.usb_id.split(':'))))
                assigned.add(x.com_port.upper())
        token = sorted(keys)[0] if keys else f'unresolved:{index}:{interfaces[0].identity}'
        result.append(ModemDevice(hashlib.sha256(token.encode()).hexdigest(),title,interfaces,ps,
                                  'PnP container/physical parent' if keys else 'ارتباط PnP غير متاح؛ لم ندمج بالتخمين'))
    for port in inventory.serial_ports:
        if port.device.upper() not in assigned:
            model = model_from_text(port.description)
            title = f'{model.brand} {model.model}' if model else port.description
            result.append(ModemDevice(hashlib.sha256(('serial:'+port.device).encode()).hexdigest(),title,[],[port],
                                      'منفذ غير مرتبط بجهاز PnP؛ لا يثبت أنه مودم'))
    return result

def port_role(port):
    name = port.description.lower()
    if re.search(r'diag|diagnostic|debug|trace', name): return 'Diagnostics'
    if re.search(r'modem|at port|pc ui|application|app port', name): return 'AT candidate'
    return 'Unknown'

def candidates(device, preferred=None, include_diagnostics=False):
    allowed = [p for p in device.ports if include_diagnostics or port_role(p) != 'Diagnostics']
    return sorted(allowed, key=lambda p: (p.device != preferred, port_role(p) != 'AT candidate', p.device))
