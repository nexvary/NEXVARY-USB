import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from nexvary_usim_lab.core import Report, Reading, LabError
from nexvary_usim_lab.wificall_capabilities import export_capabilities, STAGES
from nexvary_usim_lab.__main__ import main


class WiFiCallCapabilityTests(unittest.TestCase):
    def report(self, simulated=False):
        return Report("NEXVARY USB Studio", "0.8.1", "2026-10-09T16:00:00+00:00",
                      "COM5", simulated, [
            Reading("Connection", "OK", "OK", ""),
            Reading("Manufacturer", "OK", "huawei", ""),
            Reading("Model", "OK", "K3770", ""),
            Reading("Firmware", "OK", "21.023.04.00.11", ""),
            Reading("SIM status", "OK", "+CPIN: READY", ""),
            Reading("CSIM probe", "OK", "OK", ""),
            Reading("CCHO probe", "TIMEOUT", "SECRET", ""),
            Reading("ICCID", "OK", "89123456789012345678", ""),
        ])

    def test_stages_remain_independent_and_secrets_absent(self):
        result = export_capabilities(self.report(), usb_id="12d1:14c9")
        self.assertEqual(set(STAGES), set(result["stages"]))
        self.assertEqual("observed", result["stages"]["modem_at"]["state"])
        self.assertEqual("observed", result["stages"]["card_access"]["state"])
        for stage in STAGES[2:]:
            self.assertEqual("not_verified", result["stages"][stage]["state"])
        self.assertFalse(result["calling_authorized"])
        self.assertFalse(result["subscriber_number_available"])
        self.assertEqual("K3770", result["identity"]["model"])
        self.assertEqual("12D1:14C9", result["identity"]["usb_id"])
        wire = json.dumps(result)
        self.assertNotIn("SECRET", wire)
        self.assertNotIn("89123456789012345678", wire)
        self.assertNotIn("COM5", wire)

    def test_select_mf_never_proves_aka_or_calls(self):
        selected = Reading("APDU SELECT MF", "ACCEPTED", "SW=9000", "")
        result = export_capabilities(self.report(), select_mf=selected)
        self.assertEqual("observed", result["stages"]["apdu"]["state"])
        self.assertEqual("not_verified", result["stages"]["usim_aka"]["state"])
        self.assertEqual("Not Verified", result["route_status"])

    def test_simulated_results_cannot_be_physical_evidence(self):
        result = export_capabilities(self.report(True), select_mf=Reading("APDU SELECT MF", "ACCEPTED", "SW=9000", ""))
        for stage in ("modem_at", "card_access", "apdu"):
            self.assertEqual("simulated", result["stages"][stage]["state"])
        self.assertTrue(result["simulated"])

    def test_malformed_select_and_at_ack_are_inconclusive(self):
        result = export_capabilities(self.report(), select_mf=Reading("APDU SELECT MF", "ACCEPTED", "OK", ""))
        self.assertEqual("not_verified", result["stages"]["apdu"]["state"])
        self.assertIsNone(result["identity"]["usb_id"])

    def test_identity_injection_and_invalid_inventory_rejected(self):
        report = self.report()
        report.readings.append(Reading("Model", "OK", "K3770\nKi=SECRET", ""))
        self.assertIsNone(export_capabilities(report)["identity"]["model"])
        with self.assertRaises(LabError):
            export_capabilities(report, usb_id="12D1:14C9 SECRET")
        report.readings.append(Reading("Model", "OK", "IMSI 89123456789012345678", ""))
        self.assertIsNone(export_capabilities(report)["identity"]["model"])

    def test_cli_export_uses_inventory_without_authorizing_calls(self):
        from nexvary_usim_lab.core import Port
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "capabilities.json"
            with patch("nexvary_usim_lab.__main__.probe", return_value=self.report(True)), \
                 patch("nexvary_usim_lab.__main__.ports", return_value=[Port("COM5", "modem", "huawei", "12D1", "14C9")]), \
                 patch("nexvary_usim_lab.__main__.select_master_file") as select, patch("builtins.print"):
                self.assertEqual(0, main(["capabilities", "--port", "COM5", "--export", str(target)]))
                select.assert_not_called()
                data = json.loads(target.read_text())
                self.assertTrue(data["simulated"])
                self.assertFalse(data["calling_authorized"])
                before = target.read_bytes()
                self.assertEqual(2, main(["capabilities", "--port", "COM5", "--export", str(target)]))
                self.assertEqual(before, target.read_bytes())

    def test_cli_fixed_select_requires_explicit_consent(self):
        selected = Reading("APDU SELECT MF", "ACCEPTED", "SW=9000", "")
        with patch("nexvary_usim_lab.__main__.probe", return_value=self.report(True)), \
             patch("nexvary_usim_lab.__main__.ports", return_value=[]), \
             patch("nexvary_usim_lab.__main__.select_master_file", return_value=selected) as select, patch("builtins.print"):
            self.assertEqual(0, main(["capabilities", "--port", "COM5", "--consent"]))
            select.assert_called_once_with("COM5", 115200)


if __name__ == "__main__":
    unittest.main()
