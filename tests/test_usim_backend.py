"""Synthetic AKA responses only; no observed carrier authentication."""
import time,unittest
from nexvary_usim_lab.core import DemoSerial,LabError
from nexvary_usim_lab.usim_backend import ModemUsimBackend,Authorization,parse_aka

TOKEN='T'*40;KEY='device-a';AID='A0000000871002';RAND='11'*16;AUTN='22'*16
class AkaTests(unittest.TestCase):
    def backend(self,factory=DemoSerial,**kwargs):
        args=dict(port='COM7',device_key=KEY,aid=AID,authorization=Authorization(KEY,TOKEN,time.monotonic()+60),token=TOKEN,consent=True,factory=factory);args.update(kwargs);return ModemUsimBackend(**args)
    def test_scoped_and_foreground_authorization(self):
        for kw in ({'consent':False},{'aid':'A0000000000000'},{'token':'short'}):
            with self.assertRaises(LabError):self.backend(**kw)
        b=self.backend(authorization=Authorization('other',TOKEN,time.monotonic()+60))
        with self.assertRaises(LabError):b.authenticate(RAND,AUTN)
        self.assertNotIn(TOKEN,repr(b))
    def test_result_contract_matches_wifi_call(self):
        data=b'\xdb\x08'+bytes(range(8))+b'\x10'+b'c'*16+b'\x10'+b'i'*16
        self.assertEqual(('0001020304050607','63'*16,'69'*16,None),parse_aka(data))
        self.assertEqual((None,None,None,'31'*14),parse_aka(b'\xdc\x0e'+b'1'*14))
        for data in (b'',b'\xdb\x04'+b'x'*20,b'\xdc\x0f'+b'x'*15):
            with self.assertRaises(LabError):parse_aka(data)
    def test_actual_command_path_with_synthetic_transport(self):
        payload=(b'\xdb\x04'+b'resp'+b'\x10'+b'c'*16+b'\x10'+b'i'*16+b'\x90\x00').hex().upper()
        command=f'AT+CGLA=1,80,"018800812210{RAND}10{AUTN}00"'
        class Fake(DemoSerial):
            ANSWERS={f'AT+CCHO="{AID}"':('1','OK'),command:(f'+CGLA: {len(payload)},"{payload}"','OK'),'AT+CCHC=1':('OK',)}
        b=self.backend(Fake);self.assertEqual(('72657370','63'*16,'69'*16),b.authenticate(RAND,AUTN))
        with self.assertRaises(LabError):b.authenticate(RAND,AUTN)
    def test_expired_and_malformed_challenges(self):
        b=self.backend(authorization=Authorization(KEY,TOKEN,time.monotonic()-1))
        with self.assertRaises(LabError):b.authenticate(RAND,AUTN)
        with self.assertRaises(LabError):self.backend().authenticate('11',AUTN)

    def test_optional_kc_is_discarded_from_contract(self):
        data=b'\xdb\x04'+b'resp'+b'\x10'+b'c'*16+b'\x10'+b'i'*16+b'\x08'+b'k'*8
        self.assertEqual(('72657370','63'*16,'69'*16,None),parse_aka(data))
