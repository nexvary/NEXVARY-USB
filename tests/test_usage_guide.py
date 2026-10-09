"""Plain-language report interpretation, synthetic inputs only."""
import unittest
from nexvary_usim_lab.usage_guide import explain_report, connection_ok
from nexvary_usim_lab.core import Report,Reading

def report(*rows,simulated=False):return Report('NEXVARY USB Studio','test','test','COM5',simulated,list(rows))
class GuideTests(unittest.TestCase):
    def test_ready_registered_and_iccid_timeout_not_failed_sim(self):
        r=report(Reading('Connection','OK','OK',''),Reading('SIM status','OK','+CPIN: READY',''),Reading('ICCID','TIMEOUT','unavailable',''),Reading('SIM EF ICCID','READABLE','suppressed',''),Reading('Registration','OK','+CREG: 2,1,"PRIVATE","PRIVATE"',''))
        text=explain_report(r);self.assertIn('جاهزة',text);self.assertIn('المحلية',text);self.assertIn('ملفها نجح',text);self.assertNotIn('PRIVATE',text)
    def test_failed_connection_cannot_be_success(self):
        r=report(Reading('Connection','TIMEOUT','OK',''),Reading('SIM status','OK','+CPIN: READY',''))
        self.assertFalse(connection_ok(r));self.assertIn('لم يكتمل',explain_report(r));self.assertNotIn('جاهزة',explain_report(r))
    def test_pin_is_not_ready_or_automatically_entered(self):
        text=explain_report(report(Reading('Connection','OK','OK',''),Reading('SIM status','OK','+CPIN: SIM PIN','')))
        self.assertIn('تطلب PIN',text);self.assertNotIn('جاهزة للاستخدام',text)
    def test_select_success_does_not_imply_aka(self):
        text=explain_report(report(Reading('Connection','OK','OK',''),Reading('APDU SELECT MF','ACCEPTED','SW=9000','')))
        self.assertIn('المكالمات لم تثبت',text)
    def test_simulated_and_no_report_explicit(self):
        self.assertIn('محاكاة',explain_report(report(Reading('Connection','OK','OK',''),simulated=True)))
        self.assertIn('لم نُجرِ',explain_report(None))
