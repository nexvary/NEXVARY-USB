import unittest

from nexvary_usim_lab.readonly_apdu_gateway import (
    ApduRejected, ReadOnlyApduGateway, ReadOnlyApduPolicy,
)

class ReadOnlyApduTests(unittest.TestCase):
    def test_read_binary(self):
        self.assertEqual(ReadOnlyApduPolicy().validate(bytes.fromhex("00B0000020")),
                         bytes.fromhex("00B0000020"))

    def test_read_record(self):
        self.assertEqual(ReadOnlyApduPolicy().validate(bytes.fromhex("00B2010421")),
                         bytes.fromhex("00B2010421"))

    def test_get_response(self):
        ReadOnlyApduPolicy().validate(bytes.fromhex("00C000000F"))

    def test_reject_mutation_and_auth(self):
        for apdu in ("0020000000", "0088000000", "00D6000001",
                     "00DC000001", "00A4000000", "00B000000101",
                     "80B0000001", "00B2010501", "00C0010001"):
            with self.subTest(apdu=apdu), self.assertRaises(ApduRejected):
                ReadOnlyApduPolicy().validate(bytes.fromhex(apdu))

    def test_gateway_response_and_bounds(self):
        gw = ReadOnlyApduGateway(lambda _: bytes.fromhex("DEAD9000"))
        self.assertEqual(gw.transmit(bytes.fromhex("00B0000002")), bytes.fromhex("DEAD9000"))
        with self.assertRaises(ValueError):
            ReadOnlyApduGateway(lambda _: b"\x90").transmit(bytes.fromhex("00B0000001"))
        with self.assertRaises(ValueError):
            ReadOnlyApduGateway(lambda _: b"X" * 259).transmit(bytes.fromhex("00B0000001"))

if __name__ == "__main__":
    unittest.main()
