"""Run the example scripts with a recording stand-in for `utp`; no app or socket."""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
# /bin/sh is dash on Debian and bash (POSIX mode) on macOS; exercise both parsers.
SHELLS = [shell for shell in ("sh", "bash") if shutil.which(shell)]


class ExampleScriptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.calls = self.root / "utp-calls"
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        utp = bin_dir / "utp"
        utp.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$UTP_CALLS"\n')
        utp.chmod(0o700)
        self.env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "UTP_CALLS": str(self.calls)}

    def tearDown(self):
        self.temporary.cleanup()

    def run_example(self, shell, name, *args, **env):
        return subprocess.run(
            [shell, str(EXAMPLES / name), *args],
            env={**self.env, **env},
            text=True,
            capture_output=True,
            timeout=10,
        )

    def test_worker_complete_reports_each_missing_session_id(self):
        cases = [
            ({}, "Set WORKER_SESSION_ID to the session ID of this worker from utp list"),
            ({"WORKER_SESSION_ID": "worker"},
             "Set MANAGER_SESSION_ID to the session ID of the manager from utp list"),
        ]
        for shell in SHELLS:
            for env, message in cases:
                with self.subTest(shell=shell, env=env):
                    result = self.run_example(shell, "worker-complete.sh", ULTRATERM_SLOT="2", **env)

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(message, result.stderr)
                    self.assertFalse(self.calls.exists())

    def test_worker_complete_registers_then_reports(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                result = self.run_example(
                    shell, "worker-complete.sh", "Done.", ULTRATERM_SLOT="2",
                    WORKER_SESSION_ID="worker", MANAGER_SESSION_ID="manager",
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    self.calls.read_text().splitlines(),
                    [
                        "register-manager --slot 1 --from-id worker --expected-id manager",
                        "task-done --from-id worker --summary Done.",
                    ],
                )
                self.calls.unlink()

    def test_manager_delegate_never_chmods_through_a_symlink(self):
        target = self.root / "unrelated.txt"
        target.write_text("not a packet\n")
        target.chmod(0o644)
        link = self.root / "handoff.md"
        link.symlink_to(target)
        for shell in SHELLS:
            with self.subTest(shell=shell):
                result = self.run_example(shell, "manager-delegate.sh", str(link))

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("not a symlink", result.stderr)
                self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o644)
                self.assertFalse(self.calls.exists())

    def test_manager_delegate_privatizes_a_regular_packet(self):
        packet = self.root / "handoff.md"
        packet.write_text("# Goal\n")
        for shell in SHELLS:
            with self.subTest(shell=shell):
                packet.chmod(0o644)
                result = self.run_example(shell, "manager-delegate.sh", str(packet))

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(stat.S_IMODE(os.stat(packet).st_mode), 0o600)
                self.assertIn(f"--packet {packet}", self.calls.read_text())
                self.calls.unlink()


if __name__ == "__main__":
    unittest.main()
