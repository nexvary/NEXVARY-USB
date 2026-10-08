# NEXVARY USB Studio 0.4.0

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
ModemUsimBackend is implemented locally with consent/scoped authorization, but
remote WiFi-Call broker integration, real AKA, ePDG/IPsec, IMS and calls are not
verified. QMI/MBIM control, PC/SC APDU, inbound Arabic PDU decoding and automatic
cellular-data dialing remain unimplemented.

## Run

```bash
python -m pip install -r requirements.txt
python -m nexvary_usim_lab gui
python -m nexvary_usim_lab ports
python -m nexvary_usim_lab diagnose --export report.json
python -m nexvary_usim_lab probe --port COM7 --export modem-report.json
```

On Ubuntu use a virtual environment and existing serial permissions. No root,
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
