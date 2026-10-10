"""Bounded read-only EF_DIR application inventory, no subscriber EFs."""
import re
from .core import LabError, Reading
from .device_operations import ATSession

def tlvs(data):
    offset=0;items=[]
    while offset<len(data):
        if data[offset]==0xff and all(b==0xff for b in data[offset:]):break
        if offset+2>len(data):raise LabError('Malformed SIM TLV.')
        tag=data[offset];offset+=1
        if tag&0x1f==0x1f:
            for _ in range(3):
                if offset>=len(data):raise LabError('Malformed SIM TLV tag.')
                part=data[offset];offset+=1;tag=(tag<<8)|part
                if not part&0x80:break
            else:raise LabError('SIM TLV tag exceeds safe length.')
        if offset>=len(data):raise LabError('Malformed SIM TLV length.')
        length=data[offset];offset+=1
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
    matches=[re.fullmatch(r'\+CRSM:\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*"?([A-Fa-f0-9]*)"?)?',x) for x in lines if x.startswith('+CRSM:')]
    if len(matches)!=1 or matches[0] is None:raise LabError('استجابة CRSM غير صحيحة.')
    m=matches[0];sw=(int(m[1]),int(m[2]));raw=m[3] or ''
    if any(not 0<=x<=255 for x in sw):raise LabError('رمز CRSM خارج حدود SW1/SW2.')
    if sw not in ((144,0),) and sw[0] not in (145,159):raise DirectoryFailure('CARD_STATUS',f'البطاقة رفضت EF_DIR: SW={sw[0]:02X}{sw[1]:02X}',sw)
    if len(raw)%2 or len(raw)>1024:raise LabError('طول ملف SIM غير صحيح.')
    return bytes.fromhex(raw)

def applications(port,factory=None):
    with ATSession(port,factory=factory) as s:
        card=s.card_status()
        if card.status!='OK' or card.value!='+CPIN: READY':
            raise DirectoryFailure('NEEDS_USER' if card.status=='OK' else card.status,
                                   'لم تثبت جاهزية الشريحة؛ لم نرسل قراءة EF_DIR. '+card.value)
        metadata=_crsm(s,'AT+CRSM=192,12032,0,0,0')
        # A few AT implementations return SW=9000 but no metadata when P3=0.
        # Only after a complete successful transaction, request the standard
        # 15-byte legacy header once. Never retry on timeout/error/partial IO.
        if not metadata:
            metadata=_crsm(s,'AT+CRSM=192,12032,0,0,15')
        if not metadata:
            raise DirectoryFailure(
                'UNKNOWN',
                'استجاب المودم لأمر EF_DIR بلا بيانات وصفية حتى بعد طلب 15 بايت؛ '
                'لم نفترض غياب تطبيق USIM أو عدم دعم الشريحة.'
            )
        record_length=None;record_count=None
        if metadata[:1]==b'\x62':
            outer=tlvs(metadata)
            for tag,value in tlvs(outer[0][1]):
                if tag==0x82 and len(value)==5 and value[0]&7 in (2,6):
                    record_length=int.from_bytes(value[2:4],'big');record_count=value[4]
        elif len(metadata)>=15 and metadata[13] in (1,3):record_length=metadata[14]
        if record_length is None or not 1<=record_length<=255:
            raise DirectoryFailure('UNKNOWN','تعذر تحديد طول سجلات EF_DIR من وصف الملف؛ قد تكون الصيغة غير متوافقة. لم نفترض غياب USIM.')
        found={}
        for index in range(1,min(record_count or 8,8)+1):
            try:record=_crsm(s,f'AT+CRSM=178,12032,{index},4,{record_length}')
            except DirectoryFailure as exc:
                if index>1 and exc.sw==(0x6a,0x83):break
                raise
            if len(record)!=record_length:raise LabError('طول سجل EF_DIR غير مطابق للبيانات الوصفية.')
            for tag,value in tlvs(record):
                if tag!=0x61:continue
                for inner,aid in tlvs(value):
                    if inner==0x4f and 7<=len(aid)<=16:
                        name='USIM' if aid.startswith(bytes.fromhex('A0000000871002')) else 'ISIM' if aid.startswith(bytes.fromhex('A0000000871004')) else 'Other'
                        if name!='Other':found[aid.hex().upper()]=name
        if record_count and record_count>8:
            raise DirectoryFailure('PARTIAL','قرأنا حد السجلات الآمن؛ دليل التطبيقات غير مكتمل.')
        return [Reading('SIM application', 'DECLARED', name+' / AID '+aid,
                        'EF_DIR يعلن التطبيق؛ لا يثبت الوصول أو AKA') for aid,name in found.items()] or [Reading('SIM applications','UNKNOWN','لا تطبيقات USIM/ISIM معلنة ضمن السجلات المقروءة','لا يثبت غياب التطبيقات')]
