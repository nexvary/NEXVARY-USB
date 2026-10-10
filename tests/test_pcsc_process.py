import subprocess
import unittest
from unittest.mock import patch
from nexvary_usim_lab.pcsc_process import external_report, from_result
from nexvary_usim_lab.core import LabError, Reading
from nexvary_usim_lab.presentation import explain


class ExternalPcscTests(unittest.TestCase):
    def test_enumeration_never_promotes_card_access(self):
        report=from_result({'schema':'nexvary.field-pcsc.v1','enumeration':True,
                            'reader_count':1,'connected':False})
        rows={r.name:r for r in report.readings}
        self.assertEqual(rows['PC/SC enumeration'].status,'OK')
        self.assertEqual(rows['PC/SC SELECT USIM'].status,'UNVERIFIED')
        self.assertEqual(rows['USIM AKA'].status,'UNVERIFIED')

    def test_client_deadline_does_not_retry(self):
        with patch('nexvary_usim_lab.pcsc_process.subprocess.run',
                   side_effect=subprocess.TimeoutExpired('client',30)) as run:
            report=external_report()
        self.assertEqual(run.call_count,1)
        self.assertEqual(report.readings[0].status,'TIMEOUT')
        command=run.call_args.args[0]
        self.assertIn('pcsc-check',command)
        self.assertNotIn('--port',command)

    def test_card_success_retains_sw_but_not_authentication(self):
        report=from_result({'schema':'nexvary.field-pcsc.v1','enumeration':True,
            'connected':True,'select_mf':True,'ef_dir_read':True,'usim_selected':True,
            'steps':[{'operation':'READ RECORD 1','sw':'9000','data_bytes':33}]})
        rows={r.name:r for r in report.readings}
        self.assertEqual(rows['PC/SC SELECT USIM'].status,'OK')
        self.assertEqual(rows['READ RECORD 1'].value,'SW=9000; bytes=33')
        self.assertEqual(rows['USIM AKA'].status,'UNVERIFIED')
        with self.assertRaises(LabError):from_result({'schema':'other'})

    def test_missing_driver_and_missing_usb_id_have_specific_explanations(self):
        self.assertIn('تعريف',explain(Reading('PC/SC diagnostic','NEEDS_USER','SCard status 8010002E','')))
        self.assertIn('VID/PID',explain(Reading('USB VID:PID','UNVERIFIED','Not available','')))
