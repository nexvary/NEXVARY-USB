"""Read-only Windows PnP discovery, including USB mass-storage-only modems.

No USB mode switching, driver installation, registry mutation or SIM access.
Full PnP InstanceIds (which can contain device serial numbers) are never
serialized or written to diagnostics.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import hashlib
import platform
import re
import subprocess
from typing import Callable

from .catalog import identification_hint
from .core import LabError, Port, ports, redact

_VENDOR = re.compile(r"\bVID_(12D1|19D2)\b", re.IGNORECASE)
_PRODUCT = re.compile(r"\bPID_([0-9A-F]{4})\b", re.IGNORECASE)
_COM = re.compile(r"\bCOM\d{1,4}\b", re.IGNORECASE)
_NAME = re.compile(r"Huawei|Vodafone|ZTE|Mobile Broadband|HSUPA|HSPA|Data Card", re.IGNORECASE)
_STORAGE = re.compile(r"CD.?ROM|Mass Storage|DiskDrive|USBSTOR|Virtual CD", re.IGNORECASE)
_AT_CLASS = {"Ports", "Modem"}

# Never execute shell interpolated inputs. This query sends nothing to hardware.
_PNP_QUERY = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$all = @(Get-PnpDevice -PresentOnly -ErrorAction Stop | Where-Object {
    $id = [string]$_.InstanceId
    $name = [string]$_.FriendlyName
    ($id -match 'VID_(12D1|19D2)') -or
    ($name -match 'Huawei|Vodafone|ZTE|Mobile Broadband|HSUPA|HSPA|Data Card')
} | ForEach-Object {
    $props = @(Get-PnpDeviceProperty -InstanceId $_.InstanceId -ErrorAction SilentlyContinue)
    $container = ($props | Where-Object KeyName -eq 'DEVPKEY_Device_ContainerId').Data
    $parent = ($props | Where-Object KeyName -eq 'DEVPKEY_Device_Parent').Data
    $driver = ($props | Where-Object KeyName -eq 'DEVPKEY_Device_DriverVersion').Data
    $ancestors = @()
    $cursor = [string]$parent
    for ($depth=0; $depth -lt 12 -and $cursor; $depth++) {
        $ancestors += $cursor
        $cursor = [string](Get-PnpDeviceProperty -InstanceId $cursor -KeyName 'DEVPKEY_Device_Parent' -ErrorAction SilentlyContinue).Data
    }
    $com = ''
    $reg = 'Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Enum\' + $_.InstanceId + '\Device Parameters'
    $com = [string](Get-ItemProperty -LiteralPath $reg -Name PortName -ErrorAction SilentlyContinue).PortName
    [PSCustomObject]@{
        Name = [string]$_.FriendlyName
        Class = [string]$_.Class
        Status = [string]$_.Status
        InstanceId = [string]$_.InstanceId
        ContainerId = [string]$container
        Parent = [string]$parent
        Ancestors = @($ancestors)
        ComPort = $com
        DriverVersion = [string]$driver
    }
})
ConvertTo-Json -InputObject $all -Compress -Depth 5
"""

@dataclass(frozen=True)
class UsbDevice:
    name: str
    family: str
    usb_id: str
    device_class: str
    os_status: str
    mode: str
    com_port: str
    advice: str
    identity: str = field(default='', repr=False)
    container: str = field(default='', repr=False)
    ancestors: tuple[str, ...] = field(default=(), repr=False)
    driver: str = ''

    def public_dict(self):
        return {key: value for key, value in asdict(self).items()
                if key not in ('identity', 'container', 'ancestors')}

@dataclass(frozen=True)
class Inventory:
    status: str
    devices: list[UsbDevice]
    serial_ports: list[Port]
    message: str
    diagnostic: str
    # Exportable and privacy safe: no IMEI, IMSI, full PnP IDs or phone numbers.
    def public_dict(self) -> dict:
        return dict(status=self.status, devices=[d.public_dict() for d in self.devices],
                    serial_ports=[asdict(p) for p in self.serial_ports], message=self.message,
                    diagnostic=self.diagnostic)

def _clean(value: object, max_len: int = 110) -> str:
    return redact(str(value if value is not None else ""))[:max_len]

