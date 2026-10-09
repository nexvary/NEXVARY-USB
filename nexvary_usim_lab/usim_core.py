"""NEXVARY USIM Core: local, consented, bounded read-only capability inspection.

No arbitrary APDU API, subscriber EF reads, authentication or mutations here.
Actual authentication remains in the separately authorized ModemUsimBackend.
"""
import re
from .core import LabError, Reading
from .device_operations import ATSession
from .sim_inspector import applications

class ApduFailure(LabError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status

STATUS = {
    '9000': 'تم تنفيذ الأمر بنجاح؛ لا يثبت AKA.',
    '6A86': 'معلمات SELECT غير مقبولة في هذا المسار.',
    '6A82': 'التطبيق أو الملف غير متاح في هذا المسار؛ لا يثبت غيابه عن البطاقة.',
    '6982': 'شروط الأمان أو صلاحيات الوصول غير مستوفاة.',
    '6985': 'حالة البطاقة الحالية لا تسمح بهذا الأمر.',
    '6D00': 'تعليمة APDU غير مقبولة في المسار الحالي.',
    '6E00': 'فئة APDU غير مقبولة في المسار الحالي.',
}

def status_message(sw):
    return STATUS.get(sw, 'أعادت البطاقة حالة غير ناجحة؛ احتفظ بالرمز لتشخيص التوافق.')

class ApplicationTransport:
    """Only fixed SELECT(AID) and GET RESPONSE; cannot transmit caller APDUs."""
    def __init__(self, session):
        self.session = session

    def _exchange(self, apdu):
        state, lines = self.session._command(f'AT+CSIM={len(apdu)},"{apdu}"', 6)
        if state == 'TIMEOUT':
            raise ApduFailure('TIMEOUT', 'لم يكتمل رد المودم؛ لم نعد إرسال الأمر ولم نستنتج عدم الدعم.')
        if state != 'OK':
            raise ApduFailure('MODEM_ERROR', 'المودم رفض قناة CSIM؛ لا توجد نتيجة من البطاقة.')
        matches = [re.fullmatch(r'\+CSIM:\s*(\d+)\s*,\s*"([A-Fa-f0-9]+)"', x)
                   for x in lines if x.startswith('+CSIM:')]
        if len(matches) != 1 or matches[0] is None:
            raise ApduFailure('MALFORMED', 'استجابة CSIM غير صحيحة؛ لم نعتبر OK دليل نجاح.')
        m = matches[0]
        raw = m[2]
        if int(m[1]) != len(raw) or len(raw) % 2 or not 4 <= len(raw) <= 520:
            raise ApduFailure('MALFORMED', 'طول استجابة CSIM غير مطابق.')
        return bytes.fromhex(raw)

    def select_application(self, aid):
        if not isinstance(aid, str) or not re.fullmatch(r'A000000087100[24][A-Fa-f0-9]{0,18}', aid) or len(aid) % 2:
            raise LabError('يسمح بفحص AID كامل لتطبيق USIM/ISIM فقط.')
        # SELECT by DF name, FCP requested. No retry of SELECT or any AUTH command.
        reply = self._exchange('00A40404' + f'{len(aid)//2:02X}' + aid.upper() + '00')
        total = 0
        for _ in range(4):
            total += len(reply) - 2
            if total > 1024:
                raise ApduFailure('MALFORMED', 'تجاوز الرد حد بيانات FCP.')
            sw = reply[-2:]
            if sw[0] in (0x61, 0x9F):
                reply = self._exchange('00C00000' + f'{sw[1]:02X}')
                # Length correction only for GET RESPONSE, once, never AUTHENTICATE.
                if reply[-2] == 0x6C:
                    reply = self._exchange('00C00000' + f'{reply[-1]:02X}')
                continue
            value = sw.hex().upper()
            if value != '9000':
                raise ApduFailure('CARD_STATUS', 'SW=' + value + ': ' + status_message(value))
            return 'SW=9000'
        raise ApduFailure('CONTINUATION_LIMIT', 'رد البطاقة يحتاج متابعة تجاوزت الحد الآمن؛ أوقفنا الفحص.')

class NexvaryUsimCore:
    def __init__(self, port, factory=None):
        self.port, self.factory = port, factory

    def inspect(self, consent=False):
        if not consent:
            raise LabError('قراءة التطبيقات واختبار الوصول يحتاجان موافقة محلية صريحة.')
        # Discover before SELECT; never guess a USIM AID or imply AKA readiness.
        try:
            declared = applications(self.port, factory=self.factory)
        except LabError as exc:
            return [Reading('SIM applications', getattr(exc, 'status', 'UNKNOWN'), str(exc),
                            'لم نثبت غياب USIM أو ISIM أو أهلية المشغل.')]
        result = list(declared)
        candidates = [r for r in declared if r.status == 'DECLARED']
        if candidates:
            with ATSession(self.port, factory=self.factory) as session:
                transport = ApplicationTransport(session)
                for row in candidates[:8]:
                    name, aid = row.value.split(' / AID ', 1)
                    try:
                        value = transport.select_application(aid)
                        result.append(Reading(name + ' access', 'SELECTED', value,
                                             'نجح اختيار التطبيق عبر CSIM؛ AUTHENTICATE لم يُرسل، وAKA غير مثبت.'))
                    except ApduFailure as exc:
                        result.append(Reading(name + ' access', exc.status, str(exc),
                                             'إعلان EF_DIR منفصل عن صلاحية الوصول والمصادقة.'))
                        if exc.status in ('TIMEOUT', 'MALFORMED', 'CONTINUATION_LIMIT'):
                            break  # Never continue on uncertain modem/card session state.
        result.append(Reading('USIM AKA', 'UNVERIFIED', 'لم تنفذ مصادقة على الشريحة في هذا الفحص',
                              'تحتاج تحديًا مصرحًا به ونجاح Backend؛ IMS/ePDG والمكالمات تحقق مستقل.'))
        return result
