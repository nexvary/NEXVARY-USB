# تعريف Windows PC/SC — بناء تطوير x64

بُني التعريف المشتق من vsmartcard داخل GitHub Actions، مع DLL وINF وCAT غير موقعة. هذه حزمة تطوير وليست مثبتًا معتمدًا للاستخدام العام. نجاح البناء أو تحميل واجهة COM لا يثبت تعداد قارئ بواسطة Windows Smart Card Resource Manager.

## ما تحتويه الحزمة

- NEXVARYVirtualSIMReader.dll وNEXVARYVirtualSIMReader.inf وNEXVARYVirtualSIMReader.cat.
- BUILD-EVIDENCE.json: commit البناء والحالة المستقلة للتوقيع والتثبيت والتعداد والأجهزة.
- NATIVE-CHECKS.json: تحميل DLL وإنشاء COM Driver Entry واختبار النقل الأصلي WinSock مع مودم اصطناعي، وفقد الخدمة وإعادة الاتصال وتجزئة الرد والمهلة.
- سجلات PE وSHA256 والمصدر المطابق وتعديلات NEXVARY، تحت GPL-3.0.

للتكرار استخدم workflow «Windows virtual reader driver build» في المستودع الحالي. يُثبَّت المصدر عند commit 8a411e3672e843f9bb9fd750fc8dc56a26bb3bc8، وتُنزّل WDK 10.0.26100.1 مع تحقق SHA256 داخل مجلد مؤقت معزول. لا يستبدل البناء تعريفًا مثبتًا ولا يشغّل مثبت vsmartcard الأصلي ولا يولّد شهادة أو يغيّر سياسة Windows.

## حدود التشغيل

القارئ مخصص للاتصال بـ127.0.0.1:35963 فقط، باستخدام خدمة «قارئ SIM الافتراضي» في USB Studio. يبدأ المستخدم الخدمة بعد موافقة محلية قصيرة. النقل للقراءة فقط؛ AUTH غير مسموح عبر هذا المسار. لا تفتح المنفذ على الشبكة.

ATR ‏3B00 تمثيل للنقل وليس ATR كهربائيًا من الشريحة. إعادة الضبط تعني إعادة اختيار جلسة البطاقة فقط. يُتحقق من جاهزية SIM وSELECT MF قبل إعلان البطاقة. التوقف أو انتهاء الموافقة يقطع الجلسة؛ إعادة تشغيل المضيف تحتاج موافقة جديدة.

اسم DLL وخدمة UMDF ومعرّف root وCLSID مستقلة عن BixVReader، لتفادي الكتابة فوق تعريف vsmartcard موجود. الحزمة x64 فقط. تعتمد على UMDF 1.9 القديم؛ يجب التحقق من التوافق على إصدارات Windows المستهدفة قبل التوزيع العام.

## ما يمنع المثبت العام

لا تتوفر في هذا العمل شهادة أو صلاحية توقيع موثوقة للتوزيع. إنشاء CAT بواسطة Inf2Cat اختبار قابلية التوقيع، وليس توقيعًا. لا تُعرض هذه الملفات بوصفها تعريفًا مثبتًا أو قارئًا معدودًا. لا يُطلب تعطيل Secure Boot أو حماية Windows أو تفعيل test signing كمسار استخدام عادي.

الخطوات المتبقية: توقيع الحزمة وفق متطلبات Windows المستهدف بواسطة جهة مخولة، تثبيت مراقب في بيئة اختبار، تعداد SCardListReaders والاتصال SCardConnect ونقل SELECT/GET RESPONSE/READ RECORD من عميل خارجي، ثم إعادة ذلك على مودم وشريحة حقيقيين. لا توجد هنا أدلة على تلك الخطوات ولا AKA أو ePDG أو IMS أو مكالمات.

Direct CSIM وتشخيص USB Studio يعملان دون هذا التعريف. فتح صفحة «قارئ SIM الافتراضي» وتشغيل الخدمة لا يثبتان Windows PC/SC؛ أبقِ نتائج تشغيل الخدمة والتوقيع والتعداد والاتصال ونقل APDU منفصلة.

## أداة إنشاء الجهاز وفحص Windows

تحتوي الحزمة الجديدة على NEXVARY-Reader-Setup.exe، ومصدرها reader_setup.cpp، وزرّي التشغيل Check-Reader.cmd وInstall-Reader.cmd.

