import unittest
from nexvary_usim_lab.core import LabError
from nexvary_usim_lab.virtual_sim import CsimTransport, VirtualCardEngine, TransportFailure, directory_metadata
from nexvary_usim_lab.virtual_reader import VpcdAdapter

AID = bytes.fromhex('A0000000871002')
RECORD = bytes.fromhex('61094F07A0000000871002')
FCP = bytes.fromhex('620B82054221000B0183022F00')
class ScriptSession:
    def __init__(self, responses): self.responses=list(responses); self.sent=[]
    def _command(self, value, duration):
        self.sent.append(value)
        result=self.responses.pop(0)
        if isinstance(result,tuple): return result
        return 'OK',[f'+CSIM: {len(result)},"{result}"']
class TransportTests(unittest.TestCase):
    def test_t0_case4_and_continuation_accumulate(self):
        s=ScriptSession(['AA6102','BBCC9000']); t=CsimTransport(s)
        r=t.exchange(bytes.fromhex('00A4040407A000000087100200'))
        self.assertEqual(r.data,bytes.fromhex('AABBCC'))
        self.assertEqual(s.sent[0],'AT+CSIM=24,"00A4040407A0000000871002"')
        self.assertEqual(s.sent[1],'AT+CSIM=10,"00C0000002"')
    def test_6c_only_read_never_auth(self):
        s=ScriptSession(['6C10']); t=CsimTransport(s)
        self.assertEqual(t.exchange(bytes.fromhex('0088008101AA00')).sw,bytes.fromhex('6C10'))
        self.assertEqual(len(s.sent),1)
        s=ScriptSession(['6C02','AABB9000']); t=CsimTransport(s)
        self.assertEqual(t.exchange(bytes.fromhex('00C0000001')).data,b'\xaa\xbb')
    def test_timeout_never_retries_and_blocks_late_reply(self):
        s=ScriptSession([('TIMEOUT',[]),'9000']); t=CsimTransport(s)
        with self.assertRaises(TransportFailure): t.exchange(bytes.fromhex('0088008101AA00'))
        with self.assertRaises(TransportFailure): t.send(bytes.fromhex('00C0000001'))
        self.assertEqual(len(s.sent),1)
    def test_bad_length_and_duplicate_reply(self):
        for reply in [('OK',['+CSIM: 6,"9000"']),('OK',['+CSIM: 4,"9000"']*2),('OK',[])]:
            with self.subTest(reply=reply):
                with self.assertRaises(TransportFailure): CsimTransport(ScriptSession([reply])).send(bytes.fromhex('00A4000C023F00'))
    def test_directory_and_adf(self):
        s=ScriptSession([('OK',['+CPIN: READY']),'9000','9000',FCP.hex()+'9000',RECORD.hex()+'9000','9000'])
        e=VirtualCardEngine(s); e.initialize()
        self.assertEqual(e.discover_applications(),[AID])
        self.assertEqual(e.select_aid(AID).sw,b'\x90\x00')
        self.assertTrue(all('ATZ' not in x and 'CCHO' not in x for x in s.sent))
    def test_no_unknown_ef_pin_auth_channel_or_aid(self):
        s=ScriptSession([('OK',['+CPIN: READY']),'9000']); e=VirtualCardEngine(s);e.initialize()
        for apdu in ('002000010431323334','0088008101AA','0070000001','00A40004026F07','00A4040407A0000000871002','01A4000C023F00','00B201040B'):
            with self.subTest(apdu=apdu):
                with self.assertRaises(LabError): e.transmit(bytes.fromhex(apdu))
        self.assertEqual(len(s.sent),2)
    def test_pin_required_not_card(self):
        s=ScriptSession([('OK',['+CPIN: SIM PIN'])]);e=VirtualCardEngine(s)
        with self.assertRaises(TransportFailure):e.initialize()
        self.assertFalse(e.ready);self.assertEqual(len(s.sent),1)
    def test_fcp_identity_and_partial_metadata(self):
        self.assertEqual(directory_metadata(FCP),(11,1))
        for data in (FCP[:-1],FCP.replace(b'\x2f\x00',b'\x6f\x07'),b''):
            with self.assertRaises(LabError):directory_metadata(data)
    def test_continuation_bounded(self):
        s=ScriptSession(['6101']*10);t=CsimTransport(s)
        with self.assertRaises(TransportFailure):t.exchange(bytes.fromhex('00C0000001'))
        self.assertTrue(t.failed)
    def test_virtual_atr_opt_in_and_actual_get_response(self):
        s=ScriptSession([('OK',['+CPIN: READY']),'9000',('OK',['+CPIN: READY']),FCP.hex()+'9000',('OK',['+CPIN: READY']),'9000',('OK',['+CPIN: READY'])])
        e=VirtualCardEngine(s);e.initialize()
        with self.assertRaises(LabError):VpcdAdapter(e)
        a=VpcdAdapter(e,True,True)
        self.assertEqual(a.handle(b'\x04'),b'\x3b\x00')
        self.assertEqual(a.handle(bytes.fromhex('00A40004022F0000')),bytes([0x61,len(FCP)]))
        self.assertEqual(a.handle(bytes([0,0xc0,0,0,len(FCP)])),FCP+b'\x90\x00')
        with self.assertRaises(LabError):a.handle(bytes.fromhex('00C0000001'))
        a.handle(b'\x00')
        with self.assertRaises(LabError):a.handle(b'\x04')
        a.handle(b'\x01');self.assertEqual(a.handle(b'\x04'),b'\x3b\x00')
if __name__=='__main__':unittest.main()
