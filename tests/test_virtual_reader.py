"""Real loopback vpcd frames, synthetic modem; no PC/SC OS daemon here."""
import socket,struct,time,unittest
from nexvary_usim_lab.virtual_reader import VirtualReaderService
from nexvary_usim_lab.core import DemoSerial,LabError
class Modem(DemoSerial):
    ANSWERS={'AT+CPIN?':('+CPIN: READY','OK'),'AT+CSIM=14,"00A4000C023F00"':('+CSIM: 4,"9000"','OK')}
class ReaderTests(unittest.TestCase):
    def service(self,**kw):
        s=VirtualReaderService('COM9',0,True,True,True,kw.get('factory',Modem),kw.get('lifetime',5));s.start();self.addCleanup(s.stop);return s
    def frame(self,peer,data):peer.sendall(struct.pack('!H',len(data))+data)
    def receive(self,peer):
        header=peer.recv(2);self.assertEqual(len(header),2)
        length=struct.unpack('!H',header)[0];return peer.recv(length)
    def test_real_loopback_discovery_transmit_and_stop(self):
        s=self.service();self.assertEqual(s.listener.getsockname()[0],'127.0.0.1')
        peer=socket.create_connection(('127.0.0.1',s.vpcd_port),timeout=2);self.addCleanup(peer.close)
        self.frame(peer,b'\x04');self.assertEqual(self.receive(peer),b'\x3b\x00')
        self.frame(peer,bytes.fromhex('00A4000C023F00'));self.assertEqual(self.receive(peer),b'\x90\x00')
        s.stop();self.assertEqual(peer.recv(1),b'');self.assertFalse(s.thread.is_alive())
        self.assertNotIn('9000',repr(s.audit));self.assertNotIn('RAND',repr(s.audit))
    def test_unauthorized_auth_removes_virtual_card(self):
        s=self.service();peer=socket.create_connection(('127.0.0.1',s.vpcd_port),timeout=2);self.addCleanup(peer.close)
        self.frame(peer,b'\x04');self.receive(peer)
        self.frame(peer,bytes.fromhex('0088008101AA'));self.assertEqual(peer.recv(1),b'')
        s.thread.join(1);self.assertEqual(s.state,'UNAVAILABLE')
    def test_reconnect_requires_new_local_start(self):
        s=self.service();peer=socket.create_connection(('127.0.0.1',s.vpcd_port),timeout=2)
        self.frame(peer,b'\x04');self.receive(peer);peer.close();s.thread.join(1)
        self.assertFalse(s.thread.is_alive())
        s.vpcd_port=0 # a fresh allocated pair; do not assume OS TIME_WAIT reuse
        s.start();peer=socket.create_connection(('127.0.0.1',s.vpcd_port),timeout=2);self.addCleanup(peer.close)
        self.frame(peer,b'\x04');self.assertEqual(self.receive(peer),b'\x3b\x00')
    def test_companion_slot_is_absent_not_second_card(self):
        s=self.service();peer=socket.create_connection(('127.0.0.1',s.vpcd_port+1),timeout=2);self.addCleanup(peer.close)
        self.frame(peer,b'\x04');self.assertEqual(self.receive(peer),b'')
        self.assertEqual(s.absent_listener.getsockname()[0],'127.0.0.1')
        s.stop();self.assertFalse(s.absent_thread.is_alive())
    def test_no_consent_and_occupied_port(self):
        with self.assertRaises(LabError):VirtualReaderService('COM9')
        s=self.service()
        other=VirtualReaderService('COM10',s.vpcd_port,True,True,True,Modem)
        with self.assertRaises(LabError):other.start()
    def test_card_not_ready_cannot_return_atr(self):
        class Locked(Modem):ANSWERS={'AT+CPIN?':('+CPIN: SIM PIN','OK')}
        s=self.service(factory=Locked);peer=socket.create_connection(('127.0.0.1',s.vpcd_port),timeout=2);self.addCleanup(peer.close)
        try:self.frame(peer,b'\x04');self.assertEqual(peer.recv(3),b'')
        except (ConnectionResetError,ConnectionAbortedError):pass
        s.thread.join(1);self.assertEqual(s.state,'UNAVAILABLE')
    def test_consent_expiration_waiting(self):
        s=self.service(lifetime=1);s.thread.join(2);self.assertFalse(s.thread.is_alive());self.assertEqual(s.state,'EXPIRED')
