"""Arabic public result presentation, separate from protocol status codes."""
NAMES={'PC/SC connection':'اتصال بطاقة PC/SC','PC/SC SELECT MF':'اختيار MF عبر PC/SC','PC/SC EF_DIR':'قراءة EF_DIR عبر PC/SC','PC/SC SELECT USIM':'اختيار USIM عبر PC/SC','PC/SC diagnostic':'تشخيص PC/SC','PC/SC provenance':'مصدر دليل PC/SC','Connection':'الاتصال بالمودم','Manufacturer':'الشركة المصنعة','Model':'الموديل',
       'Firmware':'إصدار البرنامج الداخلي','SIM status':'حالة الشريحة','ICCID':'رقم الشريحة المنقح',
       'Signal':'الإشارة','Registration':'التسجيل في الشبكة','CSIM probe':'فحص صيغة CSIM',
       'CGLA probe':'فحص صيغة CGLA','CCHO probe':'فحص صيغة CCHO','CRSM probe':'فحص صيغة CRSM',
       'SIM EF ICCID':'ملف رقم الشريحة','SIM applications':'تطبيقات الشريحة',
       'SIM application':'تطبيق معلن','APDU SELECT MF':'اختيار الملف الأساسي','USIM AKA':'مصادقة USIM AKA',
       'Serial port':'منفذ المودم المختار','USB VID:PID':'هوية USB الحالية',
       'Virtual reader service':'خدمة القارئ المحلي','PC/SC enumeration':'تعداد قارئ PC/SC',
       'PC/SC APDU transfer':'نقل APDU عبر PC/SC','Direct CSIM':'اختيار MF عبر CSIM',
       'EF_DIR CSIM':'قراءة EF_DIR عبر CSIM','EF_DIR FCP':'وصف ملف EF_DIR',
       'EF_DIR dimensions':'أبعاد سجلات EF_DIR','USIM directory':'عنوان تطبيق USIM',
       'ISIM directory':'عنوان تطبيق ISIM','USIM direct access':'اختيار تطبيق USIM',
       'ISIM direct access':'اختيار تطبيق ISIM','Direct SIM transport':'حالة نقل SIM',
       'Virtual PC/SC':'إثبات قارئ PC/SC','ePDG / IMS / Calls':'ePDG وIMS والمكالمات'}
SUCCESS={'OK','READABLE','SELECTED'}
FAIL={'ERROR','REJECTED','IO_ERROR','MODEM_ERROR','MALFORMED','CARD_STATUS','NOISY'}

def outcome(reading):
    stages={'OBSERVED':'مُلاحظ','DECLARED':'مُعلن','STOPPED':'متوقف',
            'WAITING_PCSC':'بانتظار اتصال','CONNECTED_READ_ONLY':'متصل للقراءة',
            'EXPIRED':'انتهت الموافقة','STOPPING':'جارٍ الإيقاف'}
    if reading.status in stages:return stages[reading.status]
    if reading.name=='SIM status' and reading.status=='OK' and reading.value!='+CPIN: READY': return 'يحتاج تدخل المستخدم'
    if reading.status in SUCCESS: return 'ناجح'
    if reading.status=='ACCEPTED':
        proven = reading.value=='SW=9000' or (reading.name=='Direct CSIM' and reading.value=='SELECT MF SW=9000')
        return 'ناجح' if proven else 'غير محسوم'
    if reading.status in FAIL:return 'فشل'
    if reading.status=='NEEDS_USER':return 'يحتاج تدخل المستخدم'
    if reading.status in ('UNVERIFIED','NOT_TESTED'):return 'غير مختبر'
    return 'غير محسوم'

def explain(reading):
    if reading.name=='USB VID:PID' and reading.status=='UNVERIFIED':
        return 'هوية VID/PID غير متاحة من الجرد الحالي؛ لا نستنتجها من اسم المودم.'
    if reading.name=='PC/SC diagnostic':
        hints={'8010001D':'خدمة Windows Smart Card أو pcsc-lite غير متاحة؛ لا يعني ذلك فشل المودم.',
               '8010002E':'لم يُعثر على قارئ PC/SC؛ تشغيل الخدمة وحده لا يثبّت تعريف القارئ.',
               '8010000C':'لا بطاقة متاحة في القارئ؛ راجع التحقق والموافقة واتصال المودم.'}
        for code,hint in hints.items():
            if code in reading.value:return hint
        return 'تعذر اختبار القارئ المحدد. يلزم قارئ NEXVARY واحد؛ لا نختار بطاقة أخرى تلقائيًا.'
    if reading.name=='SIM applications' and any(term in reading.value.lower()
        for term in ('truncated sim tlv','malformed sim tlv','tlv غير مكتمل')):
        return ('بيانات دليل تطبيقات الشريحة EF_DIR غير مكتملة أو بصيغة غير متوقعة؛ '
                'لم يثبت غياب USIM أو تلف الشريحة.')
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
