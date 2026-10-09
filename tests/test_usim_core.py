"""Synthetic protocol regression; separately retained owner physical reports."""
import json
import unittest
from pathlib import Path
from nexvary_usim_lab.core import DemoSerial, LabError
from nexvary_usim_lab.usim_core import ApplicationTransport, NexvaryUsimCore, ApduFailure
from nexvary_usim_lab.sim_inspector import applications

AID='A0000000871002'
SELECT='00A4040407'+AID+'00'
class Session:
    def __init__(self, replies):self.replies=list(replies);self.sent=[]
    def _command(self, command, duration):self.sent.append(command);return self.replies.pop(0)

def response(raw):return ('OK',[f'+CSIM: {len(raw)},"{raw}"'])

class CoreTests(unittest.TestCase):
    def test_select_success_is_not_aka(self):
        s=Session([response('9000')]);self.assertEqual('SW=9000',ApplicationTransport(s).select_application(AID));self.assertEqual([f'AT+CSIM={len(SELECT)},"{SELECT}"'],s.sent)
    def test_status_timeout_and_modem_rejection_are_distinct(self):
        for reply,status in [(response('6A86'),'CARD_STATUS'),(('TIMEOUT',[]),'TIMEOUT'),(('ERROR',[]),'MODEM_ERROR'),(('OK',[]),'MALFORMED')]:
            s=Session([reply])
            with self.assertRaises(ApduFailure) as exc:ApplicationTransport(s).select_application(AID)
            self.assertEqual(status,exc.exception.status);self.assertEqual(1,len(s.sent))
    def test_get_response_and_single_corrected_length(self):
        s=Session([response('6108'),response('6C04'),response('62009000')]);self.assertEqual('SW=9000',ApplicationTransport(s).select_application(AID));self.assertEqual('AT+CSIM=10,"00C0000004"',s.sent[-1])
    def test_bounded_continuation(self):
        s=Session([response('6101')]*5)
        with self.assertRaises(ApduFailure) as exc:ApplicationTransport(s).select_application(AID)
        self.assertEqual('CONTINUATION_LIMIT',exc.exception.status);self.assertEqual(5,len(s.sent))
    def test_apdu_length_mismatch(self):
        s=Session([('OK',['+CSIM: 6,"9000"'])])
        with self.assertRaises(ApduFailure):ApplicationTransport(s).select_application(AID)
    def test_aid_allowlist(self):
        for aid in ['A0000000871003','A0000000871002\rAT','A00000008710021','00A4000C023F00']:
            s=Session([])
            with self.assertRaises(LabError):ApplicationTransport(s).select_application(aid)
            self.assertEqual([],s.sent)
    def test_consent_before_serial_open(self):
        def fail(*args):self.fail('serial must not open')
        with self.assertRaises(LabError):NexvaryUsimCore('COM7',factory=fail).inspect()
    def test_directory_timeout_not_silently_returned_as_complete(self):
        class Fake(DemoSerial):
            ANSWERS={'AT+CRSM=192,12032,0,0,0':('+CRSM: 144,0,"620782054221000B02"','OK'),'AT+CRSM=178,12032,1,4,11':('+CRSM: 144,0,"61094F07'+AID+'"','OK'),'AT+CRSM=178,12032,2,4,11':('ERROR',)}
        with self.assertRaises(LabError):applications('COM7',factory=Fake)
    def test_core_declared_selected_and_aka_independent(self):
        class Fake(DemoSerial):
            ANSWERS={'AT+CRSM=192,12032,0,0,0':('+CRSM: 144,0,"620782054221000B01"','OK'),'AT+CRSM=178,12032,1,4,11':('+CRSM: 144,0,"61094F07'+AID+'"','OK'),'AT+CRSM=178,12032,2,4,11':('+CRSM: 106,131','OK'),f'AT+CSIM={len(SELECT)},"{SELECT}"':('+CSIM: 4,"9000"','OK')}
        rows=NexvaryUsimCore('COM7',factory=Fake).inspect(True)
        self.assertEqual(['DECLARED','SELECTED','UNVERIFIED'],[r.status for r in rows])
    def test_field_reports_retained_with_no_location(self):
        files=list(Path(__file__).with_name('field-evidence').glob('*.json'));self.assertEqual(2,len(files))
        for path in files:
            raw=path.read_text();d=json.loads(raw);self.assertIs(False,d['simulated']);self.assertEqual('0.6.0',d['version']);rows={r['name']:r for r in d['readings']}
            self.assertEqual('SW=9000',rows['APDU SELECT MF']['value']);self.assertEqual('TIMEOUT',rows['CCHO probe']['status']);self.assertNotIn('007ECF',raw);self.assertNotIn('A10F',raw)
            if d['device']=='COM7':self.assertNotIn('SIM EF ICCID',rows)
