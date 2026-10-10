"""Independent native SCard client for an existing NEXVARY virtual reader.

No daemon/driver install, no service restart, no raw APDU API, no PIN or AUTH.
Synthetic ATR and session reselect limits must be accepted by the local host.
Reports native PC/SC separately from the modem host's Direct CSIM report.
"""
import argparse
import ctypes as C
import ctypes.util
import json
import platform
import sys
from pathlib import Path

class PcscError(RuntimeError):pass

def check_reader(reader=None):
    windows=platform.system()=='Windows'
    lib=C.WinDLL('winscard.dll') if windows else C.CDLL(C.util.find_library('pcsclite') or 'libpcsclite.so.1')
    D=C.c_uint32 if windows else C.c_ulong
    L=C.c_int32 if windows else C.c_long
    H=C.c_size_t if windows else C.c_ulong
    list_fn=lib.SCardListReadersW if windows else lib.SCardListReaders
    connect=lib.SCardConnectW if windows else lib.SCardConnect
    text=C.c_wchar_p if windows else C.c_char_p
    lib.SCardEstablishContext.argtypes=[D,C.c_void_p,C.c_void_p,C.POINTER(H)]
    list_fn.argtypes=[H,text,C.c_void_p,C.POINTER(D)]
    connect.argtypes=[H,text,D,D,C.POINTER(H),C.POINTER(D)]
    lib.SCardDisconnect.argtypes=[H,D];lib.SCardReleaseContext.argtypes=[H]
    class Pci(C.Structure):_fields_=[('protocol',D),('length',D)]
    lib.SCardTransmit.argtypes=[H,C.POINTER(Pci),C.c_void_p,D,C.c_void_p,C.c_void_p,C.POINTER(D)]
    for f in (lib.SCardEstablishContext,list_fn,connect,lib.SCardTransmit,lib.SCardDisconnect,lib.SCardReleaseContext):f.restype=L
    result={'schema':'nexvary.field-pcsc.v1','runtime':'native WinSCard' if windows else 'native pcsc-lite',
            'enumeration':False,'connected':False,'select_mf':False,'ef_dir_read':False,
            'usim_selected':False,'aka_verified':False,'calls_verified':False,'steps':[],
            'provenance':'live PC/SC operation; physical vs synthetic modem must be established by host evidence'}
    ctx=H();card=H();protocol=D()
    def checked(code):
        if code:raise PcscError('SCard status '+f'{code & 0xffffffff:08X}')
    try:
        checked(lib.SCardEstablishContext(2,None,None,C.byref(ctx)))
        size=D();checked(list_fn(ctx,None,None,C.byref(size)))
        if not 1<=size.value<=32768:raise PcscError('Invalid bounded reader list.')
        names=C.create_unicode_buffer(size.value) if windows else C.create_string_buffer(size.value)
        checked(list_fn(ctx,None,names,C.byref(size)))
        names=(''.join(names[:size.value]) if windows else names.raw.decode('utf-8')).split('\0')
        names=[n for n in names if n];result['enumeration']=True
        # Never send commands to an arbitrary system card just because it is first.
        candidates=[n for n in names if 'NEXVARY' in n.upper()]
        if reader is None:
            if len(candidates)!=1:raise PcscError('Choose exactly one NEXVARY virtual reader with --reader.')
            reader=candidates[0]
        if reader not in names:raise PcscError('Selected reader is not enumerated.')
        result['reader']=reader
        checked(connect(ctx,reader if windows else reader.encode(),2,1,C.byref(card),C.byref(protocol)))
        result['connected']=True
        def tx(apdu):
            sent=C.create_string_buffer(apdu);received=C.create_string_buffer(258);length=D(258);pci=Pci(protocol.value,C.sizeof(Pci))
            checked(lib.SCardTransmit(card,C.byref(pci),sent,len(apdu),None,received,C.byref(length)))
            if not 2<=length.value<=258:raise PcscError('Invalid card response size.')
            response=received.raw[:length.value]
            return response[:-2],response[-2:]
        def exchange(apdu,name):
            data,sw=tx(apdu)
            for _ in range(8):
                if sw[0] not in (0x61,0x9f):break
                next_data,sw=tx(bytes([0,0xc0,0,0,sw[1]]));data+=next_data
                if len(data)>2048:raise PcscError('Directory response exceeded bound.')
            result['steps'].append({'operation':name,'sw':sw.hex().upper(),'data_bytes':len(data)})
            if sw!=b'\x90\x00':raise PcscError('Card status '+sw.hex().upper())
            return data
        exchange(bytes.fromhex('00A4000C023F00'),'SELECT MF');result['select_mf']=True
        fcp=exchange(bytes.fromhex('00A40004022F0000'),'SELECT EF_DIR / GET RESPONSE')
        # Same strict metadata parser, independently transported through SCard.
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from nexvary_usim_lab.virtual_sim import directory_metadata,record_aids
        length,count=directory_metadata(fcp);aids=set()
        result['directory']={'fcp':fcp.hex().upper(),'record_bytes':length,'records':count,'read_limit':8}
        for i in range(1,min(count,8)+1):
            record=exchange(bytes([0,0xb2,i,4,length]),f'READ RECORD {i}')
            if len(record)!=length:raise PcscError('Record size differs from FCP.')
            aids.update(record_aids(record))
        result['ef_dir_read']=True;result['aids']=[a.hex().upper() for a in sorted(aids)]
        for aid in sorted(aids):
            exchange(bytes([0,0xa4,4,4,len(aid)])+aid+b'\x00','SELECT discovered ADF')
            if aid[:7]==bytes.fromhex('A0000000871002'):result['usim_selected']=True
    except Exception as exc:
        result['error']=str(exc) if isinstance(exc,PcscError) else 'PC/SC or directory metadata unavailable; no automatic retry.'
    finally:
        if card.value:lib.SCardDisconnect(card,0)
        if ctx.value:lib.SCardReleaseContext(ctx)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--consent',action='store_true');p.add_argument('--reader');p.add_argument('--export');a=p.parse_args()
    if not a.consent:p.error('Explicit --consent required for directory read; start host with separate consent first.')
    result=check_reader(a.reader);raw=json.dumps(result,indent=2,ensure_ascii=False)
    if a.export:
        with Path(a.export).open('x',encoding='utf-8') as f:f.write(raw)
    print(raw.encode('ascii','backslashreplace').decode())
    return 0 if result['ef_dir_read'] else 2
if __name__=='__main__':raise SystemExit(main())
