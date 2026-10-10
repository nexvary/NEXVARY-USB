"""Real vpcd wire adapter, reversed mode on loopback only, read-only scope.

Connect a separately installed vsmartcard IFD driver to 127.0.0.1:<port>.
The transport ATR (3B00) and session reselect are opt-in emulation, never
represented as the physical UICC ATR or electrical reset. No AUTH over TCP.
"""
import socket
import struct
import threading
import time
from collections import deque
from .core import LabError
from .device_operations import ATSession
from .virtual_sim import VirtualCardEngine

class ReaderExpired(LabError):
    pass

TRANSPORT_ATR = bytes.fromhex('3B00')

class VpcdAdapter:
    def __init__(self, engine, emulated_atr=False, session_reset=False):
        if not emulated_atr or not session_reset:
            raise LabError('Explicit acceptance of transport ATR and session-only reset required.')
        self.engine = engine
        self.pending = b''
        self.powered = True
        self.card_verified = engine.ready
    def handle(self, payload):
        if len(payload) == 1:
            op = payload[0]
            if op == 0:
                self.powered = False; self.pending = b''; self.engine.ready = False
                return None
            if op in (1,2):
                self.pending = b''
                self.engine.initialize()  # SELECT session only, never ATZ/CFUN.
                self.powered = True; self.card_verified = self.engine.ready
                return None
            if op == 4:
                if not self.card_verified: raise LabError('Card presence never established.')
                state, lines = self.engine.session._command('AT+CPIN?', 4)
                if state != 'OK' or lines != ['+CPIN: READY']:
                    self.engine.ready = False; self.card_verified = False
                    raise LabError('Current SIM presence not confirmed; remove virtual card.')
                return TRANSPORT_ATR
            raise LabError('Unsupported vpcd control.')
        if not self.powered: raise LabError('Virtual session powered off.')
        if payload[:4] == b'\x00\xc0\x00\x00' and len(payload) == 5:
            if not self.pending: raise LabError('GET RESPONSE without pending card data.')
            count = payload[4] or 256
            if count > len(self.pending): raise LabError('GET RESPONSE exceeds pending data.')
            data, self.pending = self.pending[:count], self.pending[count:]
            return data + (bytes([0x61,len(self.pending)]) if self.pending else b'\x90\x00')
        self.pending = b''
        reply = self.engine.transmit(payload)
        # PC/SC T=0 SELECT consumers can GET RESPONSE. This caches *actual*
        # modem/card data; no manufactured success or alternate AID redirect.
        if payload[1] == 0xa4 and reply.sw == b'\x90\x00' and reply.data:
            if len(reply.data) > 256: raise LabError('FCP exceeds short T=0 reader capability.')
            self.pending = reply.data
            return bytes([0x61,len(reply.data) % 256])
        return reply.wire

