"""Core unit tests: fingerprint, manifest, catalog integrity, detection, memory, safety.

Run with:  python tests/test_core.py
"""
from __future__ import annotations

import hashlib
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import memory, safety
from agmod.engines import ENGINE_CATALOG
from agmod.manifest import ModManifest
from agmod.registry import adapters, detect_engine
from agmod.structures import fingerprint_files


class TestFingerprint(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(fingerprint_files([]), hashlib.sha256().hexdigest())

    def test_order_independent_and_content_sensitive(self):
        with tempfile.TemporaryDirectory() as d:
            p1 = os.path.join(d, "a.dll")
            p2 = os.path.join(d, "b.dll")
            with open(p1, "wb") as f:
                f.write(b"A" * 1000)
            with open(p2, "wb") as f:
                f.write(b"B" * 1000)
            fwd = fingerprint_files([p1, p2])
            rev = fingerprint_files([p2, p1])
            self.assertEqual(fwd, rev)
            self.assertNotEqual(fwd, fingerprint_files([p1]))
            with open(p1, "wb") as f:
                f.write(b"A" * 1001)
            self.assertNotEqual(fwd, fingerprint_files([p1, p2]))


class TestManifest(unittest.TestCase):
    def test_roundtrip(self):
        m = ModManifest(id="com.x.y", name="Y", version="1.2.3", engine="unity",
                        repo="o/r", entry="com.x.y.dll", description="hi")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "mod.json")
            m.save(p)
            self.assertEqual(m.to_dict(), ModManifest.load(p).to_dict())


class TestCatalog(unittest.TestCase):
    def test_unique_ids_and_required_fields(self):
        ids = [e["id"] for e in ENGINE_CATALOG]
        self.assertEqual(len(ids), len(set(ids)), "duplicate engine ids")
        for e in ENGINE_CATALOG:
            for k in ("id", "name", "family", "markers", "mod_framework", "structure"):
                self.assertIn(k, e, f"{e.get('id')} missing {k}")
            self.assertTrue(e["markers"], f"{e['id']} has empty markers")


class TestDetection(unittest.TestCase):
    def test_empty_dir_not_detected(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(detect_engine(d))
            for a in adapters():
                self.assertFalse(a.detect(d), f"{a.id} falsely detected an empty dir")

    def test_registry_ids_unique(self):
        ids = [a.id for a in adapters()]
        self.assertEqual(len(ids), len(set(ids)), "duplicate adapter ids")


class TestMemoryKinds(unittest.TestCase):
    def test_format_widths_match(self):
        for kind, (fmt, width) in memory._SIZES.items():
            self.assertGreater(width, 0)
            self.assertEqual(struct.calcsize(fmt), width, kind)


class TestSafety(unittest.TestCase):
    def test_blocked_names(self):
        self.assertTrue(safety.is_blocked_name("BEService.exe"))
        self.assertTrue(safety.is_blocked_name("easyanticheat.exe"))
        self.assertFalse(safety.is_blocked_name("Terraria.exe"))
        self.assertFalse(safety.is_blocked_name(""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
