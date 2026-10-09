"""Bounded read-only EF_DIR application inventory, no subscriber EFs."""
import re
from .core import LabError, Reading
from .device_operations import ATSession

def tlvs(data):
    offset=0;items=[]
    while offset<len(data):
        if data[offset]==0xff and all(b==0xff for b in data[offset:]):break
        if offset+2>len(data):raise LabError('Malformed SIM TLV.')
        tag=data[offset];length=data[offset+1];offset+=2
        if length&0x80:
            count=length&0x7f
            if count not in (1,2) or offset+count>len(data):raise LabError('Malformed SIM TLV length.')
            length=int.from_bytes(data[offset:offset+count],'big');offset+=count
        if offset+length>len(data):raise LabError('Truncated SIM TLV.')
        items.append((tag,data[offset:offset+length]));offset+=length
    return items

class DirectoryFailure(LabError):
    def __init__(self, status, message, sw=None):
        super().__init__(message); self.status=status; self.sw=sw

def _crsm(session,command):
    state,lines=session._command(command,6)
    if state=='TIMEOUT':raise DirectoryFailure('TIMEOUT','قراءة دليل تطبيقات SIM انتهت بمهلة؛ لا يثبت عدم الدعم.')
    if state!='OK':raise DirectoryFailure('MODEM_ERROR','المودم رفض قراءة EF_DIR.')
    matches=[re.fullmatch(r'\+CRSM:\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*"([A-Fa-f0-9]*)")?',x) for x in lines if x.startswith('+CRSM:')]
    if len(matches)!=1 or matches[0] is None:raise LabError('استجابة CRSM غير صحيحة.')
    m=matches[0];sw=(int(m[1]),int(m[2]));raw=m[3] or ''
    if any(not 0<=x<=255 for x in sw):raise LabError('رمز CRSM خارج حدود SW1/SW2.')
    if sw not in ((144,0),) and sw[0] not in (145,159):raise DirectoryFailure('CARD_STATUS',f'البطاقة رفضت EF_DIR: SW={sw[0]:02X}{sw[1]:02X}',sw)
    if len(raw)%2 or len(raw)>1024:raise LabError('طول ملف SIM غير صحيح.')
    return bytes.fromhex(raw)

def applications(port,factory=None):
    with ATSession(port,factory=factory) as s:
        metadata=_crsm(s,'AT+CRSM=192,12032,0,0,0')
        record_length=None
        if metadata[:1]==b'\x62':
            outer=tlvs(metadata)
            for tag,value in tlvs(outer[0][1]):
                if tag==0x82 and len(value)>=5:record_length=int.from_bytes(value[2:4],'big')
        elif len(metadata)>=15 and metadata[13] in (1,3):record_length=metadata[14]
        if record_length is None or not 1<=record_length<=255:
            raise LabError('تعذر تحديد طول سجلات EF_DIR؛ لم نفترض تطبيق USIM.')
        found={}
        for index in range(1,9):
            try:record=_crsm(s,f'AT+CRSM=178,12032,{index},4,{record_length}')
            except DirectoryFailure as exc:
                if index>1 and exc.sw==(0x6a,0x83):break
                raise
            for tag,value in tlvs(record):
                if tag!=0x61:continue
                for inner,aid in tlvs(value):
                    if inner==0x4f and 7<=len(aid)<=16:
                        name='USIM' if aid.startswith(bytes.fromhex('A0000000871002')) else 'ISIM' if aid.startswith(bytes.fromhex('A0000000871004')) else 'Other'
                        if name!='Other':found[aid.hex().upper()]=name
        return [Reading('SIM application', 'DECLARED', name+' / AID '+aid,
                        'EF_DIR يعلن التطبيق؛ لا يثبت الوصول أو AKA') for aid,name in found.items()] or [Reading('SIM applications','UNKNOWN','لا تطبيقات USIM/ISIM معلنة ضمن السجلات المقروءة','لا يثبت غياب التطبيقات')]
