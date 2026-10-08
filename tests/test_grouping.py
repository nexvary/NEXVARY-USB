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
