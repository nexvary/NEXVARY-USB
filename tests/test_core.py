import json
import unittest
from unittest.mock import patch

from nexvary_usim_lab.core import (
    QUERIES, DemoSerial, LabError, _one_query, demo, probe, redact, to_csv, to_json, select_master_file,
)

class CoreTests(unittest.TestCase):
    def test_no_mutating_queries(self):
        cmds = [q.command for q in QUERIES]
        self.assertEqual(len(cmds), len(set(cmds)))
        for cmd in cmds:
            self.assertTrue(cmd in ("AT",) or cmd.endswith(("?", "=?")) or cmd in ("AT+CGMI", "AT+CGMM", "AT+CGMR", "AT+CCID", "AT+CSQ"))
            self.assertNotIn("CIMI", cmd)
            self.assertNotIn("CPIN=", cmd)
        with self.assertRaises(LabError):
            _one_query(DemoSerial("dummy", 115200), 'AT+CMGS="123"')

    def test_demo_is_explicit_and_identifiers_are_masked(self):
        result = demo()
        self.assertTrue(result.simulated)
        self.assertEqual(len(QUERIES), len(result.readings))
        output = to_json(result)
        self.assertNotIn("89882123456789012345", output)
        self.assertIn("2345", output)
        self.assertIn("OFFLINE-DEMO", output)
        self.assertIn("REJECTED", output)
        self.assertTrue(json.loads(output)["simulated"])

    def test_real_probe_contract_with_injected_serial(self):
        report = probe("COM9", factory=DemoSerial)
        self.assertFalse(report.simulated)
        self.assertEqual("COM9", report.device)
        self.assertEqual("OK", report.readings[0].status)
        self.assertIn("ICCID", to_csv(report))

    def test_refuse_invalid_command_and_port(self):
        for port in ("", "foo\x00bar", "a"*256):
            with self.assertRaises(LabError):
                probe(port, factory=DemoSerial)
        with self.assertRaises(LabError):
            probe("COM5", 0, factory=DemoSerial)

    def test_redaction_and_controls(self):
        self.assertEqual("***********1234", redact("123456789001234"))
        self.assertEqual("prefix ****************2345", redact("prefix 89882123456789012345"))
        self.assertNotIn("\x00", redact("a\x00b"))
        self.assertEqual("no digits", redact("no digits"))

    def test_transport_times_out_and_rejects_errors(self):
        transport = DemoSerial("COM1", 115200)
        state, _ = _one_query(transport, "AT+CGLA=?", deadline_seconds=0.2)
        self.assertEqual("REJECTED", state)
        class NoReply(DemoSerial):
            def readline(self): return b""
        state, _ = _one_query(NoReply("COM1", 115200), "AT", deadline_seconds=0.2)
        self.assertEqual("TIMEOUT", state)

    def test_fixed_select_mf_uicc_no_fcp(self):
        class SelectModem(DemoSerial):
            ANSWERS = dict(DemoSerial.ANSWERS, **{
                'AT+CSIM=14,"00A4000C023F00"': ('+CSIM: 4,"9000"', 'OK')})
        result = select_master_file("COM5", factory=SelectModem)
        self.assertEqual("ACCEPTED", result.status)
        self.assertEqual("SW=9000", result.value)
        self.assertIn("UICC_NO_FCP", result.note)

    def test_invalid_result_length_is_rejected(self):
        class BadReply(DemoSerial):
            ANSWERS = dict(DemoSerial.ANSWERS, **{
                'AT+CSIM=14,"00A4000C023F00"': ('+CSIM: 6,"9000"', 'OK')})
        with self.assertRaises(LabError):
            select_master_file("COM5", factory=BadReply)
    def test_missing_reply_is_not_success(self):
        with self.assertRaises(LabError):
            select_master_file("COM5", factory=DemoSerial)

    def test_pcsc_optional_is_non_mutating(self):
        with patch.dict("sys.modules", {"smartcard": None}):
            from nexvary_usim_lab.core import pcsc_readers
            present, names = pcsc_readers()
            self.assertFalse(present)
            self.assertEqual([], names)

if __name__ == "__main__":
    unittest.main()
