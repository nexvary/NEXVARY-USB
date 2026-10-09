# Reviewed Android contract and Windows 0.6.0

The owner-supplied APK is NEXVARY SIM Manager, package
`com.nexvary.simmanager`, versionName `0.922.0`, versionCode `922`, minimum
Android 9/API 28, target API 35. SHA-256:
`96605bb924f749b8ed180129d96d8c6f987d23c6221592bebd67f724ca488320`.

Review is based on decoded manifest and app-owned DEX method contracts, not on
an original Android source tree. The APK itself and decompiled implementation
are not redistributed in this repository. Debuggable is true; this is not a
validated production Android release. allowBackup and usesCleartextTraffic
are false; CAMERA is the only platform permission declared. No INTERNET or
privileged eUICC-management permission is declared. There is no remote bridge
service. The private EmergencyWalletActivity is a separate medical wallet,
not an eSIM activation-code vault.

## Implemented interoperability

1. Windows accepts the APK parser's `LPA:1$address$matching-id[$oid[$flag]]`
   format, including `1$...` and case-insensitive `lpa:` scheme. Matching ID
   accepts uppercase ASCII letters, digits and hyphen, maximum 1024 characters;
   optional OID accepts dotted decimal, maximum 128 characters; confirmation
   flag is absent, empty, 0 or 1. Total normalized maximum is 2048 characters.
2. User validates and explicitly consents to foreground QR display. The QR
   carries the real entered LPA payload. Scan with the Android app's existing
   camera scanner, then use its confirmation/external-LPA flow. MainActivity
   also advertises ACTION_VIEW `lpa` and ACTION_SEND `text/plain`; Windows does
   not invent a network receiver for these Android intents.
3. Windows decodes one QR from a bounded local image and validates the same
   format. Codes are password-masked, absent from repr/diagnostics, never
   automatically saved, copied or transmitted. QR dialog clears the entry
   after closing. Closing an application releases memory but is not a promise
   of cryptographic memory zeroization. Manually chosen QR source images remain
   in the user's filesystem. Anyone seeing a real QR could use its credential.
4. The phone's RecyclingReportBuilder exports UTF-8 CSV with exactly
   `batch,quantity,classification,condition_score`. Windows imports this exact
   schema, bounds file/rows/values, rejects extra identifiers, spreadsheet
   formulas and duplicate batches. Enum values reviewed: LAB_REUSE,
   MATERIAL_RECYCLE, HOLD_FOR_RECHECK. Source is explicitly phone-reported;
   these records do not prove Windows reader/card state and are excluded from
   modem reports. Scores are limited to 0..100 by the desktop importer.

## Not provided or proven

No original Android Gradle project was supplied, so the original APK cannot be
rebuilt or safely patched from this review. No live phone connection, ADB,
profile download/install/enable/delete, eUICC privileged backend, subscription
migration, Ki/OPc extraction or public APDU API is introduced. The reviewed app
intentionally gates direct eUICC operations pending authorized backend and
live compatibility checks; external LPA handles actual provisioning.

Real validation still requires the phone, an authorized LPA, an owner-provided
activation code, a compatible eUICC and operator permission. Mock contract/QR
and GUI tests do not establish successful provisioning. USB Studio remains
separate from NEXVARY-WiFi-Call; its existing private mutual-TLS AKA contract is
unchanged and live AKA/carrier calling remains unverified.

## Upstream references and licenses

- GSMA SGP.22 v2.3, Annex F activation-code representation:
  https://www.gsma.com/solutions-and-impact/technologies/esim/wp-content/uploads/2021/04/SGP.22-v2.3.pdf
- QR creation: python-qrcode 8.2, BSD-3-Clause core with MIT QR portions;
  https://github.com/lincolnloop/python-qrcode/blob/main/LICENSE
- QR decoding: zxing-cpp 2.3.0, Apache-2.0;
  https://github.com/zxing-cpp/zxing-cpp/tree/v2.3.0/wrappers/python
- Pillow: bundled upstream license. KDE Oxygen full-color icons and existing
  license notices are preserved from the concurrent 0.5.1 release.
