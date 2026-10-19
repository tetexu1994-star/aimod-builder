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

    def test_launch_game_prioritizes_framework_loader(self):
        from unittest import mock
        from agmod.discovery import launch_game

        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "SkyrimSE.exe"), "w").close()
            skse = os.path.join(tmp, "skse64_loader.exe")
            open(skse, "w").close()

            with mock.patch("subprocess.Popen") as mock_popen:
                res = launch_game(tmp)
                self.assertTrue(res["success"])
                self.assertEqual(res["method"], "direct_executable")
                self.assertTrue(res.get("is_loader"))
                self.assertEqual(res["exe"], skse)
                mock_popen.assert_called_once_with([skse], cwd=tmp)

    def test_launch_game_companion_steam_appid(self):
        from unittest import mock
        from agmod.discovery import launch_game

        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "Terraria.exe"), "w").close()
            with mock.patch("subprocess.Popen") as mock_popen, mock.patch("sys.platform", "darwin"):
                res = launch_game(tmp)
                self.assertTrue(res["success"])
                self.assertEqual(res["method"], "steam_protocol")
                self.assertEqual(res["appid"], "1281930")
                self.assertTrue(res.get("is_companion_loader"))
                mock_popen.assert_called_once_with(["open", "steam://rungameid/1281930"])

    def test_process_tracks_loader_candidates(self):
        from agmod.process import get_running_game_processes

        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "Stardew Valley.exe"), "w").close()
            open(os.path.join(tmp, "StardewModdingAPI.exe"), "w").close()

            fake_cache = [("StardewModdingAPI.exe", 12345), ("chrome.exe", 999)]
            from unittest import mock
            with mock.patch("agmod.process._PROCESS_CACHE", {"timestamp": 9999999999.0, "processes": fake_cache}), \
                 mock.patch("agmod.process.psutil", None), \
                 mock.patch("sys.platform", "darwin"):
                procs = get_running_game_processes(tmp, force_refresh=False)
                self.assertEqual(len(procs), 1)
                self.assertEqual(procs[0]["pid"], 12345)


if __name__ == "__main__":
    unittest.main()

