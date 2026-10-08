# NEXVARY USB

**NEXVARY USB Studio v0.3.0 — integrated beta**. Windows desktop and Linux CLI with safe modem management.
Current scope: read-only modem inventory, SIM status, masked ICCID, AT capability
queries, optional owner-consented fixed APDU SELECT MF, optional PC/SC reader inventory,
offline simulation, redacted JSON/CSV exports, and three physical-label-based models
(Huawei E153, ZTE MF190S, Huawei/Vodafone K3770).

**The project is experimental.** It does not currently perform USIM AKA, control
VoWiFi calls, activate ePDG/IPsec/IMS, flash modems, unlock carrier restrictions,
extract SIM keys, or send SMS. Model catalog entries do not imply functionality:
compatibility requires tests on the actual modem and authorized SIM.

## Windows — portable GUI from source

```powershell
git clone https://github.com/nexvary/NEXVARY-USB.git
cd NEXVARY-USB
py -m pip install -r requirements.txt
py -m nexvary_usim_lab gui
```

To run without hardware:

```powershell
py -m nexvary_usim_lab demo
py -m nexvary_usim_lab catalog
py -m nexvary_usim_lab ports
py -m nexvary_usim_lab diagnose --export usb-diagnostic.json
```

Windows binaries: GitHub Actions → **USB-USIM Lab checks** → latest successful run → **Artifacts** → `NEXVARY-USB-Studio-Windows-Installer` (Inno Setup) or `NEXVARY-USB-Studio-Windows-Portable`.
Do not confuse CI with real hardware validation.

## Ubuntu 24.04 / desktop Linux

```bash
git clone https://github.com/nexvary/NEXVARY-USB.git
cd NEXVARY-USB
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m nexvary_usim_lab gui
```

Headless use: `python -m nexvary_usim_lab ports` and
`python -m nexvary_usim_lab probe --port /dev/ttyUSB0 --export report.json`.
For GUI also install your distribution's Tkinter dependency if missing.
On Linux use existing user serial permissions rather than indiscriminate root use.
If the stick appears only as a USB storage device, first inspect its USB VID:PID
and the distribution usb_modeswitch database. **Do not blindly run external
firmware or modeswitch commands** against an unknown device.

## Tests, output, and hardware sequence

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m nexvary_usim_lab probe --port COM3 --export report.json
python -m nexvary_usim_lab select-mf --port COM3 --consent
```

Port is chosen by the user, never guessed. SELECT MF is a fixed APDU read-only
selection test with an explicit owner consent flag, and returns only SW1/SW2.
It does not prove AKA support; the operating system and modem must permit it.
No arbitrary APDU execution or public API is provided.

## Hardware catalog

| Label confirmed by owner photo | Vendor | First investigation |
|---|---|---|
| E153 | Huawei | Expose AT port, check +CSIM and +CGLA |
| MF190S | ZTE | Detect correct AT port, check UICC command behavior |
| K3770 (not K3770-Z) | Huawei / Vodafone | Identify storage/modem USB mode and AT port |

Huawei family VID `12D1`, ZTE `19D2` are **hints**, not exact
model IDs. The photo does not expose per-device USB VID:PID, firmware or
actual supported APDU interfaces.

## NEXVARY WiFi Call integration

This project is now **standalone**. It was initialized from the previously
verified diagnostics in `nexvary/NEXVARY-WiFi-Call` at
`f441b5d4eac7a97f54424bd0035e86d1100be81e`.
The original module remains in that repo; nothing was removed there.

A future `ModemUsimBackend` must be separately audited and enabled only
after proving card-initiated, authorized authentication. Carrier Wi-Fi Calling
also requires independent operator entitlement, ePDG SWu/IPsec and IMS
verification. No credentials, Ki/OPc or challenge/response secrets in logs.

Read `docs/USB-USIM-LAB.md` for research boundaries and upgrade gates.
Third-party projects are studied as references; their source code is not
copied into this repository.

## Next milestones

- Real USB modem profile testing on three labeled devices; USB-storage vs modem
  interfaces; VID:PID/driver evidence.
- Safe USIM/ISIM file inventory with consent, strict allowed operations,
  and no personal identifiers in exported reports.
- Opt-in SIM-resident AKA backend with strict authentication, time bounds,
  and documented modem-specific support.
- SMS and cellular-data modules separately gated by explicit device/user
  permissions; no silent network changes.
- Production installer and integrity-signed Windows build once hardware
  and security verification are complete.

## Windows USB detected but no COM ports?

As of this revision the GUI scans both Windows Plug and Play devices and serial COM ports.
It now shows Huawei/ZTE interfaces even when Windows recognizes only a mass-storage
or a USB device without modem driver. Use **تحديث الأجهزة**, then **تقرير USB** to
export a redacted inventory and send it for analysis. The report excludes raw
PnP InstanceId/device serials and does not include subscriber IMSI/IMEI.

If `USB_NO_COM` appears, check Device Manager for removable disk, CD-ROM,
modem, and unrecognized USB interfaces; identify vendor/product IDs without
installing random drivers or flashing the modem. The program does not silently
switch USB modes or install unsigned drivers. If the OS genuinely has no device,
changing code cannot make an unplugged/faulty USB device readable.


## Integrated desktop capabilities (v0.3.0)

Five RTL desktop areas: modem/USB devices, SIM and APDU, SMS, redacted reports, and PC/SC/compatibility. The app now includes real user-confirmed one-at-a-time outbound English/ASCII SMS, read-only received SMS display, masked ICCID file accessibility checks over AT+CRSM, fixed SELECT MF over AT+CSIM, modem AT diagnostics, Windows PnP USB inventory and JSON/CSV export. Hardware-specific operations are **not** considered validated merely because the software builds. The Windows package includes a generated custom NEXVARY icon and an Inno Setup installer. The installer is not digitally code-signed.

## Not yet achieved

A generalized USIM/ISIM APDU abstraction, authenticated SIM AKA backend, secure bridge to NEXVARY-WiFi-Call, EAP-AKA/IPsec SWu/ePDG, IMS registration, actual carrier Wi-Fi calls, and Arabic UCS2 SMS. Operator privileges and service entitlement cannot be assumed from an older 3G modem. Refer to `docs/DELIVERY-STATUS.md` before claiming production readiness.
