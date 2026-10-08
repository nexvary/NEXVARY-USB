"""Real loopback mTLS transport, synthetic backend and PUBLIC CI certificates."""
import hashlib,ssl,time,threading,unittest
from pathlib import Path
from nexvary_usim_lab.secure_bridge import PrivateUsimBridge,BridgeUsimClient
from nexvary_usim_lab.usim_backend import Authorization
from nexvary_usim_lab.core import LabError

CERTS=Path(__file__).with_name('tls-fixtures');TOKEN='A'*40

def pin(name):
    der=ssl.PEM_cert_to_DER_cert((CERTS/(name+'.pem')).read_text())
    return hashlib.sha256(der).hexdigest()
class SyntheticBackend:
    def __init__(self):self._authorization=Authorization('synthetic-modem',TOKEN,time.monotonic()+60);self.revoked=False;self.calls=0
    def _authorize(self):
        if self.revoked or self._authorization.expires<time.monotonic():raise LabError('expired')
    def revoke(self):self.revoked=True
    def authenticate_ami(self,*_):self._authorize();self.calls+=1;return '12'*4,'34'*16,'56'*16,None
class TLSBridgeTests(unittest.TestCase):
    def setUp(self):
        self.backend=SyntheticBackend()
        self.server=PrivateUsimBridge(self.backend,str(CERTS/'server.pem'),str(CERTS/'server-key.pem'),str(CERTS/'ca.pem'),pin('client'))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.stop();self.thread.join(2)
    def client(self,token=TOKEN,peer=None):
        return BridgeUsimClient(self.server.port,'synthetic-modem',token,str(CERTS/'ca.pem'),str(CERTS/'client.pem'),str(CERTS/'client-key.pem'),peer or pin('server'))
    def test_real_mtls_transport_contract(self):
        self.assertEqual(('12'*4,'34'*16,'56'*16),self.client().authenticate('11'*16,'22'*16))
        self.assertEqual(1,self.backend.calls)
    def test_wrong_scoped_token_does_not_reach_modem(self):
        with self.assertRaises(LabError):self.client('B'*40).authenticate('11'*16,'22'*16)
        self.assertEqual(0,self.backend.calls)
    def test_pinned_peer_mismatch(self):
        with self.assertRaises(LabError):self.client(peer='0'*64).authenticate('11'*16,'22'*16)
        self.assertEqual(0,self.backend.calls)
    def test_revocation_and_secret_repr(self):
        client=self.client();self.assertNotIn(TOKEN,repr(client));self.server.stop()
        with self.assertRaises(LabError):client.authenticate('11'*16,'22'*16)
    def test_client_certificate_required(self):
        import socket
        context=ssl.create_default_context(cafile=str(CERTS/'ca.pem'))
        rejected=False
        try:
            with socket.create_connection(('127.0.0.1',self.server.port),timeout=3) as raw:
                with context.wrap_socket(raw,server_hostname='localhost') as tls:
                    tls.sendall(b'POST /v1/usim/aka HTTP/1.1\r\n\r\n')
                    # OpenSSL platforms may reject by TLS alert or silent EOF.
                    rejected=tls.recv(1)==b''
        except (OSError,ssl.SSLError):
            rejected=True
        self.assertTrue(rejected)
        self.assertEqual(0,self.backend.calls)

    def test_replay_request_id_refused_before_backend(self):
        from unittest.mock import patch
        import uuid
        with patch('nexvary_usim_lab.secure_bridge.uuid.uuid4',return_value=uuid.UUID('11111111-1111-4111-8111-111111111111')):
            self.client().authenticate('11'*16,'22'*16)
            with self.assertRaises(LabError):self.client().authenticate('33'*16,'44'*16)
        self.assertEqual(1,self.backend.calls)
