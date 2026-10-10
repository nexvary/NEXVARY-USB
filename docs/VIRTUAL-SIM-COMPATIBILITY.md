# Compatibility and evidence ledger — 0.10.2

Only **one owner-tested physical device** is established here: Huawei K3770,
firmware 21.023.04.00.11, USB 12D1:14C9. E153 is not a second verified device.
Port names in retained evidence are historical, never connection constants.

| Model | Firmware | VID:PID | Ports | AT | SIM READY | CSIM | CRSM | SELECT | USIM application | AKA | Virtual PC/SC | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Huawei K3770 | 21.023.04.00.11 | 12D1:14C9 | owner reports COM5/COM7 AT; COM6 diagnostics, rediscover each run | observed | observed | MF + EF_DIR + READ RECORD + ADF observed | ICCID read observed on historical COM5 | MF 9000 observed | EF_DIR: 5 × 33 bytes; USIM AID discovered and selected | not tested successfully | runtime implemented, physical modem unverified | owner reports 2026-10-09 + screenshot 2026-10-10; JSON pending |
| Huawei E153 | unknown | 12D1:unknown | AT candidate | unknown | unknown | unknown | unknown | unknown | unknown | unknown | conditional | prior label/name ambiguity; not independently proven owner hardware |
| Huawei E173 | unknown | 12D1:mode-dependent | AT serial candidate | upstream AT profile lead only | unknown | unknown | unknown | unknown | unknown | unknown | conditional | xlab/at, not a NEXVARY field test |
| Huawei E1750 | unknown | 12D1:mode-dependent | AT serial candidate | upstream documentation lead only | unknown | unknown | unknown | unknown | unknown | unknown | conditional | gsm-gateway AT documentation, no APDU proof |
| ZTE MF190 / MF190S | unknown | 19D2:mode-dependent | AT serial candidate | unknown per exact firmware | unknown | unknown | unknown | unknown | unknown | unknown | conditional | ZTE SIM/USIM slot documentation; model variants must not be conflated |
| Quectel EC200U | variant required | unknown here | upstream serial modem | upstream project evidence | upstream project evidence | upstream implementation/live narrative | not assessed | upstream narrative | upstream narrative | upstream narrative only | upstream bridge narrative; not independently retested | GSM-SIP Bridge reference, not requirement to buy hardware |
| Scripted multi-modem fixtures | synthetic | synthetic | COM7/COM9 fixtures | simulated | simulated | simulated | existing synthetic tests | simulated | simulated discovery/select | simulated result | actual Linux PC/SC runtime test with synthetic card | CI report distinguishes actual OS runtime from mocked hardware |

No device is declared permanently incompatible from a timeout. CCHO/CGLA are
inconclusive on the owner K3770; direct CSIM avoids making them prerequisites.
All devices need a local serial interface and actual response validation.
HiLink-only HTTP interfaces are not APDU transport evidence. "Unlocked" and
"Voice Enabled" do not establish external UICC access.

Transport profiles are explicit, declarative options: `mode=tpdu|apdu` and
`mf_p2=0|4|12`. Default is standards-based T=0 / UICC no-FCP MF select; **no
firmware-specific speculative retry**. Current field tool and UI use this
safe default. Other frame modes are available through the engine API and
must be validated per firmware before introducing a default override.

0.10.1 introduces richer field collection and an independent native SCard test. No new physical model/firmware evidence was collected; the table remains a ledger of prior observations and declared synthetic tests. Windows source preparation is not driver build/signing/enumeration evidence.

## Owner field evidence — 2026-10-10

USB Studio 0.10.1 report NEXVARY-esults.png on COM6 shows K3770 / 21.023.04.00.11, SIM READY, SELECT MF SW=9000, EF_DIR FCP, five records of 33 bytes, USIM AID A0000000871002FF49FF018900000100 and successful SELECT ADF. This is owner-supplied physical-device evidence, not a simulation or independent retest. Exact ADF status is not displayed in the PNG; JSON is pending. Current USB VID/PID is unavailable in this report; the historical 12D1:14C9 is not re-established. Local service waiting does not prove PC/SC enumeration/transfer. AKA, ISIM selection, ePDG, IMS and calls remain unverified. Screenshot SHA256 is recorded in profiles/K3770.json.