1. فك الضغط في مجلد واحد، وأبقِ DLL وINF وCAT بجانب أداة الإعداد.
2. افتح NEXVARY-Reader-Setup.exe للفحص العربي، أو Check-Reader.cmd لإبقاء التقرير ظاهرًا. هذه الخطوة لا تثبت تعريفًا.
3. الحزمة الحالية غير موقعة؛ سيقول الفحص «غير جاهزة للتثبيت»، ويرفض --install قبل إنشاء أي جهاز أو إضافة ملفات إلى Driver Store. لا تغيّر سياسة Windows لتجاوز ذلك.
4. بعد الحصول على حزمة موقعة موثوقة ومطابقة، شغّل Install-Reader.cmd كمسؤول. تستخدم الأداة SetupAPI لإنشاء root\NEXVARYVirtualSIMReader ثم UpdateDriverForPlugAndPlayDevices لتثبيت INF. لا تستخدم FORCE، ولا تنشئ نسخة ثانية عند وجود الجهاز.
5. عند فشل التثبيت، تحاول إزالة الجهاز الذي أنشأته هذه المحاولة فقط وتعرض نتيجة التراجع. لا تحذف جهازًا موجودًا مسبقًا أو تعريفه.
6. أعد الفحص: وجود جهاز root لا يعني نجاح تعداد قارئ. يعرض التقرير own_root_devices وnexvary_reader_enumerated بشكل مستقل. تعداد Windows هنا فعلي من SCardListReaders؛ لا يثبت SCardConnect أو APDU.
7. شغّل الخدمة المحلية بعد الموافقة في USB Studio، ثم نفّذ اختبار PC/SC الميداني الموجود في التطبيق لإثبات الاتصال والنقل. لا تعرض اتصال الخدمة باعتباره اتصال البطاقة.

للأوامر التقنية: `NEXVARY-Reader-Setup.exe --check` يُخرج JSON، و`--install` هو الإجراء الوحيد الذي يمكنه تعديل إعداد جهاز. لا يوجد خيار لتجاوز التوقيع. التحقق يستخدم WinVerifyTrust وتحقق عضوية INF وDLL في الكتالوج باستخدام SHA256، مع فحص هوية INF المخصصة للقارئ. تبقى ملفات الحزمة مفتوحة للقراءة مع منع الكتابة والحذف طوال محاولة التثبيت.

اختبارات CI تنفذ الفحص ورفض الحزمة غير الموقعة والملفات الناقصة، وتتحقق من عدم زيادة عدد أجهزة NEXVARY. لا تنفذ مسار التثبيت الموثوق، لأنه لا توجد حزمة موقعة متاحة.

## المسار الخارجي للتوقيع

لا يوجد في إعدادات البناء الحالية مفتاح توقيع أو خدمة توقيع متاحة. يمكن تقديم حزمة إلى Microsoft Hardware Developer Program من حساب مخول؛ حساب التقديم لهذا المسار يحتاج شهادة EV وفق وثائق Microsoft. هذا يتطلب هوية الجهة وشهادتها وصلاحية الحساب، ولا يمكن استبداله بإنشاء شهادة ذاتية على جهاز المستخدم. لم نفحص حساب Microsoft للمالك، ولم نجرِ تقديمًا أو شراءً نيابة عنه.

المراجع الرسمية:
- https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/code-signing-reqs
- https://learn.microsoft.com/en-us/windows/win32/api/wintrust/ns-wintrust-wintrust_catalog_info
- https://learn.microsoft.com/en-us/windows/win32/api/setupapi/nf-setupapi-setupdicreatedeviceinfow
- https://learn.microsoft.com/en-us/windows/win32/api/newdev/nf-newdev-updatedriverforplugandplaydevicesw


يتطلب DLL القارئ مكتبات Visual C++ x64 ‏MSVCP140/VCRUNTIME140/VCRUNTIME140_1 في System32. تفحص الأداة وجودها قبل إنشاء الجهاز؛ وجود الملفات وحده لا يثبت توافق جميع نسخها. أداة الفحص نفسها مبنية /MT ولا تحتاج تنزيل تلك المكتبات لتشغيلها. تُنزّل التبعيات من Microsoft عند الحاجة، ولا يثبتها الفحص تلقائيًا:
https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist

NEXVARY-Unsigned-Signing-Input.cab يجمع DLL وINF وCAT وPDB في مجلد حزمة واحد لتسليمه إلى جهة توقيع مخولة. هذا مدخل غير موقع، وليس طلبًا مقبولًا أو شهادة أو إثبات توافق. لم نوقّع CAB أو نقدمه. مسار النشر العام يحتاج مراجعة متطلبات Windows المستهدف وWHCP/HLK؛ توثيق Microsoft الحالي يقيد attestation بسيناريوهات اختبار، لذلك لا نعتمده كإثبات صلاحية توزيع عام:
https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/code-signing-attestation
