Historical 0.4.0 report. For the current release see [0.5.0 operations](REMAINING-FEATURES-v0.5.md).

# NEXVARY USB Studio 0.4.0 — implementation and verification

## Implemented

- Qt Arabic RTL GUI with native text shaping, original vector icons, six pages,
  Back navigation, adaptive sidebar and scrollable controls/tables.
- Windows PnP container and physical USB parent-chain discovery, COM registry
  mapping and driver version inventory. One grouped card per proven physical device.
  VID/PID alone never merges modems; unresolved interfaces remain separate.
- Device-scoped bounded AT discovery. Diagnostics ports excluded from automatic
  candidates, explicit advanced testing available. Last working port saved locally.
- Process-wide nonblocking serial leases cover probe, APDU, SMS and AKA operations.
- SIM/PIN state, masked ICCID, bounded EF_DIR application inventory and fixed MF
  SELECT variants, retaining K3770 `6A86` regression evidence.
- One explicitly confirmed ASCII SMS; opt-in experimental BMP/UCS2 SMS-SUBMIT PDU,
  70-character limit, input injection rejection and SMS mode restoration.
- Local text inbox with masked sender; no message contents in device reports.
- Network signal/registration/operator/APN/context queries, explicit APN changes
  only after proving an inactive context, then verifying by read-back.
- Extensible JSON evidence profiles for Huawei K3770/E153 and ZTE MF190S.
- Opt-in private loopback mTLS bridge/client with pinned peers, scoped credentials,
  deadlines, revocation and real TLS transport tests using synthetic AKA results.
- In-process consent and authorization-gated ModemUsimBackend compatible with the
  WiFi-Call callable result contract. See USIM-INTEGRATION.md for integration limits.
- JSON/CSV reports, optional PC/SC reader enumeration, branded Inno Setup packaging,
  stable upgrade AppId, shortcuts and uninstall preserving user settings.

## Software evidence

Tests use injected serial/PnP fixtures, never physical hardware fallback. Existing
K3770 reported observations are retained as reported evidence, not re-measured.
GUI verification creates screenshots from running Qt at four physical resolutions
and three scale factors (72 page cases per operating system), plus synthetic
multi-modem cards and Back navigation. Packaged Windows verification installs,
starts the EXE and opens six pages, upgrades from the actual 0.3.1 installer, removes the program, and verifies a
user-settings sentinel survived. Runner DPI simulation is not a physical monitor
or GPU/driver test. No USB modem or SIM is attached to CI.

## Remaining hardware and integration gates

- Re-test actual K3770 grouping/COM selection, firmware and each SELECT variant.
- E153/MF190S exact IDs, drivers, firmware, supported interfaces and commands.
- Real UCS2 send/delivery, inbound Arabic PDU decoding and modem SMS mode behavior.
- EF_DIR and application access on each card; logical-channel AKA with operator
  challenge, entitlement and carrier identity. SELECT success does not prove AKA.
- Production certificate pairing, broker modem routing, user-facing AKA consent
  and live WiFi-Call integration. Private mTLS transport itself is implemented.
- QMI/MBIM command transports, PC/SC APDU operations and automatic cellular-data
  connection are not implemented; interface inventory is not operational support.
- Real Windows 10/11 install/display-scaling checks, hardware unplug races and
  antimalware/code-signing deployment checks. Executables are not code-signed.

No automatic USB driver installation, firmware write, SIM modification, carrier
bypass, file association changes, background messages or public APDU endpoint.
