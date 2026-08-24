import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


CLIENT = Path(__file__).resolve().parents[1] / "clients" / "python" / "utp"


class ReportHookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output = self.root / "payload.json"
        self.hook = self.root / "report-hook"
        self.hook.write_text(
            "#!/usr/bin/env python3\n"
            "import os, pathlib, sys\n"
            "pathlib.Path(os.environ['REPORT_OUTPUT']).write_text(sys.stdin.read())\n"
        )
        self.hook.chmod(0o700)

    def tearDown(self):
        self.temporary.cleanup()

    def run_report(self):
        return subprocess.run(
            [
                str(CLIENT),
                "report",
                "--project",
                "sample-product",
                "--summary",
                "The feature is available.",
                "--verification",
                "The focused workflow passed.",
                "--rollback",
                "Restore the previous verified build.",
            ],
            env={
                **os.environ,
                "UTP_REPORT_HOOK": str(self.hook),
                "REPORT_OUTPUT": str(self.output),
            },
            text=True,
            capture_output=True,
        )

    def test_delivers_structured_report_to_local_hook(self):
        result = self.run_report()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(self.output.read_text()),
            {
                "project": "sample-product",
                "summary": "The feature is available.",
                "verification": "The focused workflow passed.",
                "rollback": "Restore the previous verified build.",
            },
        )

    def test_rejects_group_writable_hook(self):
        self.hook.chmod(0o720)

        result = self.run_report()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not group/world writable", result.stderr)
        self.assertFalse(self.output.exists())

    def test_rejects_group_writable_hook_directory(self):
        self.root.chmod(0o720)

        result = self.run_report()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("directory must be current-user-owned and private", result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
