"""Arabic user-facing explanations; exports retain original evidence and codes."""
from .core import Reading

NAMES = {
    "Connection":"اتصال AT", "Manufacturer":"الشركة المصنعة",
    "Model":"الموديل", "Firmware":"إصدار Firmware",
    "SIM status":"حالة الشريحة", "ICCID":"معرّف الشريحة",
    "Signal":"قوة الإشارة", "Registration":"التسجيل بالشبكة",
    "CSIM probe":"اختبار صيغة CSIM",
    "CRSM probe":"اختبار صيغة CRSM",
    "CGLA probe":"اختبار صيغة CGLA",
    "CCHO probe":"اختبار صيغة CCHO",
    "SIM applications":"تطبيقات SIM/USIM",
    "SIM application":"تطبيق SIM",
    "SIM EF ICCID":"ملف EF-ICCID",
    "APDU SELECT MF":"اختيار الملف MF",
}
STATUS = {
    "OK":"استجاب", "READABLE":"نجحت القراءة",
    "ACCEPTED":"قُبل الأمر", "DECLARED":"مُعلن",
    "REJECTED":"رُفض الأمر", "UNSUPPORTED":"رُفض الأمر",
    "TIMEOUT":"انتهت المهلة", "MODEM_ERROR":"خطأ عبر المودم",
    "IO_ERROR":"انقطاع الاتصال", "CARD_STATUS":"حالة البطاقة",
    "UNKNOWN":"غير محسوم", "NOISY":"تشويش بالمنفذ",
    "NOT_TESTED":"غير مختبر", "UNAVAILABLE":"غير متاح",
}
EXPLAIN = {
    "REJECTED":"رفض المودم هذا الأمر في الجلسة الحالية. لا يثبت أن الشريحة أو الموديل غير مدعومين.",
    "UNSUPPORTED":"رفض المودم هذا الأمر على المنفذ الحالي؛ لا يمكن الحكم بعدم الدعم من هذه النتيجة.",
    "TIMEOUT":"لم يصل رد مكتمل خلال المهلة. لا يعني ذلك أن الشريحة تالفة.",
    "IO_ERROR":"تعذر التواصل مع المنفذ. راجع توصيل USB والبرامج التي قد تستخدمه.",
    "MODEM_ERROR":"المودم رفض الوصول المطلوب؛ لا يثبت غياب تطبيق USIM أو ISIM.",
    "NOISY":"استقبل البرنامج إشعارات كثيرة دون رد يمكن اعتماده.",
}

def ui_reading(reading: Reading):
    if reading.status in EXPLAIN:
        value = EXPLAIN[reading.status]
    elif reading.name in ("CSIM probe", "CRSM probe", "CGLA probe", "CCHO probe") and reading.status == "OK":
        value = "استجاب المودم لاختبار الصيغة فقط؛ لم تثبت قراءة APDU أو مصادقة AKA."
    else:
        value = reading.value + (" — " + reading.note if reading.note else "")
    return (NAMES.get(reading.name, reading.name), STATUS.get(reading.status, "غير محسوم"), value)
