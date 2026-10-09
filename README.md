# NEXVARY USB Studio 0.8.2 — WiFi-Call capability evidence

Windows **التقارير → دليل قدرات WiFi-Call** exports the current device report
with independent AT, SIM-status, APDU, AKA, ePDG, IMS and voice/call stages.
No new device command is sent by the GUI export. Syntax acknowledgments and
SELECT MF never authorize calls or establish AKA; authentication/calling remain
unverified in this diagnostic contract. Existing features and the private mTLS
bridge are preserved.

```bash
python -m nexvary_usim_lab capabilities --port COM5 --export wifi-call-capabilities.json
```

The CLI adds the existing fixed SELECT MF test only with explicit `--consent`.
No subscriber/authentication secrets are exported. There is one owner modem:
Huawei K3770, firmware `21.023.04.00.11`, observed USB ID `12D1:14C9`.
Earlier E153 references do not establish a second physical device.

[Release details and verification limits](docs/RELEASE-0.8.2-AR.md) ·
[Capability contract](docs/WIFI-CALL-CAPABILITY-CONTRACT.md)

---

# NEXVARY USB Studio 0.7.2 — K3770 diagnostic reliability

The user-started comprehensive scan now evaluates read-only SIM-status and signal responses on each eligible AT port before choosing the most capable port. AT success alone is not evidence of SIM readiness. Diagnostics ports remain excluded by default. No PIN, SIM mutation, authentication, SMS or APN changes are sent by this selection process.

A modem ERROR is labeled REJECTED rather than UNSUPPORTED. Numeric CME/CMS errors are sanitized; they do not imply permanent incompatibility. Earlier owner-reported COM5/COM7 success remains historical evidence, never a new physical test of 0.7.2.

When all candidate ports answer AT but do not return SIM data, SIM readiness is unverified. CSIM syntax OK is not proof of APDU authentication, USIM AKA, IMS, or Wi-Fi Calling.

---
# NEXVARY USB Studio 0.7.1

يبدأ البرنامج الآن بمساعد استخدام من خمس مراحل، مع شرح النتائج بالعربية وزر التالي والمرحلة السابقة، وشروحات عملية داخل كل وظيفة. الوظائف المتقدمة محفوظة. [دليل الاستخدام](docs/USAGE-GUIDE-AR.md).

# NEXVARY USB Studio 0.7.0

تحديث USIM Core مبني على أحدث 0.6.0: اكتشاف USIM/ISIM واختبار SELECT للتطبيقات المعلنة، معالجة مهلة ورفض البطاقة منفصلين، وحفظ أدلة K3770 الميدانية المنقحة. نجاح SELECT لا يثبت AKA. [تفاصيل التنفيذ والقيود](docs/USIM-CORE-v0.7.md).

## Windows 0.6.0: NEXVARY SIM Manager integration

Reviewed owner APK: `com.nexvary.simmanager` 0.922.0. New eSIM Manager page
validates LPA codes, generates and reads QR locally, and imports the phone's
recycling CSV reports. Codes stay out of diagnostic reports. Android profile
provisioning still requires an authorized LPA; no live phone/AKA/carrier result
is claimed. Full-color icons and the 0.5.1 black/neon-green/royal-red theme are
preserved. See [review and contract](docs/ESIM-MANAGER-INTEGRATION.md).

## الإصدار 0.5.0

قراءة SMS PDU العربي وGSM7، اتصال بيانات عبر خدمات النظام، SELECT PC/SC، وجسر USB يختاره محرك WiFi-Call صراحة. راجع [الوظائف وحدود التحقق](docs/REMAINING-FEATURES-v0.5.md). كل أدلة الأجهزة السابقة تبقى كما هي؛ لا إثبات AKA أو مكالمات جديدة.

# NEXVARY USB Studio 0.5.0

Arabic RTL USB modem workstation for Windows, with Linux CLI/desktop support.
Upgraded from the existing 0.3.1 code; device operations are preserved and extended.

The main view groups interfaces by Windows PnP container/physical USB ancestry,
never just VID/PID. Device cards provide scan, SIM, SMS, network, advanced details
and reports. AT discovery runs only after a user action, skips Diagnostics by
default and saves the working port locally. Unresolved PnP relationships are
shown honestly instead of merging independent modems.

Included: SIM/PIN state, redacted ICCID, EF_DIR USIM/ISIM application inventory,
fixed SELECT MF, network status, APN changes with inactive-context/read-back
checks, confirmed ASCII SMS, experimental single-part Arabic UCS2 PDU SMS,
local inbox, reports, optional PC/SC reader enumeration and evidence profiles.

**Hardware support is not established by compilation.** K3770 has owner-reported
AT/SIM READY and SELECT MF `6A86` evidence; E153/MF190S have label evidence.
No new physical-device test was performed during automated development.
ModemUsimBackend and the foreground private mTLS bridge are implemented with
consent and scoped authorization. WiFi-Call engine selection is wired explicitly;
real AKA, ePDG/IPsec, IMS and calls still require hardware/operator validation.
Received Arabic PDU, fixed PC/SC SELECT and OS-managed cellular data are now
implemented. QMI/MBIM is managed by the OS services; raw protocol drivers are
not bundled. See the 0.5.0 feature document for supported paths and limitations.

## Run

```bash
python -m pip install -r requirements.txt
python -m nexvary_usim_lab gui
python -m nexvary_usim_lab ports
python -m nexvary_usim_lab diagnose --export report.json
python -m nexvary_usim_lab probe --port COM7 --export modem-report.json
```

On Ubuntu install `libegl1 libgl1 fonts-noto-core`, then use a virtual environment and existing serial permissions. No root,
USB driver installation, firmware flashing or blind USB mode-switching is needed
for diagnostics. The Windows installer does not alter file associations.

## Verification

```bash
python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=1.5 python scripts/windows_ui_smoke.py
```

GitHub Actions runs tests on Ubuntu 24.04 and Windows Server 2022, captures real
Qt page screenshots for 1024×768, 1280×720, 1366×768 and 1920×1080 at 100%, 125%
and 150%, builds the portable EXE and Inno Setup installer, checks packaged UI,
install/upgrade/uninstall and settings preservation, and publishes SHA256SUMS.
Synthetic device screenshots are explicitly marked and are not physical evidence.

- [Delivery status](docs/DELIVERY-STATUS.md)
- [USIM integration limits](docs/USIM-INTEGRATION.md)
- [Seven upstream projects and license review](docs/THIRD-PARTY-REVIEW.md)

No arbitrary APDU listener, SIM key extraction, silent SMS or automatic dialing.


## Version 0.8.0 — comparison of modem AT interfaces (software-level)

The SIM page offers **مقارنة منافذ المودم**: a consented and bounded, read-only
capability matrix per physically grouped modem, excluding Diagnostics by default.
It probes AT, CPIN?, CSQ, CREG?, CSIM=? and CRSM=? on up to four candidate
ports, records **only classified results** (no raw SIM, cell, ICCID, SMS or
authentication material) and prefers a SIM-responsive interface over one that
responds to AT alone. Test-syntax acknowledgments are explicitly *not* APDU or
USIM AKA proof. Port results are not written to disk by this comparison.
The SIM results table now explains transient modem errors in Arabic rather
than claiming that an entire SIM is permanently unsupported.

This is a software regression improvement, not verified on a physical K3770 in
this commit. Hardware-specific access, CCHO/CGLA, USIM AKA and IMS/ePDG remain
dependent on device, SIM and operator evidence.
