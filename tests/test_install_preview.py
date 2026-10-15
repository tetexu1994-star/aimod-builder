from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import install_preview, packages, rollback


class TestInstallPreview(unittest.TestCase):
    def _package(self, game: str):
        return packages.build_package_spec(game, "unity", "gold-plus", "Gold Plus", "1.0.0")

    def test_preview_reports_add_and_dependency_compatibility(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as source:
            core = Path(game, "BepInEx", "core")
            core.mkdir(parents=True)
            (core / "BepInEx.dll").write_bytes(b"")
            (Path(game, "BepInEx") / "version.txt").write_text("5.4.23.0", encoding="utf-8")
            src = Path(source, "GoldPlus.dll")
            src.write_bytes(b"mod")
            result = install_preview.preview_install(
                game,
                "gold-plus",
                [(str(src), "BepInEx/plugins/GoldPlus.dll")],
                package_spec=self._package(game),
            )
            self.assertTrue(result["ready"])
            self.assertEqual(result["summary"], {"add": 1, "overwrite": 0, "unchanged": 0})
            self.assertEqual(result["dependencies"]["checks"][0]["compatibility"], "compatible")

    def test_preview_flags_other_mod_ownership(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as source:
            core = Path(game, "BepInEx", "core")
            core.mkdir(parents=True)
            (core / "BepInEx.dll").write_bytes(b"")
            (Path(game, "BepInEx") / "version.txt").write_text("5.4.23.0", encoding="utf-8")
            existing = Path(game, "BepInEx", "plugins", "GoldPlus.dll")
            existing.parent.mkdir(parents=True)
            existing.write_bytes(b"old")
            rollback.record_install(game, "other-mod", [str(existing)], {})
            src = Path(source, "GoldPlus.dll")
            src.write_bytes(b"new")
            result = install_preview.preview_install(
                game,
                "gold-plus",
                [(str(src), "BepInEx/plugins/GoldPlus.dll")],
                package_spec=self._package(game),
            )
            self.assertFalse(result["ready"])
            self.assertTrue(any("owned by another mod" in error for error in result["errors"]))
            self.assertEqual(result["changes"][0]["action"], "overwrite")

    def test_preview_reports_missing_loader(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as source:
            src = Path(source, "GoldPlus.dll")
            src.write_bytes(b"mod")
            result = install_preview.preview_install(
                game,
                "gold-plus",
                [(str(src), "BepInEx/plugins/GoldPlus.dll")],
                package_spec=self._package(game),
            )
            self.assertFalse(result["ready"])
            self.assertTrue(any("required dependency is missing" in error for error in result["errors"]))

    def test_dependency_mismatch_is_a_blocker(self):
        with tempfile.TemporaryDirectory() as game:
            core = Path(game, "BepInEx", "core")
            core.mkdir(parents=True)
            (core / "BepInEx.dll").write_bytes(b"")
            (Path(game, "BepInEx") / "version.txt").write_text("5.4.22.0", encoding="utf-8")
            result = install_preview.preview_install(game, "gold-plus", [], package_spec=self._package(game))
            self.assertFalse(result["ready"])
            self.assertTrue(any("version mismatch" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
