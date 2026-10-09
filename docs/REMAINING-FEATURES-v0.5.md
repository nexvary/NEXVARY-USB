# USB Studio 0.5.0: implemented operations and verification gates

This release continues 0.4.0; it does not add real hardware evidence.

## Received SMS

PDU SMS-DELIVER UCS2 (Arabic BMP) and GSM7 decoding, GSM escape characters,
8/16-bit concatenation headers, explicit separate part labels, bounded sizes,
masked senders and mode restoration. Unsupported encodings, compressed SMS and
national GSM shift tables are labelled unsupported. No automatic deletion or
multipart merging. Legacy Text read remains available. Inbox stays local and
is excluded from diagnostics. AT+CMGL may mark messages read on some firmware.

## Cellular data and QMI/MBIM

Windows: WWAN AutoConfig `netsh mbn` inventory, existing profiles, explicit
connect/disconnect on the named interface and subsequent connection status.
Linux: NetworkManager existing GSM profile UUID, GSM device validation,
explicit connection up/disconnect and address/status readback. ModemManager
owns QMI/MBIM protocol serialization, bearer configuration and routing.
The API also provides `modem_status(modem_index)` with a strict status-field
allow-list. No raw QMI/MBIM command terminal is exposed.

These are actual OS controller calls, tested with simulated command runners.
A successful command is not proof of internet connectivity. No system profile,
DNS or route is automatically created/deleted. Windows legacy serial-only
Huawei/ZTE devices may need an existing RAS/vendor dialer: this release does
not implement PPP/RAS dialing or replace their drivers. Raw libqmi/libmbim
binary protocol drivers are not included. Existing profiles can permit roaming;
review their configuration before consenting to a data connection.

Sources consulted (no source copied):
- https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/netsh-mbn
- https://networkmanager.pages.freedesktop.org/NetworkManager/NetworkManager/nmcli.html
- https://www.networkmanager.dev/docs/api/latest/settings-gsm.html

## PC/SC

Native Windows WinSCard reader inventory and exclusive T=0/T=1 fixed SELECT MF,
Arabic status interpretation. Linux optional pyscard with exclusive connection.
Child-process deadline protects the GUI from driver hangs; handles are released
with LEAVE_CARD, without reset or write. Only fixed SELECT is supported; this
is not a generic file editor, authentication endpoint or PIN management tool.
Linux dependency: pyscard and PC/SC service/driver, installed separately.
Reference: https://pyscard.sourceforge.io/user-guide.html

## WiFi-Call integration

The existing engine factory can now explicitly select a standalone USB mTLS
client instead of PhoneAkaBackend. Existing phone configurations remain valid.
The USB client is copied into the reviewed hardened engine stage, without GUI
or repo runtime dependencies. USB Studio offers a foreground opt-in bridge
session, at most 300 seconds, <=32 authentications, revoked on stop. It listens
only on 127.0.0.1; a separately provisioned private tunnel is required between
machines. Certificate CA validation, both peer pins, client certificates and
short-lived scoped token remain mandatory. No arbitrary APDU route exists.

Provisioned certificates/private keys are never generated from public CI
fixtures. Keep configuration and keys in owner-only storage (Linux mode0600;
Windows private owner ACL). Supply an actually discovered USIM AID and proven
AT port; never substitute the K3770 SELECT evidence as proof of authentication.
Run: `python -m nexvary_usim_lab bridge --config /private/session.json --consent`.
The portable EXE accepts the same `bridge --config ... --consent` arguments.

Bridge configuration keys: serial_port, device_key, aid, token, server_cert,
server_key, client_ca, client_pin, port. Token is a freshly provisioned random
32–128 character base64url value matching the engine configuration; port must
be an explicit 1–65535 loopback port. Do not put secrets in command-line args.

Engine private configuration keys: backend="usb", port, device_key, token,
server_ca, client_cert, client_key, server_pin; optional identity is an explicitly
owner/operator-provisioned carrier NAI. Neither project extracts IMSI/Ki/OPc or
invents an identity. `NEXVARY_ENGINE_AUTH_FILE` selects the owned mode0600 file.

Hardware/operator gates still required: real CCHO/CGLA support, actual USIM AKA
SUCCESS or SYNC_FAILURE, authorized subscriber NAI, ePDG reachability, entitlement,
IKEv2/IPsec, IMS registration, incoming/outgoing calls and audio. No call server
or user's deployed WiFi-Call installation was changed. No claimed successful
call or live carrier authentication is contained in this release.
