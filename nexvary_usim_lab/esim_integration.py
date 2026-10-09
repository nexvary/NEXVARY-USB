"""Offline contract with reviewed com.nexvary.simmanager 0.922.0.

No provisioning, network API, persistence or arbitrary APDU exposure.
Activation credentials are intentionally excluded from repr and diagnostics.
"""
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import re

APK_IDENTITY = {
    'package': 'com.nexvary.simmanager', 'version': '0.922.0',
    'sha256': '96605bb924f749b8ed180129d96d8c6f987d23c6221592bebd67f724ca488320',
    'integration': 'offline LPA QR and phone-exported CSV',
}

class IntegrationError(ValueError):
    """Secret-free user-facing validation error."""

@dataclass(frozen=True)
class Activation:
    smdp_address: str
    confirmation_required: bool
    matching_id_present: bool
    _normalized: str = field(repr=False)

    def qr_payload(self):
        """Explicit foreground handoff only; never pass to logs/reports."""
        return self._normalized

    def summary(self):
        return {'smdp_address': self.smdp_address,
                'matching_id': 'محجوب' if self.matching_id_present else 'غير موجود',
                'confirmation_required': self.confirmation_required,
                'provisioning_verified': False}


def parse_activation(text: str) -> Activation:
    if not isinstance(text, str) or len(text) > 4096:
        raise IntegrationError('طول كود التفعيل غير صالح')
    text = text.strip()
    if text[:4].lower() == 'lpa:':
        normalized = 'LPA:' + text[4:]
    elif text.startswith('1$'):
        normalized = 'LPA:' + text
    else:
        raise IntegrationError('أدخل كود LPA يبدأ بـ LPA:1$ أو 1$')
    if not 7 <= len(normalized) <= 2048:
        raise IntegrationError('طول كود التفعيل غير صالح')
    parts = normalized[4:].split('$')
    if not 3 <= len(parts) <= 5 or parts[0] != '1':
        raise IntegrationError('صيغة كود التفعيل غير مدعومة')
    # Match the reviewed Android parser; no request is made to this address.
    host, matching = parts[1].strip(), parts[2].strip()
    if not host or len(host) > 255 or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,253}[A-Za-z0-9])?', host):
        raise IntegrationError('عنوان SM-DP+ غير صالح')
    if len(matching) > 1024 or (matching and not re.fullmatch(r'[A-Z0-9-]+', matching)):
        raise IntegrationError('معرّف التفعيل غير صالح لهذا الإصدار من تطبيق الهاتف')
    oid = parts[3].strip() if len(parts) >= 4 else ''
    if oid and (len(oid) > 128 or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)+', oid)):
        raise IntegrationError('معرّف SM-DP+ OID غير صالح')
    flag = parts[4].strip() if len(parts) == 5 else ''
    if flag not in ('', '0', '1'):
        raise IntegrationError('علامة طلب رمز التأكيد غير صالحة')
    # Android normalizes scheme and trims each field for validation, retaining
    # the original payload; preserve it for exact QR handoff interoperability.
    return Activation(host, flag == '1', bool(matching), normalized)


def qr_png(activation: Activation) -> bytes:
    import qrcode
    from qrcode.exceptions import DataOverflowError
    try:
        code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                             box_size=6, border=4)
        code.add_data(activation.qr_payload()); code.make(fit=True)
        output = BytesIO()
        code.make_image(fill_color='black', back_color='white').save(output, format='PNG')
        return output.getvalue()
    except DataOverflowError:
        raise IntegrationError('الكود أطول من سعة QR؛ استخدم مشاركة النص في الهاتف') from None


def read_qr(path: str | Path) -> Activation:
    from PIL import Image, UnidentifiedImageError
    import zxingcpp
    file = Path(path)
    if not file.is_file() or file.stat().st_size > 8 * 1024 * 1024:
        raise IntegrationError('اختر صورة QR محلية لا تتجاوز 8 ميغابايت')
    try:
        with Image.open(file) as image:
            if image.width * image.height > 16_000_000:
                raise IntegrationError('أبعاد صورة QR أكبر من الحد المسموح')
            decoded = zxingcpp.read_barcodes(image.convert('RGB'), formats=zxingcpp.BarcodeFormat.QRCode)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise IntegrationError('تعذر قراءة صورة QR') from None
    if len(decoded) != 1 or not decoded[0].valid:
        raise IntegrationError('يجب أن تحتوي الصورة على QR واحد صالح')
    return parse_activation(decoded[0].text)


def read_recycling_csv(path: str | Path) -> list[dict]:
    """Import only the four non-subscriber fields exported by APK 0.922.0.

    Origin is phone-reported, never a Windows hardware observation.
    Unknown schema, executable spreadsheet formulas and extra IDs are rejected.
    """
    import csv
    from io import StringIO
    file = Path(path)
    if not file.is_file() or file.stat().st_size > 1024 * 1024:
        raise IntegrationError('اختر تقرير CSV لا يتجاوز ميغابايت واحدًا')
    try:
        content = file.read_bytes().decode('utf-8-sig')
        reader = csv.DictReader(StringIO(content), strict=True)
        if reader.fieldnames != ['batch', 'quantity', 'classification', 'condition_score']:
            raise IntegrationError('صيغة التقرير لا تطابق تقرير تطبيق الهاتف 0.922.0')
        records = []
        seen = set()
        for row in reader:
            if len(records) >= 10000 or None in row or any(v is None for v in row.values()):
                raise IntegrationError('عدد السجلات أو أعمدة التقرير غير صالح')
            def number(key, upper):
                value = row[key]
                if not re.fullmatch(r'[0-9]{1,9}', value) or int(value) > upper:
                    raise IntegrationError('قيمة رقمية غير صالحة في التقرير')
                return int(value)
            batch = number('batch', 999999999)
            quantity = number('quantity', 999999999)
            score = number('condition_score', 100)
            classification = row['classification']
            if classification not in ('LAB_REUSE', 'MATERIAL_RECYCLE', 'HOLD_FOR_RECHECK'):
                raise IntegrationError('تصنيف غير صالح في التقرير')
            if batch in seen:
                raise IntegrationError('رقم دفعة مكرر في التقرير')
            seen.add(batch)
            records.append(dict(batch=batch, quantity=quantity, classification=classification,
                                condition_score=score, evidence='phone_reported_not_hardware_verified'))
        return records
    except (UnicodeError, csv.Error, OSError):
        raise IntegrationError('تعذر قراءة تقرير الهاتف') from None
