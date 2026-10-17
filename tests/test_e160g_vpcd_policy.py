"""Regression tests for the existing vpcd adapter, without a modem or driver.

These tests exercise policy denial and ATR control only. They do not establish
Windows PC/SC enumeration or physical E160G compatibility.
"""
import unittest
from unittest.mock import Mock

from nexvary_usim_lab.virtual_reader import VpcdAdapter, TRANSPORT_ATR


class VirtualReaderPolicyTests(unittest.TestCase):
    def setUp(self):
        self.engine = Mock()
        self.engine.ready = True
        self.engine.aids = [bytes.fromhex("A0000000871002")]
        self.adapter = VpcdAdapter(self.engine, emulated_atr=True, session_reset=True)

    def test_unknown_application_not_forwarded(self):
        unknown = bytes.fromhex("00A4040007A0000000010203")
        self.assertEqual(self.adapter.handle(unknown), bytes.fromhex("6A82"))
        self.assertTrue(self.adapter.last_policy_denied)
        self.engine.transmit.assert_not_called()

    def test_identity_get_data_not_forwarded(self):
        self.assertEqual(self.adapter.handle(bytes.fromhex("00CA000000")),
                         bytes.fromhex("6D00"))
        self.engine.transmit.assert_not_called()

    def test_emulated_atr_requires_live_sim_check(self):
        self.engine.session._command.return_value = ("OK", ["+CPIN: READY"])
        self.assertEqual(self.adapter.handle(b"\x04"), TRANSPORT_ATR)
        self.engine.session._command.assert_called_once_with("AT+CPIN?", 4)

    def test_absent_sim_does_not_emit_atr(self):
        self.engine.session._command.return_value = ("OK", ["+CPIN: SIM PIN"])
        with self.assertRaises(Exception):
            self.adapter.handle(b"\x04")
        self.assertFalse(self.adapter.card_verified)

    def test_power_off_disables_apdu(self):
        self.adapter.handle(b"\x00")
        with self.assertRaises(Exception):
            self.adapter.handle(bytes.fromhex("00B0000002"))
        self.engine.transmit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
