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

    def run_client(self, args):
        return subprocess.run(
            [str(CLIENT), *args],
            env={
                **os.environ,
                "UTP_REPORT_HOOK": str(self.hook),
                "REPORT_OUTPUT": str(self.output),
            },
            text=True,
            capture_output=True,
        )

    def run_report(self, *extra):
        return self.run_client(
            [
                "report",
                "--route",
                "felix:sample-group",
                "--project",
                "sample-product",
                *extra,
            ]
        )

    def run_authorized_report(self):
        return self.run_report(
            "--summary",
            "The feature is available.",
            "--verification",
            "The focused workflow passed.",
            "--rollback",
            "Restore the previous verified build.",
            "--user-authorized",
        )

    def run_redact(self, *extra):
        return self.run_client(
            [
                "redact",
                "--route",
                "felix:sample-group",
                "--project",
                "sample-product",
                *extra,
            ]
        )

    def test_delivers_structured_report_to_local_hook(self):
        result = self.run_authorized_report()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(self.output.read_text()),
            {
                "kind": "report",
                "project": "sample-product",
                "summary": "The feature is available.",
                "verification": "The focused workflow passed.",
                "route": "felix:sample-group",
                "rollback": "Restore the previous verified build.",
            },
        )

    def test_requires_explicit_delivery_authorization(self):
        result = self.run_report(
            "--summary",
            "Done.",
            "--verification",
            "Verified.",
            "--rollback",
            "Revert.",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--user-authorized", result.stderr)
        self.assertFalse(self.output.exists())

    def test_file_kind_requires_file(self):
        result = self.run_report(
            "--kind",
            "file",
            "--summary",
            "Caption.",
            "--user-authorized",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--file", result.stderr)
        self.assertFalse(self.output.exists())

    def test_report_kind_rejects_file(self):
        attachment = self.root / "report.txt"
        attachment.write_text("sample contents")

        result = self.run_report(
            "--file",
            str(attachment),
            "--summary",
            "The feature is available.",
            "--verification",
            "The focused workflow passed.",
            "--rollback",
            "Restore the previous verified build.",
            "--user-authorized",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--file only applies to --kind file|image", result.stderr)
        self.assertFalse(self.output.exists())

    def test_delivers_file_kind_with_realpath_and_caption(self):
        attachment = self.root / "report.txt"
        attachment.write_text("sample contents")

        result = self.run_report(
            "--kind",
            "file",
            "--file",
            str(attachment),
            "--summary",
            "Optional caption.",
            "--user-authorized",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(self.output.read_text()),
            {
                "kind": "file",
                "project": "sample-product",
                "summary": "Optional caption.",
                "verification": "",
                "route": "felix:sample-group",
                "rollback": "",
                "file": os.path.realpath(attachment),
            },
        )

    def test_delivers_image_kind(self):
        image = self.root / "chart.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")

        result = self.run_report(
            "--kind",
            "image",
            "--file",
            str(image),
            "--summary",
            "Chart.",
            "--user-authorized",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(self.output.read_text()),
            {
                "kind": "image",
                "project": "sample-product",
                "summary": "Chart.",
                "verification": "",
                "route": "felix:sample-group",
                "rollback": "",
                "file": os.path.realpath(image),
            },
        )

    def test_redact_requires_explicit_authorization(self):
        result = self.run_redact(
            "--message-id",
            "7",
            "--reason",
            "cleanup",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--user-authorized", result.stderr)
        self.assertFalse(self.output.exists())

    def test_redact_delivers_deduped_sorted_message_ids(self):
        result = self.run_redact(
            "--message-id",
            "7",
            "--message-id",
            "3",
            "--message-id",
            "7",
            "--reason",
            "cleanup",
            "--user-authorized",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(self.output.read_text()),
            {
                "op": "redact",
                "project": "sample-product",
                "route": "felix:sample-group",
                "message_ids": [3, 7],
                "reason": "cleanup",
            },
        )

    def test_redact_rejects_more_than_twenty_ids(self):
        args = []
        for message_id in range(1, 22):
            args += ["--message-id", str(message_id)]

        result = self.run_redact(
            *args,
            "--reason",
            "cleanup",
            "--user-authorized",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("1-20", result.stderr)
        self.assertFalse(self.output.exists())

    def test_redact_rejects_non_positive_ids(self):
        result = self.run_redact(
            "--message-id",
            "0",
            "--reason",
            "cleanup",
            "--user-authorized",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("positive integers", result.stderr)
        self.assertFalse(self.output.exists())

    def test_rejects_group_writable_hook(self):
        self.hook.chmod(0o720)

        result = self.run_authorized_report()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not group/world writable", result.stderr)
        self.assertFalse(self.output.exists())

    def test_rejects_group_writable_hook_directory(self):
        self.root.chmod(0o720)

        result = self.run_authorized_report()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("directory must be current-user-owned and private", result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
