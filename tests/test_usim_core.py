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
            ANSWERS={ 'AT+CPIN?':('+CPIN: READY','OK'), 'AT+CRSM=192,12032,0,0,0':('+CRSM: 144,0,"620782054221000B02"','OK'),'AT+CRSM=178,12032,1,4,11':('+CRSM: 144,0,"61094F07'+AID+'"','OK'),'AT+CRSM=178,12032,2,4,11':('ERROR',)}
        with self.assertRaises(LabError):applications('COM7',factory=Fake)
    def test_core_declared_selected_and_aka_independent(self):
        class Fake(DemoSerial):
            ANSWERS={ 'AT+CPIN?':('+CPIN: READY','OK'), 'AT+CRSM=192,12032,0,0,0':('+CRSM: 144,0,"620782054221000B01"','OK'),'AT+CRSM=178,12032,1,4,11':('+CRSM: 144,0,"61094F07'+AID+'"','OK'),'AT+CRSM=178,12032,2,4,11':('+CRSM: 106,131','OK'),f'AT+CSIM={len(SELECT)},"{SELECT}"':('+CSIM: 4,"9000"','OK')}
        rows=NexvaryUsimCore('COM7',factory=Fake).inspect(True)
        self.assertEqual(['DECLARED','SELECTED','UNVERIFIED'],[r.status for r in rows])
    def test_field_reports_retained_with_no_location(self):
        files=list(Path(__file__).with_name('field-evidence').glob('*.json'));self.assertEqual(2,len(files))
        for path in files:
            raw=path.read_text(encoding="utf-8");d=json.loads(raw);self.assertIs(False,d['simulated']);self.assertEqual('0.6.0',d['version']);rows={r['name']:r for r in d['readings']}
            self.assertEqual('SW=9000',rows['APDU SELECT MF']['value']);self.assertEqual('TIMEOUT',rows['CCHO probe']['status']);self.assertNotIn('007ECF',raw);self.assertNotIn('A10F',raw)
            if d['device']=='COM7':self.assertNotIn('SIM EF ICCID',rows)


class EfDirMetadataFallbackTests(unittest.TestCase):
    """Synthetic regression only; no card or modem is accessed by the test."""
    def test_empty_success_uses_one_safe_15_byte_header_read(self):
        legacy=bytes([0,0,0,22,0x2f,0,4,0,0,0,0,1,2,1,11]).hex().upper()
        class Fake(DemoSerial):
            ANSWERS={
                'AT+CPIN?':('+CPIN: READY','OK'),
                'AT+CRSM=192,12032,0,0,0':('+CRSM: 144,0','OK'),
                'AT+CRSM=192,12032,0,0,15':('+CRSM: 144,0,"'+legacy+'"','OK'),
                'AT+CRSM=178,12032,1,4,11':('+CRSM: 144,0,"61094F07'+AID+'"','OK'),
                'AT+CRSM=178,12032,2,4,11':('+CRSM: 106,131','OK'),
            }
            sent=[]
            def write(self,data):
                self.sent.append(data.decode('ascii').strip())
                super().write(data)
        Fake.sent=[]
        result=applications('COM7',factory=Fake)
        self.assertEqual('DECLARED',result[0].status)
        self.assertIn('USIM',result[0].value)
        self.assertEqual(1,Fake.sent.count('AT+CRSM=192,12032,0,0,15'))
        self.assertFalse(any('+CCHO' in x or '+CGLA' in x for x in Fake.sent))

    def test_empty_15_byte_response_is_still_unknown(self):
        from nexvary_usim_lab.sim_inspector import DirectoryFailure
        class Fake(DemoSerial):
            ANSWERS={
                'AT+CPIN?':('+CPIN: READY','OK'),
                'AT+CRSM=192,12032,0,0,0':('+CRSM: 144,0','OK'),
                'AT+CRSM=192,12032,0,0,15':('+CRSM: 144,0','OK')}
        with self.assertRaises(DirectoryFailure) as error:
            applications('COM7',factory=Fake)
        self.assertEqual('UNKNOWN',error.exception.status)
        self.assertIn('15',str(error.exception))

    def test_timeout_never_triggers_a_second_read(self):
        from unittest.mock import patch
        from nexvary_usim_lab.sim_inspector import DirectoryFailure
        class Fake(DemoSerial):
            ANSWERS={'AT+CPIN?':('+CPIN: READY','OK')}
        with patch('nexvary_usim_lab.sim_inspector._crsm',
                   side_effect=DirectoryFailure('TIMEOUT','partial response')) as read:
            with self.assertRaises(DirectoryFailure) as error:
                applications('COM7',factory=Fake)
        self.assertEqual('TIMEOUT',error.exception.status)
        self.assertEqual(1,read.call_count)

    def test_unquoted_crsm_header_supported(self):
        from nexvary_usim_lab.sim_inspector import _crsm
        class Session:
            def _command(self,command,duration):
                return 'OK',['+CRSM: 144,0,620782054221000B01']
        self.assertEqual(bytes.fromhex('620782054221000B01'),
                         _crsm(Session(),'AT+CRSM=192,12032,0,0,0'))


class EfDirMalformedTlvRegression(unittest.TestCase):
    """Synthetic partial TLV from modem, not a new physical-device report."""
    def test_padding_only_at_record_end(self):
        from nexvary_usim_lab.sim_inspector import tlvs
        self.assertEqual([(0x4f,b'a')],tlvs(b'\x4f\x01a\xff\xff'))
        self.assertEqual([(0x4f,b'a')],tlvs(b'\x4f\x01a\x00\x00'))
        with self.assertRaises(LabError):
            tlvs(b'\x61\x10\x4f\x02a\xff\xff')

    def test_truncated_fcp_is_diagnostic_unknown_not_usim_absence(self):
        from nexvary_usim_lab.sim_inspector import DirectoryFailure
        class Fake(DemoSerial):
            ANSWERS={
                'AT+CPIN?':('+CPIN: READY','OK'),
                'AT+CRSM=192,12032,0,0,0':(
                    '+CRSM: 144,0,"620F82054221000B01"','OK')}
        with self.assertRaises(DirectoryFailure) as err:
            applications('COM7',factory=Fake)
        self.assertEqual('UNKNOWN',err.exception.status)
        self.assertIn('وصف ملف EF_DIR',str(err.exception))
        self.assertNotIn('Truncated SIM TLV',str(err.exception))

    def test_truncated_record_is_classified_without_guessing_aid(self):
        from nexvary_usim_lab.sim_inspector import DirectoryFailure
        class Fake(DemoSerial):
            ANSWERS={
                'AT+CPIN?':('+CPIN: READY','OK'),
                'AT+CRSM=192,12032,0,0,0':(
                    '+CRSM: 144,0,"620782054221000B01"','OK'),
                'AT+CRSM=178,12032,1,4,11':(
                    '+CRSM: 144,0,"610E4F07A0000000871002"','OK')}
        with self.assertRaises(DirectoryFailure) as err:
            applications('COM7',factory=Fake)
        self.assertEqual('UNKNOWN',err.exception.status)
        self.assertIn('سجل EF_DIR رقم 1',str(err.exception))
        self.assertNotIn('A0000000871002',str(err.exception))
