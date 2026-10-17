# Windows Virtual PC/SC delivery gates — Huawei E160G

The read-only gateway is a *transport policy*, not a Windows PC/SC driver. It accepts only short case-2 basic-channel READ BINARY (B0), READ RECORD (B2, absolute), and GET RESPONSE (C0) APDUs. It refuses SELECT, AUTHENTICATE, PIN, UPDATE, proprietary CLA and extended APDUs. Card selection must remain in the existing consented diagnostic session; no generic PC/SC exposure is implied.

## Ordered engineering gates (19)
1. [x] Register E160G field evidence (COM10, 12D1:1001, firmware).
2. [x] Preserve K3770 evidence separately.
3. [x] Record successful SELECT MF without treating it as AKA.
4. [x] Record EF_DIR metadata and five-record read.
5. [x] Record successful USIM application selection.
6. [x] Define conservative APDU allowlist.
7. [x] Reject PIN, AUTHENTICATE and writes.
8. [x] Bound APDU length and response size.
9. [x] Add synthetic unit tests for accepted commands.
10. [x] Add synthetic unit tests for rejected commands.
11. [x] Add synthetic unit tests for malformed transport responses.
12. [ ] Verify EF_DIR TLV parsing against sanitized physical captures.
13. [ ] Integrate gateway with existing CSIM/TPDU transport without bypassing user consent.
14. [ ] Implement session lifecycle, timeout and disconnect recovery.
15. [ ] Select a trusted compatible Windows PC/SC reader provider; no driver installation without explicit consent.
16. [ ] Implement provider adapter and enumerate reader through Windows SCard API.
17. [ ] Run unit tests and Windows CI smoke/build with captured logs.
18. [ ] Perform owner-supervised E160G read-only PC/SC hardware test.
19. [ ] Produce verified signed or appropriately disclosed unsigned portable EXE/installer with checksums.

## Evidence boundaries
Owner screenshot proves modem diagnostics only. It does not establish Windows PC/SC reader registration, a successful PC/SC APDU, AKA, ePDG, IMS or calls. No existing Windows driver is installed by these commits. No build has been run as part of these changes.

## Test commands
```bash
python -m unittest tests.test_readonly_apdu_gateway -v
python -m unittest discover -s tests -v
```