class VirtualReaderService:
    def __init__(self, port, vpcd_port=35963, consent=False, emulated_atr=False,
                 session_reset=False, factory=None, lifetime=300):
        if not consent or not emulated_atr or not session_reset:
            raise LabError('Reader requires local consent and explicit limited emulation acceptance.')
        if type(vpcd_port) is not int or not 0 <= vpcd_port <= 65534 or not 1 <= lifetime <= 300:
            raise LabError('Invalid local reader session limits.')
        self.port, self.vpcd_port, self.factory, self.lifetime = port, vpcd_port, factory, lifetime
        self.stop_event = threading.Event()
        self.listener = self.peer = self.thread = None
        self.absent_listener = self.absent_peer = self.absent_thread = None
        self.state = 'STOPPED'
        self._initial_consent = True
        self.audit = deque(maxlen=128)
        self._lock = threading.Lock()
    def start(self, consent=False):
        with self._lock:
            if not self._initial_consent and consent is not True:
                raise LabError('Restart requires fresh explicit local consent.')
            if self.thread and self.thread.is_alive(): raise LabError('Reader session already running.')
            if self.absent_thread and self.absent_thread.is_alive():
                self.absent_thread.join(1)
                if self.absent_thread.is_alive(): raise LabError('Previous companion slot is still stopping.')
            self.peer = self.absent_peer = None
            self._initial_consent = False
            self.stop_event.clear()
            # The stock vpcd IFD advertises two slots and uses base_port+1.
            # A failed reverse connection in slot 1 can crash that driver. Keep
            # a real second endpoint that reports NO ATR / NO CARD, not a fake
            # second SIM. Both listeners are loopback only.
            requested = self.vpcd_port
            for attempt in range(8 if requested == 0 else 1):
                wire = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                absent = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    wire.bind(('127.0.0.1',requested))
                    base = wire.getsockname()[1]
                    if base >= 65535: raise OSError('No adjacent slot port.')
                    absent.bind(('127.0.0.1',base+1))
                    wire.listen(1); wire.settimeout(.25)
                    absent.listen(1); absent.settimeout(.25)
                    break
                except OSError:
                    wire.close(); absent.close()
            else: raise LabError('Local vpcd port pair unavailable; no other service stopped.')
            self.listener = wire; self.absent_listener = absent; self.vpcd_port = base
            self.state = 'WAITING_PCSC'
            self.absent_thread = threading.Thread(target=self._absent_slot, daemon=True)
            self.absent_thread.start()
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
    def _absent_slot(self):
        deadline = time.monotonic()+self.lifetime
        listener=self.absent_listener
        try:
            # vpcd ejects a connection on a zero-length ATR, so absence polls
            # reconnect. Accept each poll while consent remains active.
            while not self.stop_event.is_set() and time.monotonic()<deadline:
                try: peer,_ = listener.accept()
                except socket.timeout: continue
                self.absent_peer=peer; peer.settimeout(.25)
                try:
                    while not self.stop_event.is_set():
                        length=struct.unpack('!H',self._read(peer,2,deadline))[0]
                        if length != 1: raise LabError('No card in companion slot.')
                        payload=self._read(peer,1,min(deadline,time.monotonic()+5))
                        if payload==b'\x04':
                            peer.sendall(b'\x00\x00') # actual absence, no synthetic card
                            break
                        elif payload not in (b'\x00',b'\x01',b'\x02'):raise LabError('Unsupported control.')
                except Exception:pass
                finally:
                    peer.close()
                    if self.absent_peer is peer:self.absent_peer=None
        except Exception:pass
        finally:listener.close()
    def stop(self):
        self.stop_event.set()
        for wire in (self.peer,self.listener,self.absent_peer,self.absent_listener):
            if wire:
                try: wire.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                wire.close()
        if self.thread and self.thread is not threading.current_thread(): self.thread.join(8)
        if self.absent_thread and self.absent_thread is not threading.current_thread(): self.absent_thread.join(1)
        if self.thread and self.thread.is_alive():
            self.state = 'STOPPING'
        else: self.state = 'STOPPED'
    def _read(self, wire, count, deadline):
        data = bytearray()
        # Idle header waits are allowed until consent expires. Once any byte
        # arrives, a single frame has at most five seconds to complete.
        frame_deadline = deadline
        while len(data) < count and not self.stop_event.is_set():
            if time.monotonic() >= frame_deadline: raise ReaderExpired('vpcd frame/session deadline.')
            try: chunk = wire.recv(count-len(data))
            except socket.timeout: continue
            if not chunk: raise LabError('vpcd disconnected.')
            if not data: frame_deadline = min(deadline,time.monotonic()+5)
            data.extend(chunk)
        if len(data) != count: raise LabError('Reader stopped.')
        return bytes(data)
    def _run(self):
        deadline = time.monotonic()+self.lifetime
        try:
            # No automatic modem reconnection: reconnect is a new local consent.
            while not self.stop_event.is_set() and time.monotonic() < deadline:
                try: peer,_ = self.listener.accept(); break
                except socket.timeout: continue
            else: return
            self.peer = peer; peer.settimeout(.25)
            with ATSession(self.port,factory=self.factory) as session:
                engine = VirtualCardEngine(session); engine.initialize()
                adapter = VpcdAdapter(engine,True,True)
                if time.monotonic() >= deadline: raise ReaderExpired('Consent expired during verification.')
                if self.stop_event.is_set(): raise LabError('Reader stopped.')
                self.state = 'CONNECTED_READ_ONLY'
                while not self.stop_event.is_set():
                    header = self._read(peer,2,deadline)
                    length = struct.unpack('!H',header)[0]
                    if not 1 <= length <= 261: raise LabError('vpcd frame length rejected.')
                    payload = self._read(peer,length,min(deadline,time.monotonic()+5))
                    if time.monotonic() >= deadline: raise ReaderExpired('Consent expired before operation.')
                    response = adapter.handle(payload)
                    # Modem I/O can finish after consent expires or Stop. Never
                    # publish an ATR or APDU response from that stale operation.
                    if time.monotonic() >= deadline: raise ReaderExpired('Consent expired during operation.')
                    if self.stop_event.is_set(): raise LabError('Reader stopped.')
                    self.audit.append({'operation':'control' if length==1 else 'read_only_apdu','outcome':'completed'})
                    if response is not None:
                        peer.sendall(struct.pack('!H',len(response))+response)
        except Exception as exc:
            # Removing the virtual card is more accurate than inventing SW=9000
            # or a card error for a transport failure. No sensitive exceptions.
            self.state = 'EXPIRED' if isinstance(exc,ReaderExpired) else 'TIMEOUT' if getattr(exc,'status',None) in ('TIMEOUT','SESSION_UNCERTAIN') else 'UNAVAILABLE'
            self.audit.append({'operation':'session','outcome':self.state})
        finally:
            for wire in (self.peer,self.listener,self.absent_peer,self.absent_listener):
                if wire:
                    try: wire.close()
                    except OSError: pass
            if self.stop_event.is_set(): self.state = 'STOPPED'
            elif self.state not in ('UNAVAILABLE','TIMEOUT'): self.state = 'EXPIRED'
