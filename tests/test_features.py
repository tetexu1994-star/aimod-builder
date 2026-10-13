"""Tests for new features: AOB Pattern Scanner, ScanSession, Unreal Adapter, and Inspector."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod.adapters.unreal import UnrealAdapter
from agmod.inspector import inspect_feature
from agmod.memory import ScanSession
from agmod.pattern import Pattern, create_pattern
from agmod.registry import adapters, detect_engine


class TestPatternScanner(unittest.TestCase):
    def test_exact_pattern(self):
        pat = Pattern("48 89 5C 24 08")
        buf = b"\x90\x90\x48\x89\x5C\x24\x08\xC3"
        self.assertEqual(pat.find_first(buf), 2)

    def test_wildcard_pattern(self):
        pat = Pattern("48 89 ?? 24 ?? 57")
        buf = b"\x00\x11\x48\x89\x5C\x24\x10\x57\x48\x83"
        self.assertEqual(pat.find_first(buf), 2)
        self.assertEqual(pat.find_all(buf), [2])

    def test_multiple_occurrences(self):
        pat = Pattern("AA ?? BB")
        buf = b"\xAA\x01\xBB\xCC\xAA\x02\xBB"
        self.assertEqual(pat.find_all(buf), [0, 4])

    def test_create_pattern_helper(self):
        data = b"\x48\x8B\x05\x12\x34\x56\x78"
        pat_str = create_pattern(data, mask="xxx????")
        self.assertEqual(pat_str, "48 8B 05 ?? ?? ?? ??")


class TestUnrealAdapter(unittest.TestCase):
    def test_unreal_detection_and_scaffolding(self):
        adapter = UnrealAdapter()
        with tempfile.TemporaryDirectory() as game_dir:
            self.assertFalse(adapter.detect(game_dir))

            # Add uproject marker
            uproject_file = os.path.join(game_dir, "MyGame.uproject")
            with open(uproject_file, "w") as f:
                f.write("{}")

            self.assertTrue(adapter.detect(game_dir))
            det = detect_engine(game_dir)
            self.assertIsNotNone(det)
            self.assertEqual(det["id"], "unreal")

            # Test scaffolding
            with tempfile.TemporaryDirectory() as mod_proj:
                adapter.scaffold_mod(mod_proj, "test_mod", "Test Mod")
                self.assertTrue(os.path.isfile(os.path.join(mod_proj, "enabled.txt")))
                self.assertTrue(os.path.isfile(os.path.join(mod_proj, "mod.json")))
                lua_path = os.path.join(mod_proj, "scripts", "main.lua")
                self.assertTrue(os.path.isfile(lua_path))
                with open(lua_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.assertIn("Test Mod", content)
                self.assertIn("RegisterHook", content)


class TestScanSessionLogic(unittest.TestCase):
    def test_session_filtering(self):
        sess = ScanSession(pid=1234, kind="int32")
        sess.candidates = [0x1000, 0x2000, 0x3000]
        sess.last_value = 100
        sess.round = 1

        # Mock memory reading in next_scan
        import agmod.memory as mem
        orig_read = mem.read_value
        try:
            # Suppose 0x1000 is now 80, 0x2000 is still 100, 0x3000 is 50
            mem.read_value = lambda h, addr, kind: {0x1000: 80, 0x2000: 100, 0x3000: 50}.get(addr, 0)
            
            # Next scan for exact 80
            survivors = sess.next_scan(handle=0, new_value=80, scan_type="exact")
            self.assertEqual(survivors, 1)
            self.assertEqual(sess.candidates, [0x1000])
            self.assertEqual(sess.round, 2)
        finally:
            mem.read_value = orig_read


class TestInspector(unittest.TestCase):
    def test_inspect_unreal(self):
        with tempfile.TemporaryDirectory() as game_dir:
            with open(os.path.join(game_dir, "Game.uproject"), "w") as f:
                f.write("{}")
            res = inspect_feature(game_dir, "gold")
            self.assertTrue(res["success"])
            self.assertEqual(res["engine"]["id"], "unreal")
            self.assertIn("ue4ss", res["recommended_strategy"]["persistent_mod"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
