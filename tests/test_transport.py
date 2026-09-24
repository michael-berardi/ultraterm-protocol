"""Real CLI exchanges against private disposable Unix sockets; never the app socket."""
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1] / 'clients/python/utp'


class TransportTests(unittest.TestCase):
    def exchange(self, reply, args=None, delay=0, codec=None):
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / '.ultraterm'
            path.mkdir()
            requests = []
            errors = []
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(str(path / 'utp.sock'))
                server.listen(8)
                server.settimeout(2)

                def serve():
                    try:
                        conn, _ = server.accept()
                        with conn:
                            data = b''
                            while not data.endswith(b'\n'):
                                data += conn.recv(65536)
                            requests.append(json.loads(data))
                            time.sleep(delay)
                            try:
                                conn.sendall(reply)
                            except BrokenPipeError:
                                pass
                        server.settimeout(.15)
                        try:
                            conn, _ = server.accept()
                            conn.close()
                            requests.append('UNSAFE RETRY')
                        except socket.timeout:
                            pass
                    except Exception as exc:
                        errors.append(exc)

                thread = threading.Thread(target=serve)
                thread.start()
                env = {**os.environ, 'HOME': home, 'TMUX_PANE': '', 'UC_BIN': str(Path(home) / 'uc')}
                if codec == 'nonexecutable':
                    Path(env['UC_BIN']).write_text('#!/bin/sh\nexit 0\n')
                result = subprocess.run([str(CLIENT), *(args or ['diagnose'])], env=env,
                                        capture_output=True, text=True, timeout=14)
                thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(len(requests), 1)
                self.assertNotIn('Traceback', result.stderr)
                return result, requests[0]

    def test_diagnose_and_version(self):
        response = dict(ok=True, protocolVersion='2.2.0', wireVersion=2, activeConnections=1, connectionLimit=32)
        result, request = self.exchange(json.dumps(response).encode() + b'\n')
        self.assertEqual(request, {'cmd': 'diagnose'})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), response)
        result = subprocess.run([str(CLIENT), '--version'], text=True, capture_output=True)
        self.assertEqual(result.stdout.strip(), '2.2.0')

    def test_bounded_invalid_replies(self):
        for reply, error in [(b'', 'disconnected'), (b'{"ok":true}', 'truncated'),
                             (b'x' * (1024 * 1024 + 1), 'oversized'),
                             (b'no\n', 'malformed'), (b'\xff\n', 'malformed'),
                             (b'[]\n', 'malformed'), (b'{"ok":1}\n', 'malformed')]:
            with self.subTest(error=error, length=len(reply)):
                result, _ = self.exchange(reply)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(error, result.stderr)
                self.assertNotIn('mutation outcome unknown', result.stderr)

    def test_mutation_disconnect_is_unknown_and_not_retried(self):
        for reply in [b'', b'{}\n', b'{"ok":true}']:
            result, request = self.exchange(reply, ['send', '--slot', '2', 'hello'])
            self.assertEqual(request['cmd'], 'send')
            self.assertIn('mutation outcome unknown', result.stderr)
            self.assertIn('do not retry automatically', result.stderr)

    def test_timeout_is_bounded_and_not_retried(self):
        start = time.monotonic()
        result, _ = self.exchange(b'', ['send', '--slot', '2', 'hello'], delay=10.2)
        self.assertIn('timeout', result.stderr)
        self.assertIn('mutation outcome unknown', result.stderr)
        self.assertLess(time.monotonic() - start, 13)

    def test_missing_and_refused_socket(self):
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / '.ultraterm'
            path.mkdir()
            for stale in [False, True]:
                if stale:
                    with socket.socket(socket.AF_UNIX) as server:
                        server.bind(str(path / 'utp.sock'))
                result = subprocess.run([str(CLIENT), 'diagnose'], env={**os.environ, 'HOME': home},
                                        text=True, capture_output=True, timeout=2)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('no request sent', result.stderr)
                self.assertIn('refused' if stale else 'not found', result.stderr)
                self.assertNotIn('Traceback', result.stderr)

    def test_inspect_shape_checked_before_codec(self):
        for text in [None, 42, {}, []]:
            result, _ = self.exchange(json.dumps({'ok': True, 'text': text}).encode() + b'\n',
                                      ['inspect', '--slot', '2'])
            self.assertIn('expected text string', result.stderr)
        result, _ = self.exchange(b'{"ok":false,"error":"not attached"}\n', ['inspect', '--slot', '2'])
        self.assertIn('not attached', result.stderr)

    def test_explicit_id_is_never_dropped_for_slot(self):
        for args, reply in [(['send', '--slot', '2', '--id', 'SESSION-A', 'hello'], b'{"ok":true}\n'),
                            (['inspect', '--slot', '2', '--id', 'SESSION-A', '--no-uc'],
                             b'{"ok":true,"text":"hello"}\n')]:
            with self.subTest(cmd=args[0]):
                result, request = self.exchange(reply, args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(request.get('id'), 'SESSION-A')
                self.assertNotIn('slot', request)

    def test_missing_and_nonexecutable_codec_fail_cleanly(self):
        for codec in [None, 'nonexecutable']:
            result, _ = self.exchange(b'{"ok":true,"text":"hello"}\n', ['inspect', '--slot', '2'], codec=codec)
            self.assertIn('optional UC codec unavailable', result.stderr)
            self.assertIn('--no-uc', result.stderr)
