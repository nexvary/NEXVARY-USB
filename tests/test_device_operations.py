import unittest
from nexvary_usim_lab.core import LabError, DemoSerial
from nexvary_usim_lab.device_operations import ATSession, _parse_crsm, ICCID_FILE

class TestSIMOperations(unittest.TestCase):
    def test_sim_read_suppresses_full_ef(self):
        r = _parse_crsm(['+CRSM: 144,0,"98123456789012345678"'])
        self.assertEqual("READABLE", r.status)
        self.assertNotIn("981234", r.value)
        self.assertEqual("CARD_STATUS", _parse_crsm(["+CRSM: 106,130"]).status)

    def test_card_read_realistic_emulator(self):
        class Fake(DemoSerial):
            ANSWERS = dict(DemoSerial.ANSWERS, **{ICCID_FILE: ('+CRSM: 144,0,"98123456789012345678"', 'OK')})
        with ATSession("COM7", factory=Fake) as session:
            self.assertEqual("READABLE", session.sim_file_check().status)

    def test_sms_safety(self):
        with self.assertRaises(LabError):
            with ATSession("COM7", factory=DemoSerial) as s:
                s.send_sms("+201000000000", "Test", confirmed=False)
        with self.assertRaises(LabError):
            with ATSession("COM7", factory=DemoSerial) as s:
                s.send_sms("+201000000000\rAT+CFUN=1", "Test", confirmed=True)
        with self.assertRaises(LabError):
            with ATSession("COM7", factory=DemoSerial) as s:
                s.send_sms("+201000000000", "عربي", confirmed=True)

    def test_valid_sms_submission(self):
        class SMSFake(DemoSerial):
            ANSWERS = dict(DemoSerial.ANSWERS, **{
                "AT+CMGF=1": ("OK",), 'AT+CSCS="GSM"': ("OK",),
                'AT+CMGS="+201000000000"': (">",)})
            def write(self, payload):
                if payload.endswith(b"\x1a"):
                    self.pending = [b'+CMGS: 27\r\n', b'OK\r\n']
                else:
                    super().write(payload)
        with ATSession("COM7", factory=SMSFake) as s:
            self.assertIn("reference 27",s.send_sms("+201000000000", "Hello", True))

    def test_invalid_path(self):
        for path in ("", "COM0", "COM1\nAT+CFUN=1", "file.txt"):
            with self.assertRaises(LabError):
                ATSession(path, factory=DemoSerial)

if __name__ == "__main__":
    unittest.main()
