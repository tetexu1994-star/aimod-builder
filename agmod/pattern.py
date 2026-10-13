"""AOB (Array of Bytes) pattern scanning and signature matching.

Essential for game modding:
Instead of hardcoding memory addresses or offsets that break on game updates,
AOB pattern scanning searches memory/binaries for distinctive byte sequences
with wildcards (?? or ?), providing patch-resistant hook targets.
"""
from __future__ import annotations

import re
import sys
from typing import Sequence

IS_WINDOWS = sys.platform == "win32"


class Pattern:
    """Represents a compiled byte pattern with wildcards."""

    def __init__(self, pattern_str: str):
        self.raw_str = pattern_str.strip()
        self.bytes_list: list[int | None] = []
        self._parse(self.raw_str)

    def _parse(self, text: str) -> None:
        tokens = text.split()
        for token in tokens:
            t = token.strip()
            if not t:
                continue
            if t in ("?", "??"):
                self.bytes_list.append(None)
            else:
                self.bytes_list.append(int(t, 16))

    def __len__(self) -> int:
        return len(self.bytes_list)

    def matches(self, buffer: Sequence[int], offset: int = 0) -> bool:
        """Check if buffer matches this pattern at offset."""
        pat_len = len(self.bytes_list)
        if offset + pat_len > len(buffer):
            return False
        for i, expected in enumerate(self.bytes_list):
            if expected is not None and buffer[offset + i] != expected:
                return False
        return True

    def find_first(self, buffer: bytes, start: int = 0) -> int:
        """Find the first occurrence of the pattern in buffer. Returns offset or -1."""
        if not self.bytes_list:
            return -1
        pat_len = len(self.bytes_list)
        buf_len = len(buffer)
        if buf_len < pat_len:
            return -1

        # Optimization: find the first non-wildcard byte
        first_idx = 0
        while first_idx < pat_len and self.bytes_list[first_idx] is None:
            first_idx += 1

        if first_idx >= pat_len:
            # All wildcards
            return start if start <= buf_len - pat_len else -1

        first_byte = self.bytes_list[first_idx]
        pos = start
        while pos <= buf_len - pat_len:
            try:
                candidate = buffer.index(first_byte, pos + first_idx) - first_idx
            except ValueError:
                return -1

            if candidate < pos or candidate > buf_len - pat_len:
                return -1

            if self.matches(buffer, candidate):
                return candidate
            pos = candidate + 1
        return -1

    def find_all(self, buffer: bytes, limit: int = 100) -> list[int]:
        """Find all occurrences of the pattern in buffer up to `limit`."""
        hits: list[int] = []
        pos = 0
        buf_len = len(buffer)
        while pos <= buf_len - len(self.bytes_list) and len(hits) < limit:
            hit = self.find_first(buffer, start=pos)
            if hit == -1:
                break
            hits.append(hit)
            pos = hit + 1
        return hits


def create_pattern(data: bytes, mask: str | None = None) -> str:
    """Generate a pattern string from bytes and mask (x = exact, ? = wildcard)."""
    parts: list[str] = []
    for i, b in enumerate(data):
        if mask and i < len(mask) and mask[i] == "?":
            parts.append("??")
        else:
            parts.append(f"{b:02X}")
    return " ".join(parts)


def scan_process_pattern(pid: int, pattern_str: str, limit: int = 50) -> list[int]:
    """Scan memory of target process for an AOB pattern.

    On Windows, uses OpenProcess + VirtualQueryEx + ReadProcessMemory.
    On non-Windows, raises OSError.
    """
    if not IS_WINDOWS:
        raise OSError("Process pattern scanning is Windows-only")

    from . import memory

    pat = Pattern(pattern_str)
    if not pat.bytes_list:
        return []

    h = memory.open_process(pid)
    hits: list[int] = []
    try:
        cur_addr = 0
        while cur_addr < memory.MAX_ADDRESS and len(hits) < limit:
            mbi = memory._query(h, cur_addr)
            if mbi is None:
                break
            base = mbi.BaseAddress or 0
            size = mbi.RegionSize or 0
            state = mbi.State
            protect = mbi.Protect

            # We scan committed executable or readable memory
            is_comm = (state == memory.MEM_COMMIT)
            is_readable = bool(protect and not (protect & memory.PAGE_NOACCESS) and not (protect & memory.PAGE_GUARD))

            if is_comm and is_readable and size > len(pat):
                chunk = memory.read_bytes(h, base, min(size, 8 * 1024 * 1024))
                if chunk:
                    sub_hits = pat.find_all(chunk, limit=limit - len(hits))
                    for offset in sub_hits:
                        hits.append(base + offset)

            next_addr = base + size
            if next_addr <= cur_addr:
                break
            cur_addr = next_addr
    finally:
        memory.close_process(h)
    return hits