def _parse_windows(text: str) -> list[UsbDevice]:
    try:
        items = json.loads(text or "[]")
    except (TypeError, ValueError):
        raise LabError("تعذر تحليل بيانات Windows PnP.") from None
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list) or len(items) > 1024:
        raise LabError("استجابة Windows PnP غير متوقعة.")
    result = []
    for obj in items:
        if not isinstance(obj, dict):
            continue
        raw_id = str(obj.get("InstanceId", ""))
        name = _clean(obj.get("Name") or "USB device")
        vendor = _VENDOR.search(raw_id)
        if not vendor and not _NAME.search(name):
            continue
        pid = _PRODUCT.search(raw_id)
        vid = vendor.group(1).upper() if vendor else ""
        product = pid.group(1).upper() if pid else ""
        family = "Huawei" if vid == "12D1" else "ZTE" if vid == "19D2" else "Huawei / ZTE / Vodafone (غير مؤكد)"
        kind = _clean(obj.get("Class", ""), 40)
        status = _clean(obj.get("Status", "Unknown"), 30)
        com = _COM.search(str(obj.get("ComPort", ""))) or _COM.search(name)
        port = com.group().upper() if com else ""
        if status.lower() not in ("ok", "unknown", ""):
            mode, advice = "DRIVER_PROBLEM", "Windows أبلغ عن مشكلة؛ افتح Device Manager وافحص تعريف الجهاز."
        elif kind.casefold() in ("cdrom", "diskdrive") or _STORAGE.search(name):
            mode, advice = "STORAGE_ONLY", "قد تكون الفلاشة بوضع التخزين؛ تحتاج تعريف المودم أو تهيئة USB مناسبة للموديل، دون تغيير تلقائي."
        elif port or kind in _AT_CLASS:
            mode, advice = "SERIAL_CANDIDATE", "واجهة مودم/COM محتملة؛ جرّب اختيار المنفذ المناسب للفحص."
        else:
            mode, advice = "USB_DETECTED", "Windows يكتشف الجهاز لكن لم يُثبت وجود منفذ AT/COM بعد."
        result.append(UsbDevice(
            name=name, family=family, usb_id=f"{vid or '????'}:{product or '????'}",
            device_class=kind or "Unknown", os_status=status or "Unknown",
            mode=mode, com_port=port, advice=advice,
            identity=raw_id.casefold(), container=str(obj.get('ContainerId', '')).casefold(),
            ancestors=tuple(str(x).casefold() for x in (obj.get('Ancestors') or [obj.get('Parent', '')]) if x),
            driver=_clean(obj.get('DriverVersion', ''), 40)))
    # Keep technical interfaces for advanced details; grouping is separate.
    return result[:100]

def detect(platform_name: str | None = None, runner: Callable | None = None,
           port_provider: Callable[[], list[Port]] | None = None) -> Inventory:
    current_os = platform_name or platform.system()
    provider = port_provider or ports
    warnings = []
    try:
        serial_ports = provider()
    except (LabError, OSError) as exc:
        serial_ports = []
        warnings.append("تعذر قراءة منافذ COM المحلية.")
    devices: list[UsbDevice] = []
    if current_os == "Windows":
        run = runner or subprocess.run
        try:
            completed = run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _PNP_QUERY],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=12, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode != 0:
                warnings.append("تعذر فحص أجهزة Windows PnP؛ جرب Device Manager.")
            else:
                try:
                    devices = _parse_windows(completed.stdout.strip())
                except LabError:
                    warnings.append("تعذر تحليل نتيجة Windows PnP.")
        except (OSError, subprocess.TimeoutExpired):
            warnings.append("تعذر تشغيل فحص Windows PnP خلال المهلة.")
    elif current_os != "Linux":
        warnings.append("فحص Windows PnP متاح على Windows فقط.")

    has_modem_port = bool(serial_ports)
    if devices and any(x.mode == "DRIVER_PROBLEM" for x in devices) and not has_modem_port:
        status = "DRIVER_PROBLEM"
        message = "Windows اكتشف جهازًا، لكن تعريفًا أو واجهة USB به مشكلة."
    elif devices and not has_modem_port:
        status = "USB_NO_COM"
        message = "Windows اكتشف جهاز Huawei/ZTE، لكن لم يظهر منفذ COM."
    elif has_modem_port:
        status = "COM_AVAILABLE"
        message = "عُثر على منافذ COM؛ اختر منفذ AT واختبره (ليس كل منفذ مودمًا)."
    elif warnings:
        status = "DIAGNOSTIC_ERROR"
        message = "لم نستطع إكمال فحص الأجهزة؛ راجع حالة التشخيص."
    elif current_os == "Windows":
        status = "NOT_DETECTED"
        message = "لا يوجد جهاز Huawei/ZTE ظاهر أو منفذ COM. جرب منفذ USB آخر وافتح Device Manager."
    else:
        status = "NOT_DETECTED"
        message = "لم تُكتشف منافذ Serial؛ على Linux افحص lsusb والتعريفات."
    return Inventory(status, devices, serial_ports, message, " | ".join(warnings) if warnings else "OK")

def to_diagnostic_json(inventory: Inventory) -> str:
    """Export sanitized inventory even when no COM port exists."""
    # Includes no device instance path or USB serial value.
    return json.dumps(inventory.public_dict(), ensure_ascii=False, indent=2) + "\n"
