import json
import subprocess
import unittest
from types import SimpleNamespace
from nexvary_usim_lab.core import Port
from nexvary_usim_lab.discovery import detect, to_diagnostic_json, _parse_windows

def fake_runner(stdout="[]", code=0):
    def run(args, **kwargs):
        assert args[0].lower() == "powershell.exe"
        assert kwargs["timeout"] <= 12
        assert kwargs["check"] is False
        return SimpleNamespace(stdout=stdout, returncode=code)
    return run

class DiscoveryTests(unittest.TestCase):
    def test_mass_storage_without_com_is_displayed(self):
        items = [{"Name":"USB Mass Storage Device","Class":"USB","Status":"OK",
                  "InstanceId":"USB\\VID_12D1&PID_1446\\1234567890123456789"}]
        result = detect("Windows", fake_runner(json.dumps(items)), lambda: [])
        self.assertEqual("USB_NO_COM", result.status)
        self.assertEqual("STORAGE_ONLY", result.devices[0].mode)
        self.assertIn("12D1:1446", result.devices[0].usb_id)
        self.assertNotIn("1234567890123456789", to_diagnostic_json(result))
        self.assertNotIn("InstanceId", to_diagnostic_json(result))

    def test_driver_error_and_serial_port(self):
        items = [{"Name":"Vodafone Mobile Broadband","Class":"Unknown","Status":"Error",
                  "InstanceId":"USB\\VID_12D1&PID_14AC\\SENSITIVE_IDENTIFIER"}]
        no_com = detect("Windows", fake_runner(json.dumps(items)), lambda: [])
        self.assertEqual("DRIVER_PROBLEM", no_com.status)
        self.assertEqual("DRIVER_PROBLEM", no_com.devices[0].mode)
        com = Port("COM11", "Huawei Mobile Connect", "Huawei", "12D1", "14AC")
        ready = detect("Windows", fake_runner(json.dumps(items)), lambda: [com])
        self.assertEqual("COM_AVAILABLE", ready.status)
        self.assertEqual("COM11", ready.serial_ports[0].device)

    def test_empty_diagnostics_distinguished_from_failed_query(self):
        empty = detect("Windows", fake_runner(), lambda: [])
        self.assertEqual("NOT_DETECTED", empty.status)
        failed = detect("Windows", fake_runner(code=1), lambda: [])
        self.assertEqual("DIAGNOSTIC_ERROR", failed.status)
        self.assertNotEqual("", failed.diagnostic)

    def test_single_record_and_zte(self):
        device = {"Name":"ZTE MF190S (COM7)","Class":"Ports","Status":"OK",
                  "InstanceId":"USB\\VID_19D2&PID_2000\\REDACT"}
        snap = detect("Windows", fake_runner(json.dumps(device)), lambda: [])
        self.assertEqual(1, len(snap.devices))
        self.assertEqual("SERIAL_CANDIDATE", snap.devices[0].mode)
        self.assertEqual("COM7", snap.devices[0].com_port)
        self.assertNotIn("REDACT", to_diagnostic_json(snap))

    def test_other_usb_devices_are_not_mislabeled(self):
        noise = [{"Name":"Generic USB Root Hub","Class":"USB","Status":"OK",
                  "InstanceId":"USB\\VID_8086&PID_AAAA\\12345678"}]
        self.assertEqual([], _parse_windows(json.dumps(noise)))
        snap = detect("Linux", port_provider=lambda: [])
        self.assertEqual("NOT_DETECTED", snap.status)

    def test_unavailable_powershell(self):
        def fail(*args, **kwargs):
            raise subprocess.TimeoutExpired("powershell.exe", 12)
        snap = detect("Windows", fail, lambda: [])
        self.assertEqual("DIAGNOSTIC_ERROR", snap.status)
        self.assertNotIn("Traceback", snap.diagnostic)

if __name__ == "__main__":
    unittest.main()
