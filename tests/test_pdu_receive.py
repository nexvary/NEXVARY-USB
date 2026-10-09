"""Synthetic protocol fixtures only; no received messages from real modems."""
import unittest
from nexvary_usim_lab.core import LabError,DemoSerial
from nexvary_usim_lab.pdu import deliver,_septets
from nexvary_usim_lab.device_operations import ATSession

def fixture(text='مرحبا',header=b''):
    payload=header+text.encode('utf-16-be')
    tpdu=bytes.fromhex(('40' if header else '00')+'0C91020100000000000862109021436500')+bytes([len(payload)])+payload
    return '00'+tpdu.hex(),len(tpdu)
class ReceiveTests(unittest.TestCase):
    def test_arabic_and_length_from_independent_deliver_fixture(self):
        pdu,size=fixture();value=deliver(pdu,size)
        self.assertEqual('مرحبا',value['text']);self.assertEqual('+201000000000',value['sender']);self.assertEqual('UCS2',value['encoding'])
    def test_udh_parts_not_merged(self):
        pdu,size=fixture('عربي',bytes.fromhex('050003420201'))
        value=deliver(pdu,size);self.assertEqual('عربي',value['text']);self.assertEqual({'reference':66,'total':2,'sequence':1},value['part'])
    def test_gsm7_known_packed_hello(self):
        self.assertEqual('hello',_septets(bytes.fromhex('E8329BFD06'),5))
        tpdu='000C9102010000000000006210902143650005E8329BFD06'
        self.assertEqual('hello',deliver('00'+tpdu)['text'])
    def test_malformed_truncated_unsupported_rejected(self):
        pdu,size=fixture()
        for bad in (pdu[:-2],pdu+'00','GG',pdu[:2]+'01'+pdu[4:]):
            with self.assertRaises(LabError):deliver(bad,size)
        with self.assertRaises(LabError):deliver(pdu,size+1)
        pdu,size=fixture('x',bytes.fromhex('050003420203'))
        with self.assertRaises(LabError):deliver(pdu,size)
    def test_at_inbox_restores_mode_masks_sender_and_no_report_export(self):
        pdu,size=fixture()
        class Wire(DemoSerial):
            ANSWERS={'AT+CMGF?':('+CMGF: 1','OK'),'AT+CMGF=0':('OK',),'AT+CMGL=4':(f'+CMGL: 8,0,,{size}',pdu,'OK'),'AT+CMGF=1':('OK',)}
        with ATSession('COM7',factory=Wire) as s:
            rows=s.inbox();self.assertEqual('مرحبا',rows[0]['preview']);self.assertNotIn('201000000000',str(rows))
            self.assertEqual('REC UNREAD',rows[0]['status'])
    def test_nonreceived_submit_ignored_and_invalid_received_labelled(self):
        class Wire(DemoSerial):
            ANSWERS={'AT+CMGF?':('+CMGF: 0','OK'),'AT+CMGF=0':('OK',),'AT+CMGL=4':('+CMGL: 1,2,,2','0001','+CMGL: 2,1,,2','0001','OK')}
        with ATSession('COM7',factory=Wire) as s:
            rows=s.inbox();self.assertEqual(1,len(rows));self.assertIn('تالف',rows[0]['status'])
