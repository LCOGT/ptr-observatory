# fli_wheels.py — Importable FLI Filter-Wheel Module
import os
import time
import threading
from ctypes import windll, c_int, c_char, c_char_p, c_char, POINTER, create_string_buffer, byref

# — Load and prototype FLI SDK —
_sdk_dir = os.path.dirname(os.path.abspath(__file__))
os.add_dll_directory(_sdk_dir)
_lib = windll.LoadLibrary("libfli.dll")

# Version check (optional)
_lib.FLIGetLibVersion.argtypes = [c_char_p, c_int]
_lib.FLIGetLibVersion.restype  = c_int

# Device list
_lib.FLICreateList.argtypes = [c_int]
_lib.FLICreateList.restype  = c_int
_lib.FLIDeleteList.argtypes = []
_lib.FLIDeleteList.restype  = c_int
_lib.FLIListFirst.argtypes  = [POINTER(c_int), POINTER(c_char), c_int, POINTER(c_char), c_int]
_lib.FLIListFirst.restype   = c_int
_lib.FLIListNext = _lib.FLIListNext
_lib.FLIListNext.argtypes   = _lib.FLIListFirst.argtypes
_lib.FLIListNext.restype    = c_int

# Open/Close
_lib.FLIOpen.argtypes       = [POINTER(c_int), c_char_p, c_int]
_lib.FLIOpen.restype        = c_int
_lib.FLIClose.argtypes      = [c_int]
_lib.FLIClose.restype       = c_int

# Active-wheel & serial
_lib.FLISetActiveWheel.argtypes  = [c_int, c_int]
_lib.FLISetActiveWheel.restype   = c_int
_lib.FLIGetSerialString.argtypes = [c_int, POINTER(c_char), c_int]
_lib.FLIGetSerialString.restype  = c_int

# Filter info & movement
_lib.FLIGetFilterCount.argtypes  = [c_int, POINTER(c_int)]
_lib.FLIGetFilterCount.restype   = c_int
_lib.FLIGetFilterPos.argtypes    = [c_int, POINTER(c_int)]
_lib.FLIGetFilterPos.restype     = c_int
_lib.FLISetFilterPos.argtypes    = [c_int, c_int]
_lib.FLISetFilterPos.restype     = c_int
_lib.FLIGetFilterName.argtypes   = [c_int, c_int, POINTER(c_char), c_int]
_lib.FLIGetFilterName.restype    = c_int

# Domain masks
FLIDOMAIN_USB         = 0x02
FLIDEVICE_FILTERWHEEL = 0x200

# Internal storage of wheel info: serial -> {'handle': int, 'position': int}
_wheels = {}

# — Enumerate USB filter wheels —
def _enumerate_wheels():
    mask = FLIDOMAIN_USB | FLIDEVICE_FILTERWHEEL
    rc = _lib.FLICreateList(mask)
    if rc != 0:
        raise RuntimeError(f"FLICreateList({hex(mask)}) failed: {rc}")
    domain = c_int()
    fn_buf = create_string_buffer(128)
    nm_buf = create_string_buffer(128)
    devices = []
    rc = _lib.FLIListFirst(byref(domain), fn_buf, len(fn_buf), nm_buf, len(nm_buf))
    while rc == 0:
        devices.append((fn_buf.value.decode(), domain.value))
        rc = _lib.FLIListNext(byref(domain), fn_buf, len(fn_buf), nm_buf, len(nm_buf))
    _lib.FLIDeleteList()
    return devices

# — Initialize wheels: open and record serials & positions —
def initialize_wheels():
    """
    Detect, open all USB filter wheels, and return a mapping:
      { serial: initial_position }
    """
    global _wheels
    _wheels.clear()
    for filepath, domain in _enumerate_wheels():
        handle = c_int()
        rc = _lib.FLIOpen(byref(handle), filepath.encode('ascii'), domain)
        if rc != 0:
            continue
        # read serial
        buf = create_string_buffer(64)
        _lib.FLIGetSerialString(handle.value, buf, len(buf))
        serial = buf.value.decode()
        # read current position
        pos = c_int()
        _lib.FLIGetFilterPos(handle.value, byref(pos))
        _wheels[serial] = {'handle': handle.value, 'position': pos.value}
    if not _wheels:
        raise RuntimeError("No filter wheels initialized.")
    # return mapping serial->position
    return {s: info['position'] for s, info in _wheels.items()}

# — Set positions concurrently by serial & block until done —
def set_positions(position_map):
    """
    position_map: dict of serial -> target_slot
    Moves wheels concurrently and blocks until completion.
    Returns dict of serial -> final_position.
    """
    results = {}
    lock = threading.Lock()

    def _move(serial, handle, target):
        _lib.FLISetFilterPos(handle, target)
        pos = c_int()
        while True:
            _lib.FLIGetFilterPos(handle, byref(pos))
            if pos.value == target:
                with lock:
                    results[serial] = pos.value
                break
            time.sleep(0.05)
        # update stored position
        _wheels[serial]['position'] = pos.value

    threads = []
    for serial, target in position_map.items():
        if serial not in _wheels:
            raise KeyError(f"Unknown wheel serial: {serial}")
        handle = _wheels[serial]['handle']
        t = threading.Thread(target=_move, args=(serial, handle, target))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    return results

# — Optional cleanup: close all wheels —
def close_wheels():
    """Closes all open wheel handles."""
    for info in _wheels.values():
        _lib.FLIClose(info['handle'])
    _wheels.clear()

