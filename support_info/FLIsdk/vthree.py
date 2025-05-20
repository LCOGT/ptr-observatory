
import os
import time
import threading
import random
from ctypes import windll, c_int, c_char, c_char_p, POINTER, create_string_buffer, byref

# —————————————————————————————————————————————————————————————————————————————
# 1) Add this folder to the DLL search path
# —————————————————————————————————————————————————————————————————————————————
sdk_dir = os.path.dirname(os.path.abspath(__file__))
os.add_dll_directory(sdk_dir)

# —————————————————————————————————————————————————————————————————————————————
# 2) Load the FLI SDK via stdcall (so decorated exports resolve)
# —————————————————————————————————————————————————————————————————————————————
lib = windll.LoadLibrary("libfli.dll")

# —————————————————————————————————————————————————————————————————————————————
# 3) Prototype only the functions we need
# —————————————————————————————————————————————————————————————————————————————

# Version check
lib.FLIGetLibVersion.argtypes = [c_char_p, c_int]
lib.FLIGetLibVersion.restype  = c_int

# Build / tear down the internal device list
lib.FLICreateList.argtypes = [c_int]
lib.FLICreateList.restype  = c_int
lib.FLIDeleteList.argtypes = []
lib.FLIDeleteList.restype  = c_int

# Enumerate devices: (domainOut*, filenameBuf, fnLen, nameBuf, nameLen)
lib.FLIListFirst.argtypes = [
    POINTER(c_int),       # domainOut*
    POINTER(c_char), c_int,  # filename buffer, its length
    POINTER(c_char), c_int   # friendly-name buffer, its length
]
lib.FLIListFirst.restype = c_int
lib.FLIListNext = lib.FLIListNext
lib.FLIListNext.argtypes = lib.FLIListFirst.argtypes
lib.FLIListNext.restype  = c_int

# Open / Close: (&handle, filename, interfaceDomain)
lib.FLIOpen.argtypes  = [POINTER(c_int), c_char_p, c_int]
lib.FLIOpen.restype   = c_int
lib.FLIClose.argtypes = [c_int]
lib.FLIClose.restype  = c_int

# Read serial & switch wheels
lib.FLIGetSerialString.argtypes = [c_int, POINTER(c_char), c_int]
lib.FLIGetSerialString.restype  = c_int
lib.FLISetActiveWheel.argtypes   = [c_int, c_int]
lib.FLISetActiveWheel.restype    = c_int

# Filter‐wheel info
lib.FLIGetFilterCount .argtypes = [c_int, POINTER(c_int)]
lib.FLIGetFilterCount .restype  = c_int
lib.FLIGetFilterName  .argtypes = [c_int, c_int, POINTER(c_char), c_int]
lib.FLIGetFilterName  .restype  = c_int

# —————————————————————————————————————————————————————————————————————————————
# 4) Sanity check: print SDK version
# —————————————————————————————————————————————————————————————————————————————
ver_buf = create_string_buffer(64)
if lib.FLIGetLibVersion(ver_buf, len(ver_buf)) == 0:
    print("SDK version:", ver_buf.value.decode())
else:
    print("⚠ Could not read SDK version")

# —————————————————————————————————————————————————————————————————————————————
# 5) Enumerate *all* USB filter wheels
# —————————————————————————————————————————————————————————————————————————————
FLIDOMAIN_USB         = 0x02
FLIDEVICE_FILTERWHEEL = 0x200

domain_mask = FLIDOMAIN_USB | FLIDEVICE_FILTERWHEEL
rc = lib.FLICreateList(domain_mask)
if rc != 0:
    raise RuntimeError(f"FLICreateList({hex(domain_mask)}) failed: {rc}")

domain = c_int()
fn_buf = create_string_buffer(128)
nm_buf = create_string_buffer(128)

devices = []
rc = lib.FLIListFirst(
    byref(domain), fn_buf, len(fn_buf), nm_buf, len(nm_buf)
)
while rc == 0:
    filepath = fn_buf.value.decode()  # use this to open
    devices.append((filepath, domain.value))
    rc = lib.FLIListNext(byref(domain), fn_buf, len(fn_buf), nm_buf, len(nm_buf))

lib.FLIDeleteList()

if not devices:
    raise RuntimeError("No FLI filter wheels detected on USB")

print(f"Discovered {len(devices)} wheel(s) by filepaths:",
      ", ".join(f for f, _ in devices))

# —————————————————————————————————————————————————————————————————————————————
# 6) Open each wheel by filepath & domain, read serial, list slots
# —————————————————————————————————————————————————————————————————————————————
handles = []
for filepath, dom in devices:
    h = c_int()
    rc = lib.FLIOpen(byref(h), filepath.encode('ascii'), dom)
    if rc != 0:
        print(f"✖ Could not open wheel at {filepath!r}: rc={rc}")
        continue

    # Read its serial number
    s_buf = create_string_buffer(64)
    if lib.FLIGetSerialString(h.value, s_buf, len(s_buf)) == 0:
        serial = s_buf.value.decode()
    else:
        serial = '<unknown>'

    print(f"✔ Opened wheel serial={serial} (handle={h.value})")
    handles.append((h.value, serial))

# List slots for each wheel by serial
for handle, serial in handles:
    cnt = c_int()
    lib.FLIGetFilterCount(handle, byref(cnt))
    print(f"\nWheel {serial} has {cnt.value} slots:")
    for slot in range(cnt.value):
        nb = create_string_buffer(32)
        lib.FLIGetFilterName(handle, slot, nb, len(nb))
        print(f"  [{slot:2d}] {nb.value.decode()}")

# —————————————————————————————————————————————————————————————————————————————
# 7) Rotate each wheel to a random slot concurrently, reporting by serial
# —————————————————————————————————————————————————————————————————————————————
def rotate_wheel(handle, serial):
    cnt = c_int()
    lib.FLIGetFilterCount(handle, byref(cnt))
    if cnt.value < 2:
        print(f"Wheel {serial}: not enough slots to rotate.")
        return

    target = random.randrange(cnt.value)
    print(f"→ Wheel {serial}: rotating to slot {target}...")
    lib.FLISetFilterPos(handle, target)
    pos = c_int()
    while True:
        lib.FLIGetFilterPos(handle, byref(pos))
        if pos.value == target:
            print(f"✓ Wheel {serial}: now at slot {pos.value}")
            break
        time.sleep(0.1)

threads = []
for handle, serial in handles:
    t = threading.Thread(target=rotate_wheel, args=(handle, serial))
    t.start()
    threads.append(t)
for t in threads:
    t.join()

# —————————————————————————————————————————————————————————————————————————————
# 8) Clean up: close all wheels by serial
# —————————————————————————————————————————————————————————————————————————————
for handle, serial in handles:
    lib.FLIClose(handle)
    print(f"Closed wheel {serial}")

print("\nDone.")

