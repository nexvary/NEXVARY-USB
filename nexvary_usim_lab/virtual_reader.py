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

TRANSPORT_ATR = bytes.fromhex('3B00')

class VpcdAdapter:
    def __init__(self, engine, emulated_atr=False, session_reset=False):
        if not emulated_atr or not session_reset:
            raise LabError('Explicit acceptance of transport ATR and session-only reset required.')
        self.engine = engine
        self.pending = b''
        self.powered = True
    def handle(self, payload):
        if len(payload) == 1:
            op = payload[0]
            if op == 0:
                self.powered = False; self.pending = b''; self.engine.ready = False
                return None
            if op in (1,2):
                self.pending = b''
                self.engine.initialize()  # SELECT session only, never ATZ/CFUN.
                self.powered = True
                return None
            if op == 4:
                if not self.engine.ready or not self.powered: raise LabError('Card not present or powered.')
                state, lines = self.engine.session._command('AT+CPIN?', 4)
                if state != 'OK' or lines != ['+CPIN: READY']:
                    self.engine.ready = False
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
        if type(vpcd_port) is not int or not 0 <= vpcd_port <= 65535 or not 1 <= lifetime <= 300:
            raise LabError('Invalid local reader session limits.')
        self.port, self.vpcd_port, self.factory, self.lifetime = port, vpcd_port, factory, lifetime
        self.stop_event = threading.Event()
        self.listener = self.peer = self.thread = None
        self.state = 'STOPPED'
        self.audit = deque(maxlen=128)
        self._lock = threading.Lock()
    def start(self):
        with self._lock:
            if self.thread and self.thread.is_alive(): raise LabError('Reader session already running.')
            self.stop_event.clear()
            wire = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                wire.bind(('127.0.0.1',self.vpcd_port)); wire.listen(1); wire.settimeout(.25)
            except OSError:
                wire.close(); raise LabError('Local vpcd port unavailable; no other service stopped.') from None
            self.listener = wire; self.vpcd_port = wire.getsockname()[1]
            self.state = 'WAITING_PCSC'
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
    def stop(self):
        self.stop_event.set()
        for wire in (self.peer,self.listener):
            if wire:
                try: wire.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                wire.close()
        if self.thread and self.thread is not threading.current_thread(): self.thread.join(8)
        if self.thread and self.thread.is_alive():
            self.state = 'STOPPING'
        else: self.state = 'STOPPED'
    def _read(self, wire, count, deadline):
        data = bytearray()
        # Idle header waits are allowed until consent expires. Once any byte
        # arrives, a single frame has at most five seconds to complete.
        frame_deadline = deadline
        while len(data) < count and not self.stop_event.is_set():
            if time.monotonic() >= frame_deadline: raise LabError('vpcd frame/session deadline.')
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
                self.state = 'CONNECTED_READ_ONLY'
                while not self.stop_event.is_set():
                    header = self._read(peer,2,deadline)
                    length = struct.unpack('!H',header)[0]
                    if not 1 <= length <= 261: raise LabError('vpcd frame length rejected.')
                    payload = self._read(peer,length,min(deadline,time.monotonic()+5))
                    response = adapter.handle(payload)
                    self.audit.append({'operation':'control' if length==1 else 'read_only_apdu','outcome':'completed'})
                    if response is not None:
                        peer.sendall(struct.pack('!H',len(response))+response)
        except Exception as exc:
            # Removing the virtual card is more accurate than inventing SW=9000
            # or a card error for a transport failure. No sensitive exceptions.
            self.state = 'TIMEOUT' if getattr(exc,'status',None) in ('TIMEOUT','SESSION_UNCERTAIN') else 'UNAVAILABLE'
            self.audit.append({'operation':'session','outcome':self.state})
        finally:
            for wire in (self.peer,self.listener):
                if wire:
                    try: wire.close()
                    except OSError: pass
            if self.stop_event.is_set(): self.state = 'STOPPED'
            elif self.state not in ('UNAVAILABLE','TIMEOUT'): self.state = 'EXPIRED'
