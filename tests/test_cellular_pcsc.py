"""Simulated OS controllers and cards; not actual data or reader validation."""
import unittest,types,sys
from unittest.mock import patch
from nexvary_usim_lab.cellular import CellularManager
from nexvary_usim_lab.pcsc import _operation,run
from nexvary_usim_lab.core import LabError
UUID='12345678-1234-4234-8234-123456789abc'
class CellularTests(unittest.TestCase):
    def manager(self,system='Linux',kind='gsm'):
        self.calls=[]
        def runner(args,**kw):
            self.calls.append(args);self.assertFalse(kw['shell']);self.assertLessEqual(kw['timeout'],60)
            out=kind.encode() if 'GENERAL.TYPE' in args or 'connection.type' in args else b'100 (connected)\n10.0.0.2/32'
            return types.SimpleNamespace(returncode=0,stdout=out)
        return CellularManager(system,runner)
    @patch('nexvary_usim_lab.cellular.shutil.which',return_value='/usr/bin/nmcli')
    def test_gsm_up_and_selected_device_disconnect(self,_):
        manager=self.manager();self.assertIn('10.0.0.2',manager.change('wwan0',UUID,True,True));self.assertTrue(any('up' in c and 'ifname' in c for c in self.calls))
        self.assertIn('10.0.0.2',manager.change('wwan0',connect=False,confirmed=True))
    @patch('nexvary_usim_lab.cellular.shutil.which',return_value='/usr/bin/nmcli')
    def test_unrelated_network_and_invalid_profile_refused(self,_):
        manager=self.manager(kind='ethernet')
        with self.assertRaises(LabError):manager.change('eth0',UUID,True,True)
        self.assertEqual(1,len(self.calls))
        manager=self.manager()
        for profile in ('bad',None,'--all'):
            with self.assertRaises(LabError):manager.change('wwan0',profile,True,True)
        self.assertFalse(any('up' in c for c in self.calls))
    def test_consent_and_injection_fail_before_runner(self):
        manager=self.manager()
        with self.assertRaises(LabError):manager.change('wwan0',UUID)
        with self.assertRaises(LabError):manager.change('bad\nname',UUID,confirmed=True)
        self.assertEqual([],self.calls)
    def test_windows_scoped_profile_no_route_or_driver_mutation(self):
        manager=self.manager('Windows');manager.change('Cellular 2','Operator Profile',True,True)
        self.assertIn('interface=Cellular 2',self.calls[0]);self.assertIn('connmode=name',self.calls[0]);self.assertIn('name=Operator Profile',self.calls[0]);self.assertEqual(2,len(self.calls))
    @patch('nexvary_usim_lab.cellular.shutil.which',return_value=None)
    def test_missing_dependency(self,_):
        with self.assertRaises(LabError):self.manager().inventory()
class PcscTests(unittest.TestCase):
    def test_consent_required(self):
        with self.assertRaises(LabError):run('reader')
    @patch('nexvary_usim_lab.pcsc.platform.system',return_value='Linux')
    def test_fixed_select_only_cleanup_and_no_card_contents(self,_):
        wire=types.SimpleNamespace(connect=lambda:None,disconnect=lambda:self.calls.append('close'),transmit=lambda apdu:(self.calls.append(apdu) or ([1,2,3],0x6A,0x86)))
        reader=types.SimpleNamespace(createConnection=lambda:wire);reader.__str__=lambda:'reader'
        class Reader:
            def __str__(self):return 'reader'
            def createConnection(self):return wire
        self.calls=[]
        modules={'smartcard.System':types.SimpleNamespace(readers=lambda:[Reader()]),'smartcard.ExclusiveConnectCardConnection':types.SimpleNamespace(ExclusiveConnectCardConnection=lambda x:x)}
        with patch.dict(sys.modules,modules):
            result=_operation('reader');self.assertIn('6A86',result);self.assertEqual([[0,164,0,4,2,63,0,0],'close'],self.calls)
