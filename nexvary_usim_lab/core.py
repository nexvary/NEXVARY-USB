"""Hardware-safe modem diagnostics. No SIM authentication or mutation is attempted.

Only an explicit fixed allow-list of read-only AT queries is sent. Raw device
responses never reach the reports; subscription identifiers are masked.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import csv
import io
import json
import re
import time
from typing import Callable

class LabError(RuntimeError):
    """Expected, sanitized diagnostic error."""

@dataclass(frozen=True)
class Port:
    device: str
    description: str
    manufacturer: str
    vid: str
    pid: str

@dataclass(frozen=True)
class Query:
    name: str
    command: str
    note: str

# Deliberately no AT+CIMI, PIN submission, raw APDU, SMS mutation, or network changes.
QUERIES = (
    Query("Connection", "AT", "Basic AT command channel"),
    Query("Manufacturer", "AT+CGMI", "Identification only"),
    Query("Model", "AT+CGMM", "Identification only"),
    Query("Firmware", "AT+CGMR", "Identification only"),
    Query("SIM status", "AT+CPIN?", "Read status; never submit a PIN"),
    Query("ICCID", "AT+CCID", "Masked SIM identifier, if available"),
    Query("Signal", "AT+CSQ", "Cellular signal diagnostic"),
    Query("Registration", "AT+CREG?", "Cellular registration diagnostic"),
    Query("CSIM probe", "AT+CSIM=?", "Test syntax response is not proof of USIM AKA"),
    Query("CGLA probe", "AT+CGLA=?", "Test syntax response is not proof of USIM AKA"),
    Query("CCHO probe", "AT+CCHO=?", "Test syntax response is not proof of USIM AKA"),
    Query("CRSM probe", "AT+CRSM=?", "Test syntax response is not proof of USIM AKA"),
)

# ICCID, IMSI, IMEI and similar decimal identifiers; retain only final four.
_PRIVATE_DECIMAL = re.compile(r"(?<!\d)\d{12,22}(?!\d)")
# Extremely conservative sanitation for diagnostic text in case of a modem error.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

def redact(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("Expected text")
    value = _CONTROL.sub("", value)
    return _PRIVATE_DECIMAL.sub(lambda m: "*" * (len(m.group()) - 4) + m.group()[-4:], value)[:512]

def ports() -> list[Port]:
    try:
        from serial.tools import list_ports
    except ImportError as e:
        raise LabError("Install pyserial to discover serial modems.") from None
    found = []
    for p in list_ports.comports():
        found.append(Port(
            device=str(p.device),
            description=redact(str(p.description or "Serial device")),
            manufacturer=redact(str(p.manufacturer or "Unknown")),
            vid=f"{p.vid:04X}" if p.vid is not None else "—",
            pid=f"{p.pid:04X}" if p.pid is not None else "—",
        ))
    return sorted(found, key=lambda p: p.device)

def pcsc_readers() -> tuple[bool, list[str]]:
    """Optional PC/SC inventory. No APDU is sent to any card."""
    try:
        from smartcard.System import readers
    except ImportError:
        return False, []
    except Exception:
        return False, []
    try:
        return True, [redact(str(r)) for r in readers()]
    except Exception:
        return True, []

def _open_serial(device: str, baudrate: int):
    try:
        import serial
    except ImportError:
        raise LabError("Install pyserial before connecting to a modem.") from None
    try:
        return serial.Serial(port=device, baudrate=baudrate, timeout=0.15, write_timeout=2)
    except Exception:
        raise LabError("Unable to open serial port; check its driver and other software.") from None

def _one_query(transport, command: str, deadline_seconds: float = 4) -> tuple[str, str]:
    """Process expected AT reply while discarding unsolicited network chatter.

    On real modems the command port may emit repeated unsolicited status lines
    before the terminal OK/ERROR. A raw 32-line cap previously caused false
    "Response limit exceeded" on Huawei K3770 even as later commands worked.
    No unsolicited text is copied to exported reports.
    """
    if command not in {q.command for q in QUERIES}:
        raise LabError("AT command is not in the read-only allow-list.")
    if not 0.2 <= deadline_seconds <= 15:
        raise LabError("Invalid query deadline.")
    expected_prefix = {
        "AT+CPIN?": "+CPIN:",
        "AT+CCID": "+CCID:",
        "AT+CSQ": "+CSQ:",
        "AT+CREG?": "+CREG:",
        "AT+CSIM=?": "+CSIM:",
        "AT+CGLA=?": "+CGLA:",
        "AT+CCHO=?": "+CCHO:",
        "AT+CRSM=?": "+CRSM:",
    }.get(command)
    unprefixed_id = command in ("AT+CGMI", "AT+CGMM", "AT+CGMR")
    try:
        transport.reset_input_buffer()
        transport.write((command + "\r").encode("ascii"))
        transport.flush()
        deadline = time.monotonic() + deadline_seconds
        output = []
        noise_count = 0
        total_bytes = 0
        while time.monotonic() < deadline:
            chunk = transport.readline()
            if not chunk:
                continue
            total_bytes += len(chunk)
            if total_bytes > 32768:
                return "NOISY", "Excess unsolicited modem traffic"
            line = chunk.decode("ascii", errors="replace").strip()
            if not line or line.upper() == command.upper():
                continue
            if line == "OK":
                return "OK", redact(" | ".join(output)) or "OK"
            if line == "ERROR" or line.startswith(("+CME ERROR", "+CMS ERROR")):
                return "UNSUPPORTED", "Modem rejected this command"
            if (expected_prefix and line.startswith(expected_prefix)) or (
                command == "AT+CCID" and line.isdecimal() and 18 <= len(line) <= 22
            ):
                if len(output) < 5:
                    output.append(line[:160])
            elif unprefixed_id and len(line) <= 80 and not line.startswith(("+", "^", "%")):
                # Identification commands return a plain model/vendor/version.
                if len(output) < 5:
                    output.append(line)
            else:
                noise_count += 1
                if noise_count > 512:
                    return "NOISY", "Continuous unsolicited modem traffic"
        if output:
            return "TIMEOUT", "Reply data received; final OK not received"
        return "TIMEOUT", "No complete reply within deadline"
    except LabError:
        raise
    except Exception:
        return "IO_ERROR", "Serial transport failed"

@dataclass
class Reading:
    name: str
    status: str
    value: str
    note: str

@dataclass
class Report:
    product: str
    version: str
    timestamp_utc: str
    device: str
    simulated: bool
    readings: list[Reading]
    disclaimer: str = "AT probes do not establish AKA, PC/SC, ePDG, IMS or calling support."

    def public_dict(self) -> dict:
        return asdict(self)

def probe(device: str, baudrate: int = 115200,
          factory: Callable | None = None) -> Report:
    if not device or len(device) > 255 or "\x00" in device:
        raise LabError("Choose a valid serial port.")
    if baudrate not in (9600, 19200, 38400, 57600, 115200, 230400):
        raise LabError("Unsupported baud rate.")
    factory = factory or _open_serial
    transport = factory(device, baudrate)
    results = []
    try:
        for query in QUERIES:
            state, value = _one_query(transport, query.command)
            results.append(Reading(query.name, state, redact(value), query.note))
    finally:
        transport.close()
    return Report(
        product="NEXVARY USB-USIM Lab", version="0.1.2",
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        device=redact(device), simulated=False, readings=results)

class DemoSerial:
    """Offline only. Never used as a fallback for a physical device."""
    ANSWERS = {
        "AT": ("OK",),
        "AT+CGMI": ("Demo Modem Manufacturer", "OK"),
        "AT+CGMM": ("Demo USB Model", "OK"),
        "AT+CGMR": ("Demo Firmware", "OK"),
        "AT+CPIN?": ("+CPIN: READY", "OK"),
        "AT+CCID": ("+CCID: 89882123456789012345", "OK"),
        "AT+CSQ": ("+CSQ: 15,99", "OK"),
        "AT+CREG?": ("+CREG: 0,1", "OK"),
        "AT+CSIM=?": ("ERROR",),
        "AT+CGLA=?": ("ERROR",),
        "AT+CCHO=?": ("ERROR",),
        "AT+CRSM=?": ("ERROR",),
    }
    def __init__(self, device: str, baudrate: int):
        self.pending = []
    def reset_input_buffer(self):
        self.pending.clear()
    def write(self, content: bytes):
        command = content.decode("ascii").strip()
        self.pending = [(line + "\r\n").encode() for line in self.ANSWERS.get(command, ("ERROR",))]
    def flush(self):
        pass
    def readline(self):
        return self.pending.pop(0) if self.pending else b""
    def close(self):
        pass

def demo() -> Report:
    report = probe("OFFLINE-DEMO", factory=DemoSerial)
    report.simulated = True
    return report

def to_json(report: Report) -> str:
    # Do not accidentally serialize raw vendor data: Report is already redacted.
    return json.dumps(report.public_dict(), indent=2, ensure_ascii=False) + "\n"

def to_csv(report: Report) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("device", "simulated", "name", "status", "value", "note"))
    for reading in report.readings:
        writer.writerow((report.device, report.simulated, reading.name, reading.status,
                         reading.value, reading.note))
    return output.getvalue()

# One fixed, non-persistent ISO 7816 SELECT MF (3F00). No generic APDU API.
_SELECT_MF_COMMAND = 'AT+CSIM=14,"00A40000023F00"'
_CSIM_LINE = re.compile(r'^\+CSIM:\s*(\d+)\s*,\s*"?([0-9A-Fa-f]+)"?\s*')

def select_master_file(device: str, baudrate: int = 115200,
                       factory: Callable | None = None) -> Reading:
    """Optional on-card APDU transport evidence. This cannot verify USIM AKA.

    Caller must obtain local card owner's consent. The APDU changes only the
    current selected file; no UPDATE, VERIFY, AUTHENTICATE or PIN is issued.
    Do not expose this over HTTP or include raw card response in any report.
    """
    if not device or len(device) > 255 or "\x00" in device:
        raise LabError("Choose a valid serial port.")
    if baudrate not in (9600, 19200, 38400, 57600, 115200, 230400):
        raise LabError("Unsupported baud rate.")
    transport = (factory or _open_serial)(device, baudrate)
    try:
        state, _ = _one_query(transport, "AT")
        if state != "OK":
            raise LabError("Modem AT channel is not ready.")
        try:
            transport.reset_input_buffer()
            transport.write((_SELECT_MF_COMMAND + "\r").encode("ascii"))
            transport.flush()
            deadline = time.monotonic() + 5.0
            response_status = None
            total = 0
            while time.monotonic() < deadline:
                raw = transport.readline()
                total += len(raw)
                if total > 4096:
                    raise LabError("Modem APDU reply exceeded the allowed size.")
                line = raw.decode("ascii", errors="replace").strip()
                if not line or line == _SELECT_MF_COMMAND:
                    continue
                match = _CSIM_LINE.fullmatch(line)
                if match is not None:
                    hex_result = match.group(2).upper()
                    if int(match.group(1)) != len(hex_result) or len(hex_result) < 4 or len(hex_result) % 2:
                        raise LabError("Malformed APDU result length.")
                    response_status = hex_result[-4:]
                elif line == "OK":
                    if response_status is None:
                        raise LabError("Modem omitted the APDU card response.")
                    result = "ACCEPTED" if response_status == "9000" else "CARD_STATUS"
                    return Reading("APDU SELECT MF", result, "SW=" + response_status,
                                   "An APDU reply does not verify AKA or ISIM access")
                elif line == "ERROR" or line.startswith(("+CME ERROR", "+CMS ERROR")):
                    raise LabError("Modem refused the fixed APDU.")
            raise LabError("No complete APDU reply within five seconds.")
        except LabError:
            raise
        except Exception:
            raise LabError("APDU serial transport unavailable.") from None
    finally:
        transport.close()
