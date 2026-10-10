"""Restricted Direct Modem SIM Transport. No electrical reset, PIN or card writes.

Original implementation of TS 27.007 CSIM and short ISO 7816 T=0 framing.
ATR is deliberately not supplied by this transport. All failures invalidate the
session; a timed-out command (especially AUTHENTICATE) is never retransmitted.
"""
import re
from dataclasses import dataclass
from .core import LabError, Reading
from .device_operations import ATSession
from .sim_inspector import tlvs

class TransportFailure(LabError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status

@dataclass(repr=False)
class CardReply:
    data: bytes
    sw: bytes
    def __repr__(self): return '<CardReply: payload private>'
    @property
    def wire(self): return self.data + self.sw
    def require_success(self):
        if self.sw != b'\x90\x00':
            raise TransportFailure('CARD_STATUS', 'Card status SW=' + self.sw.hex().upper())
        return self.data

def short_apdu(value):
    if not isinstance(value, bytes) or not 4 <= len(value) <= 261:
        raise LabError('Only bounded short APDUs are supported.')
    if len(value) <= 5: return value, False
    lc = value[4]
    if lc == 0 or len(value) not in (5 + lc, 6 + lc):
        raise LabError('Invalid short APDU length; extended APDU unavailable.')
    return value, len(value) == 6 + lc

class CsimTransport:
    def __init__(self, session, mode='tpdu'):
        if mode not in ('tpdu', 'apdu'): raise LabError('Unknown modem framing profile.')
        self.session, self.mode = session, mode
        self.failed = False
    def send(self, apdu):
        value, case4 = short_apdu(apdu)
        if self.failed: raise TransportFailure('SESSION_UNCERTAIN', 'Stop and reconnect explicitly.')
        # T=0 case 4: send command-data TPDU without trailing Le. GET RESPONSE
        # is a distinct transaction following the actual card status.
        if self.mode == 'tpdu' and case4: value = value[:-1]
        encoded = value.hex().upper()
        state, lines = self.session._command(f'AT+CSIM={len(encoded)},"{encoded}"', 6)
        if state != 'OK':
            self.failed = True
            raise TransportFailure(state, 'CSIM transport incomplete or rejected; no automatic retry.')
        found = [re.fullmatch(r'\+CSIM:\s*(\d+)\s*,\s*"([0-9A-Fa-f]+)"', x)
                 for x in lines if x.startswith('+CSIM:')]
        if len(found) != 1 or found[0] is None:
            self.failed = True
            raise TransportFailure('MALFORMED', 'Invalid CSIM framing; payload suppressed.')
        length, raw = found[0].groups()
        if int(length) != len(raw) or len(raw) % 2 or not 4 <= len(raw) <= 516:
            self.failed = True
            raise TransportFailure('MALFORMED', 'Invalid CSIM response length.')
        response = bytes.fromhex(raw)
        return CardReply(response[:-2], response[-2:])
    def exchange(self, apdu):
        reply = self.send(apdu)
        # 6C correction is safe only for read/GET RESPONSE, never SELECT/AUTH.
        if reply.sw[0] == 0x6c and len(apdu) == 5 and apdu[1] in (0xb2, 0xc0):
            reply = self.send(apdu[:-1] + reply.sw[1:])
        data = bytearray(reply.data)
        for _ in range(8):
            if len(data) > 2048: break
            if reply.sw[0] not in (0x61, 0x9f): return CardReply(bytes(data), reply.sw)
            # Preserve GSM/UICC class on the basic channel; no guessed AID.
            get_response = bytes([apdu[0], 0xc0, 0, 0, reply.sw[1]])
            reply = self.send(get_response)
            if reply.sw[0] == 0x6c:
                reply = self.send(get_response[:-1] + reply.sw[1:])
            data.extend(reply.data)
        self.failed = True
        raise TransportFailure('CONTINUATION_LIMIT', 'Card continuation exceeded safe bounds.')

def directory_metadata(data):
    if data[:1] == b'\x62':
        outer = tlvs(data)
        if len(outer) != 1 or outer[0][0] != 0x62: raise LabError('Invalid EF_DIR FCP.')
        descriptors = [v for t,v in tlvs(outer[0][1]) if t == 0x82]
        ids = [v for t,v in tlvs(outer[0][1]) if t == 0x83]
        if len(descriptors) != 1 or ids != [b'\x2f\x00']:
            raise LabError('EF_DIR metadata missing or does not match requested file.')
        desc = descriptors[0]
        if len(desc) != 5 or desc[0] & 7 not in (2, 6): raise LabError('EF_DIR is not a supported record file.')
        length, count = int.from_bytes(desc[2:4], 'big'), desc[4]
    elif len(data) >= 15 and data[4:6] == b'\x2f\x00' and data[13] in (1, 3):
        length = data[14]
        count = int.from_bytes(data[2:4], 'big') // length if length else 0
    else: raise LabError('EF_DIR metadata incomplete; no guessed record reads.')
    if not 1 <= length <= 255 or not 1 <= count <= 255:
        raise LabError('Invalid EF_DIR record dimensions.')
    return length, count

def record_aids(data):
    result = set()
    for tag, value in tlvs(data):
        if tag != 0x61: continue
        for inner, aid in tlvs(value):
            if inner == 0x4f and 7 <= len(aid) <= 16 and aid[:7] in (
                    bytes.fromhex('A0000000871002'), bytes.fromhex('A0000000871004')):
                result.add(aid)
    return result

class VirtualCardEngine:
    """Basic-channel, read-only external policy: MF, EF_DIR and discovered ADFs.

    No arbitrary file reads, AUTH, MANAGE CHANNEL, PIN or writes over PC/SC.
    SELECT/GET RESPONSE data are returned only from the physical transport.
    """
    def __init__(self, session, mode='tpdu', mf_p2=0x0c):
        if mf_p2 not in (0,4,12): raise LabError('Invalid SELECT MF profile.')
        self.session, self.transport, self.mf_p2 = session, CsimTransport(session, mode), mf_p2
        self.ready = False
        self.selected = None
        self.record_length = self.record_count = None
        self.aids = set()
    def initialize(self):
        self.ready = False; self.selected = None; self.aids.clear()
        self.record_length = self.record_count = None
        state, lines = self.session._command('AT+CPIN?', 4)
        if state != 'OK' or lines != ['+CPIN: READY']:
            raise TransportFailure('NEEDS_USER' if state == 'OK' else state, 'SIM READY not established. No PIN/PUK submitted.')
        reply = self.transport.exchange(bytes([0,0xa4,0,self.mf_p2,2,0x3f,0]))
        reply.require_success()
        self.ready = True; self.selected = 'mf'
    def transmit(self, apdu):
        value, _ = short_apdu(apdu)
        if not self.ready: raise TransportFailure('NOT_READY', 'Card session not ready.')
        # No logical channel or secure messaging impersonation.
        if value[0] != 0: raise LabError('Read-only basic channel CLA 00 only.')
        ins = value[1]
        target = None
        if ins == 0xa4:
            if len(value) < 7 or value[3] not in (0,4,12): raise LabError('SELECT policy denied.')
            payload = value[5:5+value[4]]
            if value[2] == 0 and payload in (b'\x3f\x00', b'\x2f\x00'):
                target = 'mf' if payload == b'\x3f\x00' else 'dir'
                if target == 'dir' and self.selected != 'mf': raise LabError('Select MF before EF_DIR.')
            elif value[2] == 4 and payload in self.aids: target = 'adf'
            else: raise LabError('Only discovered USIM/ISIM AIDs and fixed directory SELECTs permitted.')
        elif ins == 0xb2:
            if len(value) != 5 or self.selected != 'dir' or value[3] != 4 or self.record_length is None or not 1 <= value[2] <= min(self.record_count, 8) or value[4] != self.record_length:
                raise LabError('Only records described by current EF_DIR metadata permitted.')
        else: raise LabError('Operation outside read-only Virtual SIM Reader scope.')
        reply = self.transport.exchange(value)
        if ins == 0xa4:
            self.selected = target if reply.sw == b'\x90\x00' else None
            if target == 'dir':
                self.record_length = self.record_count = None
                if reply.sw == b'\x90\x00' and reply.data:
                    self.record_length, self.record_count = directory_metadata(reply.data)
        elif reply.sw == b'\x90\x00':
            if len(reply.data) != self.record_length: raise LabError('EF_DIR record length mismatch.')
            self.aids.update(record_aids(reply.data))
        return reply
    def discover_applications(self):
        self.transmit(bytes([0,0xa4,0,self.mf_p2,2,0x3f,0])).require_success()
        reply = self.transmit(bytes.fromhex('00A40004022F0000'))
        reply.require_success()
        if self.record_length is None: raise LabError('No EF_DIR metadata. USIM support remains unknown.')
        for index in range(1, min(self.record_count,8)+1):
            self.transmit(bytes([0,0xb2,index,4,self.record_length])).require_success()
        return sorted(self.aids)
    def select_aid(self, aid):
        if aid not in self.aids: raise LabError('AID must be discovered on this card in this session.')
        return self.transmit(bytes([0,0xa4,4,4,len(aid)]) + aid + b'\x00')

def inspect_direct(port, consent=False, factory=None):
    if not consent: raise LabError('Direct SIM discovery requires local owner consent.')
    rows = []
    try:
        with ATSession(port, factory=factory) as session:
            engine = VirtualCardEngine(session)
            engine.initialize()
            rows += [Reading('Direct CSIM', 'ACCEPTED', 'SELECT MF SW=9000', 'Actual operation; not AKA.')]
            aids = engine.discover_applications()
            for aid in aids:
                name = 'USIM' if aid[:7].hex().upper().endswith('1002') else 'ISIM'
                rows.append(Reading(name+' directory', 'DECLARED', aid.hex().upper(), 'EF_DIR via CSIM; no subscriber EFs.'))
                reply = engine.select_aid(aid)
                rows.append(Reading(name+' direct access', 'SELECTED' if reply.sw == b'\x90\x00' else 'CARD_STATUS', 'SW='+reply.sw.hex().upper(), 'SELECT ADF; no AUTHENTICATE.'))
            if not aids: rows.append(Reading('Direct applications','UNKNOWN','No USIM/ISIM in first eight records','Not proof of absence.'))
    except LabError as exc:
        rows.append(Reading('Direct SIM transport',getattr(exc,'status','UNKNOWN'),str(exc),'No retry, PIN or firmware modification.'))
    rows.append(Reading('USIM AKA','UNVERIFIED','Not tested','ePDG, IMS and calls remain independently unverified.'))
    return rows
