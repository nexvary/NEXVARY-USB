"""Synthetic PnP fixtures, never presented as observed device inventory."""
import json,tempfile,unittest
from pathlib import Path
from nexvary_usim_lab.discovery import Inventory,_parse_windows,to_diagnostic_json
from nexvary_usim_lab.grouping import group_devices,candidates,port_role
from nexvary_usim_lab.port_discovery import discover_at,PortPreferences
from nexvary_usim_lab.core import Port,DemoSerial,LabError,probe
from nexvary_usim_lab.device_operations import ATSession

def inventory():
    devices=[]
    for serial,com,cid in [('PHYSICAL-A','COM7','12345678-1111-2222-3333-123456789000'),('PHYSICAL-B','COM9','12345678-1111-2222-3333-123456789001')]:
        parent='USB\\VID_12D1&PID_14C9\\'+serial
        for name,kind,identifier in [('Huawei K3770','USB',parent),('Vodafone Modem '+com,'Modem','USB\\VID_12D1&PID_14C9&MI_01\\'+serial),('Diagnostics '+com.replace('7','6').replace('9','8'),'Ports','USB\\VID_12D1&PID_14C9&MI_02\\'+serial)]:
            devices.append(dict(Name=name,Class=kind,Status='OK',InstanceId=identifier,ContainerId=cid,Ancestors=[parent]))
    return Inventory('COM_AVAILABLE',_parse_windows(json.dumps(devices)),[],'Synthetic PnP fixture','OK')

class GroupingTests(unittest.TestCase):
    def test_two_identical_models_not_combined(self):
        groups=group_devices(inventory());self.assertEqual(2,len(groups));self.assertEqual([3,3],[len(x.interfaces) for x in groups])
        self.assertEqual(['COM7'],[x.device for x in candidates(groups[0])])
    def test_private_ids_excluded(self):
        text=to_diagnostic_json(inventory())
        for value in ('PHYSICAL-A','12345678-1111','ancestors','identity'):self.assertNotIn(value,text)
    def test_missing_keys_do_not_group_by_vid_pid(self):
        data=inventory()
        from dataclasses import replace
        data=replace(data,devices=[replace(x,identity='',container='',ancestors=()) for x in data.devices])
        self.assertEqual(6,len(group_devices(data)))
    def test_parent_groups_across_missing_containers(self):
        data=inventory()
        from dataclasses import replace
        data=replace(data,devices=[replace(x,container='') for x in data.devices])
        self.assertEqual(2,len(group_devices(data)))
    def test_diagnostics_never_auto_probed_and_success_remembered(self):
        with tempfile.TemporaryDirectory() as path:
            pref=PortPreferences(Path(path)/'ports.json');group=group_devices(inventory())[0]
            seen=[]
            def factory(port,speed):seen.append(port);return DemoSerial(port,speed)
            self.assertEqual('COM7',discover_at(group,pref,factory)[0]);self.assertEqual(['COM7'],seen)
            self.assertEqual('COM7',pref.get(group.key))
    def test_process_lease_covers_all_apis(self):
        with ATSession('COM7',factory=DemoSerial):
            with self.assertRaises(LabError):probe('com7',factory=DemoSerial)
            with self.assertRaises(LabError):
                with ATSession('COM7',factory=DemoSerial):pass
        self.assertFalse(probe('COM7',factory=DemoSerial).simulated)

    def test_duplicate_container_cannot_override_distinct_physical_parents(self):
        from dataclasses import replace
        data=inventory()
        data=replace(data,devices=[replace(x,container='12345678-1111-2222-3333-123456789000') for x in data.devices])
        self.assertEqual(2,len(group_devices(data)))

class CapabilitySelectionTests(unittest.TestCase):
    def test_prefers_sim_capable_port_over_old_at_only_preference(self):
        with tempfile.TemporaryDirectory() as dirname:
            pref=PortPreferences(Path(dirname)/'ports.json')
            device=group_devices(inventory())[0]
            from nexvary_usim_lab.core import Port
            device.ports=[
                Port('COM7','Vodafone Secondary Modem','Huawei','12D1','14C9'),
                Port('COM5','Vodafone Primary Modem','Huawei','12D1','14C9'),
            ]
            pref.remember(device.key,'COM7')
            calls=[]
            class Modem(DemoSerial):
                def __init__(self,port,speed):
                    super().__init__(port,speed)
                    self.port=port
                def write(self,data):
                    calls.append((self.port,data.decode().strip()))
                    super().write(data)
                    if self.port=='COM7' and data.decode().strip() in ('AT+CPIN?','AT+CSQ'):
                        self.pending=[b'ERROR\r\n']
            selected, failures=discover_at(device,pref,Modem,assess_sim=True)
            self.assertEqual('COM5',selected)
            self.assertEqual('COM5',pref.get(device.key))
            self.assertNotIn(('COM7','AT+CGMR'),calls)
            self.assertTrue(any(p=='COM7' and 'unverified' in status for p,status in failures))

    def test_no_sim_response_does_not_claim_unsupported_hardware(self):
        with tempfile.TemporaryDirectory() as dirname:
            pref=PortPreferences(Path(dirname)/'ports.json')
            device=group_devices(inventory())[0]
            class ATOnly(DemoSerial):
                ANSWERS=dict(DemoSerial.ANSWERS,**{'AT+CPIN?':('ERROR',),'AT+CSQ':('ERROR',)})
            selected, fail=discover_at(device,pref,ATOnly,assess_sim=True)
            self.assertEqual('COM7',selected)
            self.assertTrue(any('unverified' in x[1] for x in fail))
            self.assertIsNone(pref.get(device.key))

    def test_unsolicited_network_reports_do_not_misclassify_sim(self):
        with tempfile.TemporaryDirectory() as dirname:
            device=group_devices(inventory())[0]
            class Noisy(DemoSerial):
                ANSWERS=dict(DemoSerial.ANSWERS,**{
                    'AT+CPIN?':('+CREG: 2,1', '+CPIN: READY','OK'),
                    'AT+CSQ':('+CMTI: "SM",2','+CSQ: 18,0','OK')})
            self.assertEqual('COM7',discover_at(device,PortPreferences(Path(dirname)/'prefs.json'),Noisy,assess_sim=True)[0])
