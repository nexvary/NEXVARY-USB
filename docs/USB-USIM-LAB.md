# NEXVARY USB-USIM Lab: modem recycling / VoWiFi research

## Status
**0.1.0 — local read-only USB modem diagnostics.** No USIM authentication,
actual ePDG tunnel, IMS registration, or call has been verified. No firmware
flashing, SIM state modification or operator bypass takes place.

`repository root` includes Windows/Linux CLI, Tk desktop GUI, optional PC/SC
reader inventory, explicit synthetic demo, redacted JSON/CSV export and mocked
serial-port unit tests. Source commands are restricted to a fixed allow-list
of read-only AT queries. No remote listener or server operation is started.

## Compatibility sources to evaluate separately
- Osmocom pySim: USIM/ISIM exploration; applicable AT/PCSC integration.
- Virtual Smart Card (vpcd): virtual-reader architecture, not an automatic
  modem-to-PC/SC converter.
- fasferraz/USIM-https-server, fasferraz/SWu-IKEv2: architectural comparison;
  do not expose a generic SIM authentication service.
- pagecat/vowifi_gateway: upstream pinned audit already staged in this repo.
- gsm-sip-bridge, vowifi-go, shannon-ims: device and protocol references.
  Their licenses must be verified per component. No code copied here.

## Integration boundary
Future `ModemUsimBackend` must implement the **same fail-closed interface**
needed by `nexvary_aka_backend.py`, but **must not** inherit Android phone
tokens, silently reuse enrollment, replace native IMS, or return sample
vectors. The SIM's long-term keys remain on the card. Credentials, RAND,
AUTN, RES, CK, IK and AUTS must never appear in diagnostic exports.
A local AT+CSIM availability probe is insufficient to claim AKA support.

## Hardware trial checklist
- [ ] Capture modem external model, VID/PID and OS driver
- [ ] Distinguish modem AT serial port from storage/diagnostic ports
- [ ] Verify physical SIM detection without attempting PIN retries
- [ ] Inventory available CSIM/CGLA/CCHO or vendor/QMI APIs
- [ ] Record safe redacted evidence for each modem
- [ ] With authorization, validate UICC application access and challenge path
- [ ] Independently verify carrier entitlement / ePDG / IMS

## Constrained physical APDU evidence
Version 0.1.x supports one optional local, consented `AT+CSIM` SELECT
MF (file 3F00), returning only the last two ISO-7816 status bytes. This
changes only the current file selection (not persistent card data).
It cannot discover ISIM keys or authenticate the subscription and is not
a remotely callable API.
