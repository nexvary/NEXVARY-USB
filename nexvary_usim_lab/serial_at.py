"""Shared framed AT receiver. Never logs raw data or retries commands.

An incomplete transaction poisons this connection: a late OK must not complete
another command. Reopen explicitly after reviewing the result. Serial leases
are owned by the caller, including during SMS prompt/body transactions.
"""
from collections import deque
from dataclasses import dataclass
import re
import time

ERROR_CODES = {
    'CME': {3:'العملية غير مسموحة حاليًا',10:'الشريحة غير موجودة',11:'الشريحة تطلب PIN',
            12:'الشريحة تطلب PUK',13:'تعذر الوصول إلى الشريحة',14:'الشريحة مشغولة',
            15:'الشريحة غير ملائمة للعملية',16:'كلمة المرور غير صحيحة',
            17:'الشريحة تطلب PIN2',18:'الشريحة تطلب PUK2',30:'لا توجد خدمة شبكة',
            100:'خطأ عام غير محدد'},
    'CMS': {302:'العملية غير مسموحة',303:'العملية غير مدعومة في هذا المسار',
            310:'الشريحة غير موجودة',311:'الشريحة تطلب PIN',312:'الشريحة تطلب PUK',
            313:'تعذر الوصول إلى الشريحة',314:'الشريحة مشغولة',
            320:'خطأ في ذاكرة الرسائل',321:'موضع ذاكرة غير صحيح',322:'ذاكرة الرسائل ممتلئة',
            331:'لا توجد خدمة شبكة',500:'خطأ عام غير محدد'}
}

def error_message(line):
    match = re.fullmatch(r'\+(CME|CMS) ERROR:\s*(\d{1,4})', line)
    if not match:
        return 'المودم رفض الأمر على المنفذ الحالي؛ لا يثبت عدم الدعم الدائم.'
    category, code = match[1], int(match[2])
    return f'{category} {code}: ' + ERROR_CODES[category].get(code,'رمز خطأ من المودم؛ يحتاج مراجعة التوافق')

@dataclass(repr=False)
class Reply:
    status: str
    lines: list
    stage: str
    error: str = ''
    def __repr__(self): return f'<AT Reply: {self.status}, {self.stage}; data private>'

class SerialAT:
    def __init__(self, wire):
        self.wire = wire
        self.buffer = bytearray()
        self.frames = deque()
        self.events = deque(maxlen=64)  # event type only, no identity/SMS/key material
        self.uncertain = False
        self.last = None
        self.echo = None
        self.first = True
        self.urc_body = False

    def command(self, command, duration=5, prompt=False, expected=None):
        if self.uncertain:
            return Reply('SESSION_UNCERTAIN', [], 'blocked', 'رد سابق غير مكتمل؛ أوقفنا الجلسة لمنع اختلاط الردود.')
        if not isinstance(command,str) or any(c in command for c in ('\r','\n','\x1a','\x00')):
            raise ValueError('Invalid AT command framing')
        if self.first:
            self.wire.reset_input_buffer()
            self.first = False
        # Any frames left after a final reply are unsolicited, never reply data.
        self.frames.clear(); self.buffer.clear()
        self.echo = command
        self.wire.write((command+'\r').encode('ascii'))
        self.wire.flush()
        if expected is None and command.startswith('AT+'):
            expected = '+' + command[3:].split('?')[0].split('=')[0] + ':'
        return self.receive(duration, prompt=prompt, expected=expected)

    def receive(self, duration=5, limit=32768, prompt=False, expected=None):
        deadline=time.monotonic()+duration
        lines=[];total=0;noise=0
        while time.monotonic()<deadline:
            if not self.frames:
                chunk=self.wire.readline()
                if not chunk:
                    continue
                total+=len(chunk)
                if total>limit:
                    return self._finish('NOISY',lines,'receive-limit')
                self.buffer.extend(chunk)
                if len(self.buffer)>4096:
                    return self._finish('MALFORMED',lines,'frame-limit')
                # readline may return a fragment or multiple lines on real drivers.
                while True:
                    match=re.search(rb'[\r\n]',self.buffer)
                    if not match:break
                    self.frames.append(bytes(self.buffer[:match.start()]))
                    del self.buffer[:match.end()]
                if prompt and bytes(self.buffer).strip()==b'>':
                    self.frames.append(b'>');self.buffer.clear()
                if not self.frames:continue
            line=self.frames.popleft().decode('ascii',errors='replace').strip()
            if not line or line==self.echo:continue
            if self.urc_body:
                self.urc_body=False;noise+=1;continue
            if line=='OK':return self._finish('OK',lines,'final')
            if line=='ERROR' or line.startswith(('+CME ERROR:', '+CMS ERROR:')):
                return self._finish('ERROR',lines,'final',error_message(line))
            if prompt and line=='>':return self._finish('PROMPT',lines,'prompt')
            urc=line.startswith(('^','%','+CMTI:', '+CMT:', '+CDS:', '+CREG:', '+CGREG:', '+CEREG:', '+CSSU:')) or line in ('RING','NO CARRIER')
            if urc and not (expected and line.startswith(expected)):
                self.events.append('UNSOLICITED');noise+=1
                self.urc_body=line.startswith(('+CMT:', '+CDS:'))
                continue
            lines.append(line[:1024])
            if len(lines)>200:return self._finish('NOISY',[],'line-limit')
        return self._finish('NOISY' if noise>512 else 'TIMEOUT',lines,
                            'partial' if lines or self.buffer else 'no-response')

    def _finish(self,status,lines,stage,error=''):
        if status not in ('OK','ERROR','PROMPT'):self.uncertain=True
        self.last=Reply(status,lines,stage,error)
        return self.last


def receiver(wire):
    engine=getattr(wire,'_nexvary_at_receiver',None)
    if engine is None:
        engine=SerialAT(wire)
        wire._nexvary_at_receiver=engine
    return engine
