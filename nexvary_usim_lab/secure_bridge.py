"""Opt-in private AKA transport: mTLS + pinned peers + scoped backend credential.

No automatic service or public bind. Tunnel the loopback port if using another
machine. Only one fixed AKA operation exists; arbitrary APDU/AT is impossible.
"""
import base64
import hashlib
import hmac
import http.client
import json
import socket
import ssl
import threading
import time
import re
import uuid
from .core import LabError
from .usim_backend import parse_aka

PATH='/v1/usim/aka'

def _pin(value):
    if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
        raise LabError('Invalid private TLS certificate pin.')
    return value

def _response_payload(result):
    res,ck,ik,auts=result
    if auts is not None:return 'SYNC_FAILURE',b'\xdc\x0e'+bytes.fromhex(auts)
    r,c,i=map(bytes.fromhex,(res,ck,ik))
    return 'SUCCESS',b'\xdb'+bytes([len(r)])+r+b'\x10'+c+b'\x10'+i

class PrivateUsimBridge:
    """Explicitly started, short-lived loopback listener; requires provisioned mTLS.

    Construct only after the owner has authorized a ModemUsimBackend session.
    No certificate generation, credential storage or operator bypass occurs here.
    """
    def __init__(self,backend,server_cert,server_key,client_ca,client_pin,port=0):
        self.backend=backend;self.pin=_pin(client_pin);self.stop_event=threading.Event()
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(server_cert,server_key);context.load_verify_locations(client_ca);context.verify_mode=ssl.CERT_REQUIRED
        self.context=context;self.active=None
        self.listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1',port));self.listener.listen(4);self.listener.settimeout(.25)
        self.port=self.listener.getsockname()[1];self.used=set()
    def __repr__(self):return '<PrivateUsimBridge: pinned private session>'
    def stop(self):
        self.stop_event.set();self.backend.revoke();self.listener.close()
        if self.active:
            try:self.active.shutdown(socket.SHUT_RDWR)
            except OSError:pass
    def serve_forever(self):
        try:
            while not self.stop_event.is_set():
                try:self.backend._authorize()
                except LabError:break
                try:wire,_=self.listener.accept()
                except socket.timeout:continue
                except OSError:break
                self._handle(wire)
        finally:
            self.stop()
    def _handle(self,wire):
        tls=None;timer=None
        def expire():
            target=tls or wire
            try:target.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        # Bounds the entire TLS handshake/header/body phase, including trickle input.
        timer=threading.Timer(8,expire);timer.daemon=True;timer.start()
        try:
            wire.settimeout(5);tls=self.context.wrap_socket(wire,server_side=True);self.active=tls
            if not hmac.compare_digest(hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest(),self.pin):return
            stream=tls.makefile('rb');first=stream.readline(512)
            if first!=b'POST '+PATH.encode()+b' HTTP/1.1\r\n':return
            headers={};total=0
            while True:
                line=stream.readline(1025);total+=len(line)
                if total>4096 or not line.endswith(b'\r\n'):return
                if line==b'\r\n':break
                key,value=line.decode('ascii').split(':',1);key=key.lower()
                if key in headers:return
                headers[key]=value.strip()
            if headers.get('content-type')!='application/json' or 'transfer-encoding' in headers or any(k.startswith(('forwarded','x-forwarded')) for k in headers):return
            length=int(headers.get('content-length','0'))
            if not 1<=length<=1024:return
            body=stream.read(length)
            if len(body)!=length:return
            result=json.loads(body)
            if not isinstance(result,dict) or set(result)!={'device_key','request_id','rand','autn'}:return
            request_id=result['request_id']
            if str(uuid.UUID(request_id))!=request_id or request_id in self.used or len(self.used)>=32:return
            auth=self.backend._authorization
            bearer=headers.get('authorization','')
            if not hmac.compare_digest(bearer,'Bearer '+auth.token) or result['device_key']!=auth.device_key:return
            self.backend._authorize();self.used.add(request_id)
            timer.cancel();timer=None;tls.settimeout(35)
            try:
                state,payload=_response_payload(self.backend.authenticate_ami(result['rand'],result['autn']))
                data=dict(state=state,payload=base64.b64encode(payload).decode(),request_id=request_id)
                status='200 OK'
            except Exception:
                status='403 Forbidden';data={'state':'UNAVAILABLE'}
            raw=json.dumps(data).encode()
            tls.sendall((f'HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {len(raw)}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n').encode()+raw)
        except Exception:
            pass  # Never log a credential, RAND/AUTN, RES, CK, IK or original exception.
        finally:
            if timer:timer.cancel()
            self.active=None
            if tls:tls.close()
            wire.close()

class BridgeUsimClient:
    """Same WiFi-Call backend call contract, via a provisioned loopback TLS tunnel."""
    def __init__(self,port,device_key,token,server_ca,client_cert,client_key,server_pin):
        if type(port) is not int or not 1<=port<=65535 or not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',token):
            raise LabError('Invalid private bridge configuration.')
        self.port=port;self.key=device_key;self.token=token;self.pin=_pin(server_pin)
        self.context=ssl.create_default_context(cafile=server_ca);self.context.minimum_version=ssl.TLSVersion.TLSv1_2
        self.context.load_cert_chain(client_cert,client_key)
    def __repr__(self):return '<BridgeUsimClient: private credentials>'
    def identity(self):raise LabError('Carrier identity is configured separately.')
    def authenticate_ami(self,rand,autn):
        import re
        if not all(isinstance(x,str) and re.fullmatch('[0-9A-Fa-f]{32}',x) for x in (rand,autn)):
            raise LabError('Invalid AKA challenge.')
        request_id=str(uuid.uuid4());connection=None;timer=None
        try:
            connection=http.client.HTTPSConnection('localhost',self.port,timeout=35,context=self.context)
            connection.connect()
            if not hmac.compare_digest(hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest(),self.pin):
                raise LabError('Private TLS peer pin mismatch.')
            tlswire=connection.sock
            def expire():
                try:tlswire.shutdown(socket.SHUT_RDWR)
                except OSError:pass
            timer=threading.Timer(35,expire);timer.daemon=True;timer.start()
            body=json.dumps(dict(device_key=self.key,request_id=request_id,rand=rand,autn=autn))
            connection.request('POST',PATH,body,headers={'Content-Type':'application/json','Authorization':'Bearer '+self.token})
            response=connection.getresponse();raw=response.read(4097)
            if response.status!=200 or response.getheader('Content-Type')!='application/json' or len(raw)>4096:raise LabError('Authorized modem authentication unavailable.')
            result=json.loads(raw)
            if set(result)!={'state','payload','request_id'} or result['request_id']!=request_id or result['state'] not in ('SUCCESS','SYNC_FAILURE'):
                raise LabError('Malformed private bridge response.')
            data=base64.b64decode(result['payload'],validate=True)
            if len(data)>128 or (result['state']=='SUCCESS' and data[:1]!=b'\xdb') or (result['state']=='SYNC_FAILURE' and data[:1]!=b'\xdc'):
                raise LabError('Malformed private AKA response.')
            return parse_aka(data)
        except LabError:raise
        except Exception:raise LabError('Private modem bridge unavailable; check pairing, certificates and consent.') from None
        finally:
            if timer:timer.cancel()
            if connection:connection.close()
    def authenticate(self,rand,autn):
        res,ck,ik,auts=self.authenticate_ami(rand,autn)
        return (auts,None,None) if auts is not None else (res,ck,ik)
