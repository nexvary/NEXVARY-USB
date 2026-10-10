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

# Exercise the *new CSIM backend* behind real mTLS with independent WiFi client.
from test_csim_aka import CsimAkaTests
fixture=CsimAkaTests();backend=fixture.backend()
bridge=PrivateUsimBridge(backend,str(CERTS/'server.pem'),str(CERTS/'server-key.pem'),str(CERTS/'ca.pem'),pin('client'))
thread=threading.Thread(target=bridge.serve_forever,daemon=True);thread.start()
try:
    client=UsbAkaBackend(port=bridge.port,device_key='device',token='T'*40,server_ca=str(CERTS/'ca.pem'),client_cert=str(CERTS/'client.pem'),client_key=str(CERTS/'client-key.pem'),server_pin=pin('server'))
    assert client.authenticate('11'*16,'22'*16)==('72657370','63'*16,'69'*16)
    try:client.authenticate('11'*16,'22'*16)
    except Exception:pass
    else:raise AssertionError('Duplicate challenge accepted')
    assert sum(b'00880081' in x for x in fixture.fake.commands)==1
    print('CSIM + real mTLS + WiFi engine PASS; synthetic card/AKA, no carrier proof.')
finally:bridge.stop();thread.join(2)

# Staged strongSwan card callback contract uses the same *actual* mTLS client.
# It is not a loaded charon plugin or an IKE/ePDG proof.
from strongswan_card_adapter import StrongSwanCardAdapter
backend=SyntheticBackend()
bridge=PrivateUsimBridge(backend,str(CERTS/'server.pem'),str(CERTS/'server-key.pem'),str(CERTS/'ca.pem'),pin('client'))
thread=threading.Thread(target=bridge.serve_forever,daemon=True);thread.start()
try:
    identity='0123456789012345@nai.epc.mnc001.mcc001.3gppnetwork.org'
    client=UsbAkaBackend(identity=identity,port=bridge.port,device_key='synthetic-modem',token=TOKEN,server_ca=str(CERTS/'ca.pem'),client_cert=str(CERTS/'client.pem'),client_key=str(CERTS/'client-key.pem'),server_pin=pin('server'))
    adapter=StrongSwanCardAdapter(client)
    assert adapter.get_quintuplet(identity,b'R'*16,b'A'*16)==('SUCCESS',bytes.fromhex('34'*16),bytes.fromhex('56'*16),bytes.fromhex('12'*4))
    assert backend.calls==1
    assert adapter.get_quintuplet(identity,b'R'*16,b'A'*16)[0]=='FAILED'
    assert backend.calls==1
    print('Staged simaka callback + actual mTLS PASS; synthetic AKA; native strongSwan plugin not loaded.')
finally:bridge.stop();thread.join(2)
