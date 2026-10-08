"""Process-wide serial ownership shared by diagnostics, SMS and AKA."""
from contextlib import contextmanager
from threading import Lock
from .core import LabError
_guard = Lock()
_locks = {}
@contextmanager
def lease(port):
    key = port.upper() if port.upper().startswith('COM') else port
    with _guard:
        lock = _locks.setdefault(key, Lock())
    if not lock.acquire(blocking=False):
        raise LabError('المنفذ مشغول بعملية أخرى داخل البرنامج؛ انتظر اكتمالها.')
    try:
        yield
    finally:
        lock.release()
