# Huawei E160G integration — hardware validation profile

Device label: Huawei Mobile Connect E160G HSDPA USB Stick (2G/3G). The owner reports network-unlocked firmware; this does not establish CSIM, CRSM, CCHO, CGLA, AKA or PC/SC support.

## Safe integration checklist
1. Connect the E160G directly to a Windows USB port with a test SIM. Do not include IMEI, ICCID, IMSI or serial numbers in exported reports.
2. In NEXVARY USB Studio, scan devices and group interfaces by physical USB ancestry/PnP container, not model text or a guessed VID/PID. Verify the displayed model from Windows PnP descriptors or read-only ATI/AT+CGMM.
3. With user consent, probe eligible AT interfaces in order: AT, ATI, AT+CGMM, AT+CPIN?, AT+CSQ, AT+CREG?, AT+CSIM=?, AT+CRSM=?. Exclude Diagnostics ports by default. Respect timeouts and existing rate limits.
4. Label each result SUPPORTED / REJECTED / UNKNOWN / TIMEOUT based on actual response. AT+CSIM=? success is syntax evidence only; it does not prove an APDU exchange, USIM access or AKA.
5. Permit the existing bounded read-only SELECT MF/EF_DIR diagnostics only through the application's established explicit-consent flow. Do not send PIN/PUK, authentication, write APDUs, SMS, APN changes, firmware flashing, unlock commands or USB mode switching automatically.
6. Verify SIM status, network, reports, redaction, PNG/JSON/CSV exports and wizard navigation. Save only sanitized device capabilities, not subscriber identifiers.
7. Run Windows CI and GUI smoke tests; then perform an owner-supervised physical E160G test before claiming compatibility.

## Compatibility gate
E160G support is **provisional** until a real device is recognized and each requested capability is demonstrated. A network-unlocked 3G modem is not inherently a PC/SC reader. Existing K3770 behavior must remain unchanged.

## Device evidence requested
Sanitized Windows Device Manager hardware IDs (VID/PID and interface MI only), enumerated COM port labels, firmware version (if available), and classified read-only AT responses. Do not collect full device identifiers or raw SIM secrets.

## Owner hardware evidence — 2026-10-17
Owner-supplied screenshot from NEXVARY USB Studio 0.10.2: E160G on COM10, USB VID:PID 12D1:1001, firmware 11.604.18.01.00. SIM ready; SELECT MF returned SW=9000; EF_DIR metadata and five records read; USIM AID discovered and SELECT USIM reported successful. PC/SC transport, AKA, ePDG, IMS and calls remain untested. The screenshot is owner evidence, not independently reproduced by CI. Avoid persisting raw identifiers or authentication material. Next: verify TLV length/record parsing and implement read-only Windows PC/SC transport using a compatible signed user-approved provider; do not silently install drivers.
