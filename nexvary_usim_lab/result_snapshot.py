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

def snapshot_rows(report):
    """User-visible, redacted text, deliberately omitting raw modem payload."""
    if report is None:
        raise LabError('افحص الجهاز قبل حفظ صورة النتائج.')
    if len(report.readings)>128:
        raise LabError('تقرير الفحص كبير جدًا؛ احفظ JSON المنقح بدل الصورة.')
    result=[]
    for r in report.readings:
        title=redact(NAMES.get(r.name,r.name))
        state=outcome(r)
        detail=redact(explain(r))
        # Technical response and note can explain a mismatch; mask all IDs.
        extra=redact(r.value)
        if extra and extra!=detail and extra not in detail:
            detail=detail+'   |   '+extra
        if r.note and r.name not in ('ICCID',):
            note=redact(r.note)
            if note not in detail and len(detail)+len(note)<750:
                detail += '   |   '+note
        result.append((title,state,detail))
    return result

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
