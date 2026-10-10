import unittest
from nexvary_usim_lab.core import DemoSerial, Port
from nexvary_usim_lab.reader_diagnostics import field_report, reader_evidence
from test_virtual_sim import FCP, RECORD

def reply(data): return (f'+CSIM: {len(data)},"{data}"','OK')
class FieldModem(DemoSerial):
    ANSWERS={'AT+CGMI':('Huawei','OK'),'AT+CGMM':('K3770','OK'),
        'AT+CGMR':('21.023.04.00.11','OK'),'AT+CPIN?':('+CPIN: READY','OK'),
        'AT+CSIM=14,"00A4000C023F00"':reply('9000'),
        'AT+CSIM=14,"00A40004022F00"':reply(FCP.hex()+'9000'),
        'AT+CSIM=10,"00B201040B"':reply(RECORD.hex()+'9000'),
        'AT+CSIM=24,"00A4040407A0000000871002"':reply('9000')}
class FieldTests(unittest.TestCase):
    def test_report_preserves_directory_evidence_without_promoting_pcsc(self):
        r=field_report('COM9',True,FieldModem,[Port('COM9','USB','Huawei','12D1','14C9')],'STOPPED')
        rows={x.name:x for x in r.readings}
        self.assertTrue(r.simulated)
        self.assertEqual(rows['USB VID:PID'].value,'12D1:14C9')
        self.assertEqual(rows['EF_DIR FCP'].value,FCP.hex().upper())
        self.assertEqual(rows['EF_DIR dimensions'].value,'11 bytes; 1 records')
        self.assertEqual(rows['EF_DIR record 1'].value,'A0000000871002')
        self.assertEqual(rows['USIM direct access'].status,'SELECTED')
        e=reader_evidence(r)
        self.assertTrue(e['ef_dir_read']);self.assertTrue(e['usim_selected'])
        self.assertFalse(e['pcsc_enumerated']);self.assertFalse(e['aka_verified'])
    def test_locked_sim_report_does_not_send_apdu(self):
        class Locked(FieldModem):
            ANSWERS=dict(FieldModem.ANSWERS,**{'AT+CPIN?':('+CPIN: SIM PIN','OK')})
            sent=[]
            def write(self,data):self.sent.append(data);super().write(data)
        r=field_report('COM9',True,Locked)
        rows={x.name:x for x in r.readings}
        self.assertEqual(rows['SIM status'].value,'+CPIN: SIM PIN')
        self.assertFalse(any(b'CSIM' in x for x in Locked.sent))
        self.assertFalse(reader_evidence(r)['direct_select_mf'])
    def test_failed_directory_preserves_sim_and_mf_evidence(self):
        class Reject(FieldModem):
            ANSWERS=dict(FieldModem.ANSWERS,**{'AT+CSIM=14,"00A40004022F00"':reply('6A82')})
        r=field_report('COM9',True,Reject)
        e=reader_evidence(r)
        self.assertTrue(e['direct_select_mf']);self.assertFalse(e['ef_dir_read'])
        row=next(x for x in r.readings if x.name=='Direct SIM transport')
        self.assertEqual(row.status,'CARD_STATUS');self.assertIn('6A82',row.value)
