"""Single owner-operated field tool; redacted stages never authorize calling."""
import json
from datetime import datetime,timezone
from . import __version__
from .core import Reading, Report, LabError, ports
from .device_operations import ATSession
from .virtual_sim import VirtualCardEngine

def field_report(port, consent=False, factory=None, inventory=None, service_state=None):
    if not consent: raise LabError('Local SIM discovery requires explicit owner consent.')
    readings=[Reading('Serial port','SELECTED',port,'Current discovered/selected port, never a connection constant.')]
    # USB identity comes only from current local inventory, not prior fixtures.
    try:
        found = (ports() if factory is None else []) if inventory is None else inventory
        selected = next((p for p in found if p.device == port), None)
        if selected and selected.vid != '—' and selected.pid != '—':
            readings.append(Reading('USB VID:PID','OBSERVED',selected.vid+':'+selected.pid,'Current local USB inventory.'))
        else:
            readings.append(Reading('USB VID:PID','UNVERIFIED','Not available','No identity inferred from a model name.'))
    except LabError:
        readings.append(Reading('USB VID:PID','UNVERIFIED','Inventory unavailable','No identity inferred.'))
    readings.extend([
        Reading('Virtual reader service',service_state or 'UNVERIFIED','Local service state only','Separate from PC/SC enumeration and card access.'),
        Reading('PC/SC enumeration','UNVERIFIED','Not performed by Direct CSIM diagnostics','Use explicit PC/SC inventory; no reader inferred from the service.'),
        Reading('PC/SC APDU transfer','UNVERIFIED','Not performed','Requires a chosen reader and independent application test.')])
    with ATSession(port,factory=factory) as session:
        for name,command in (('Manufacturer','AT+CGMI'),('Model','AT+CGMM'),('Firmware','AT+CGMR')):
            state,lines=session._command(command,4)
            # Only non-subscriber modem identity, never arbitrary response logs.
            import re
            value=next((x for x in lines if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._-]{0,47}',x)), 'Not available')
            readings.append(Reading(name,state,value,'Modem identity only.'))
            if state!='OK':
                return Report('NEXVARY USB Studio',__version__,datetime.now(timezone.utc).isoformat(),port,factory is not None,readings)
        engine=VirtualCardEngine(session)
        try:
            card=session.card_status()
            readings.append(card)
            if card.status != 'OK' or card.value != '+CPIN: READY':
                raise LabError('SIM READY not established; no APDU submitted.')
            engine.initialize(sim_ready_checked=True)
            readings.extend([Reading('Direct CSIM','ACCEPTED','SELECT MF SW=9000','Actual card operation; not AKA.')])
            aids=engine.discover_applications()
            readings.append(Reading('EF_DIR CSIM','READABLE','Metadata and bounded records read','No subscriber EFs.'))
            readings.append(Reading('EF_DIR FCP','READABLE',engine.directory_fcp.hex().upper(),'Actual directory metadata only; no subscriber files.'))
            readings.append(Reading('EF_DIR dimensions','READABLE',f'{engine.record_length} bytes; {engine.record_count} records',f'Read first {min(engine.record_count,8)} records; no guessed sizes.'))
            for index,record_apps in engine.directory_records:
                readings.append(Reading(f'EF_DIR record {index}','READABLE',', '.join(a.hex().upper() for a in record_apps) or 'No USIM/ISIM AID','Only public application AIDs retained; other record fields suppressed.'))
            for aid in aids:
                name='USIM' if aid[:7]==bytes.fromhex('A0000000871002') else 'ISIM'
                readings.append(Reading(name+' directory','DECLARED',aid.hex().upper(),'AID from current EF_DIR.'))
                reply=engine.select_aid(aid)
                readings.append(Reading(name+' direct access','SELECTED' if reply.sw==b'\x90\x00' else 'CARD_STATUS','SW='+reply.sw.hex().upper(),'SELECT ADF only.'))
            if not aids:readings.append(Reading('SIM applications','UNKNOWN','No USIM/ISIM in first eight records','Not proof of absence.'))
        except LabError as exc:
            readings.append(Reading('Direct SIM transport',getattr(exc,'status','UNKNOWN'),str(exc),'No retry; no firmware or card modification.'))
    readings.extend([Reading('Virtual PC/SC','UNVERIFIED','Requires separate live PC/SC enumeration and transmit','Transport ATR and session reset are emulated, by explicit opt-in.'),
        Reading('USIM AKA','UNVERIFIED','Not tested','Separate scoped mTLS backend required.'),
        Reading('ePDG / IMS / Calls','UNVERIFIED','Not tested','SIM transport alone grants no operator entitlement.')])
    return Report('NEXVARY USB Studio',__version__,datetime.now(timezone.utc).isoformat(),port,factory is not None,readings)

def reader_evidence(report):
    rows=report.readings
    def seen(name,status):return any(r.name==name and r.status==status for r in rows)
    return {'schema':'nexvary.virtual-sim.v1','version':__version__,
        'simulated':report.simulated,'scope':'directory_read_only',
        'direct_select_mf':seen('Direct CSIM','ACCEPTED'),
        'ef_dir_read':seen('EF_DIR CSIM','READABLE'),
        'usim_selected':seen('USIM direct access','SELECTED'),
        'pcsc_enumerated':False,'aka_verified':False,'calling_authorized':False,
        'physical_atr_available':False,'electrical_reset_available':False}
