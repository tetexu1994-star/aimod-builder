"""Windows process memory read/write and value scanning, using only ctypes.

Single-player, offline use on processes you own. Never attach these to a game
protected by anti-cheat.

The memory operations are Windows-only; on other platforms the module imports
cleanly and raises a clear error at call time (so the rest of the project stays
cross-platform for review/development).
"""
from __future__ import annotations

import ctypes
import struct
import sys

IS_WINDOWS = sys.platform == "win32"

# value kind -> (struct little-endian format, byte width) — cross-platform
_SIZES = {
    "int8": ("<b", 1),
    "uint8": ("<B", 1),
    "int16": ("<h", 2),
    "uint16": ("<H", 2),
    "int32": ("<i", 4),
    "uint32": ("<I", 4),
    "int64": ("<q", 8),
    "uint64": ("<Q", 8),
    "float32": ("<f", 4),
    "float64": ("<d", 8),
}

MAX_ADDRESS = 0x7FFF_FFFF_FFFF  # user-mode address space ceiling

if IS_WINDOWS:
    import ctypes.wintypes as wt

    PROCESS_VM_READ = 0x0010
    PROCESS_VM_WRITE = 0x0020
    PROCESS_VM_OPERATION = 0x0008
    PROCESS_QUERY_INFORMATION = 0x0400
    MEM_COMMIT = 0x1000
    PAGE_NOACCESS = 0x01
    PAGE_GUARD = 0x100

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class MEMORY_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BaseAddress", ctypes.c_void_p),
            ("AllocationBase", ctypes.c_void_p),
            ("AllocationProtect", wt.DWORD),
            ("RegionSize", ctypes.c_size_t),
            ("State", wt.DWORD),
            ("Protect", wt.DWORD),
            ("Type", wt.DWORD),
        ]

    _k32.OpenProcess.restype = wt.HANDLE
    _k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _k32.ReadProcessMemory.restype = wt.BOOL
    _k32.ReadProcessMemory.argtypes = [
        wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
    ]
    _k32.WriteProcessMemory.restype = wt.BOOL
    _k32.WriteProcessMemory.argtypes = [
        wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
    ]
    _k32.VirtualQueryEx.restype = ctypes.c_size_t
    _k32.VirtualQueryEx.argtypes = [
        wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t,
    ]
    _k32.CloseHandle.restype = wt.BOOL
    _k32.CloseHandle.argtypes = [wt.HANDLE]


def _require_windows() -> None:
    if not IS_WINDOWS:
        raise OSError("memory tools are Windows-only")


def open_process(pid: int) -> int:
    _require_windows()
    handle = _k32.OpenProcess(
        PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION,
        False,
        pid,
    )
    if not handle:
        raise OSError(f"OpenProcess({pid}) failed (error {ctypes.get_last_error()}). Run as admin?")
    return handle


def close_process(handle: int) -> None:
    if handle and IS_WINDOWS:
        _k32.CloseHandle(handle)


def read_bytes(handle: int, address: int, size: int) -> bytes:
    _require_windows()
    buf = (ctypes.c_char * size)()
    nread = ctypes.c_size_t(0)
    ok = _k32.ReadProcessMemory(handle, ctypes.c_void_p(address), buf, size, ctypes.byref(nread))
    if not ok:
        raise OSError(f"ReadProcessMemory(0x{address:x}) failed (error {ctypes.get_last_error()})")
    return buf.raw[: nread.value]


def write_bytes(handle: int, address: int, data: bytes) -> int:
    _require_windows()
    buf = (ctypes.c_char * len(data)).from_buffer_copy(data)
    nwritten = ctypes.c_size_t(0)
    ok = _k32.WriteProcessMemory(handle, ctypes.c_void_p(address), buf, len(data), ctypes.byref(nwritten))
    if not ok:
        raise OSError(f"WriteProcessMemory(0x{address:x}) failed (error {ctypes.get_last_error()})")
    return nwritten.value


def read_value(handle: int, address: int, kind: str = "int32"):
    fmt, size = _SIZES[kind]
    return struct.unpack(fmt, read_bytes(handle, address, size))[0]


def write_value(handle: int, address: int, value, kind: str = "int32") -> int:
    fmt, _ = _SIZES[kind]
    return write_bytes(handle, address, struct.pack(fmt, value))


def _iter_regions(handle: int, start: int = 0, end: int = MAX_ADDRESS):
    _require_windows()
    addr = start
    mbi = MEMORY_BASIC_INFORMATION()
    while addr < end:
        n = _k32.VirtualQueryEx(handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if not n:
            break
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize or 0
        if size == 0:
            break
        yield base, size, mbi
        addr = base + size


def scan_bytes(handle: int, needle: bytes, start: int = 0, end: int = MAX_ADDRESS, limit: int = 1000) -> list[int]:
    """Return addresses where `needle` appears in readable committed memory."""
    hits: list[int] = []
    for base, size, mbi in _iter_regions(handle, start, end):
        if mbi.State != MEM_COMMIT:
            continue
        if mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD):
            continue
        try:
            data = read_bytes(handle, base, size)
        except OSError:
            continue
        idx = data.find(needle)
        while idx != -1 and len(hits) < limit:
            hits.append(base + idx)
            idx = data.find(needle, idx + 1)
        if len(hits) >= limit:
            break
    return hits


def scan_value(handle: int, value, kind: str = "int32", start: int = 0, end: int = MAX_ADDRESS, limit: int = 1000) -> list[int]:
    """Scan for a scalar value of the given kind and return candidate addresses."""
    fmt, _ = _SIZES[kind]
    return scan_bytes(handle, struct.pack(fmt, value), start, end, limit)
