"""Arabic public result presentation, separate from protocol status codes."""
NAMES={'Connection':'الاتصال بالمودم','Manufacturer':'الشركة المصنعة','Model':'الموديل',
       'Firmware':'إصدار البرنامج الداخلي','SIM status':'حالة الشريحة','ICCID':'رقم الشريحة المنقح',
       'Signal':'الإشارة','Registration':'التسجيل في الشبكة','CSIM probe':'فحص صيغة CSIM',
       'CGLA probe':'فحص صيغة CGLA','CCHO probe':'فحص صيغة CCHO','CRSM probe':'فحص صيغة CRSM',
       'SIM EF ICCID':'ملف رقم الشريحة','SIM applications':'تطبيقات الشريحة',
       'SIM application':'تطبيق معلن','APDU SELECT MF':'اختيار الملف الأساسي','USIM AKA':'مصادقة USIM AKA'}
SUCCESS={'OK','READABLE','SELECTED'}
FAIL={'ERROR','REJECTED','IO_ERROR','MODEM_ERROR','MALFORMED','CARD_STATUS','NOISY'}

def outcome(reading):
    if reading.name=='SIM status' and reading.status=='OK' and reading.value!='+CPIN: READY': return 'يحتاج تدخل المستخدم'
    if reading.status in SUCCESS: return 'ناجح'
    if reading.status=='ACCEPTED':return 'ناجح' if reading.value=='SW=9000' else 'غير محسوم'
    if reading.status in FAIL:return 'فشل'
    if reading.status=='NEEDS_USER':return 'يحتاج تدخل المستخدم'
    if reading.status in ('UNVERIFIED','NOT_TESTED'):return 'غير مختبر'
    return 'غير محسوم'

def explain(reading):
    state=reading.status
    if state in ('REJECTED','MODEM_ERROR','ERROR'):
        return ('المودم متصل، لكن أمر قراءة حالة الشريحة رُفض على المنفذ الحالي.'
                if reading.name=='SIM status' else 'المودم رفض الأمر على المنفذ الحالي؛ لا يثبت عدم الدعم الدائم.')
    if state=='TIMEOUT':return 'لم يصل رد مكتمل في الوقت المحدد؛ لم نعد إرسال الأمر تلقائيًا.'
    if state=='SESSION_UNCERTAIN':return 'توقف الفحص لأن ردًا سابقًا غير مكتمل؛ أعد فتح الجلسة يدويًا بعد مراجعة النتيجة.'
    if state=='UNSUPPORTED':return 'التوافق لم يثبت في هذا المسار؛ نتيجة واحدة لا تكفي لنفي الدعم.'
    if state=='NOISY':return 'تجاوز تدفق إشعارات المودم حد الاستقبال الآمن؛ حالة الجلسة غير محسومة.'
    if state=='IO_ERROR':return 'انقطع استقبال البيانات؛ تحقق من اتصال المودم والمنفذ.'
    if state=='UNVERIFIED':return 'الوصول أو المصادقة لم يُختبرا على الشريحة في هذا الفحص.'
    if state=='NEEDS_USER':return reading.value
    return {'+CPIN: READY':'الشريحة جاهزة؛ لا يثبت ذلك نجاح AKA.',
            '+CPIN: SIM PIN':'الشريحة تطلب PIN؛ لم نرسل أي رمز.',
            '+CPIN: SIM PUK':'الشريحة تطلب PUK؛ لم نرسل أي رمز.'}.get(reading.value,reading.value)
