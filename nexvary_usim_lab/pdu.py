"""Bounded SMS-DELIVER decoder (3GPP TS 23.040/23.038).

Returns local inbox content only. Never export subscriber addresses or messages.
Concatenated parts are labelled, not silently merged across senders/references.
"""
import re
from .core import LabError

GSM = ('@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ'
       ' !"#¤%&\'()*+,-./0123456789:;<=>?'
       '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§'
       '¿abcdefghijklmnopqrstuvwxyzäöñüà')
EXT = {10:'\f',20:'^',40:'{',41:'}',47:'\\',60:'[',61:'~',62:']',64:'|',101:'€'}

def _septets(data, count, start=0):
    values=[]
    for n in range(count):
        bit=start+n*7; byte=bit//8; shift=bit%8
        if bit+7>len(data)*8: raise LabError('SMS PDU truncated.')
        value=(data[byte]>>shift)
        if shift>1: value|=data[byte+1]<<(8-shift)
        values.append(value&127)
    text=[];escape=False
    for value in values:
        if escape:
            if value not in EXT: raise LabError('Unsupported GSM extension.')
            text.append(EXT[value]);escape=False
        elif value==27:escape=True
        else:text.append(GSM[value])
    if escape:raise LabError('Truncated GSM escape.')
    return ''.join(text)

def deliver(hex_pdu, tpdu_length=None):
    if not isinstance(hex_pdu,str) or not re.fullmatch('[0-9A-Fa-f]{2,1024}',hex_pdu) or len(hex_pdu)%2:
        raise LabError('Invalid SMS PDU.')
    raw=bytes.fromhex(hex_pdu);pos=0
    def take(n):
        nonlocal pos
        if n<0 or pos+n>len(raw):raise LabError('SMS PDU truncated.')
        value=raw[pos:pos+n];pos+=n;return value
    smsc=take(1)[0];take(smsc);start=pos
    if tpdu_length is not None and (type(tpdu_length) is not int or len(raw)-start!=tpdu_length):raise LabError('SMS TPDU length mismatch.')
    flags=take(1)[0]
    if flags&3:raise LabError('Only received SMS-DELIVER is supported.')
    size=take(1)[0];toa=take(1)[0]
    if size>20:raise LabError('SMS sender exceeds limit.')
    address=take((size+1)//2)
    if toa&0x70==0x50:
        sender=_septets(address,size*4//7)
    else:
        digits=''.join(f'{b&15:X}{b>>4:X}' for b in address)[:size]
        if not digits.isdecimal():raise LabError('Unsupported SMS address.')
        sender=('+' if toa&0x70==0x10 else '')+digits
    take(1) # PID
    dcs=take(1)[0];stamp=take(7);udl=take(1)[0]
    # Reject compressed/reserved/message-class groups we have not implemented.
    if dcs&0xC0 or dcs&0x20 or dcs&0x0C not in (0,8):raise LabError('Unsupported SMS encoding.')
    ucs2=dcs&0x0C==8
    count=udl if ucs2 else (udl*7+7)//8
    if count>140:raise LabError('SMS user data exceeds limit.')
    payload=take(count)
    if pos!=len(raw):raise LabError('SMS PDU has trailing data.')
    header=0;part=None
    if flags&0x40:
        if not payload:raise LabError('Missing SMS UDH.')
        header=payload[0]+1
        if header>len(payload):raise LabError('Truncated SMS UDH.')
        off=1
        while off<header:
            if off+2>header:raise LabError('Invalid SMS UDH.')
            tag,length=payload[off:off+2];off+=2
            if off+length>header:raise LabError('Invalid SMS UDH.')
            value=payload[off:off+length];off+=length
            if tag in (0x24,0x25):raise LabError('National GSM shift table is unsupported.')
            if tag in (0,8):
                if length!=(3 if tag==0 else 4) or part is not None:raise LabError('Invalid concatenation header.')
                ref=int.from_bytes(value[:-2],'big');total,seq=value[-2:]
                if not 1<=seq<=total<=255:raise LabError('Invalid SMS part sequence.')
                part={'reference':ref,'total':total,'sequence':seq}
    if ucs2:
        body=payload[header:]
        if len(body)%2:raise LabError('Odd UCS2 length.')
        try:text=body.decode('utf-16-be',errors='strict')
        except UnicodeError:raise LabError('Invalid UCS2 data.') from None
        if any(ord(c)>0xffff for c in text):raise LabError('Non-UCS2 code point.')
    else:
        skipped=(header*8+6)//7
        if skipped>udl:raise LabError('SMS header exceeds UDL.')
        text=_septets(payload,udl-skipped,skipped*7)
    # Timestamp left out of reports; don't fabricate dates from invalid SCTS.
    return {'sender':sender,'text':text,'part':part,'encoding':'UCS2' if ucs2 else 'GSM7'}
