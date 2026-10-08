import unittest

from nexvary_usim_lab.catalog import KNOWN_MODEMS, identification_hint, model_from_text


class CatalogTests(unittest.TestCase):
    def test_three_verified_photographic_labels_are_in_catalog(self):
        self.assertEqual({"E153", "MF190S", "K3770"}, {x.model for x in KNOWN_MODEMS})
        self.assertEqual("Huawei", model_from_text("Vodafone K3770").brand)
        self.assertEqual("ZTE", model_from_text("MF190S ZTE").brand)
        self.assertEqual("Huawei", model_from_text("E153").brand)

    def test_vid_is_not_conflated_with_model(self):
        self.assertIsNone(model_from_text("Huawei Mobile Connect 3G Modem"))
        self.assertIn("model unknown", identification_hint("USB Serial Port", "", "12D1"))
        self.assertIn("ZTE-family", identification_hint("Serial", "", "19D2"))
        self.assertIn("may not", identification_hint("Bluetooth Serial", "", "0000"))

    def test_distinguish_zte_k3770_variant(self):
        self.assertIsNone(model_from_text("ZTE K3770-Z"))
        self.assertIsNone(model_from_text("K3770-Z"))
        self.assertIsNone(model_from_text("K37701"))


if __name__ == "__main__":
    unittest.main()
