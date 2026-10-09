import unittest
from unittest.mock import patch
from nexvary_usim_lab.core import DemoSerial,LabError
from nexvary_usim_lab.device_operations import ATSession
from nexvary_usim_lab.sms import ucs2_submit
from nexvary_usim_lab.sim_inspector import tlvs,applications

class NewOperations(unittest.TestCase):
    def test_arabic_ucs2_exact_pdu(self):
        pdu,n=ucs2_submit('+201000000000','مرحبا')
        self.assertEqual('0001000C9102010000000000080A06450631062D06280627',pdu)
        self.assertEqual(len(bytes.fromhex(pdu))-1,n)
    def test_ucs2_limits_and_injection(self):
        for number,body in [('+201000000000','😀'),('+201000000000','ع'*71),('+201000000000\rAT','abc')]:
            with self.assertRaises(LabError):ucs2_submit(number,body)
    def test_ucs2_send_restores_mode(self):
        class Fake(DemoSerial):
            ANSWERS=dict(DemoSerial.ANSWERS,**{'AT+CMGF?':('+CMGF: 1','OK'),'AT+CMGF=0':('OK',),'AT+CMGF=1':('OK',),'AT+CMGS=23':('>',)})
            def __init__(self,*args):super().__init__(*args);self.sent=[]
            def write(self,raw):
                self.sent.append(raw)
                if raw.endswith(b'\x1a'):self.pending=[b'+CMGS: 4\r\n',b'OK\r\n']
                else:super().write(raw)
        fake=Fake('COM7',115200)
        with ATSession('COM7',factory=lambda *_:fake) as s:
            self.assertIn('4',s.send_ucs2_sms('+201000000000','مرحبا',True,True))
        self.assertEqual(b'AT+CMGF=1\r',fake.sent[-1])
    def test_network_does_not_return_unsolicited_identity(self):
        class Fake(DemoSerial):ANSWERS=dict(DemoSerial.ANSWERS,**{'AT+COPS?':('+CMT: 201000000000','synthetic private SMS body','+COPS: 0,0,"Test Carrier",2','OK')})
        with ATSession('COM7',factory=Fake) as s:
            result=s.network_info();self.assertIn('Test Carrier',str(result));self.assertNotIn('201000000000',str(result))
    def test_apn_requires_inactive_context_and_readback(self):
        class Fake(DemoSerial):ANSWERS=dict(DemoSerial.ANSWERS,**{'AT+CGACT?':('+CGACT: 1,0','OK'),'AT+CGDCONT=1,"IP","internet"':('OK',),'AT+CGDCONT?':('+CGDCONT: 1,"IP","internet","0.0.0.0",0,0','OK')})
        with ATSession('COM7',factory=Fake) as s:
            self.assertIn('تأكيد',s.set_apn(1,'internet',True))
            with self.assertRaises(LabError):s.set_apn(1,'bad"\rAT',True)
    def test_active_context_refused(self):
        class Fake(DemoSerial):ANSWERS={'AT+CGACT?':('+CGACT: 1,1','OK')}
        with ATSession('COM7',factory=Fake) as s:
            with self.assertRaises(LabError):s.set_apn(1,'internet',True)
    def test_ef_dir_tlv_and_usim_inventory(self):
        record=bytes.fromhex('61094F07A0000000871002')
        class Fake(DemoSerial):ANSWERS={'AT+CRSM=192,12032,0,0,0':('+CRSM: 144,0,"620782054221000B01"','OK'),'AT+CRSM=178,12032,1,4,11':('+CRSM: 144,0,"'+record.hex()+'"','OK'),'AT+CRSM=178,12032,2,4,11':('+CRSM: 106,131','OK')}
        rr=applications('COM7',factory=Fake);self.assertIn('USIM',rr[0].value);self.assertEqual('DECLARED',rr[0].status)
        with self.assertRaises(LabError):tlvs(b'\x61\x10\x00')

    def test_noisy_session_skips_urc_without_leaking(self):
        class Fake(DemoSerial):ANSWERS={'AT+CSQ':tuple('^RSSI: 201000000000' for _ in range(250))+('+CSQ: 15,99','OK')}
        with ATSession('COM7',factory=Fake) as s:
            result=s.signal();self.assertEqual('OK',result.status);self.assertNotIn('201000000000',repr(s.events))
    def test_csv_formula_injection_escaped(self):
        from nexvary_usim_lab.core import demo,Reading,to_csv
        report=demo();report.readings=[Reading('Model','OK','=HYPERLINK("bad")','test')]
        self.assertIn("'=HYPERLINK",to_csv(report))
