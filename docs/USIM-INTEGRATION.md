# Modem USIM integration status

Reviewed WiFi-Call `dev/foundation` at `f441b5d4eac7a97f54424bd0035e86d1100be81e`:
`server/engine/nexvary_aka_backend.py` and `server/docs/PHONE-AKA-BRIDGE.md`.
The public `main` branch contains only a README; the actual engine is on dev/foundation.
No changes were made to WiFi-Call or its deployed services.

`ModemUsimBackend` now implements the same callable contract:

- `authenticate_ami(rand_hex, autn_hex)` → `(RES, CK, IK, AUTS)` with one outcome present.
- `authenticate(rand_hex, autn_hex)` → `(RES, CK, IK)` or `(AUTS, None, None)`.
- `identity()` fails closed: redacted diagnostics cannot provide a carrier NAI.

Execution is local in-process. It requires current owner consent, an explicit USIM
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

This adapter is not a deployed WiFi-Call broker backend. The current broker accepts
paired phones, not USB Studio sessions. Remote pairing, mTLS transport, broker modem
routing, user-facing AKA consent lifecycle and remote revocation remain to be built
and reviewed before this adapter can be called across machines. No network service
is started, so no unencrypted network transmission is introduced by this release.

The actual K3770 response was SELECT MF `6A86`; that is not an AUTHENTICATE result.
E153/MF190S have label evidence only. CCHO/CGLA support, an accessible USIM AID,
authorized carrier challenges, network entitlement, correct carrier identity,
ePDG/SWu isolation, IMS and calls are independent gates. A synthetic AKA test only
checks software response handling. This release does not claim Wi-Fi Calling.
