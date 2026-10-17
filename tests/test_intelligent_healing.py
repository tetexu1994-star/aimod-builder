"""Tests for intelligent compiler error self-healing and special-case engine handling."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import bepinex, llm, repair
from agmod.repair import CompileError, auto_heal_compilation_failure, auto_heal_csharp_source


class TestIntelligentHealing(unittest.TestCase):
    def test_auto_heal_non_unity_cs0012(self):
        source = """using System;

namespace TerrariaPlugin
{
    public class MyPlugin : BaseUnityPlugin
    {
        public void Awake()
        {
            Logger.LogInfo("Hello Terraria");
        }
    }
}
"""
        error_output = (
            "Plugin.cs(5,29): error CS0012: The type 'MonoBehaviour' is defined in an assembly that is not referenced. "
            "You must add a reference to assembly 'UnityEngine'."
        )
        healed, fixes = auto_heal_compilation_failure(source, error_output, is_non_unity=True)
        self.assertTrue(len(fixes) >= 1)
        self.assertIn("public class BaseUnityPlugin", healed)
        self.assertIn("Console.WriteLine(", healed)
        self.assertNotIn("Logger.LogInfo(", healed)

    def test_auto_heal_missing_semicolon_cs1002(self):
        source = """using System;

namespace TestMod
{
    public class MyMod
    {
        public void Run()
        {
            int a = 1
        }
    }
}
"""
        error_output = "Plugin.cs(9,22): error CS1002: ; expected"
        healed, fixes = auto_heal_compilation_failure(source, error_output)
        self.assertTrue(any("semicolon" in f for f in fixes))
        self.assertIn("int a = 1;", healed)

    def test_auto_heal_missing_usings_cs0246(self):
        source = """namespace TestMod
{
    public class MyMod
    {
        public List<string> Items;
    }
}
"""
        error_output = "Plugin.cs(5,16): error CS0246: The type or namespace name 'List' could not be found"
        healed, fixes = auto_heal_compilation_failure(source, error_output)
        self.assertTrue(any("Injected" in f for f in fixes))
        self.assertIn("using System.Collections.Generic;", healed)

    @mock.patch("agmod.llm.chat_completion")
    def test_heal_code_with_llm_success(self, mock_chat):
        mock_chat.return_value = {
            "success": True,
            "reply": "```csharp\npublic class FixedCode { public void Run() {} }\n```",
            "model": "deepseek-chat",
        }
        res = llm.heal_code_with_llm(
            source_code="public class BrokenCode {",
            error_message="CS1513: } expected",
            game_context={"game_name": "Terraria", "engine_id": "dotnet-xna"},
        )
        self.assertTrue(res["success"])
        self.assertIn("FixedCode", res["repaired_code"])
        self.assertEqual(res["model"], "deepseek-chat")

    @mock.patch("agmod.llm.chat_completion")
    def test_heal_code_with_llm_empty_input(self, mock_chat):
        res = llm.heal_code_with_llm(source_code="", error_message="some error")
        self.assertFalse(res["success"])
        self.assertIn("empty", res["error"])

    @mock.patch("agmod.compiler.compile_with_csc")
    @mock.patch("agmod.compiler.ensure_roslyn_csc")
    def test_compile_unity_plugin_heuristic_healing(self, mock_roslyn, mock_compile):
        mock_roslyn.return_value = "/fake/csc.exe"
        with mock.patch("os.path.isfile", side_effect=lambda p: True if "csc" in p else False):
            pass

        # Verify safe fallback compilation works when initial compilation fails
        with tempfile.TemporaryDirectory() as tmp_dir:
            cs_file = os.path.join(tmp_dir, "Plugin.cs")
            dll_file = os.path.join(tmp_dir, "Plugin.dll")
            with open(cs_file, "w", encoding="utf-8") as f:
                f.write("public class Test {}")

            # Mock csc execution: fail first time, succeed on second attempt (after healing)
            fake_res_fail = mock.Mock(returncode=1, stderr="Plugin.cs(1,1): error CS0012: The type 'MonoBehaviour' is defined in an assembly that is not referenced", stdout="")
            fake_res_ok = mock.Mock(returncode=0, stderr="", stdout="")

            # When csc succeeds, create the dummy dll
            def fake_compile(csc, out_dll, refs, source, langversion):
                if mock_compile.call_count > 1:
                    with open(out_dll, "wb") as f:
                        f.write(b"MZfake_dll")
                    return fake_res_ok
                return fake_res_fail

            mock_compile.side_effect = fake_compile

            with mock.patch("os.path.isfile", side_effect=lambda p: True if "csc" in p or "Plugin.dll" in p or "Plugin.cs" in p else False):
                with mock.patch("agmod.sdk.find_dotnet", return_value=None):
                    res = bepinex.compile_unity_plugin(tmp_dir, "test_mod", cs_file, dll_file)
                    self.assertTrue(res.get("success"))
                    self.assertIn("healed_by", res)


if __name__ == "__main__":
    unittest.main()
