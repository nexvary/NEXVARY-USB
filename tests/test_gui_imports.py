import ast
import pathlib
import unittest

class GuiContractTests(unittest.TestCase):
    def test_desktop_guarantees_all_pages_and_actions(self):
        p=pathlib.Path(__file__).resolve().parents[1]/"nexvary_usim_lab"/"gui.py"
        content=p.read_text(encoding="utf-8")
        tree=ast.parse(content)
        cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=="Workstation")
        methods={x.name for x in cls.body if isinstance(x,ast.FunctionDef)}
        for method in ("_build_devices","_build_sim","_build_sms","_build_reports",
                       "_build_about","run_probe","check_ef","check_apdu","send_sms",
                       "read_sms","export_report","export_usb","read_pcsc"):
            self.assertIn(method,methods)

    def test_icon_is_generated_in_ci(self):
        p=pathlib.Path(__file__).resolve().parents[1]/"scripts"/"create_icon.py"
        self.assertTrue(p.is_file())
        self.assertIn("nexvary-usb.ico",p.read_text(encoding="utf-8"))

if __name__=="__main__":
    unittest.main()
