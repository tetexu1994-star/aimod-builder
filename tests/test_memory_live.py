from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agmod import memory

# A tiny real process that holds a known int32 in memory at a stable address.
# The test reads/writes that process's memory through the actual Windows APIs.
_HELPER = (
    "import ctypes, os, time\n"
    "val = ctypes.c_int32(100)\n"
    "print(f'PID={os.getpid()} ADDR={ctypes.addressof(val)}', flush=True)\n"
    "time.sleep(60)\n"
)


class TestMemoryLive(unittest.TestCase):
    @unittest.skipUnless(memory.IS_WINDOWS, "memory engine is Windows-only")
    def test_write_and_verify_against_real_process(self):
        with tempfile.TemporaryDirectory() as d:
            helper = os.path.join(d, "helper.py")
            with open(helper, "w", encoding="utf-8") as f:
                f.write(_HELPER)
            proc = subprocess.Popen(
                [sys.executable, helper], stdout=subprocess.PIPE, text=True
            )
            try:
                line = proc.stdout.readline().strip()
                self.assertIn("PID=", line)
                self.assertIn("ADDR=", line)
                pid = int(line.split("PID=")[1].split()[0])
                addr = int(line.split("ADDR=")[1])

                h = memory.open_process(pid)
                try:
                    self.assertEqual(memory.read_value(h, addr, "int32"), 100)

                    res = memory.write_and_verify(h, addr, 99999, "int32")
                    self.assertTrue(res["changed"])
                    self.assertEqual(res["before"], 100)
                    self.assertEqual(res["after"], 99999)

                    self.assertTrue(memory.verify_value(h, addr, 99999, "int32")["matches"])
                    self.assertFalse(memory.verify_value(h, addr, 100, "int32")["matches"])
                finally:
                    memory.close_process(h)
            finally:
                proc.terminate()
                proc.wait(timeout=5)
                if proc.stdout:
                    proc.stdout.close()


if __name__ == "__main__":
    unittest.main()
