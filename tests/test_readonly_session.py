import unittest
from nexvary_usim_lab.readonly_session import ReadOnlySession, SessionClosed

READ = bytes.fromhex("00B0000002")

class ReadOnlySessionTests(unittest.TestCase):
    def test_consent_required_and_closed_by_default(self):
        session = ReadOnlySession(lambda _: bytes.fromhex("ABCD9000"))
        with self.assertRaises(SessionClosed):
            session.transmit(READ)
        with self.assertRaises(PermissionError):
            session.open(consent=False)
        self.assertFalse(session.status().connected)

    def test_open_transmit_close(self):
        session = ReadOnlySession(lambda _: bytes.fromhex("ABCD9000"))
        self.assertEqual(session.open(consent=True).generation, 1)
        self.assertEqual(session.transmit(READ), bytes.fromhex("ABCD9000"))
        with self.assertRaises(RuntimeError):
            session.open(consent=True)
        session.close()
        with self.assertRaises(SessionClosed):
            session.transmit(READ)
        self.assertEqual(session.open(consent=True).generation, 2)

    def test_disconnect_fail_closed(self):
        def disconnected(_):
            raise ConnectionError("modem unplugged")
        session = ReadOnlySession(disconnected)
        session.open(consent=True)
        with self.assertRaises(ConnectionError):
            session.transmit(READ)
        self.assertFalse(session.status().connected)
        with self.assertRaises(SessionClosed):
            session.transmit(READ)

    def test_timeout_fail_closed(self):
        session = ReadOnlySession(lambda _: (_ for _ in ()).throw(TimeoutError()))
        session.open(consent=True)
        with self.assertRaises(TimeoutError):
            session.transmit(READ)
        self.assertFalse(session.status().connected)

if __name__ == "__main__":
    unittest.main()
