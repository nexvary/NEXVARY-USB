"""Actual private TLS transport with independent WiFi client; synthetic AKA only."""
import os,sys,threading
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'))
engine=Path(os.environ['NEXVARY_WIFI_ENGINE']).resolve();sys.path.insert(0,str(engine))
from nexvary_usb_backend import UsbAkaBackend
from test_secure_bridge import SyntheticBackend,CERTS,pin,TOKEN
from nexvary_usim_lab.secure_bridge import PrivateUsimBridge
backend=SyntheticBackend();bridge=PrivateUsimBridge(backend,str(CERTS/'server.pem'),str(CERTS/'server-key.pem'),str(CERTS/'ca.pem'),pin('client'))
thread=threading.Thread(target=bridge.serve_forever,daemon=True);thread.start()
try:
    client=UsbAkaBackend(port=bridge.port,device_key='synthetic-modem',token=TOKEN,server_ca=str(CERTS/'ca.pem'),client_cert=str(CERTS/'client.pem'),client_key=str(CERTS/'client-key.pem'),server_pin=pin('server'))
    assert client.authenticate('11'*16,'22'*16)==('12'*4,'34'*16,'56'*16)
    assert backend.calls==1
    print('Cross-project TLS PASS; independent engine client, synthetic AKA. Hardware and calls not verified.')
finally:bridge.stop();thread.join(2)
