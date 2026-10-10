# Source, protocol and license review — 2026-10-10

Inspected full local clones plus the listed files. New NEXVARY code implements
standard operations and interoperates with a **separately installed** vpcd IFD
handler. Upstream Python/Rust sources and GPL driver binaries are not copied
into the Windows EXE or the headless source package. Protocol support is actual
code, not merely documentation links. Keep upstream licenses when separately
installing/redistributing their components; personal use does not waive them.

| Source | Inspected revision/files | License evidence | Implementation outcome |
|---|---|---|---|
| [pySim](https://github.com/osmocom/pysim) | `9aa8934da2415b161eb9726adad2ba7b4f35d1a7`; `pySim/transport/modem_atcmd.py`, `pySim/transport/__init__.py`, `contrib/sim-rest-server.py` | modem transport file GPL-2.0-or-later | CSIM character count, TPDU/case-4 distinction, bounded status continuation in `virtual_sim.py`; stricter response validation, no ATZ or raw trace logging |
| [GSM-SIP Bridge](https://github.com/selvakn/gsm-sip-bridge) | `4c2ac404cdb27c62ee86931108db7e36198e67b3`; `gsm-sip-bridge/src/vowifi/usim_bridge.rs`, `modules/usim.rs`, docs/vowifi-bridge.md, docs/omnikey-pcsc-vowifi.md, vpcd contract | root GPL-3.0; dependency/per-file terms apply | Actual vpcd wire frames and SELECT/GET RESPONSE interoperation. No automatic alternate AID redirect, no raw AKA logs, no guessed EC200U quirk on Huawei. Upstream live-test narrative is upstream evidence, not independent NEXVARY hardware proof |
| [vsmartcard](https://github.com/frankmorgner/vsmartcard) | `8a411e3672e843f9bb9fd750fc8dc56a26bb3bc8`; VirtualSmartcard.py, vpcd.[ch], ifd-vpcd.c, reader.conf.in, win32 | virtualsmartcard GPL-3.0-or-later per-file | real 2-byte network-order length + controls 00/01/02/04 in `virtual_reader.py`; reversed IFD mode avoids upstream default INADDR_ANY listener |
| [Osmocom VoWiFi with Asterisk](https://osmocom.org/projects/foss-ims-client/wiki/VoWiFi_with_Asterisk) | direct page returned anti-bot wall on this audit | documentation; individual runtimes separately licensed | Page unavailable directly; do not claim a full current-page review. Cross-checked architecture against GSM-SIP Bridge's own implementation and attribution; SIM → EAP-AKA → ePDG/IPsec → IMS → SIP remain independent stages |
| SIM REST Server | same pySim revision, `contrib/sim-rest-server.py` | project/file GPL terms | Fixed authentication service idea only; existing NEXVARY mTLS/peer pins/consent used. Public unauthenticated REST endpoint and Kc export not adopted |

`pySim` returns a dummy ATR and resets using ATZ. The new engine does not call
ATZ and never reports a physical ATR/electrical reset. The transport ATR `3B00`
is explicitly virtual. Windows virtual-card protocol access is not equivalent
to an installed Windows PC/SC driver; no signed driver is claimed.

SIM REST Server exposes RAND/AUTN-based authentication through its route;
NEXVARY retains restricted local mTLS and scoped authorization, no arbitrary
APDU endpoint, and no challenge/key data in audit records. Python immutable
bytes/str cannot guarantee zeroization; deployment with strict secure-memory
requirements needs a separately reviewed native secret container.

## Additional primary evidence for compatibility candidates

- [xlab/at](https://github.com/xlab/at): E173 AT profile is a candidate lead, not USIM/AKA evidence.
- [mdpuma/gsm-gateway-3g-dongle](https://github.com/mdpuma/gsm-gateway-3g-dongle/blob/master/doc/at_commands.md): E1750 AT command documentation is an AT lead, not CSIM/AKA proof. Unsafe reset/mode-change instructions are not used.
- [ZTE manufacturer MF190 guide](https://download.ztedevices.com/UploadFiles/product/598/1620/manual/P020101228494805265164.pdf): SIM/USIM slot is not a promise of external APDU access.

No universal Huawei/ZTE AKA support was found or asserted. Firmware/USB mode
and actual operation evidence must be collected per device.
