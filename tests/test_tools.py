from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import ilspy, melonloader, uassetgui


class TestNewIntegrations(unittest.TestCase):
    def test_is_il2cpp_unity_false_when_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(melonloader.is_il2cpp_unity(d))

    def test_is_il2cpp_unity_true_with_gameassembly(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "GameAssembly.dll").write_bytes(b"")
            self.assertTrue(melonloader.is_il2cpp_unity(d))

    def test_is_il2cpp_unity_true_with_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "global-metadata.dat").write_bytes(b"")
            self.assertTrue(melonloader.is_il2cpp_unity(d))

    def test_scaffold_melon_mod_writes_project(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as proj:
            os.makedirs(os.path.join(game, "MelonLoader", "net6"), exist_ok=True)
            melonloader.scaffold_melon_mod(proj, game, "test-mod", "Test Mod")
            self.assertTrue(os.path.isfile(os.path.join(proj, "Mod.cs")))
            self.assertTrue(os.path.isfile(os.path.join(proj, "test-mod.csproj")))
            self.assertTrue(os.path.isfile(os.path.join(proj, "mod.json")))
            with open(os.path.join(proj, "test-mod.csproj"), encoding="utf-8") as f:
                self.assertIn("net6.0", f.read())

    def test_build_melon_mod_without_dotnet_returns_clear_error(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as proj:
            with mock.patch.object(melonloader.shutil, "which", return_value=None):
                result = melonloader.build_melon_mod(proj, game)
            self.assertFalse(result["success"])
            self.assertIn(".NET SDK", result["error"])

    def test_find_uassetgui_is_pure(self):
        p = uassetgui.find_uassetgui()
        self.assertTrue(p is None or isinstance(p, str))

    def test_find_ilspycmd_is_pure(self):
        p = ilspy.find_ilspycmd()
        self.assertTrue(p is None or isinstance(p, str))


if __name__ == "__main__":
    unittest.main()
