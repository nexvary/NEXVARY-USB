"""Synthetic protocol faults and replay of owner report summaries, not new hardware tests."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from nexvary_usim_lab.core import DemoSerial, Reading, LabError, probe, redact
from nexvary_usim_lab.serial_at import SerialAT, error_message
from nexvary_usim_lab.device_operations import ATSession, ICCID_FILE, _parse_crsm
from nexvary_usim_lab.sim_inspector import applications
from nexvary_usim_lab.port_discovery import CapabilityEvidence, PortPreferences
from nexvary_usim_lab.presentation import outcome, explain
from nexvary_usim_lab.catalog import load_profiles

class FragmentWire(DemoSerial):
    def __init__(self, replies):
        super().__init__('COM5',115200);self.replies=list(replies);self.sent=[]
    def write(self, raw):
        self.sent.append(raw);self.pending=list(self.replies.pop(0))

class ReceiverTests(unittest.TestCase):
    def test_fragmented_echo_and_final_with_combined_lines(self):
        wire=FragmentWire([[b'AT+CP',b'IN?\r\n+CPIN: RE',b'ADY\r\nOK\r\n']])
        reply=SerialAT(wire).command('AT+CPIN?',.2)
        self.assertEqual('OK',reply.status);self.assertEqual(['+CPIN: READY'],reply.lines)
    def test_urc_flood_final_not_discarded(self):
        wire=FragmentWire([[b'^RSSI: PRIVATE\r\n']*800+[b'+CSQ: 18,0\r\nOK\r\n']])
        engine=SerialAT(wire);reply=engine.command('AT+CSQ',.2)
        self.assertEqual('OK',reply.status);self.assertEqual(['+CSQ: 18,0'],reply.lines)
        self.assertNotIn('PRIVATE',str(engine.events))
    def test_timeout_blocks_next_write_even_with_late_ok(self):
        wire=FragmentWire([[b'+CPIN: READY\r\n']]);engine=SerialAT(wire)
        self.assertEqual('TIMEOUT',engine.command('AT+CPIN?',.01).status)
        wire.pending=[b'OK\r\n'];self.assertEqual('SESSION_UNCERTAIN',engine.command('AT+CSQ',.01).status)
        self.assertEqual(1,len(wire.sent))
    def test_sms_urc_body_ok_cannot_finish_another_command(self):
        engine=SerialAT(FragmentWire([[b'+CMT: PRIVATE\r\nOK\r\n+CSQ: 18,0\r\nOK\r\n']]))
        reply=engine.command('AT+CSQ',.1)
        self.assertEqual(['+CSQ: 18,0'],reply.lines);self.assertNotIn('PRIVATE',repr(reply))
    def test_no_response_stage(self):
        engine=SerialAT(FragmentWire([[]]));reply=engine.command('AT',.01)
        self.assertEqual(('TIMEOUT','no-response'),(reply.status,reply.stage))
    def test_partial_without_delimiter(self):
        reply=SerialAT(FragmentWire([[b'+CPIN: READY']])).command('AT+CPIN?',.01)
        self.assertEqual(('TIMEOUT','partial'),(reply.status,reply.stage))
    def test_error_is_final_and_does_not_prove_permanent_unsupported(self):
        engine=SerialAT(FragmentWire([[b'+CME ERROR: 14\r\n'],[b'+CPIN: READY\r\nOK\r\n']]))
        self.assertIn('مشغولة',engine.command('AT+CPIN?',.1).error)
        self.assertEqual('OK',engine.command('AT+CPIN?',.1).status)
    def test_standard_cms_and_no_vendor_error_leak(self):
        self.assertIn('ممتلئة',error_message('+CMS ERROR: 322'))
        self.assertNotIn('PRIVATE',error_message('+CME ERROR: PRIVATE'))
    def test_sms_prompt_is_exact_and_no_automatic_resend(self):
        wire=FragmentWire([[b'>']]);engine=SerialAT(wire)
        self.assertEqual('PROMPT',engine.command('AT+CMGS="+201000000000"',.1,True).status)
        self.assertEqual(1,len(wire.sent))
    def test_disconnect_does_not_leak_or_retry(self):
        class Gone(DemoSerial):
            def readline(self):raise OSError('PRIVATE SERIAL')
        with ATSession('COM5',factory=Gone) as session:
            with self.assertRaises(LabError) as exc:session._command('AT',.01)
            self.assertNotIn('PRIVATE',str(exc.exception))
            self.assertEqual('SESSION_UNCERTAIN',session._command('AT',.01)[0])
    def test_concurrent_operations_fail_before_open(self):
        failures=[]
        with ATSession('COM5',factory=DemoSerial):
            def competing():
                try:
                    with ATSession('com5',factory=DemoSerial):pass
                except LabError:failures.append('busy')
            thread=threading.Thread(target=competing);thread.start();thread.join()
        self.assertEqual(['busy'],failures)

class CardAndEvidenceTests(unittest.TestCase):
    def test_card_not_ready_never_reads_iccid(self):
        class Locked(DemoSerial):
            ANSWERS=dict(DemoSerial.ANSWERS,**{'AT+CPIN?':('+CPIN: SIM PIN','OK')})
            def write(self,raw):
                self.assert_safe=raw!= (ICCID_FILE+'\r').encode()
                if not self.assert_safe:raise AssertionError('must not read file')
                super().write(raw)
        with ATSession('COM5',factory=Locked) as session:
            self.assertEqual('NEEDS_USER',session.sim_file_check().status)
    def test_cpin_rejected_never_reads_directory(self):
        class Rejected(DemoSerial):
            ANSWERS={'AT+CPIN?':('ERROR',)}
        with self.assertRaises(LabError) as exc:applications('COM5',factory=Rejected)
        self.assertEqual('REJECTED',exc.exception.status)
    def test_card_removed_after_ready_is_not_missing_usim_proof(self):
        class Removed(DemoSerial):
            ANSWERS=dict(DemoSerial.ANSWERS,**{ICCID_FILE:('+CME ERROR: 10',)})
        with ATSession('COM5',factory=Removed) as session:
            self.assertEqual('REJECTED',session.sim_file_check().status)
    def test_empty_success_file_and_bad_bcd_not_success(self):
        for raw in ('','FFFFFFFFFFFFFFFFFFFF','9812345678901234567A'):
            self.assertEqual('MALFORMED',_parse_crsm([f'+CRSM: 144,0,"{raw}"']).status)
    def test_known_profile_uses_reported_crsm_method_before_timeout_ccid(self):
        class Reported(DemoSerial):
            ANSWERS=dict(DemoSerial.ANSWERS,**{'AT+CGMI':('Huawei','OK'), 'AT+CGMM':('K3770','OK'),
                'AT+CGMR':('21.023.04.00.11','OK'), ICCID_FILE:('+CRSM: 144,0,"98123456789012345678"','OK')})
            def write(self,raw):
                if raw==b'AT+CCID\r':raise AssertionError('known timeout path must not be preferred')
                super().write(raw)
        readings={r.name:r for r in probe('COM5',factory=Reported).readings}
        self.assertEqual('OK',readings['ICCID'].status)
        self.assertNotIn('89214365870921436587',readings['ICCID'].value)
    def test_independent_capabilities(self):
        ev=CapabilityEvidence();ev.observe('AT','OK','OK');ev.observe('AT+CSQ','OK','+CSQ: 18,0')
        self.assertEqual('VERIFIED',ev.states['AT_READY'])
        for state in ('SIM_ACCESS_READY','APDU_READY','SMS_READY','DATA_READY'):
            self.assertEqual('UNKNOWN',ev.states[state])
        ev.observe('AT+CPIN?','OK','+CPIN: SIM PIN');self.assertEqual('NEEDS_USER',ev.states['SIM_ACCESS_READY'])
    def test_capability_proof_cannot_be_a_syntax_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            pref=PortPreferences(Path(directory)/'ports.json')
            with self.assertRaises(LabError):pref.verify('dev','COM5','APDU_READY','CSIM_SYNTAX_OK')
            pref.verify('dev','COM5','APDU_READY','SELECT_MF_9000')
            self.assertEqual('VERIFIED',pref.observations('dev')['COM5']['states']['APDU_READY'])
    def test_ber_high_tag_and_indefinite_length(self):
        from nexvary_usim_lab.sim_inspector import tlvs
        self.assertEqual([(0x9f33,b'abc')],tlvs(bytes.fromhex('9F3303616263')))
        with self.assertRaises(LabError):tlvs(bytes.fromhex('6180'))
    def test_profile_observations_do_not_store_card_values(self):
        ev=CapabilityEvidence();ev.observe('AT+CPIN?','OK','+CPIN: READY')
        with tempfile.TemporaryDirectory() as directory:
            pref=PortPreferences(Path(directory)/'ports.json');pref.record('device-key','COM5',ev.public_dict('Modem'))
            pref.remember('device-key','COM5');self.assertEqual('COM5',pref.get('device-key'))
            self.assertEqual('UNKNOWN',pref.observations('device-key')['COM5']['states']['APDU_READY'])
            self.assertNotIn('+CPIN:',pref.path.read_text())
    def test_profile_does_not_claim_aka_or_other_devices_verified(self):
        profiles=load_profiles();self.assertEqual('not verified',profiles['Huawei K3770']['compatibility_confidence']['usim_aka'])
        for name in ('Huawei E153','ZTE MF190S'):
            self.assertNotIn('verified_test_evidence',profiles[name])
    def test_public_phone_and_identity_redaction(self):
        for private in ('+201000000000','01000000000','123456789001234','89882123456789012345'):
            self.assertNotIn(private,redact(private))
    def test_ui_outcomes_do_not_green_card_continuation_or_locked_pin(self):
        self.assertEqual('غير محسوم',outcome(Reading('APDU SELECT MF','ACCEPTED','SW=6101','')))
        self.assertEqual('يحتاج تدخل المستخدم',outcome(Reading('SIM status','OK','+CPIN: SIM PIN','')))
        self.assertIn('المنفذ',explain(Reading('SIM status','REJECTED','ERROR','')))

if __name__=='__main__':unittest.main()
