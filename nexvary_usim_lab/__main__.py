"""CLI entry: python -m nexvary_usim_lab [gui|ports|pcsc|probe|demo]."""
import argparse
import sys
from pathlib import Path

from .core import LabError, demo, pcsc_readers, ports, probe, select_master_file, to_csv, to_json
from .catalog import KNOWN_MODEMS, identification_hint
from .discovery import detect, to_diagnostic_json

def main(argv=None):
    parser = argparse.ArgumentParser(description="NEXVARY USB-USIM Lab — read-only local diagnostics")
    parser.add_argument("action", nargs="?", choices=("gui", "ports", "pcsc", "probe", "demo", "select-mf", "catalog", "diagnose", "bridge", "capabilities"), default="gui")
    parser.add_argument("--port", help="Explicit modem serial port, for probe only")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--export", help="Optional .json or .csv redacted report")
    parser.add_argument("--consent", action="store_true", help="Explicitly consent to the fixed on-card SELECT MF test")
    parser.add_argument("--config", help="Private bridge session configuration")
    args = parser.parse_args(argv)
    try:
        if args.action == "bridge":
            if not args.config or not args.consent: parser.error("bridge requires --config and --consent")
            from .bridge_session import serve
            serve(args.config,args.consent)
            return 0
        if args.action == "gui":
            from .gui import main as start_gui
            start_gui()
            return 0
        if args.action == "diagnose":
            result = to_diagnostic_json(detect())
            if args.export:
                path = Path(args.export)
                if path.suffix.lower() != ".json":
                    parser.error("USB diagnostic export must end with .json")
                with path.open("x", encoding="utf-8") as handle:
                    handle.write(result)
                print("Diagnostic saved:", path)
            else:
                # Windows consoles may use cp1252. Emit ASCII-safe JSON to stdout;
                # exported reports retain full Unicode UTF-8 text.
                print(result.encode('ascii', 'backslashreplace').decode('ascii'))
            return 0
        if args.action == "catalog":
            for entry in KNOWN_MODEMS:
                print(f"{entry.brand} {entry.model} | {entry.marketed_as} | {entry.investigation}")
            return 0
        if args.action == "ports":
            for p in ports():
                print(f"{p.device} | {p.manufacturer} | {p.description} | {p.vid}:{p.pid} | {identification_hint(p.description, p.manufacturer, p.vid)}")
            return 0
        if args.action == "pcsc":
            installed, found = pcsc_readers()
            print("PC/SC library present" if installed else "PC/SC library absent (optional pyscard)")
            for entry in found:
                print(entry)
            return 0
        if args.action in ("probe", "select-mf", "capabilities") and not args.port:
            parser.error("--port COM3 (or /dev/ttyUSB0) is required for probe")
        if args.action == "capabilities":
            from .wificall_capabilities import capability_json
            report = probe(args.port, args.baudrate)
            selected = select_master_file(args.port, args.baudrate) if args.consent else None
            # USB identity is accepted only from local inventory of this port.
            inventory = next((p for p in ports() if p.device == args.port), None)
            usb_id = f"{inventory.vid}:{inventory.pid}" if inventory and inventory.vid != "—" and inventory.pid != "—" else None
            result = capability_json(report, select_mf=selected, usb_id=usb_id)
            if args.export:
                path = Path(args.export)
                if path.suffix.lower() != ".json":
                    parser.error("Capability export must end with .json")
                with path.open("x", encoding="utf-8") as handle:
                    handle.write(result)
                print("Capability evidence saved:", path)
            else:
                print(result.encode('ascii', 'backslashreplace').decode('ascii'))
            return 0
        if args.action == "select-mf":
            if not args.consent:
                parser.error("select-mf requires explicit --consent from the card owner")
            if args.export:
                parser.error("select-mf does not export APDU results")
            result = select_master_file(args.port, args.baudrate)
            print(result.name, result.status, result.value)
            return 0
        report = demo() if args.action == "demo" else probe(args.port, args.baudrate)
        if args.export:
            path = Path(args.export)
            if path.suffix.lower() not in (".json", ".csv"):
                parser.error("--export must end with .json or .csv")
            if path.exists():
                parser.error("Refusing to overwrite an existing report")
            content = to_csv(report) if path.suffix.lower() == ".csv" else to_json(report)
            with path.open("x", encoding="utf-8", newline="") as handle:
                handle.write(content)
            print("Redacted report saved:", path)
        print(to_json(report))
        return 0
    except (OSError, ValueError):
        print("Operation unavailable: check private configuration and system access.", file=sys.stderr)
        return 2
    except LabError as exc:
        print(f"Diagnostic unavailable: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
