"""Self-test for the memory module: read/write/scan a variable in our own process."""
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agmod import memory

x = ctypes.c_int(0x12345678)          # a known value in THIS process
addr = ctypes.addressof(x)
pid = os.getpid()

h = memory.open_process(pid)
assert memory.read_value(h, addr, "int32") == 0x12345678, "read failed"
memory.write_value(h, addr, 0x11111111, "int32")
assert x.value == 0x11111111, "write did not take effect in-process"
memory.write_value(h, addr, 0x12345678, "int32")  # restore

hits = memory.scan_value(h, 0x12345678, "int32", limit=50)
assert addr in hits, "scan did not find our own address"
memory.close_process(h)

print("memory self-test OK: read + write + scan all verified in-process")
print(f"  address=0x{addr:x}  scan_hits={len(hits)}")
