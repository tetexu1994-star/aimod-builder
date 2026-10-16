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

    def test_detect_stardew_valley_with_smapi(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "Stardew Valley.exe"), "w").close()
            open(os.path.join(tmp, "StardewModdingAPI.exe"), "w").close()
            fw = detect_game_framework(tmp)
            self.assertEqual(fw["game_type"], "stardew_valley")
            self.assertTrue(fw["installed"])
            self.assertEqual(fw["framework_id"], "smapi")
            self.assertEqual(fw["loader_exe"], "StardewModdingAPI.exe")


if __name__ == "__main__":
    unittest.main()
