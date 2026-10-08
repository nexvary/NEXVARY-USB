# Modem USIM integration status

Reviewed WiFi-Call `dev/foundation` at `f441b5d4eac7a97f54424bd0035e86d1100be81e`:
`server/engine/nexvary_aka_backend.py` and `server/docs/PHONE-AKA-BRIDGE.md`.
The public `main` branch contains only a README; the actual engine is on dev/foundation.
No changes were made to WiFi-Call or its deployed services.

`ModemUsimBackend` now implements the same callable contract:

- `authenticate_ami(rand_hex, autn_hex)` → `(RES, CK, IK, AUTS)` with one outcome present.
- `authenticate(rand_hex, autn_hex)` → `(RES, CK, IK)` or `(AUTS, None, None)`.
- `identity()` fails closed: redacted diagnostics cannot provide a carrier NAI.

The modem adapter executes locally in-process. It requires current owner consent, an explicit USIM
AID, a random private credential bound to one device and scope, and an authorization
expiry no longer than five minutes. It opens the selected application using CCHO,
sends one constructed USIM AUTHENTICATE over CGLA, handles bounded GET RESPONSE,
validates DB/DC payload structure, then closes the logical channel in `finally`.
Duplicate challenges and more than 32 challenges per session are rejected. `revoke()`
invalidates access. Port ownership is shared with diagnostics and SMS.

There is no API for arbitrary APDUs. No PIN, Ki, OP/OPc, modem unlock or card UPDATE
operation exists. Challenges and results stay in bounded volatile memory and are
not included in reports or repr. Only logical channels 1–3 are currently supported.

## What is not wired or verified

`secure_bridge.py` now provides an opt-in `PrivateUsimBridge` and `BridgeUsimClient`.
The server binds **only 127.0.0.1**, requires a private CA, client certificate,
pinned client certificate hash and the scoped device credential. The client
requires a valid hostname/CA, client certificate and pinned server certificate.
Only `POST /v1/usim/aka` exists; UUID correlation, duplicate-request limits,
request size bounds and deadlines apply. No proxy headers, arbitrary commands,
public bind, automatic certificate creation, persisted secrets or request logs
are provided. Stop/expiry revokes the underlying modem session. Tests run actual
loopback TLS with deliberately public synthetic test certificates and a fake
AKA backend; they do not authenticate a real SIM.

For another machine, forward the loopback endpoint with an independently
provisioned private tunnel and use deployment-specific mTLS certificates. Do not
use the public certificates from `tests/tls-fixtures` outside CI. This release
does not start this service automatically or provision a production session.

**Not deployed or wired:** the current WiFi-Call broker accepts paired phones,
not USB Studio sessions. Broker routing, UI session consent, certificate pairing
and deployment remain to be integrated and audited. The standalone mTLS client
implements the same authenticate/authenticate_ami contract but is not selected
by the existing engine. No live gateway or server service was modified.

The actual K3770 response was SELECT MF `6A86`; that is not an AUTHENTICATE result.
E153/MF190S have label evidence only. CCHO/CGLA support, an accessible USIM AID,
authorized carrier challenges, network entitlement, correct carrier identity,
ePDG/SWu isolation, IMS and calls are independent gates. A synthetic AKA test only
checks software response handling. This release does not claim Wi-Fi Calling.
