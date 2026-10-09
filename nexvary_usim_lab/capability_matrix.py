"""Conservative, user-triggered per-port AT capability comparison.

No subscriber identifiers, location information, raw modem replies, SMS text
or authentication material are saved. Tests can inject serial transports;
production discovery always uses the actual local port after user action.
"""
from __future__ import annotations
from dataclasses import dataclass
from .core import LabError, _open_serial, _one_query
from .coordination import lease
from .grouping import candidates, port_role

PROBES = (
    ("sim", "AT+CPIN?", "+CPIN:"),
    ("signal", "AT+CSQ", "+CSQ:"),
    ("registration", "AT+CREG?", "+CREG:"),
    ("csim_syntax", "AT+CSIM=?", "+CSIM:"),
    ("crsm_syntax", "AT+CRSM=?", "+CRSM:"),
)
WEIGHT = {"sim": 6, "signal": 3, "registration": 2}

@dataclass(frozen=True)
class PortAssessment:
    port: str
    role: str
    at: str
    sim: str
    signal: str
    registration: str
    csim_syntax: str
    crsm_syntax: str
    score: int
    # No raw card or cell data is allowed in these results.

@dataclass(frozen=True)
class CapabilityMatrix:
    device_title: str
    ports: tuple[PortAssessment, ...]
    suggested_port: str | None
    sim_verified: bool
    simulated: bool = False

    @property
    def summary(self):
        if not self.ports:
            return "لم نعثر على منفذ AT مرشح. لم نغيّر تعريفات الجهاز."
        if self.sim_verified:
            return "تأكدت استجابة قراءة حالة SIM على المنفذ المقترح؛ لا يثبت USIM AKA."
        if self.suggested_port:
            return "وجدنا منفذ AT، لكن الوصول إلى SIM لم يثبت. هذا لا يعني تلف الشريحة."
        return "لم ينجح اتصال AT عبر المنافذ المرشحة؛ افحص تعريف الجهاز والبرامج الأخرى."

def _one_port(port, factory, deadline):
    states = {name: "NOT_TESTED" for name, _, _ in PROBES}
    state = "UNAVAILABLE"
    with lease(port.device):
        wire = factory(port.device, 115200)
        try:
            state, _ = _one_query(wire, "AT", deadline)
            if state == "OK":
                for name, command, prefix in PROBES:
                    result, value = _one_query(wire, command, deadline)
                    # Reply to test-syntax query without a +CSIM/+CRSM prefix
                    # establishes an AT parser acknowledgment, not APDU access.
                    if name.endswith("_syntax") and result == "OK":
                        states[name] = "ACK_ONLY"
                    elif result == "OK" and prefix in value:
                        states[name] = "RESPONSIVE"
                    elif result == "OK":
                        states[name] = "ACK_ONLY"
                    else:
                        states[name] = result
        finally:
            wire.close()
    score = (1 if state == "OK" else 0)
    score += sum(WEIGHT[name] for name in WEIGHT if states[name] == "RESPONSIVE")
    return PortAssessment(port.device, port_role(port), state, **states, score=score)

def compare_ports(device, factory=None, max_ports=4, deadline_seconds=1.5,
                  include_diagnostics=False):
    """Bounded read-only comparison. No command mutation and no port persistence.

    The result is an observation for this session, not permanent hardware support.
    Only serial interfaces belonging to the chosen grouped physical modem are
    eligible; diagnostic-only interfaces are excluded unless separately permitted.
    """
    if type(max_ports) is not int or not 1 <= max_ports <= 8:
        raise LabError("Invalid comparison port limit.")
    if not isinstance(deadline_seconds, (int, float)) or not 0.2 <= deadline_seconds <= 5:
        raise LabError("Invalid comparison deadline.")
    port_list = candidates(device, include_diagnostics=include_diagnostics)[:max_ports]
    factory = factory or _open_serial
    results = []
    for port in port_list:
        try:
            results.append(_one_port(port, factory, deadline_seconds))
        except (LabError, OSError, ValueError):
            results.append(PortAssessment(port.device, port_role(port),
                "UNAVAILABLE", "NOT_TESTED", "NOT_TESTED", "NOT_TESTED",
                "NOT_TESTED", "NOT_TESTED", 0))
        except Exception:
            # Do not leak low-level serial driver exception data.
            results.append(PortAssessment(port.device, port_role(port),
                "UNAVAILABLE", "NOT_TESTED", "NOT_TESTED", "NOT_TESTED",
                "NOT_TESTED", "NOT_TESTED", 0))
    usable = [(i, r) for i, r in enumerate(results) if r.at == "OK"]
    selected = max(usable, key=lambda it: (it[1].score, -it[0]))[1] if usable else None
    return CapabilityMatrix(
        getattr(device, "title", "مودم USB"),
        tuple(results), selected.port if selected else None,
        bool(selected and selected.sim == "RESPONSIVE"),
        simulated=False,
    )
