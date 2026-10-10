"""Explicitly synthetic on-card responses, not carrier AKA evidence."""
import time,unittest
from nexvary_usim_lab.core import DemoSerial,LabError
from nexvary_usim_lab.usim_backend import CsimUsimBackend, Authorization
from test_virtual_sim import FCP,RECORD,AID
RAND='11'*16; AUTN='22'*16; TOKEN='T'*40
class CsimAkaTests(unittest.TestCase):
    def backend(self,state='OK',aids=RECORD,seconds=60):
        payload=(b'\xdb\x04resp\x10'+b'c'*16+b'\x10'+b'i'*16+b'\x90\x00').hex().upper()
        def response(x):return (f'+CSIM: {len(x)},"{x}"','OK')
        class Fake(DemoSerial):
            commands=[]
            ANSWERS={'AT+CPIN?':('+CPIN: READY','OK'),
                'AT+CSIM=14,"00A4000C023F00"':response('9000'),
                'AT+CSIM=14,"00A40004022F00"':response(FCP.hex().upper()+'9000'),
                'AT+CSIM=10,"00B201040B"':response(aids.hex().upper()+'9000'),
                'AT+CSIM=24,"00A4040407A0000000871002"':response('9000'),
                f'AT+CSIM=78,"008800812210{RAND}10{AUTN}"':response(payload) if state=='OK' else ('ERROR',)}
            def write(self,value):self.commands.append(value);return super().write(value)
        self.fake=Fake
        return CsimUsimBackend('COM9','device',AID.hex().upper(),Authorization('device',TOKEN,time.monotonic()+seconds),TOKEN,True,Fake)
    def test_basic_channel_without_ccho(self):
        b=self.backend();self.assertEqual(b.authenticate(RAND,AUTN),('72657370','63'*16,'69'*16))
        self.assertFalse(any(b'CCHO' in x or b'CGLA' in x for x in self.fake.commands))
        with self.assertRaises(LabError):b.authenticate(RAND,AUTN)
    def test_error_is_not_retried(self):
        b=self.backend(state='ERROR')
        with self.assertRaises(LabError):b.authenticate(RAND,AUTN)
        with self.assertRaises(LabError):b.authenticate(RAND,AUTN)
        self.assertEqual(sum(b'00880081' in x for x in self.fake.commands),1)
    def test_missing_discovered_aid_no_auth(self):
        b=self.backend(aids=b'\xff'*11)
        with self.assertRaises(LabError):b.authenticate(RAND,AUTN)
        self.assertFalse(any(b'00880081' in x for x in self.fake.commands))
    def test_consent_expired_no_serial(self):
        b=self.backend(seconds=-1)
        with self.assertRaises(LabError):b.authenticate(RAND,AUTN)
        self.assertEqual(self.fake.commands,[])
