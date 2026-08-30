import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


CLIENT = Path(__file__).resolve().parents[1] / "clients" / "python" / "utp"
LOADER = importlib.machinery.SourceFileLoader("utp_client", str(CLIENT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
UTP = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(UTP)


class HandoffPacketTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir="/tmp")
        self.root = Path(self.temporary.name)
        self.packet = self.root / "handoff.md"
        self.packet.write_text("# Goal\nContinue the verified task.\n")
        self.packet.chmod(0o600)

    def tearDown(self):
        self.temporary.cleanup()

    def test_accepts_private_current_user_packet(self):
        self.assertEqual(
            UTP.handoff_packet_path(str(self.packet)),
            os.path.realpath(self.packet),
        )

    def test_rejects_non_private_packet(self):
        self.packet.chmod(0o644)
        with self.assertRaisesRegex(SystemExit, "chmod 600"):
            UTP.handoff_packet_path(str(self.packet))

    def test_rejects_symlink_packet(self):
        link = self.root / "linked.md"
        link.symlink_to(self.packet)
        with self.assertRaisesRegex(SystemExit, "regular file"):
            UTP.handoff_packet_path(str(link))

    def test_rejects_symlinked_parent_outside_tmp(self):
        linked_parent = self.root / "outside"
        linked_parent.symlink_to(CLIENT.parent, target_is_directory=True)
        with self.assertRaisesRegex(SystemExit, "resolve to a file under /tmp"):
            UTP.handoff_packet_path(str(linked_parent / CLIENT.name))

    def test_rejects_packet_outside_tmp(self):
        with self.assertRaisesRegex(SystemExit, "resolve to a file under /tmp"):
            UTP.handoff_packet_path(str(CLIENT))

    def test_rejects_self_replacing_handoff_sender(self):
        result = __import__("subprocess").run(
            [
                str(CLIENT),
                "handoff",
                "--slot",
                "2",
                "--profile",
                "quality",
                "--packet",
                str(self.packet),
                "--expected-id",
                "session-id",
                "--manager-slot",
                "1",
                "--confirm",
                "--user-authorized",
            ],
            env={
                **{key: value for key, value in os.environ.items() if key not in {"TMUX", "TMUX_PANE"}},
                "ULTRATERM_SLOT": "2",
            },
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must run from its manager", result.stderr)

    def test_rejects_oversized_packet(self):
        self.packet.write_bytes(b"x" * (16 * 1024 + 1))
        self.packet.chmod(0o600)
        with self.assertRaisesRegex(SystemExit, "1-16384"):
            UTP.handoff_packet_path(str(self.packet))


if __name__ == "__main__":
    unittest.main()
