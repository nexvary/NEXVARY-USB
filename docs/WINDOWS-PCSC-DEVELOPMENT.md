# Windows PC/SC source staging (not an installed reader)

Pinned vsmartcard: 8a411e3672e843f9bb9fd750fc8dc56a26bb3bc8.
Reviewed `virtualsmartcard/win32/BixVReader/VpcdReader.cpp`, `.vcxproj`, `.inf`, `BixVReader.ini`, and shared vpcd wire implementation. Upstream uses UMDF1 1.9 and ATL; a normal Python EXE is not a driver. The upstream default `vicc_init(NULL, port)` listens on the network; it does not connect to NEXVARY's reverse loopback service.

Run `python scripts/prepare_windows_vpcd.py fresh-driver-source` to retain the complete upstream tree and licenses, select a single RPC_TYPE=2 reader on port 35963, change vpcd to connect only to 127.0.0.1, and handle failed initialization without presenting a card. The new directory is separate; no system file, driver, service, certificate store or security policy is modified.

Development build on a suitable Windows WDK/UMDF1 toolchain:

```powershell
msbuild fresh-driver-source/virtualsmartcard/win32/BixVReader/BixVReader.vcxproj /p:Configuration=Release /p:Platform=x64
```

This command is a build recipe, not evidence of a successful build. Current execution host has no WDK/Windows driver runtime or signing certificate. A build must retain original GPL-3.0-or-later terms and copyright; derived driver remains separate from the NEXVARY executable. No built driver is distributed in this release.

Required gates: source preparation → WDK build and static/lifecycle review → approved signing/package validation → authorized installation → native SCardListReaders → connect/ATR → actual card SELECT/GET RESPONSE/READ RECORD → removal, timeout and restart. Do not install upstream default network-listening configuration. No automatic installation, test-signing, certificate injection, Secure Boot changes or replacing system reader definitions.

Direct CSIM remains usable without any Windows PC/SC driver. `scripts/check_field_pcsc.py` supplies the independent native SCard test once a suitable driver is available; it does not infer installation from service state.
