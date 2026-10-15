from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import repak
from agmod.adapters.unreal import UnrealAdapter


class TestRepakWrapper(unittest.TestCase):
    def test_pack_and_unpack_use_supported_cli_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            override = Path(tmp, "override")
            override.mkdir()
            out_pak = Path(tmp, "mod.pak")
            with mock.patch.object(repak, "ensure_repak", return_value="repak.exe"), mock.patch.object(repak.subprocess, "run") as run:
                repak.pack_override(str(override), str(out_pak))
                self.assertEqual(run.call_args.args[0], ["repak.exe", "pack", str(override), str(out_pak)])

            out_dir = Path(tmp, "unpacked")
            with mock.patch.object(repak, "ensure_repak", return_value="repak.exe"), mock.patch.object(repak.subprocess, "run") as run:
                repak.unpack(str(out_pak), str(out_dir))
                self.assertEqual(run.call_args.args[0], ["repak.exe", "unpack", str(out_pak), "--output", str(out_dir)])

    def test_unreal_adapter_rejects_iostore_unpak(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as out:
            utoc = Path(game, "global.utoc")
            utoc.write_bytes(b"")
            with self.assertRaises(ValueError):
                UnrealAdapter().unpack_pak(game, "global.utoc", out)

    def test_unreal_adapter_rejects_pak_path_escape(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as out:
            with self.assertRaises(ValueError):
                UnrealAdapter().unpack_pak(game, "../outside.pak", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
