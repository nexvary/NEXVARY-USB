"""Native DLL COM factory and WinSock transport checks; never install a driver."""
import ctypes as C
import json
from pathlib import Path
import socket
import sys
import threading
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from nexvary_usim_lab.virtual_reader import VirtualReaderService
from test_reader_diagnostics import FieldModem
from test_virtual_sim import FCP, RECORD, AID

class Guid(C.Structure):
    _fields_=[('a',C.c_uint32),('b',C.c_uint16),('c',C.c_uint16),('d',C.c_ubyte*8)]
def guid(s):return Guid.from_buffer_copy(uuid.UUID(s).bytes_le)
def verify(output):
    output=Path(output).resolve()
    dll=C.WinDLL(str(output/'NEXVARYVirtualSIMReader.dll'))
    factory=C.c_void_p()
    get=dll.DllGetClassObject
    get.argtypes=[C.POINTER(Guid),C.POINTER(Guid),C.POINTER(C.c_void_p)];get.restype=C.c_int32
    cls=guid('67398A7C-9468-4F55-87BC-918521FA6020');iid=guid('00000001-0000-0000-C000-000000000046')
    assert get(C.byref(cls),C.byref(iid),C.byref(factory))==0 and factory.value
    def method(obj,index,restype,*types):
        vt=C.cast(obj,C.POINTER(C.POINTER(C.c_void_p))).contents
        return C.WINFUNCTYPE(restype,C.c_void_p,*types)(vt[index])
    entry=C.c_void_p();entry_iid=guid('1bec7499-8881-4f2b-b01c-a1a907304afc')
    assert method(factory,3,C.c_int32,C.c_void_p,C.POINTER(Guid),C.POINTER(C.c_void_p))(factory,None,C.byref(entry_iid),C.byref(entry))==0
    method(entry,2,C.c_uint32)(entry);method(factory,2,C.c_uint32)(factory)
    assert dll.DllCanUnloadNow()==0
    native=C.CDLL(str(output/'harness/transport.dll'))
    native.vicc_init.argtypes=[C.c_char_p,C.c_ushort];native.vicc_init.restype=C.c_void_p
    for n in ['vicc_present','vicc_exit']:
        getattr(native,n).argtypes=[C.c_void_p];getattr(native,n).restype=C.c_int
    native.vicc_transmit.argtypes=[C.c_void_p,C.c_size_t,C.c_void_p,C.POINTER(C.c_void_p)];native.vicc_transmit.restype=C.c_int
    native.release_response.argtypes=[C.c_void_p]
    # Genuine native transport into the current host; card/modem explicitly synthetic.
    service=VirtualReaderService('COM9',0,True,True,True,FieldModem);service.start()
    ctx=native.vicc_init(b'127.0.0.1',service.vpcd_port)
    assert ctx
    try:
        assert native.vicc_present(ctx)==1, {'host_state':service.state,'audit':list(service.audit)}
        def transmit(data):
            response=C.c_void_p();command=C.create_string_buffer(data)
            count=native.vicc_transmit(ctx,len(data),command,C.byref(response))
            assert count>=2
            try:return C.string_at(response,count)
            finally:native.release_response(response)
        assert transmit(bytes.fromhex('00A4000C023F00'))==b'\x90\x00'
        assert transmit(bytes.fromhex('00A40004022F0000'))==bytes([0x61,len(FCP)])
        assert transmit(bytes([0,0xc0,0,0,len(FCP)]))==FCP+b'\x90\x00'
        assert transmit(bytes.fromhex('00B201040B'))==RECORD+b'\x90\x00'
        assert transmit(bytes.fromhex('00A40404')+bytes([len(AID)])+AID+b'\x00')==b'\x90\x00'
        service.stop();assert native.vicc_present(ctx)==0
    finally:service.stop();native.vicc_exit(ctx)
    # Connection attempted before listener exists must recover without phantom presence.
    server=socket.socket();server.bind(('127.0.0.1',0));port=server.getsockname()[1]
    ctx=native.vicc_init(b'127.0.0.1',port)
    assert ctx and native.vicc_present(ctx)==0
    server.listen();problems=[]
    def fragmented():
        try:
            with server.accept()[0] as peer:
                request=b''
                while len(request)<3:
                    chunk=peer.recv(3-len(request));assert chunk;request+=chunk
                assert request==b'\x00\x01\x04'
                for b in b'\x00\x02\x3B\x00':peer.sendall(bytes([b]));time.sleep(.03)
        except BaseException as e:problems.append(str(e))
    t=threading.Thread(target=fragmented);t.start()
    try:assert native.vicc_present(ctx)==1
    finally:native.vicc_exit(ctx);server.close();t.join(5)
    assert not t.is_alive() and not problems
    # A listener accepting the ATR request but never responding must time out.
    server=socket.socket();server.bind(('127.0.0.1',0));server.listen();done=threading.Event()
    def silent():
        with server.accept()[0] as peer:
            peer.recv(3);done.wait(8)
    t=threading.Thread(target=silent);t.start()
    ctx=native.vicc_init(b'127.0.0.1',server.getsockname()[1]);start=time.monotonic()
    try:
        assert native.vicc_present(ctx)==0
        elapsed=time.monotonic()-start;assert 2<=elapsed<6
    finally:native.vicc_exit(ctx);done.set();t.join(5);server.close()
    result={'schema':'nexvary.windows-driver-native-check.v1','dll_loaded':True,
            'com_class_factory':True,'driver_entry_created':True,
            'native_winsock_transport':True,'select_mf_synthetic_modem':True,'ef_dir_get_response_synthetic':True,
            'read_record_synthetic':True,'select_usim_adf_synthetic':True,
            'missing_host_absent':True,'reconnect_after_missing_listener':True,
            'fragmented_atr':True,'silent_host_timeout':True,'timeout_seconds':round(elapsed,2),
            'installed':False,'pcsc_enumerated':False,'hardware_tested':False,
            'signature':'unsigned development build; no certificate generated/imported',
            'scope':'COM construction and native transport harness, not OS reader enumeration'}
    (output/'NATIVE-CHECKS.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=='__main__':verify(sys.argv[1])
