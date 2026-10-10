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
