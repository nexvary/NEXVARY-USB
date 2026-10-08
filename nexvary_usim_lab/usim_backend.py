"""In-process, explicit-consent USIM AKA adapter; no network listener or Ki access.

Interface matches WiFi-Call PhoneAkaBackend authenticate/authenticate_ami.
CCHO/CGLA logical channels and real carrier entitlement remain hardware gates.
"""
import re
import time
import secrets
from dataclasses import dataclass, field
from .core import LabError
from .device_operations import ATSession

@dataclass(repr=False)
class Authorization:
    device_key: str
    token: str = field(repr=False)
    expires: float
    scope: str = 'usim:authenticate'
    def __repr__(self): return '<Authorization: private>'

class ModemUsimBackend:
    def __init__(self, port, device_key, aid, authorization, token, consent=False, factory=None):
        if not consent: raise LabError('USIM AKA requires explicit current owner consent.')
        if not isinstance(aid,str) or not re.fullmatch(r'A0000000871002[0-9A-Fa-f]{0,18}',aid) or len(aid)%2:
            raise LabError('Only an explicitly discovered USIM application AID is permitted.')
        if not isinstance(token,str) or len(token)<32:
            raise LabError('Missing scoped backend authorization.')
        self._port=port; self._key=device_key; self._aid=aid.upper()
        self._authorization=authorization; self._token=token; self._factory=factory
        self._used=set(); self._count=0
    def __repr__(self): return '<ModemUsimBackend: private transient session>'
    def revoke(self):
        self._token=""
        self._used.clear()
    def identity(self): raise LabError('Carrier identity is not supplied by redacted diagnostics.')
    def _authorize(self):
        auth=self._authorization
        now=time.monotonic()
        if not isinstance(auth,Authorization) or auth.device_key!=self._key or auth.scope!='usim:authenticate' or not now<auth.expires<=now+300 or not secrets.compare_digest(auth.token,self._token):
            raise LabError('USIM backend authorization unavailable or expired.')
    def _apdu(self,session,channel,apdu):
        # Private implementation only, constructed by fixed operations below.
        state,lines=session._command(f'AT+CGLA={channel},{len(apdu)},"{apdu}"',6)
        if state=='TIMEOUT': raise LabError('USIM authentication timed out; do not retry automatically.')
        if state!='OK': raise LabError('Modem rejected the logical-channel operation.')
        matches=[re.fullmatch(r'\+CGLA:\s*(\d+)\s*,\s*"([0-9A-Fa-f]+)"',x) for x in lines if x.startswith('+CGLA:')]
        if len(matches)!=1 or matches[0] is None: raise LabError('Malformed USIM response.')
        m=matches[0]; raw=m.group(2)
        if int(m.group(1))!=len(raw) or len(raw)%2 or not 4<=len(raw)<=520: raise LabError('Malformed USIM response length.')
        return bytes.fromhex(raw)
    def authenticate_ami(self,rand,autn):
        self._authorize()
        if not all(isinstance(x,str) and re.fullmatch(r'[0-9A-Fa-f]{32}',x) for x in (rand,autn)):
            raise LabError('RAND and AUTN must each contain 16 bytes.')
        challenge=rand.upper()+autn.upper()
        if challenge in self._used or self._count>=32: raise LabError('Duplicate challenge or session limit.')
        self._used.add(challenge); self._count+=1
        with ATSession(self._port,factory=self._factory) as session:
            state,lines=session._command(f'AT+CCHO="{self._aid}"',6)
            channels=[x for x in lines if x.isdecimal()]
            if state!='OK' or len(channels)!=1: raise LabError('USIM logical channel unavailable.')
            channel=int(channels[0])
            try:
                if not 1<=channel<=3: raise LabError('This adapter supports logical channels 1–3 only.')
                self._authorize()
                data=self._apdu(session,channel,f'{channel:02X}8800812210{rand.upper()}10{autn.upper()}00')
                for _ in range(3):
                    if len(data)>=2 and data[-2] in (0x61,0x9f):
                        continuation=self._apdu(session,channel,f'{channel:02X}C00000{data[-1]:02X}')
                        data=data[:-2]+continuation
                    else: break
                if data[-2:]!=b'\x90\x00': raise LabError('Card rejected USIM authentication; status '+data[-2:].hex().upper())
                self._authorize()
                return parse_aka(data[:-2])
            finally:
                state,_=session._command(f'AT+CCHC={channel}',4)
                if state!='OK': raise LabError('Logical channel cleanup unconfirmed; stop the session.')
    def authenticate(self,rand,autn):
        res,ck,ik,auts=self.authenticate_ami(rand,autn)
        return (auts,None,None) if auts is not None else (res,ck,ik)

def parse_aka(data):
    if len(data)==16 and data[:2]==b'\xdc\x0e': return None,None,None,data[2:].hex().upper()
    if len(data)>=2 and data[0]==0xdb:
        n=data[1]; a=2+n; b=a+17
        if 4<=n<=16 and len(data) in (n+36,n+45) and data[a]==16 and data[b]==16:
            if len(data)==n+45 and data[n+36]!=8:raise LabError('Invalid optional AKA field.')
            return data[2:a].hex().upper(),data[a+1:b].hex().upper(),data[b+1:b+17].hex().upper(),None
    raise LabError('Invalid AKA result structure.')
