"""
Shared trigger event — wired by main.py, fired by:
  • ESP8266 serial reader (real button press)
  • Web UI  POST /trigger  (virtual trigger for testing)
"""
import threading

_event = threading.Event()
_lock  = threading.Lock()
_armed = True   # False while a shot is in progress


def arm() -> None:
    with _lock:
        global _armed
        _armed = True


def disarm() -> None:
    with _lock:
        global _armed
        _armed = False
    _event.clear()


def fire() -> bool:
    """Signal a trigger. Returns False if disarmed (shot in progress)."""
    with _lock:
        if not _armed:
            return False
    _event.set()
    return True


def wait() -> None:
    """Block until triggered."""
    _event.wait()
    _event.clear()
