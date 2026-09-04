"""Single-instance guard and admin-password reset, exercised for real:
a second interpreter is spawned so the OS-level lock (named mutex on
Windows, flock elsewhere) is what's under test, not a mock.

Run with:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _child_env(data_dir: Path) -> dict[str, str]:
    """Point the app modules at a throwaway data directory. settings.py
    reads PROGRAMDATA on Windows and HOME elsewhere at import time."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    if sys.platform == "win32":
        env["PROGRAMDATA"] = str(data_dir)
    else:
        env["HOME"] = str(data_dir)
    return env


class SingleInstanceTest(unittest.TestCase):
    def test_second_process_is_refused_while_first_holds_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _child_env(Path(tmp))
            # Holder: acquire, report, then wait on stdin so the lock stays
            # held for as long as the test needs.
            holder = subprocess.Popen(
                [
                    sys.executable, "-c",
                    "import single_instance, sys; "
                    "print(single_instance.acquire(), flush=True); "
                    "sys.stdin.readline()",
                ],
                env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            )
            try:
                self.assertEqual(holder.stdout.readline().strip(), "True")
                second = subprocess.run(
                    [sys.executable, "-c",
                     "import single_instance; print(single_instance.acquire())"],
                    env=env, capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(second.stdout.strip(), "False", second.stderr)
            finally:
                holder.stdin.write("\n")
                holder.stdin.close()
                holder.wait(timeout=30)

            # Once the holder exits the lock is free again.
            third = subprocess.run(
                [sys.executable, "-c",
                 "import single_instance; print(single_instance.acquire())"],
                env=env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(third.stdout.strip(), "True", third.stderr)


class PasswordResetTest(unittest.TestCase):
    def test_reset_clears_hash_and_keeps_other_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _child_env(Path(tmp))
            script = (
                "import settings as s\n"
                "orig = s.Settings(max_drinks=7, open_time='17:00').with_admin_password('hunter22')\n"
                "s.save(orig)\n"
                "assert s.load().verify_admin_password('hunter22')\n"
                "assert not s.load().verify_admin_password('admin')\n"
                "s.reset_admin_password()\n"
                "after = s.load()\n"
                "assert after.verify_admin_password('admin'), 'default not accepted'\n"
                "assert after.max_drinks == 7 and after.open_time == '17:00', 'other settings lost'\n"
                "print('ok')\n"
            )
            res = subprocess.run(
                [sys.executable, "-c", script],
                env=env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(res.stdout.strip(), "ok", res.stderr)


if __name__ == "__main__":
    unittest.main()
