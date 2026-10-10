"""A complete image is exported independent of GUI scrolling and screen DPI."""
import os
import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from nexvary_usim_lab.core import Report, Reading, LabError
from nexvary_usim_lab.result_snapshot import complete_results_image, snapshot_rows

class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def fixture(self):
        rows=[Reading('Connection','OK','OK','test')]+[
            Reading('SIM applications','TIMEOUT','+CME ERROR: 10 — رقم 01012345678',
              'Synthetic test — not a hardware claim') for _ in range(23)]
        return Report('NEXVARY USB Studio','synthetic','2026-01-01','COM7',True,rows)

    def test_one_png_has_every_row_and_no_sensitive_number(self):
        report=self.fixture()
        rows=snapshot_rows(report)
        self.assertEqual(24,len(rows))
        self.assertNotIn('01012345678',str(rows))
        img=complete_results_image(report)
        self.assertEqual(1440,img.width())
        self.assertGreater(img.height(),950)
        self.assertFalse(img.isNull())
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'complete.png'
            self.assertTrue(img.save(str(file),'PNG'))
            self.assertGreater(file.stat().st_size,10000)

    def test_empty_report_and_limits(self):
        with self.assertRaises(LabError):
            snapshot_rows(None)
        report=Report('Test','1.0','test','COM5',True,[])
        image=complete_results_image(report)
        self.assertGreater(image.height(),200)
        with self.assertRaises(LabError):
            complete_results_image(report,700)


class PrivacyAndReadableResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def test_report_and_image_never_export_creg_cell_location(self):
        from nexvary_usim_lab.core import DemoSerial, probe, to_json
        class Fake(DemoSerial):
            ANSWERS={**DemoSerial.ANSWERS,
                     'AT+CREG?':('+CREG: 2,1,"A10F","007E7359"','OK')}
        report=probe('COM7',factory=Fake)
        registration=next(r for r in report.readings if r.name=='Registration')
        self.assertEqual('+CREG: 2,1',registration.value)
        self.assertNotIn('A10F',to_json(report))
        self.assertNotIn('007E7359',to_json(report))
        # A report captured by an older version is also safe to share.
        registration.value='+CREG: 2,1,"A10F","007E7359"'
        snapshot=str(snapshot_rows(report))
        self.assertNotIn('A10F',snapshot)
        self.assertNotIn('007E7359',snapshot)
        self.assertIn('مسجل على الشبكة',snapshot)

    def test_bidi_clutter_removed_and_tlv_explained_in_arabic(self):
        report=Report('USB','0.9.1','now','COM7',False,[
            Reading('CGLA probe','TIMEOUT','لم يصل رد مكتمل',
                    'Test syntax response is not proof of USIM AKA'),
            Reading('SIM applications','UNKNOWN','Truncated SIM TLV.',
                    'لم يثبت غياب USIM'),
            Reading('ICCID','OK','ICCID: ************5886',
                    'Read status; not proof of USIM AKA')])
        cells=snapshot_rows(report)
        assert 'Test syntax' not in str(cells)
        assert 'Truncated SIM TLV' not in str(cells)
        assert 'رقم' not in cells[1][2] or 'TLV' in cells[1][2]
        self.assertIn('TLV',cells[1][2])
        self.assertNotIn('5886',str(cells))
        self.assertIn('غير محسوم',str(cells))
