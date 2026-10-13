"""Minimal PE helper: detect whether a file is a managed (.NET) assembly."""
from __future__ import annotations

import struct


def is_managed_assembly(path: str) -> bool:
    """True if `path` is a PE with a CLI (COM descriptor) data directory."""
    try:
        with open(path, "rb") as f:
            data = f.read(0x1000)
    except OSError:
        return False
    if len(data) < 0x40 or data[:2] != b"MZ":
        return False
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_off + 24 > len(data) or data[pe_off:pe_off + 4] != b"PE\x00\x00":
        return False
    opt = pe_off + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic == 0x10B:  # PE32
        dd = opt + 96
    elif magic == 0x20B:  # PE32+
        dd = opt + 112
    else:
        return False
    if dd + 15 * 8 + 4 > len(data):
        return False
    cli_rva = struct.unpack_from("<I", data, dd + 14 * 8)[0]
    return cli_rva != 0
