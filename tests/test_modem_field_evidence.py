"""Hardware-derived regression scenarios from Huawei Vodafone K3770 testing.

These tests use simulated serial responses only; they do not establish
card APDU or network entitlement on actual hardware.
"""
import unittest
from nexvary_usim_lab.core import DemoSerial, _one_query, probe, select_master_file

class VodafoneK3770(DemoSerial):
    ANSWERS = dict(DemoSerial.ANSWERS, **{
        "AT": tuple(['+CMTI: "SM",3'] * 80 + ["OK"]),
        "AT+CGMI": ("huawei", "OK"),
        "AT+CGMM": ("K3770", "OK"),
        "AT+CGMR": ("21.023.04.00.11", "OK"),
        "AT+CPIN?": ('+CREG: 1,"A10F","007ED1C5"', "+CPIN: READY", "OK"),
        "AT+CSQ": ('+CREG: 1,"A10F","007ED1C5"', "+CSQ: 18,0", "OK"),
        "AT+CSIM=?": ("OK",),
        "AT+CRSM=?": ("OK",),
        'AT+CRSM=176,12258,0,0,10': ('+CRSM: 144,0,"98123456789012345678"',"OK"),
        'AT+CSIM=14,"00A4000C023F00"': ('+CMTI: "SM",3', '+CSIM: 4,"9000"', 'OK')
    })

class NoisyPortTests(unittest.TestCase):
    def test_k3770_unrequested_notifications_do_not_break_at(self):
        report = probe("COM7", factory=VodafoneK3770)
        values = {r.name: r for r in report.readings}
        self.assertEqual("OK", values["Connection"].status)
        self.assertEqual("OK", values["Connection"].value)
        self.assertEqual("K3770", values["Model"].value)
        self.assertEqual("huawei", values["Manufacturer"].value)
        self.assertEqual("+CPIN: READY", values["SIM status"].value)
        self.assertEqual("+CSQ: 18,0", values["Signal"].value)
        self.assertEqual("OK", values["CSIM probe"].status)
        self.assertEqual("OK", values["CRSM probe"].status)
        self.assertNotIn("A10F", str(values))

    def test_bounded_noise_is_reported_without_leaking_notifications(self):
        class Flood(DemoSerial):
            ANSWERS = dict(DemoSerial.ANSWERS, AT=tuple(["+CMTI: SECRET"] * 600))
        status, value = _one_query(Flood("COM7", 115200), "AT", 0.3)
        self.assertEqual("NOISY", status)
        self.assertNotIn("SECRET", value)

    def test_nonfinal_model_reply_is_not_a_success(self):
        class Unfinished(DemoSerial):
            ANSWERS = dict(DemoSerial.ANSWERS, **{"AT+CGMM": ("K3770",)})
        status, _ = _one_query(Unfinished("COM7", 115200), "AT+CGMM", 0.2)
        self.assertEqual("TIMEOUT", status)

    def test_k3770_6a86_fallback_only_on_parameter_mismatch(self):
        class K3770Alternative(DemoSerial):
            ANSWERS = dict(DemoSerial.ANSWERS, **{
                'AT+CSIM=14,"00A4000C023F00"': ('+CSIM: 4,"6A86"', 'OK'),
                'AT+CSIM=14,"00A40004023F00"': ('+CSIM: 4,"9000"', 'OK')})
            sent = []
            def write(self, payload):
                self.sent.append(payload.decode("ascii").strip())
                super().write(payload)
        class Holder:
            modem = None
            def __call__(self, device, speed):
                self.modem = K3770Alternative(device,speed)
                return self.modem
        holder=Holder()
        result=select_master_file("COM7",factory=holder)
        self.assertEqual("ACCEPTED",result.status)
        self.assertEqual("SW=9000",result.value)
        self.assertIn("UICC_FCP",result.note)
        self.assertEqual([
            "AT", 'AT+CSIM=14,"00A4000C023F00"',
            'AT+CSIM=14,"00A40004023F00"'],holder.modem.sent)

    def test_non_6a86_card_failure_does_not_retry(self):
        class OtherStatus(DemoSerial):
            ANSWERS = dict(DemoSerial.ANSWERS, **{
                'AT+CSIM=14,"00A4000C023F00"': ('+CSIM: 4,"6982"', 'OK')})
            sent = []
            def write(self,payload):
                self.sent.append(payload.decode("ascii").strip())
                super().write(payload)
        class Holder:
            modem = None
            def __call__(self,device,speed):
                self.modem=OtherStatus(device,speed)
                return self.modem
        holder=Holder()
        result=select_master_file("COM7",factory=holder)
        self.assertEqual("CARD_STATUS",result.status)
        self.assertEqual("SW=6982",result.value)
        self.assertEqual(2,len(holder.modem.sent))

    def test_fixed_apdu_still_requires_actual_card_status_word(self):
        result = select_master_file("COM7", factory=VodafoneK3770)
        self.assertEqual("ACCEPTED", result.status)
        self.assertEqual("SW=9000", result.value)

if __name__ == "__main__":
    unittest.main()
