# WiFi-Call capability evidence contract

The existing `ModemUsimBackend`, foreground consent, short-lived scoped authorization,
pinned loopback mTLS bridge and audit behavior remain unchanged. This change adds
an independent redacted diagnostic export; it does not expose an APDU service.

Windows: open **التقارير → دليل قدرات WiFi-Call** after inspecting the selected
device. This exports the already collected observations, without sending any
new command. The existing GUI's JSON/CSV reports remain available.

```powershell
python -m nexvary_usim_lab capabilities --port COM5 --export wifi-call-capabilities.json
```

Use `--consent` only if the card owner authorizes the existing fixed SELECT MF
test in addition to the read-only AT probes. The exporter refuses overwrites.
No PIN, AUTHENTICATE, voice call, firmware change or network modification is
performed by this command. Inventory supplies the USB ID; model names never do.

Schema `nexvary.usb.capabilities.v1` includes independent stages `modem_at`,
`card_access`, `apdu`, `usim_aka`, `epdg`, `ims`, `voice_capability`,
`incoming_call`, `outgoing_call`, `two_way_audio`. Each has fixed `state` and
`evidence` strings. States are `observed`, `simulated`, or `not_verified`.
`card_access` from CPIN READY is explicitly only SIM-ready status, not EF access.
SELECT MF with SW=9000 establishes that fixed APDU only. A syntax ACK is never
APDU evidence. Timeout remains inconclusive. All authentication and calling
stages remain `not_verified` in this diagnostic export.

`calling_authorized` and `subscriber_number_available` are always false;
`route_status` is always `Not Verified`. Importers must not turn a report into
authorization, certificate trust or route availability. JSON can be modified
by its owner and is not signed attestation. Live mTLS and consent authorization
still apply separately to each authentication session.

Identity contains only manufacturer, model, firmware and observed USB ID. No
serial port, ICCID, IMSI, IMEI, number, location, raw reply, RAND, AUTN, RES,
CK/IK, Ki or OPc is exported. Injected serial transports must retain the
`simulated` flag. Regression tests verify these boundaries without a real SIM.

The owner's modem is one Huawei K3770, firmware `21.023.04.00.11`, observed USB
ID `12D1:14C9`. Earlier E153 references are not a second physical modem. Existing
owner-supplied field reports establish historical AT/card/SELECT observations;
they are not independent current-session retests and do not establish voice/AKA.
