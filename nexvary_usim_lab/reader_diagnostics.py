"""Single owner-operated field tool; redacted stages never authorize calling."""
import json
from datetime import datetime,timezone
from . import __version__
from .core import Reading, Report, LabError
from .device_operations import ATSession
from .virtual_sim import VirtualCardEngine

def field_report(port, consent=False, factory=None):
    if not consent: raise LabError('Local SIM discovery requires explicit owner consent.')
    readings=[]
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
            engine.initialize()
            readings.extend([Reading('SIM status','OK','+CPIN: READY','No PIN or PUK sent.'),
                             Reading('Direct CSIM','ACCEPTED','SELECT MF SW=9000','Actual card operation; not AKA.')])
            aids=engine.discover_applications()
            readings.append(Reading('EF_DIR CSIM','READABLE','Metadata and bounded records read','No subscriber EFs.'))
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
