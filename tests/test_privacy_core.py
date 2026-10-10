import unittest
from nexvary_usim_lab.core import registration_public

class RegistrationPrivacyTests(unittest.TestCase):
    def test_cid_and_lac_removed_even_if_only_four_hex_digits(self):
        value='+CREG: 2,1,"A10F","007E7359"'
        self.assertEqual('+CREG: 2,1',registration_public(value))
        self.assertEqual('+CREG: 0,5',registration_public('+CREG: 0,5,"BEEF","DEAD"'))
    def test_unparseable_reply_never_leaks_cell_payload(self):
        self.assertNotIn('PRIVATE',registration_public('PRIVATE CELL DATA'))
