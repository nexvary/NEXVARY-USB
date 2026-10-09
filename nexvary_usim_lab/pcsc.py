"""Fixed read-only PC/SC SELECT; no arbitrary APDU or PIN interface.

Windows uses native WinSCard (no third-party dependency); Linux uses optional
pyscard. Driver calls run in a killable child with a fixed deadline.
"""
import ctypes as C
import multiprocessing as mp
import platform
from .core import LabError, _sw_meaning
from .coordination import lease

def _windows(reader=None):
    dll=C.WinDLL('winscard.dll');D=C.c_uint32;H=C.c_size_t
    ctx=H();card=H();protocol=D()
    def checked(code):
        if code:raise LabError(f'PC/SC unavailable (status {code & 0xffffffff:08X}).')
    # Explicit ABI types protect pointer-size handles on x64.
    dll.SCardEstablishContext.argtypes=[D,C.c_void_p,C.c_void_p,C.POINTER(H)]
    dll.SCardListReadersW.argtypes=[H,C.c_wchar_p,C.c_wchar_p,C.POINTER(D)]
    dll.SCardConnectW.argtypes=[H,C.c_wchar_p,D,D,C.POINTER(H),C.POINTER(D)]
    dll.SCardDisconnect.argtypes=[H,D];dll.SCardReleaseContext.argtypes=[H]
    class PCI(C.Structure):_fields_=[('protocol',D),('length',D)]
    dll.SCardTransmit.argtypes=[H,C.POINTER(PCI),C.c_void_p,D,C.c_void_p,C.c_void_p,C.POINTER(D)]
    checked(dll.SCardEstablishContext(0,None,None,C.byref(ctx)))
    try:
        size=D();checked(dll.SCardListReadersW(ctx,None,None,C.byref(size)))
        if size.value>32768:raise LabError('PC/SC reader list too large.')
        buffer=C.create_unicode_buffer(size.value);checked(dll.SCardListReadersW(ctx,None,buffer,C.byref(size)))
        names=''.join(buffer[:size.value]).split('\0');names=[n for n in names if n]
        if reader is None:return names
        if reader not in names:raise LabError('القارئ المختار غير متصل.')
        checked(dll.SCardConnectW(ctx,reader,1,3,C.byref(card),C.byref(protocol))) # exclusive T0/T1
        command=bytes.fromhex('00A40004023F0000');sent=C.create_string_buffer(command);reply=C.create_string_buffer(258);length=D(258);pci=PCI(protocol.value,C.sizeof(PCI))
        checked(dll.SCardTransmit(card,C.byref(pci),sent,len(command),None,reply,C.byref(length)))
        response=reply.raw[:length.value]
        if len(response)<2:raise LabError('Invalid PC/SC card response.')
        sw=response[-2:].hex().upper()
        return f'SW={sw} — {_sw_meaning(sw)}؛ SELECT MF فقط، لا يثبت AKA.'
    finally:
        if card.value:dll.SCardDisconnect(card,0) # LEAVE_CARD, no reset
        dll.SCardReleaseContext(ctx)

def _operation(reader=None):
    if platform.system()=='Windows':return _windows(reader)
    try:from smartcard.System import readers
    except ImportError:raise LabError('تحتاج pyscard وخدمة PC/SC على هذا النظام.') from None
    available=readers()
    if reader is None:return [str(r) for r in available]
    match=next((r for r in available if str(r)==reader),None)
    if match is None:raise LabError('القارئ غير متصل.')
    from smartcard.ExclusiveConnectCardConnection import ExclusiveConnectCardConnection
    connection=ExclusiveConnectCardConnection(match.createConnection())
    try:
        connection.connect()
        data,sw1,sw2=connection.transmit([0,0xA4,0,4,2,0x3F,0,0])
        sw=f'{sw1:02X}{sw2:02X}'
        return f'SW={sw} — {_sw_meaning(sw)}؛ SELECT MF فقط، لا يثبت AKA.'
    finally:connection.disconnect()

def _worker(pipe,reader):
    try:pipe.send((True,_operation(reader)))
    except Exception:pipe.send((False,'PC/SC غير متاح؛ افحص الشريحة والقارئ وخدمة النظام، وقد يكون القارئ مشغولًا.'))
    finally:pipe.close()

def run(reader=None,confirmed=False,timeout=10):
    if reader is not None and (not confirmed or not isinstance(reader,str) or not 1<=len(reader)<=256):raise LabError('SELECT PC/SC يحتاج اختيار قارئ وموافقة صريحة.')
    with lease('pcsc:'+str(reader)):
        context=mp.get_context('spawn');parent,child=context.Pipe(False);process=context.Process(target=_worker,args=(child,reader),daemon=True)
        process.start();child.close()
        try:
            if not parent.poll(timeout):raise LabError('انتهت مهلة PC/SC؛ لم نرسل أمر كتابة.')
            ok,result=parent.recv()
            if not ok:raise LabError(result)
            return result
        except EOFError:raise LabError('PC/SC worker unavailable.') from None
        finally:
            parent.close();process.join(.2)
            if process.is_alive():process.terminate();process.join(2)
