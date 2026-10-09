"""Redacted evidence contract for WiFi-Call; never a calling authorization.

Only fixed locally observed diagnostic results are exported. A syntax ACK,
cellular registration or SELECT MF never establishes AKA, voice or IMS.
No subscriber identity, raw reply, challenge or key is copied into the contract.
"""
from __future__ import annotations
import json
import re
from .core import LabError, Report

SCHEMA = "nexvary.usb.capabilities.v1"
STAGES = ("modem_at", "card_access", "apdu", "usim_aka", "epdg", "ims",
          "voice_capability", "incoming_call", "outgoing_call", "two_way_audio")


def _identification(rows, name):
    row = rows.get(name)
    # Identification strings only; avoid arbitrary modem response export.
    value = row.value if row and row.status == "OK" else ""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9 ._-]{0,47}|[0-9]{1,3}(?:\.[0-9]{1,3}){1,7}", value) or re.search(r"[0-9]{7,}|[A-Fa-f0-9]{32,}", value):
        return None
    return value


def export_capabilities(report: Report, *, select_mf=None, usb_id=None):
    """Build a local observation, not an imported/trusted remote attestation.

    Optional select_mf must be the result of the existing fixed consented test
    in the same session. A caller must retain the report.simulated flag whenever
    a mock serial transport is used. Device instances are never inferred from
    model aliases. USB ID must come from inventory, not a modem model guess.
    """
    if not isinstance(report, Report) or type(report.simulated) is not bool:
        raise LabError("A local diagnostic report is required.")
    if usb_id is not None and (not isinstance(usb_id, str) or not re.fullmatch(r"[0-9A-Fa-f]{4}:[0-9A-Fa-f]{4}", usb_id)):
        raise LabError("Invalid observed USB identifier.")
    rows = {r.name: r for r in report.readings}
    stages = {s: {"state": "not_verified", "evidence": "not_tested"} for s in STAGES}
    successful = "simulated" if report.simulated else "observed"
    connection = rows.get("Connection")
    if connection and connection.status == "OK" and connection.value == "OK":
        stages["modem_at"] = {"state": successful, "evidence": "basic_at_response"}
    sim = rows.get("SIM status")
    if sim and sim.status == "OK" and sim.value == "+CPIN: READY":
        stages["card_access"] = {"state": successful, "evidence": "sim_ready_status_only"}
    # Probe may contain a separately recorded fixed SELECT MF result.
    selected = select_mf or rows.get("APDU SELECT MF")
    if selected and selected.name == "APDU SELECT MF" and selected.status == "ACCEPTED" and selected.value == "SW=9000":
        stages["apdu"] = {"state": successful, "evidence": "fixed_select_mf_9000"}
    return {
        "schema": SCHEMA,
        "product": "NEXVARY USB Studio",
        "version": report.version,
        "timestamp_utc": report.timestamp_utc,
        "simulated": report.simulated,
        "identity": {"manufacturer": _identification(rows, "Manufacturer"),
                     "model": _identification(rows, "Model"),
                     "firmware": _identification(rows, "Firmware"),
                     "usb_id": usb_id.upper() if usb_id else None},
        "stages": stages,
        "route_status": "Not Verified",
        "calling_authorized": False,
        "subscriber_number_available": False,
        "limitations": ["Local diagnostic observation, not remote attestation",
                        "AT/card/APDU do not prove AKA, voice, ePDG, IMS or calls",
                        "Timeout is inconclusive, not proof of unsupported hardware"],
    }


def capability_json(report, **kwargs):
    return json.dumps(export_capabilities(report, **kwargs), indent=2, ensure_ascii=False)
