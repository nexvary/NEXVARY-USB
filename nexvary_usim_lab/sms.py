"""Single-part UCS2 SMS-SUBMIT encoding. Software tested, modem unverified."""
import re
from .core import LabError

def ucs2_submit(number, text):
    if not isinstance(number,str) or not re.fullmatch(r'\+[1-9][0-9]{6,14}',number):
        raise LabError('أدخل رقمًا دوليًا صحيحًا.')
    if not isinstance(text,str) or not 1 <= len(text) <= 70:
        raise LabError('رسالة UCS2 واحدة: من 1 إلى 70 حرفًا.')
    if any(ord(c)<32 or ord(c)>0xffff or 0xd800<=ord(c)<=0xdfff for c in text):
        raise LabError('UCS2 يدعم أحرف BMP دون رموز Emoji أو أحرف تحكم.')
    digits=number[1:]; padded=digits + ('F' if len(digits)%2 else '')
    address=''.join(padded[i+1]+padded[i] for i in range(0,len(padded),2))
    payload=text.encode('utf-16-be')
    tpdu='0100'+f'{len(digits):02X}'+'91'+address+'0008'+f'{len(payload):02X}'+payload.hex().upper()
    return '00'+tpdu,len(bytes.fromhex(tpdu))
