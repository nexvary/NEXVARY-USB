"""Plain-language guidance from actual report readings; never infer AKA success."""
STEPS = (
 ('وصّل الفلاشة', 'ضع الشريحة في الفلاشة ثم وصّلها بمنفذ USB. اضغط البحث عن الأجهزة. لا تختَر منفذ COM يدويًا.'),
 ('اختر جهازك', 'اختر اسم الفلاشة من القائمة. الواجهات والمنافذ التابعة لها مجمعة في جهاز واحد. إذا لديك أكثر من فلاشة، اختر التي تريد العمل عليها.'),
 ('افحص الاتصال والشريحة', 'اضغط بدء الفحص وانتظر النتيجة. يختار البرنامج منفذ AT المناسب ويقرأ حالة الجهاز والشريحة والإشارة. لا يرسل SMS ولا يغيّر APN ولا يطلب PIN.'),
 ('اختر ما تريد فعله', 'اقرأ النتيجة ثم اختر وظيفة واحدة. ستجد شرحًا داخل صفحتها. كل إرسال أو تغيير إعداد يحتاج موافقة منفصلة. الفحص المتقدم اختياري.'),
 ('احفظ النتيجة', 'انتهت مراحل البدء. يمكنك حفظ تقرير منقح للمراجعة أو العودة للوظائف. لا يحتوي التقرير العام نصوص الرسائل أو معرّف الشريحة الكامل.'),
)
GOALS = (
 ('معلومات الشريحة', 'sim', 'اقرأ حالة الشريحة أولًا. قراءة رقمها وفحص التطبيقات اختياريان؛ لا تحتاج SELECT لتشغيل الرسائل.'),
 ('قراءة أو إرسال الرسائل', 'sms', 'ابدأ بقراءة الوارد. للإرسال اكتب الرقم الدولي والنص ثم راجع رسالة الموافقة؛ قد تُحتسب رسوم.'),
 ('الشبكة واتصال الإنترنت', 'network', 'ابدأ بقراءة حالة الشبكة. الاتصال يحتاج ملف بيانات موجودًا وتعريفًا مناسبًا؛ لا تغيّر APN إلا إذا تعرف إعدادات مشغلك.'),
 ('نقل كود eSIM إلى الهاتف', 'esim', 'استخدم كود LPA الخاص بك لعرض QR محلي، ثم امسحه بتطبيق الهاتف. نقل الكود لا يثبت تنزيل أو تفعيل الاشتراك.'),
 ('حفظ تقرير فقط', 'reports', 'احفظ التقرير العام لإرساله للدعم؛ تفاصيل المصادقة ونتائج المكالمات تحتاج اختبارات مستقلة.'),
)

def connection_ok(report):
    return bool(report and any(r.name=='Connection' and r.status=='OK' for r in report.readings))

def explain_report(report):
    if not report:return 'لم نُجرِ فحصًا بعد. ابدأ الفحص للحصول على نتيجة من جهازك.'
    values={r.name:r for r in report.readings}
    if not connection_ok(report):
        return 'لم يكتمل الاتصال بالمودم. أغلق برنامج إدارة الفلاشة إن كان يستخدم المنفذ، وتأكد من التعريف والتوصيل، ثم أعد الفحص يدويًا. لا توجد نتيجة ناجحة مؤكدة.'
    result=['تم الاتصال بالمودم بنجاح.']
    sim=values.get('SIM status')
    if sim and sim.status=='OK' and 'READY' in sim.value:result.append('الشريحة جاهزة للاستخدام.')
    elif sim and sim.status=='OK' and 'SIM PIN' in sim.value:result.append('الشريحة تطلب PIN. أدخله من برنامج المشغل الموثوق؛ هذا البرنامج لا يرسل PIN تلقائيًا.')
    else:result.append('جاهزية الشريحة لم تثبت؛ راجع حالة الشريحة قبل استخدام الرسائل أو البيانات.')
    registration=values.get('Registration')
    if registration and registration.status=='OK':
        import re
        match=re.search(r'\+CREG:\s*(?:\d+\s*,\s*)?([0-5])(?:\s*,|$)',registration.value)
        if match:
            result.append({'0':'المودم غير مسجل بالشبكة.','1':'المودم مسجل بالشبكة المحلية.','2':'المودم يبحث عن الشبكة.','3':'الشبكة رفضت التسجيل.','4':'حالة التسجيل غير معروفة.','5':'المودم مسجل بالتجوال؛ راجع الرسوم.'}[match[1]])
    signal=values.get('Signal')
    if signal and signal.status=='OK':
        import re
        match=re.search(r'\+CSQ:\s*(\d{1,2})\s*,',signal.value)
        if match:
            level=int(match[1])
            if 0<=level<=31:result.append(f'قوة الإشارة: {level} من 31 وفق قراءة المودم.')
            elif level==99:result.append('المودم لم يحدد قوة الإشارة.')
    iccid=values.get('ICCID');file=values.get('SIM EF ICCID')
    if iccid and iccid.status=='TIMEOUT':
        result.append('قراءة رقم الشريحة بالطريقة المباشرة لم تكتمل؛ هذا لا يعني أن الشريحة تالفة.' if not file or file.status!='READABLE' else 'قراءة رقم الشريحة المباشرة لم تكتمل، لكن الوصول إلى ملفها نجح؛ لم نعرض الرقم الكامل.')
    apdu=values.get('APDU SELECT MF')
    if apdu and apdu.status=='ACCEPTED' and apdu.value=='SW=9000':result.append('نجح اختيار الملف الأساسي على الشريحة. مصادقة AKA والمكالمات لم تثبت.')
    else:result.append('فحص APDU والمصادقة اختياريان ولم يثبت نجاحهما في هذا الفحص.')
    if report.simulated:result.insert(0,'هذه نتيجة محاكاة صريحة، وليست فحص جهاز فعلي.')
    return '\n'.join(result)
