"""Synthetic per-port regression, no modem, SIM or operator in test."""
import unittest
from nexvary_usim_lab.core import DemoSerial, Port, LabError, Reading
from nexvary_usim_lab.grouping import ModemDevice
from nexvary_usim_lab.capability_matrix import compare_ports
from nexvary_usim_lab.ui_results import ui_reading

def device():
    return ModemDevice("synthetic-key", "Huawei K3770 (synthetic fixture)", [], [
        Port("COM7", "Vodafone Secondary Modem", "Huawei", "12D1", "14C9"),
        Port("COM5", "Vodafone Primary Modem", "Huawei", "12D1", "14C9"),
        Port("COM6", "Vodafone Diagnostics", "Huawei", "12D1", "14C9"),
    ])

class SessionModem(DemoSerial):
    def __init__(self, port, speed):
        super().__init__(port, speed)
        self.port = port
    def write(self, message):
        super().write(message)
        cmd = message.decode("ascii").strip()
        if self.port == "COM7" and cmd in ("AT+CPIN?", "AT+CSQ", "AT+CREG?"):
            self.pending = [b"ERROR\r\n"]
        if cmd == "AT+CREG?" and self.port == "COM5":
            self.pending = [b'+CREG: 2,1,"PRIVATE_CELL","SECRET"\r\n',b"OK\r\n"]
        if cmd == "AT+CSIM=?":
            self.pending = [b"OK\r\n"]

class MatrixTests(unittest.TestCase):
    def test_prefers_card_port_and_excludes_diagnostics(self):
        result = compare_ports(device(), factory=SessionModem, deadline_seconds=0.2)
        self.assertEqual("COM5", result.suggested_port)
        self.assertTrue(result.sim_verified)
        self.assertEqual({"COM7", "COM5"}, {p.port for p in result.ports})
        self.assertEqual("REJECTED", next(p for p in result.ports if p.port=="COM7").sim)
        self.assertEqual("RESPONSIVE", next(p for p in result.ports if p.port=="COM5").sim)
        self.assertEqual("ACK_ONLY", next(p for p in result.ports if p.port=="COM5").csim_syntax)
        self.assertNotIn("PRIVATE_CELL", repr(result))
        self.assertNotIn("SECRET", repr(result))

    def test_at_only_does_not_prove_usim(self):
        class ATOnly(SessionModem):
            def write(self, data):
                super().write(data)
                if data.decode().strip() in ("AT+CPIN?", "AT+CSQ", "AT+CREG?"):
                    self.pending = [b"ERROR\r\n"]
        result = compare_ports(device(), factory=ATOnly, max_ports=1, deadline_seconds=0.2)
        self.assertEqual("COM5", result.suggested_port)
        self.assertFalse(result.sim_verified)
        self.assertIn("لا يعني تلف", result.summary)

    def test_connection_error_is_not_sim_failure(self):
        class Disconnected(SessionModem):
            def write(self,data):
                super().write(data)
                if data == b"AT\r":
                    self.pending=[b"ERROR\r\n"]
        result=compare_ports(device(),factory=Disconnected,deadline_seconds=0.2)
        self.assertIsNone(result.suggested_port)
        self.assertFalse(result.sim_verified)
        self.assertEqual("NOT_TESTED",result.ports[0].sim)

    def test_parameters_restricted(self):
        for limit in (0,9,True):
            with self.assertRaises(LabError):compare_ports(device(), max_ports=limit)
        with self.assertRaises(LabError):compare_ports(device(), deadline_seconds=60)

    def test_ui_arabic_and_no_permanent_unsupported_claim(self):
        name,status,note=ui_reading(Reading("SIM status","REJECTED","Modem rejected this command","Read status"))
        self.assertEqual(("حالة الشريحة","رُفض الأمر"),(name,status))
        self.assertIn("الجلسة الحالية",note)
        for code in ("TIMEOUT","MODEM_ERROR","UNSUPPORTED"):
            self.assertNotIn("غير مدعوم نهائيًا", ui_reading(Reading("SIM applications",code,"",""))[2])
        self.assertIn("لا",ui_reading(Reading("CSIM probe","OK","OK",""))[2])
