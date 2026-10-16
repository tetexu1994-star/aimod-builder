from __future__ import annotations

import os
import tempfile
import unittest

from agmod.frameworks import detect_game_framework


class TestGameFrameworks(unittest.TestCase):
    def test_detect_terraria_with_tmodloader(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "Terraria.exe"), "w").close()
            open(os.path.join(tmp, "tModLoader.dll"), "w").close()
            fw = detect_game_framework(tmp)
            self.assertEqual(fw["game_type"], "terraria")
            self.assertTrue(fw["installed"])
            self.assertEqual(fw["framework_id"], "tmodloader")
            self.assertIn("tModLoader", fw["framework_name"])

    def test_detect_terraria_with_bepinex_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "Terraria.exe"), "w").close()
            open(os.path.join(tmp, "winhttp.dll"), "w").close()
            os.makedirs(os.path.join(tmp, "BepInEx"))
            fw = detect_game_framework(tmp)
            self.assertEqual(fw["game_type"], "terraria")
            self.assertTrue(fw["installed"])
            self.assertEqual(fw["framework_id"], "bepinex_doorstop")
            self.assertIn("BepInEx", fw["framework_name"])

    def test_detect_terraria_vanilla_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "Terraria.exe"), "w").close()
            fw = detect_game_framework(tmp)
            self.assertEqual(fw["game_type"], "terraria")
            self.assertFalse(fw["installed"])
            self.assertEqual(fw["status"], "missing")
            self.assertIn("1281930", fw.get("steam_appid", ""))

    def test_detect_stardew_valley_vanilla_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "Stardew Valley.exe"), "w").close()
            fw = detect_game_framework(tmp)
            self.assertEqual(fw["game_type"], "stardew_valley")
            self.assertFalse(fw["installed"])
            self.assertEqual(fw["status"], "missing")
            self.assertIn("smapi.io", fw.get("download_url", ""))

    def test_detect_skyrim_skse(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "SkyrimSE.exe"), "w").close()
            open(os.path.join(tmp, "skse64_loader.exe"), "w").close()
            fw = detect_game_framework(tmp)
            self.assertEqual(fw["game_type"], "bethesda")
            self.assertTrue(fw["installed"])
            self.assertEqual(fw["framework_id"], "script_extender")
            self.assertIn("SKSE64", fw["framework_name"])

    def test_detect_baldurs_gate_3(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "bg3.exe"), "w").close()
            bin_dir = os.path.join(tmp, "bin")
            os.makedirs(bin_dir)
            open(os.path.join(bin_dir, "DWrite.dll"), "w").close()
            fw = detect_game_framework(tmp)
            self.assertEqual(fw["game_type"], "baldurs_gate_3")
            self.assertTrue(fw["installed"])
            self.assertEqual(fw["framework_id"], "bg3se")

    def test_detect_elden_ring_modengine(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "eldenring.exe"), "w").close()
            open(os.path.join(tmp, "modengine2_launcher.exe"), "w").close()
            fw = detect_game_framework(tmp)
            self.assertEqual(fw["game_type"], "fromsoftware")
            self.assertTrue(fw["installed"])
            self.assertEqual(fw["framework_id"], "modengine2")

    def test_detect_bannerlord(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "Bannerlord.exe"), "w").close()
            os.makedirs(os.path.join(tmp, "Modules", "Bannerlord.Harmony"))
            fw = detect_game_framework(tmp)
            self.assertEqual(fw["game_type"], "bannerlord")
            self.assertTrue(fw["installed"])
            self.assertEqual(fw["framework_id"], "bannerlord_harmony")


if __name__ == "__main__":
    unittest.main()
