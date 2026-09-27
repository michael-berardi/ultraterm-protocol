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
        self.env = {**os.environ, "HOME": str(self.root)}

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

    def test_inspect_emits_plain_history_by_default(self):
        server = self.serve_once('{"ok":true,"slot":2,"text":"terminal text\\nsecond line"}\n')
        result = subprocess.run(
            [str(CLIENT), "inspect", "--slot", "2", "--lines", "1"],
            env=self.env,
            text=True,
            capture_output=True,
            timeout=5,
        )
        server.join(timeout=2)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "terminal text\nsecond line\n")
        self.assertEqual(result.stderr, "")

    def test_inspect_no_uc_is_deprecated_no_op(self):
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
        self.assertEqual(result.stderr, "")

    def test_savings_legacy_calls_fail_clearly_without_socket(self):
        for args in ([], ["--rate", "12.5"]):
            with self.subTest(args=args):
                result = subprocess.run(
                    [str(CLIENT), "savings", *args],
                    env=self.env,
                    text=True,
                    capture_output=True,
                    timeout=5,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("UltraCompact savings were removed", result.stderr)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
