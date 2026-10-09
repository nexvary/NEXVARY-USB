"""Owner-operated modem functions with bounded AT operations.

No raw AT terminal is exposed to the UI. The API restricts card commands to
known read-only files/SELECT and requires explicit, foreground SMS confirmation.
No service listens on the network and no SIM credentials are retrieved.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Callable

from .core import LabError, Reading, _open_serial, redact
from .coordination import lease

ICCID_FILE = "AT+CRSM=176,12258,0,0,10"
_IMSI_PATTERN = re.compile(r"(?<!\d)\d{12,22}(?!\d)")
_CRSM_RESULT = re.compile(r'^\+CRSM:\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*"?([A-Fa-f0-9]*)"?)?$')
_E164 = re.compile(r"^\+[1-9]\d{6,14}$")
_SMS_RECORD = re.compile(r'^\+CMGL:\s*(\d+),\s*"([^"]*)",\s*"([^"]*)".*$')
_FINAL_ERROR = ("ERROR", "+CME ERROR", "+CMS ERROR")

def mask_identifier(value: str) -> str:
    """Mask identifiers, including 10/11-digit telephone numbers in inbox."""
    return re.sub(r"(?<!\d)\+?\d{7,22}(?!\d)",
                  lambda m: "*" * (len(m.group())-4) + m.group()[-4:],
                  value)

def _parse_crsm(lines: list[str]) -> Reading:
    for line in lines:
        m = _CRSM_RESULT.match(line.strip())
        if not m:
            continue
        sw1, sw2, raw = int(m.group(1)), int(m.group(2)), m.group(3) or ""
        if sw1 == 144 and sw2 == 0:
            # Never expose complete ICCID hex in diagnostic reports.
            return Reading("SIM EF ICCID", "READABLE",
                           "READ access confirmed; card data suppressed",
                           "File 2FE2 reached through AT+CRSM without PIN or modification")
        return Reading("SIM EF ICCID", "CARD_STATUS",
                       f"SW={sw1:02X}{sw2:02X}",
                       "Card returned a non-success status; no mutation")
    return Reading("SIM EF ICCID", "UNSUPPORTED",
                   "No valid CRSM response", "The modem may lack access to this file")

class ATSession:
    def __init__(self, port: str, factory: Callable | None = None, speed: int = 115200):
        if not isinstance(port, str) or not re.fullmatch(r"(?:COM[1-9]\d{0,3}|/dev/[A-Za-z0-9/_-]{4,100})", port, re.I):
            raise LabError("Invalid local COM/serial path.")
        self.port = port
        self._factory = factory or _open_serial
        self._speed = speed
        self._wire = None
        self.events = []

    def __enter__(self):
        self._lease = lease(self.port)
        self._lease.__enter__()
        try:
            self._wire = self._factory(self.port, self._speed)
        except Exception:
            self._lease.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._wire is not None:
                self._wire.close()
                self._wire = None
        finally:
            self._lease.__exit__(exc_type, exc, tb)

    def _write(self, bytes_: bytes):
        if self._wire is None:
            raise LabError("AT session not open")
        self._wire.write(bytes_)
        self._wire.flush()

    def _read(self, duration: float = 5, limit: int = 32768, prompt: bool = False, expected: str | None = None) -> tuple[str,list[str]]:
        deadline = time.monotonic() + duration
        lines = []
        total = 0
        urc_body = False
        while time.monotonic() < deadline:
            chunk = self._wire.readline()
            if not chunk:
                continue
            total += len(chunk)
            if total > limit:
                raise LabError("Modem response exceeded the safety limit.")
            line = chunk.decode("ascii", errors="replace").strip()
            if not line:
                continue
            if urc_body:
                urc_body = False
                continue
            if prompt and ">" in line:
                return "PROMPT", lines
            if line == "OK":
                return "OK", lines
            if line == "ERROR" or line.startswith(("+CME ERROR", "+CMS ERROR")):
                return "ERROR", lines
            unsolicited = line.startswith(('^', '%', '+CMTI:', '+CMT:', '+CDS:', '+CREG:', '+CGREG:', '+CEREG:', '+CSSU:'))
            if unsolicited and not (expected and line.startswith(expected)):
                if len(self.events) < 64:
                    self.events.append('UNSOLICITED')  # no raw event content retained
                urc_body = line.startswith(('+CMT:', '+CDS:'))
                continue
            lines.append(line[:1024])
            if len(lines) > 200:
                raise LabError("Unbounded modem traffic.")
        return "TIMEOUT", lines

    def _command(self, command: str, duration: float = 5, prompt: bool = False) -> tuple[str,list[str]]:
        if "\r" in command or "\n" in command or "\x1a" in command:
            raise LabError("AT command contains control characters.")
        self._wire.reset_input_buffer()
        self._write((command+"\r").encode("ascii"))
        expected = command.split("?")[0].split("=")[0][2:] + ":" if command.startswith("AT+") else None
        return self._read(duration, prompt=prompt, expected=expected)

    def sim_file_check(self) -> Reading:
        state, _ = self._command("AT", 3)
        if state != "OK":
            raise LabError("AT channel is not responsive.")
        state, lines = self._command(ICCID_FILE, 6)
        if state == "ERROR":
            return Reading("SIM EF ICCID", "UNSUPPORTED", "Modem rejected read-only CRSM",
                           "No secret or mutating command sent")
        if state == "TIMEOUT":
            return Reading("SIM EF ICCID", "TIMEOUT", "No complete modem response",
                           "Cannot infer whether EF is supported")
        return _parse_crsm(lines)

    def signal(self) -> Reading:
        state, lines = self._command("AT+CSQ", 4)
        csq = next((re.search(r"^\+CSQ:\s*(\d{1,2}),(\d{1,2})", line) for line in lines
                    if line.startswith("+CSQ:")), None)
        if state == "OK" and csq:
            rssi = int(csq.group(1))
            dBm = f"{-113+2*rssi} dBm" if 0 <= rssi <= 31 else "not known"
            return Reading("Signal", "OK", f"RSSI {rssi}/31 ({dBm})", "Network signal, not SIM APDU capability")
        return Reading("Signal", state, "Signal query unavailable", "Read-only")

    def inbox(self, max_messages: int = 30) -> list[dict[str,str]]:
        """PDU receive path; preserves modem mode and masks addresses locally."""
        from .pdu import deliver
        if type(max_messages) is not int or not 1 <= max_messages <= 100:
            raise LabError('Invalid SMS message count.')
        state, lines = self._command('AT+CMGF?', 4)
        mode = next((re.fullmatch(r'\+CMGF:\s*([01])', x) for x in lines if x.startswith('+CMGF:')), None)
        if state != 'OK' or not mode:
            raise LabError('تعذر حفظ وضع الرسائل الحالي؛ لم يتغير شيء.')
        original = mode.group(1)
        try:
            state, _ = self._command('AT+CMGF=0', 4)
            if state != 'OK': raise LabError('المودم لا يدعم قراءة PDU؛ اختر قراءة Text القديمة.')
            state, lines = self._command('AT+CMGL=4', 15)
            if state != 'OK': raise LabError('لم تكتمل قراءة صندوق PDU.')
            data=[]; pending=None
            for line in lines:
                match=re.fullmatch(r'\+CMGL:\s*(\d+),\s*([0-4]),.*?,\s*(\d+)',line)
                if match:
                    pending=match.groups();continue
                if pending and re.fullmatch('[A-Fa-f0-9]+',line):
                    index,status,length=pending;pending=None
                    if status not in ('0','1'):continue
                    try:
                        decoded=deliver(line,int(length));part=decoded['part']
                        state_text='REC UNREAD' if status=='0' else 'REC READ'
                        if part:state_text+=f" — جزء {part['sequence']}/{part['total']}"
                        data.append(dict(index=index,status=state_text,sender=mask_identifier(decoded['sender']),preview=decoded['text'][:150]))
                    except LabError:
                        data.append(dict(index=index,status='PDU غير مدعوم أو تالف',sender='—',preview='لم نفترض نص الرسالة.'))
                    if len(data)>=max_messages:break
            return data
        finally:
            state,_=self._command('AT+CMGF='+original,4)
            if state!='OK':raise LabError('تعذر استعادة وضع الرسائل؛ افحص إعدادات المودم.')

    def text_inbox(self, max_messages: int = 30) -> list[dict[str,str]]:
        """Local read of received SMS, never included in general reports."""
        if not 1 <= max_messages <= 100:
            raise LabError("Invalid SMS message count.")
        state, _ = self._command("AT+CMGF=1", 4)
        if state != "OK":
            raise LabError("Modem does not support text SMS mode.")
        state, lines = self._command('AT+CMGL="ALL"', 15)
        if state == "ERROR":
            raise LabError("Inbox cannot be read on this modem.")
        if state != "OK":
            raise LabError("SMS list timed out.")
        data = []
        current = None
        for line in lines:
            m = _SMS_RECORD.match(line)
            if m:
                if current and current["status"].startswith("REC"):
                    data.append(current)
                current = {"index": m.group(1), "status": m.group(2),
                           "sender": mask_identifier(redact(m.group(3)))[:45],
                           "preview": ""}
            elif current and line and not line.startswith("AT+"):
                current["preview"] = (current["preview"] + " " + line).strip()[:150]
        if current and current["status"].startswith("REC"):
            data.append(current)
        return data[:max_messages]

    def send_sms(self, number: str, body: str, confirmed: bool = False) -> str:
        """Single foreground user-confirmed SMS; never batch or auto-send.

        Restricts text mode to printable ASCII to avoid claiming untested
        Arabic UCS2 support on firmware-specific Huawei variants. This will
        be extended only after independent modem validation.
        """
        if not confirmed:
            raise LabError("Sending SMS requires explicit foreground user confirmation.")
        if not isinstance(number,str) or not _E164.fullmatch(number):
            raise LabError("Use an international number such as +201XXXXXXXXX.")
        if not isinstance(body, str) or not 1 <= len(body) <= 160:
            raise LabError("SMS length must be 1–160 characters.")
        if any(ord(x) < 32 or ord(x) > 126 for x in body):
            raise LabError("This modem profile currently sends printable English/ASCII only.")
        state, _ = self._command("AT", 3)
        if state != "OK":
            raise LabError("Modem did not answer AT.")
        state, _ = self._command("AT+CMGF=1", 4)
        if state != "OK":
            raise LabError("Modem does not support text SMS mode.")
        state, _ = self._command('AT+CSCS="GSM"', 4)
        if state != "OK":
            raise LabError("Modem rejected GSM text character set.")
        state, _ = self._command(f'AT+CMGS="{number}"', 10, prompt=True)
        if state != "PROMPT":
            raise LabError("SMS modem never issued the input prompt; nothing sent.")
        self._write(body.encode("ascii") + b"\x1a")
        state, lines = self._read(35)
        if state != "OK":
            raise LabError("SMS submission not confirmed. Do not retry until checking messages.")
        matched = next((re.search(r"\+CMGS:\s*(\d+)",line) for line in lines
                        if "+CMGS:" in line), None)
        if not matched:
            raise LabError("Modem returned OK without SMS reference; delivery is unverified.")
        return f"SMS submitted to modem (reference {matched.group(1)}); delivery not guaranteed."

    def send_ucs2_sms(self, number, body, confirmed=False, experimental_consent=False):
        from .sms import ucs2_submit
        if not confirmed or not experimental_consent:
            raise LabError('إرسال UCS2 يحتاج موافقة صريحة على اختبار غير مثبت على هذا المودم.')
        pdu, length = ucs2_submit(number, body)
        # Preserve and restore the SMS mode even after submission failure.
        state, lines = self._command('AT+CMGF?', 4)
        match = next((re.fullmatch(r'\+CMGF:\s*([01])', x) for x in lines if x.startswith('+CMGF:')), None)
        if state != 'OK' or not match:
            raise LabError('لا يمكن حفظ وضع الرسائل الحالي؛ لم نرسل شيئًا.')
        original = match.group(1)
        try:
            state, _ = self._command('AT+CMGF=0', 4)
            if state != 'OK': raise LabError('المودم رفض وضع SMS PDU.')
            state, _ = self._command(f'AT+CMGS={length}', 10, prompt=True)
            if state != 'PROMPT': raise LabError('لم يظهر طلب إدخال SMS؛ لم نرسل شيئًا.')
            self._write(pdu.encode('ascii') + b'\x1a')
            state, lines = self._read(35)
            ref = next((re.fullmatch(r'\+CMGS:\s*(\d+)', x) for x in lines if x.startswith('+CMGS:')), None)
            if state != 'OK' or not ref:
                raise LabError('نتيجة إرسال UCS2 غير مؤكدة؛ افحص صندوق الرسائل قبل إعادة الإرسال.')
            return f'أُرسلت للمودم، المرجع {ref.group(1)}؛ التسليم ودعم الجهاز لم يُثبتا.'
        finally:
            restore, _ = self._command('AT+CMGF=' + original, 4)
            if restore != 'OK':
                raise LabError('تعذر استعادة وضع الرسائل؛ نتيجة الإرسال قد تكون غير مؤكدة. لا تعاود الإرسال تلقائيًا.')

    def network_info(self):
        rows=[]
        for name, command in (('الإشارة','AT+CSQ'),('التسجيل','AT+CREG?'),
                              ('تسجيل البيانات','AT+CGREG?'),('المشغل','AT+COPS?'),
                              ('إعدادات APN','AT+CGDCONT?'),('حالة البيانات','AT+CGACT?')):
            state, lines=self._command(command,5)
            prefix=command.split('?')[0][2:]+':'
            values=[redact(x) for x in lines if x.startswith(prefix)]
            rows.append(Reading(name,state,' | '.join(values) or 'لم تتوفر بيانات','استعلام قراءة فقط؛ لا يغيّر الاتصال'))
        return rows

    def set_apn(self, cid, apn, confirmed=False):
        if not confirmed: raise LabError('تغيير APN يحتاج موافقة صريحة.')
        if type(cid) is not int or not 1<=cid<=16 or not isinstance(apn,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,99}',apn):
            raise LabError('قيمة APN أو السياق غير صحيحة.')
        state, lines=self._command('AT+CGACT?',4)
        active={int(m.group(1)):int(m.group(2)) for x in lines if (m:=re.fullmatch(r'\+CGACT:\s*(\d+)\s*,\s*([01])',x))}
        if state!='OK' or cid not in active or active[cid]:
            raise LabError('يجب إثبات أن سياق البيانات غير نشط قبل تعديل APN.')
        state,_=self._command(f'AT+CGDCONT={cid},"IP","{apn}"',5)
        if state!='OK': raise LabError('لم يؤكد المودم تغيير APN؛ أعد قراءة الإعدادات.')
        state,lines=self._command('AT+CGDCONT?',5)
        pattern=rf'^\+CGDCONT:\s*{cid},\s*"IP",\s*"{re.escape(apn)}"(?:,|$)'
        if state!='OK' or not any(re.search(pattern,x) for x in lines):
            raise LabError('تغيير APN غير مثبت بالقراءة اللاحقة.')
        return 'تم تأكيد APN بالقراءة اللاحقة؛ لم يُشغّل اتصال بيانات.'
