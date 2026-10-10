"""Single complete PNG for a user-owned diagnostic report.

The image is an export of already collected, redacted results, never a new
device probe. Render all rows to an appropriately tall canvas so neither
window size nor table scroll position clips the evidence.
"""
from __future__ import annotations
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter
from .core import LabError, redact
from .presentation import NAMES, outcome, explain

_BG=QColor('#0C1319')
_PANEL=QColor('#13212D')
_ALT=QColor('#192B38')
_LINE=QColor('#536779')
_WHITE=QColor('#EFF4FA')
_MUTED=QColor('#C3CBD3')
_GOLD=QColor('#FFD176')
_GREEN=QColor('#39FF14')

def _friendly_detail(reading):
    """Bounded Arabic-first summary; never paste raw URCs, notes, AIDs or IDs."""
    from .core import registration_public
    from .presentation import explain
    import re
    name, status = reading.name, reading.status
    if status == "OK":
        if name == "Connection":
            return "نجح اتصال الأوامر بالمودم عبر قناة AT."
        if name in ("Manufacturer", "Model", "Firmware"):
            return redact(reading.value)
        if name == "SIM status":
            return explain(reading)
        if name == "Registration":
            value=registration_public(reading.value)
            found=re.search(r'\+CREG:\s*[0-5]\s*,\s*([0-5])',value)
            if found:
                state=int(found.group(1))
                return {0:'غير مسجل بالشبكة',1:'مسجل على الشبكة المحلية',
                        2:'جاري البحث عن شبكة',3:'رفضت الشبكة التسجيل',
                        4:'حالة التسجيل غير معروفة',5:'مسجل على شبكة تجوال'}.get(
                         state,'حالة التسجيل غير محسومة')+'؛ معرّفات موقع الخلية محجوبة.'
            return "اكتمل الاستعلام؛ معرّفات موقع الخلية محجوبة."
        if name == "Signal":
            match=re.search(r'\+CSQ:\s*(\d{1,2})\s*,\s*(\d{1,2})', reading.value)
            if match:
                return 'مؤشر الإشارة: '+match.group(1)+' من 31؛ مؤشر الأخطاء: '+match.group(2)+' (99 غير معروف).'
            return 'استجاب المودم لفحص الإشارة.'
        if name in ("ICCID","SIM EF ICCID"):
            return 'تمت قراءة معرّف الشريحة مع حجب الرقم حفاظًا على الخصوصية؛ لا يثبت AKA.'
        if name.endswith(" probe"):
            return 'نجح اختبار صيغة الأمر فقط؛ لا يثبت وصول APDU أو مصادقة USIM.'
    if name=="SIM applications" and any(x in reading.value.lower()
          for x in ("truncated sim tlv","malformed sim tlv","tlv غير مكتمل")):
        return 'ملف EF_DIR أعاد بنية TLV غير مكتملة؛ سبب اختلاف الطول غير محسوم، ولا يثبت غياب USIM.'
    if name=="SIM applications" and status in ('UNKNOWN','PARTIAL'):
        # A backend error may carry raw hexadecimal data; never echo it.
        return 'اكتشاف تطبيقات SIM/USIM غير مكتمل؛ لم يثبت وجودها أو غيابها.'
    if name=="SIM application" and status=="DECLARED":
        return 'تطبيق معلن في EF_DIR؛ لم تُثبت صلاحية الوصول أو AKA.'
    if name=="APDU SELECT MF" and reading.value=="SW=9000":
        return 'اختيار الملف الأساسي ناجح (SW=9000)؛ لا يثبت AKA.'
    if name.endswith(" access") and status=="SELECTED":
        return 'نجح اختيار التطبيق؛ لم تُنفذ مصادقة AKA.'
    return redact(explain(reading))

def snapshot_rows(report):
    """Report-wide disclosure-safe Arabic text with no raw modem notes."""
    if report is None:
        raise LabError('افحص الجهاز قبل حفظ صورة النتائج.')
    if len(report.readings)>128:
        raise LabError('تقرير الفحص كبير جدًا؛ احفظ JSON المنقح بدل الصورة.')
    return [(redact(NAMES.get(r.name,r.name)),outcome(r),_friendly_detail(r))
            for r in report.readings]

