"""Synthetic contract fixtures; no real activation/profile or phone evidence."""
import tempfile
import unittest
from pathlib import Path
from nexvary_usim_lab.esim_integration import (
    APK_IDENTITY, IntegrationError, parse_activation, qr_png, read_qr, read_recycling_csv)

class EsimIntegrationTests(unittest.TestCase):
    def test_apk_contract_identity(self):
        self.assertEqual(APK_IDENTITY['version'], '0.922.0')
        self.assertEqual(len(APK_IDENTITY['sha256']), 64)

    def test_scheme_optional_oid_and_confirmation(self):
        for text in ('1$example.invalid$SYNTHETIC-SECRET', 'lpa:1$example.invalid$SYNTHETIC-SECRET'):
            activation = parse_activation(text)
            self.assertFalse(activation.confirmation_required)
            self.assertTrue(activation.matching_id_present)
            self.assertTrue(activation.qr_payload().startswith('LPA:1$'))
        self.assertTrue(parse_activation('LPA:1$example.invalid$TOKEN$1.2.3$1').confirmation_required)
        self.assertFalse(parse_activation('LPA:1$example.invalid$$$0').matching_id_present)

    def test_no_activation_secret_in_diagnostics_or_errors(self):
        activation = parse_activation('LPA:1$example.invalid$SYNTHETIC-SECRET')
        self.assertNotIn('SYNTHETIC-SECRET', repr(activation))
        self.assertNotIn('SYNTHETIC-SECRET', str(activation.summary()))
        for text in ('http://example.invalid/SYNTHETIC-SECRET', 'LPA:1$example.invalid$bad_secret'):
            with self.assertRaises(IntegrationError) as caught: parse_activation(text)
            self.assertNotIn(text, str(caught.exception))

    def test_reject_invalid_android_contract_fields(self):
        for text in ('LPA:2$host$TOKEN','LPA:1$http://host$TOKEN','LPA:1$host$lowercase',
                     'LPA:1$host$TOKEN$x.y','LPA:1$host$TOKEN$$2','LPA:1$host$TOKEN$$1$extra',
                     'LPA:1$host$'+'A'*1025,'LPA:1$host$TOKEN\nBAD'):
            with self.subTest(case=text[:40]):
                with self.assertRaises(IntegrationError): parse_activation(text)

    def test_actual_qr_roundtrip_synthetic_credential(self):
        activation = parse_activation('LPA:1$example.invalid$SYNTHETIC-SECRET$1.2.3$1')
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'activation.png'; path.write_bytes(qr_png(activation))
            self.assertEqual(read_qr(path).qr_payload(), activation.qr_payload())

    def test_reject_non_qr_and_oversized_image(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'blank.png'; Image.new('RGB',(100,100),'white').save(path)
            with self.assertRaises(IntegrationError): read_qr(path)
            path.write_bytes(b'x'*(8*1024*1024+1))
            with self.assertRaises(IntegrationError): read_qr(path)

    def test_phone_csv_import_classifies_source(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'report.csv'
            path.write_text('batch,quantity,classification,condition_score\n1,2,LAB_REUSE,80\n',encoding='utf-8')
            records=read_recycling_csv(path)
            self.assertEqual(records[0]['quantity'],2)
            self.assertEqual(records[0]['evidence'],'phone_reported_not_hardware_verified')

    def test_csv_rejects_extra_ids_formulas_duplicates_and_wrong_schema(self):
        header='batch,quantity,classification,condition_score\n'
        for data in ('batch,iccid\n1,1234\n',header+'1,2,=EXEC(),80\n',header+'1,2,LAB_REUSE,101\n',
                     header+'1,2,LAB_REUSE,80,EXTRA\n',header+'1,2,LAB_REUSE,80\n1,3,LAB_REUSE,70\n',
                     header+'1,2,UNKNOWN,80\n'):
            with tempfile.TemporaryDirectory() as d:
                path=Path(d)/'report.csv';path.write_text(data,encoding='utf-8')
                with self.assertRaises(IntegrationError): read_recycling_csv(path)
