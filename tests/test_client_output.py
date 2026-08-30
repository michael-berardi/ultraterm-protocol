import os
import socket
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path


CLIENT = Path(__file__).resolve().parents[1] / "clients" / "python" / "utp"


class ClientOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.socket_dir = self.root / ".ultraterm"
        self.socket_dir.mkdir()
        self.socket_path = self.socket_dir / "utp.sock"
        self.uc_args = self.root / "uc-args"
        self.uc = self.root / "uc"
        self.uc.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$@\" > \"$UC_ARGS_CAPTURE\"\n"
            "if [ \"$1\" = encode ]; then\n"
            "  cat >/dev/null\n"
            "  printf '{\"slot\":2,\"text\":\"readable\"}\\n'\n"
            "else\n"
            "  printf 'saved locally\\n'\n"
            "fi\n"
        )
        self.uc.chmod(0o700)
        self.env = {
            **os.environ,
            "HOME": str(self.root),
            "UC_BIN": str(self.uc),
            "UC_ARGS_CAPTURE": str(self.uc_args),
        }

    def tearDown(self):
        self.temp.cleanup()

    def serve_once(self, response):
        ready = threading.Event()

        def serve():
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(self.socket_path))
                server.listen(1)
                ready.set()
                connection, _ = server.accept()
                with connection:
                    connection.recv(65536)
                    connection.sendall(response.encode())

        thread = threading.Thread(target=serve)
        thread.start()
        self.assertTrue(ready.wait(timeout=2))
        return thread

    def test_inspect_emits_model_readable_output_by_default(self):
        server = self.serve_once('{"ok":true,"slot":2,"text":"terminal text"}\n')
        result = subprocess.run(
            [str(CLIENT), "inspect", "--slot", "2", "--lines", "1"],
            env=self.env,
            text=True,
            capture_output=True,
            timeout=5,
        )
        server.join(timeout=2)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '{"slot":2,"text":"readable"}\n')
        self.assertEqual(
            self.uc_args.read_text().splitlines(),
            ["encode", "--readable", "--stats"],
        )

    def test_inspect_no_uc_preserves_plain_history(self):
        server = self.serve_once('{"ok":true,"slot":2,"text":"terminal text"}\n')
        result = subprocess.run(
            [str(CLIENT), "inspect", "--slot", "2", "--no-uc"],
            env=self.env,
            text=True,
            capture_output=True,
            timeout=5,
        )
        server.join(timeout=2)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "terminal text\n")
        self.assertFalse(self.uc_args.exists())

    def test_savings_reads_local_uc_telemetry(self):
        result = subprocess.run(
            [str(CLIENT), "savings", "--rate", "12.5"],
            env=self.env,
            text=True,
            capture_output=True,
            timeout=5,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "saved locally\n")
        self.assertEqual(self.uc_args.read_text().splitlines(), ["telemetry", "--rate", "12.5"])


if __name__ == "__main__":
    unittest.main()
