"""Actual Linux pcsc-lite/vpcd/client test; modem and card payloads synthetic.

Only for a disposable test runner with no pcscd already running. Does not
modify system reader configuration or stop an existing daemon. No raw logs.
"""
import json,os,sys,tempfile,subprocess,time,ctypes,ctypes.util
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'))
from nexvary_usim_lab.core import DemoSerial
from nexvary_usim_lab.virtual_reader import VirtualReaderService
from test_virtual_sim import FCP,RECORD

def response(value):return (f'+CSIM: {len(value)},"{value}"','OK')
class SyntheticModem(DemoSerial):
    ANSWERS={'AT+CPIN?':('+CPIN: READY','OK'),
             'AT+CSIM=14,"00A4000C023F00"':response('9000'),
             'AT+CSIM=14,"00A40004022F00"':response(FCP.hex().upper()+'9000'),
             'AT+CSIM=10,"00B201040B"':response(RECORD.hex().upper()+'9000')}

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--pcscd',default='pcscd');parser.add_argument('--driver',default='/usr/lib/pcsc/drivers/serial/libifdvpcd.so');args=parser.parse_args()
    if sys.platform!='linux':raise RuntimeError('Linux integration only.')
    if Path('/run/pcscd/pcscd.comm').exists():raise RuntimeError('Existing PC/SC daemon detected; test refuses to stop or reuse it.')
    if not Path(args.driver).is_file():raise RuntimeError('Install vsmartcard-vpcd.')
    lib=ctypes.CDLL(ctypes.util.find_library('pcsclite') or 'libpcsclite.so.1')
    # pcsc-lite LONG/DWORD are native long on Unix (Windows ABI differs).
    Long=ctypes.c_long; ULong=ctypes.c_ulong
    for name in ('SCardEstablishContext','SCardListReaders','SCardConnect','SCardTransmit','SCardDisconnect','SCardReleaseContext'):getattr(lib,name).restype=Long
    lib.SCardEstablishContext.argtypes=[ULong,ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ULong)]
    lib.SCardListReaders.argtypes=[ULong,ctypes.c_char_p,ctypes.c_void_p,ctypes.POINTER(ULong)]
    lib.SCardConnect.argtypes=[ULong,ctypes.c_char_p,ULong,ULong,ctypes.POINTER(ULong),ctypes.POINTER(ULong)]
    lib.SCardDisconnect.argtypes=[ULong,ULong]
    lib.SCardReleaseContext.argtypes=[ULong]
    def check(code):
        if code:raise RuntimeError('PC/SC operation failed: '+hex(code&0xffffffff))
    class Pci(ctypes.Structure):_fields_=[('protocol',ULong),('length',ULong)]
    lib.SCardTransmit.argtypes=[ULong,ctypes.POINTER(Pci),ctypes.c_void_p,ULong,ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ULong)]
    service=VirtualReaderService('COM9',0,True,True,True,SyntheticModem,60);service.start()
    daemon=None;context=ULong();handle=ULong();active=ULong();names=[]
    with tempfile.TemporaryDirectory() as temp:
        try:
            driver=str(Path(args.driver).resolve())
            Path(temp,'nexvary').write_text(f'FRIENDLYNAME "NEXVARY Virtual SIM Reader (SYNTHETIC TEST)"\nDEVICENAME 127.0.0.1:{service.vpcd_port}\nLIBPATH {driver}\nCHANNELID {service.vpcd_port}\n')
            daemon_log=open(Path(temp,'pcscd-synthetic.log'),'w+b')
            daemon=subprocess.Popen([args.pcscd,'--foreground','--debug','--disable-polkit','--config',temp],stdout=daemon_log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if daemon.poll() is not None:
                    daemon_log.flush();daemon_log.seek(0)
                    log=daemon_log.read().decode('utf-8',errors='replace')
                    raise RuntimeError('Isolated pcscd could not start (synthetic test): '+log[-4096:])
                if lib.SCardEstablishContext(2,None,None,ctypes.byref(context))==0:break
                time.sleep(.1)
            else:
                daemon_log.flush();daemon_log.seek(0)
                log=daemon_log.read().decode('utf-8',errors='replace')
                raise RuntimeError('PC/SC context deadline: '+log[-4096:]+'; reader state='+service.state)
            count=ULong()
            check(lib.SCardListReaders(context,None,None,ctypes.byref(count)))
            buffer=ctypes.create_string_buffer(count.value)
            check(lib.SCardListReaders(context,None,buffer,ctypes.byref(count)))
            names=[x.decode() for x in buffer.raw.split(b'\x00') if x]
            reader=next(x for x in names if x.startswith('NEXVARY Virtual SIM Reader'))
            check(lib.SCardConnect(context,reader.encode(),2,1,ctypes.byref(handle),ctypes.byref(active)))
            def transmit(value):
                tx=(ctypes.c_ubyte*len(value)).from_buffer_copy(value); rx=(ctypes.c_ubyte*4096)();n=ULong(4096); pci=Pci(1,ctypes.sizeof(Pci))
                check(lib.SCardTransmit(handle,ctypes.byref(pci),tx,len(value),None,rx,ctypes.byref(n)))
                return bytes(rx[:n.value])
            assert transmit(bytes.fromhex('00A4000C023F00'))==b'\x90\x00'
            assert transmit(bytes.fromhex('00A40004022F0000'))==bytes([0x61,len(FCP)])
            assert transmit(bytes([0,0xc0,0,0,len(FCP)]))==FCP+b'\x90\x00'
            assert transmit(bytes.fromhex('00B201040B'))==RECORD+b'\x90\x00'
            check(lib.SCardDisconnect(handle,0));handle=ULong()
            # Stop/removal is visible to the external PC/SC consumer.
            service.stop();time.sleep(.3)
            error=lib.SCardConnect(context,reader.encode(),2,1,ctypes.byref(handle),ctypes.byref(active))
            assert error!=0,'Card removal failed'
            report={'pcsc_runtime':'actual pcsc-lite + vsmartcard-vpcd + external ctypes client','modem':'synthetic injected serial',
                    'reader_enumerated':True,'select_mf':True,'ef_dir_fcp':True,'read_record':True,'card_removal':True,
                    'atr':'explicit emulated transport ATR 3B00','reset':'session reselect only','hardware_verified':False,'aka_verified':False,'calls_verified':False}
            Path('virtual-pcsc-evidence.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report))
        finally:
            if handle.value:lib.SCardDisconnect(handle,0)
            if context.value:lib.SCardReleaseContext(context)
            service.stop()
            if daemon:
                daemon.terminate()
                try:daemon.wait(timeout=5)
                except subprocess.TimeoutExpired:daemon.kill();daemon.wait(timeout=2)
if __name__=='__main__':main()