def complete_results_image(report, width=1440):
    """Render every reading into one PNG-ready image without viewport clipping."""
    if type(width) is not int or not 800<=width<=2500:
        raise LabError('عرض صورة النتائج غير صالح.')
    rows=snapshot_rows(report)
    margin=38
    x=margin
    inner=width-2*margin
    name_w=256
    state_w=174
    detail_w=inner-name_w-state_w
    body_font=QFont('Noto Sans Arabic',11)
    body_font.setPointSize(11)
    title_font=QFont('Noto Sans Arabic',20)
    title_font.setBold(True)
    small_font=QFont('Noto Sans Arabic',10)
    header_font=QFont('Noto Sans Arabic',12)
    header_font.setBold(True)
    fm=QFontMetrics(body_font)
    def row_height(name,state,detail):
        return max(52,
                   fm.boundingRect(QRect(0,0,name_w-26,50000),
                       Qt.TextWordWrap | Qt.AlignRight,name).height()+24,
                   fm.boundingRect(QRect(0,0,detail_w-30,50000),
                       Qt.TextWordWrap | Qt.AlignRight,detail).height()+24)
    heights=[row_height(*r) for r in rows]
    header_h=172
    column_h=52
    footer_h=84
    total=header_h+column_h+sum(heights)+footer_h
    if total>26000:
        raise LabError('صورة التقرير تتجاوز الحد الآمن؛ احفظ JSON المنقح.')
    image=QImage(width,total,QImage.Format_ARGB32)
    image.fill(_BG)
    painter=QPainter(image)
    try:
        painter.setRenderHint(QPainter.Antialiasing,True)
        painter.setFont(title_font);painter.setPen(_WHITE)
        painter.drawText(QRect(x,19,inner,49),Qt.AlignRight|Qt.AlignVCenter,
                         'NEXVARY USB Studio — نتائج الفحص')
        painter.setFont(small_font);painter.setPen(_MUTED)
        desc='الجهاز / المنفذ: '+redact(report.device)+'     |     الإصدار: '+redact(report.version)
        painter.drawText(QRect(x,74,inner,30),Qt.AlignRight|Qt.AlignVCenter,desc)
        painter.setPen(_GOLD)
        notice=('محاكاة — ليست نتيجة جهاز فعلي' if report.simulated
                else 'نتائج محلية من جهاز فعلي — لا تثبت AKA أو IMS أو المكالمات')
        painter.drawText(QRect(x,111,inner,37),Qt.AlignRight|Qt.AlignVCenter,notice)
        y=header_h
        painter.fillRect(QRect(x,y,inner,column_h),_PANEL)
        painter.setFont(header_font);painter.setPen(_WHITE)
        painter.drawText(QRect(x+name_w+state_w+12,y,detail_w-22,column_h),
                         Qt.AlignRight|Qt.AlignVCenter,'النتيجة والتفسير')
        painter.drawText(QRect(x+name_w+8,y,state_w-18,column_h),
                         Qt.AlignRight|Qt.AlignVCenter,'الحالة')
        painter.drawText(QRect(x+8,y,name_w-18,column_h),
                         Qt.AlignRight|Qt.AlignVCenter,'الفحص')
        y+=column_h
        painter.setFont(body_font)
        for i,((name,state,detail),h) in enumerate(zip(rows,heights)):
            painter.fillRect(QRect(x,y,inner,h),_ALT if i%2 else _PANEL)
            painter.setPen(_LINE)
            painter.drawLine(x,y+h-1,x+inner,y+h-1)
            painter.drawLine(x+name_w,y,x+name_w,y+h)
            painter.drawLine(x+name_w+state_w,y,x+name_w+state_w,y+h)
            painter.setPen(_WHITE)
            painter.drawText(QRect(x+12,y+7,name_w-24,h-14),
                             Qt.AlignRight|Qt.AlignVCenter|Qt.TextWordWrap,name)
            painter.setPen(_GREEN if state=='ناجح' else _GOLD if state in
                           ('غير محسوم','غير مختبر','يحتاج تدخل المستخدم') else QColor('#F49BA8'))
            painter.drawText(QRect(x+name_w+8,y+6,state_w-16,h-12),
                             Qt.AlignRight|Qt.AlignVCenter|Qt.TextWordWrap,state)
            painter.setPen(_WHITE)
            painter.drawText(QRect(x+name_w+state_w+13,y+6,detail_w-25,h-12),
                             Qt.AlignRight|Qt.AlignVCenter|Qt.TextWordWrap,detail)
            y+=h
        painter.setFont(small_font);painter.setPen(_MUTED)
        painter.drawText(QRect(x,y+12,inner,28),Qt.AlignRight|Qt.AlignVCenter,
                         'صورة واحدة تشمل جميع الصفوف؛ بيانات الشريحة وأسرار المصادقة منقحة.')
        painter.drawText(QRect(x,y+42,inner,27),Qt.AlignRight|Qt.AlignVCenter,
                         'لا ترسل الصورة إلى جهة غير موثوقة قبل مراجعة محتواها.')
    finally:
        painter.end()
    return image
