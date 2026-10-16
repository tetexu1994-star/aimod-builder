from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import compiler


class TestCompiler(unittest.TestCase):
    def test_find_compiler_shape(self):
        found = compiler.find_compiler()
        self.assertIsInstance(found, dict)
        self.assertIn("type", found)
        self.assertIn("path", found)

    def test_find_roslyn_csc_is_pure(self):
        # Must not hit the network; just reports the cached path (or None).
        p = compiler.find_roslyn_csc()
        self.assertTrue(p is None or isinstance(p, str))

    def test_framework_references_is_list(self):
        refs = compiler.framework_references()
        self.assertIsInstance(refs, list)
        self.assertTrue(all(os.path.isfile(r) for r in refs))

    def test_compile_with_csc_produces_dll(self):
        found = compiler.find_compiler()
        if found.get("type") not in {"csc", "roslyn"}:
            self.skipTest("no standalone csc.exe available on this machine")

        source = (
            "using System;\n"
            "using System.Collections.Generic;\n"
            "namespace TestPlugin {\n"
            "  public static class Calc {\n"
            "    public static int Add(int a, int b) { return a + b; }\n"
            "    public static string Name() { return \"hello\"; }\n"
            "  }\n"
            "}\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp, "Calc.cs")
            out = Path(tmp, "Calc.dll")
            src.write_text(source, encoding="utf-8")
            res = compiler.compile_with_csc(found["path"], str(out), [], str(src))
            self.assertEqual(res.returncode, 0, (res.stdout or "") + (res.stderr or ""))
            self.assertTrue(out.is_file() and out.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
