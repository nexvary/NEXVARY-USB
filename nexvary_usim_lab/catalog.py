"""Hardware research catalog: label evidence, not verified USIM capabilities.

Model names are confirmed from the user's photographs. Vendor hints from
USB VID are only identification suggestions; none proves APDU or AKA support.
No driver changes, firmware unlocks, or USB mode-switch operations.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

@dataclass(frozen=True)
class KnownModem:
    model: str
    brand: str
    marketed_as: str
    usb_vendor_id: str
    radio_generation: str
    evidence: str
    investigation: str

KNOWN_MODEMS = (
    KnownModem(
        "E153", "Huawei", "Huawei Mobile Broadband E153",
        "12D1", "3G", "Physical label photo (2026-10-08)",
        "Find AT serial interface; probe CSIM/CGLA; AKA unverified.",
    ),
    KnownModem(
        "MF190S", "ZTE", "ZTE HSUPA USB Stick MF190S",
        "19D2", "3G", "Physical label photo (2026-10-08)",
        "Find AT serial interface; determine vendor-specific UICC support.",
    ),
    KnownModem(
        "K3770", "Huawei", "Vodafone Mobile Broadband K3770 (Huawei edition)",
        "12D1", "3G", "Physical label photo (2026-10-08)",
        "Check storage-to-modem driver mode; distinguish from ZTE K3770-Z.",
    ),
)

def model_from_text(text: str) -> KnownModem | None:
    """Match explicit model in metadata, never infer model from USB VID alone."""
    if not isinstance(text, str):
        return None
    value = text.upper()
    for entry in KNOWN_MODEMS:
        pattern = rf"(?<![A-Z0-9]){re.escape(entry.model)}(?![A-Z0-9-])"
        if re.search(pattern, value):
            if entry.model == "K3770" and "ZTE" in value:
                continue
            return entry
    return None

def identification_hint(description: str, manufacturer: str, vid: str) -> str:
    entry = model_from_text(f"{description} {manufacturer}")
    if entry is not None:
        return f"{entry.brand} {entry.model} (model text match; AKA not tested)"
    vid = str(vid or "").upper().replace("0X", "")
    if vid == "12D1":
        return "Huawei-family USB VID; exact model unknown"
    if vid == "19D2":
        return "ZTE-family USB VID; exact model unknown"
    return "Unidentified serial device; may not be a cellular modem"

def load_profiles(extra_directory=None):
    """Read declarative evidence files; no executable plugin imports."""
    import json
    from pathlib import Path
    directories=[Path(__file__).with_name('profiles')]
    if extra_directory: directories.append(Path(extra_directory))
    profiles={}
    for directory in directories:
        for path in sorted(directory.glob('*.json'))[:100]:
            if path.stat().st_size>65536: continue
            try:
                data=json.loads(path.read_text(encoding='utf-8'))
                if data.get('schema_version')==1 and isinstance(data.get('model'),str) and isinstance(data.get('vendor'),str):
                    profiles[data['vendor']+' '+data['model']]=data
            except (ValueError,OSError,AttributeError): continue
    return profiles
