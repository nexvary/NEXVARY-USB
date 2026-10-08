# Third-party review — 2026-10-09

These exact source revisions were inspected locally. No source code from the seven projects was copied, linked or bundled. Root license names alone do not grant reuse of every dependency. No gateway runtime was installed.

| Project | Reviewed revision | License evidence | Relevant design reference |
|---|---|---|---|
| [osmocom/pysim](https://github.com/osmocom/pysim) | `3c437d41e025b2a735e19588e937e578f17a8cd6` | GPL-2.0; per-file terms must be checked | SIM filesystem/EF_DIR and APDU status interpretation |
| [frankmorgner/vsmartcard](https://github.com/frankmorgner/vsmartcard) | `8a411e3672e843f9bb9fd750fc8dc56a26bb3bc8` | GPL-3.0 in virtualsmartcard, ccid, pcsc-relay; per-component review required | PC/SC abstraction, virtual readers for isolated tests |
| [fasferraz/USIM-https-server](https://github.com/fasferraz/USIM-https-server) | `da5d0cdff87ec1bc726cfcebfd9ec214113161ab` | GPL-3.0 | SIM-resident authentication over a secured transport; no public APDU service adopted |
| [fasferraz/SWu-IKEv2](https://github.com/fasferraz/SWu-IKEv2) | `bf5d258b7298db65e64b43065b153325eba47a9e` | GPL-3.0 | Separate SWu/EAP-AKA/IPsec stage; not embedded in USB Studio |
| [pagecat/vowifi_gateway](https://github.com/pagecat/vowifi_gateway) | `e3719840b93961f933aab3dac8bd2641936e2bcc` | MIT at root; embedded components have their own licenses | Per-SIM isolation and separation of UI, broker and gateway |
| [selvakn/gsm-sip-bridge](https://github.com/selvakn/gsm-sip-bridge) | `4c2ac404cdb27c62ee86931108db7e36198e67b3` | GPL-3.0 | Multi-modem lifecycle; Quectel evidence cannot prove Huawei/ZTE support |
| [boa-z/vowifi-go](https://github.com/boa-z/vowifi-go) | `1e9c6e6adbfcd9667695149d5ecb0f71cd062f07` | AGPL-3.0 | Typed AKA errors, logical channels and lifecycle boundaries |

## Packaged dependencies

PySide6/Qt 6.12.0 is a new runtime dependency, available under LGPL-3.0/GPL-3.0/commercial terms with component-specific licenses. pyserial 3.5 uses BSD terms. PyInstaller 6.16.0 is a build dependency with its GPL bootloader exception. Pillow 11.3.0 is used only to generate original branding artwork. Qt SVG artwork in the UI was authored in this repository.

For redistribution, retain all applicable Qt/PySide and Python runtime notices and make the corresponding runtime source and replacement/relink route available according to the license selected. The repository does not claim that upstream gateway code is permissively licensed or ready for commercial embedding.

Official runtime sources: https://code.qt.io/ and https://github.com/pyserial/pyserial.
