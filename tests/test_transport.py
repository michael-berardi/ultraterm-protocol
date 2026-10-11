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
    def exchange(self, reply, args=None, delay=0):
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
                env = {**os.environ, 'HOME': home, 'TMUX_PANE': ''}
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
        self.assertEqual(result.stdout.strip(), '2.6.1')

    def test_refit_requests_one_terminal_or_all(self):
        sid = '77777777-7777-4777-8777-777777777777'
        delivery = 'signalled; the window refits on its next frame, applied unconfirmed'
        one = dict(ok=True, refit=dict(all=False, terminals=[dict(slot=3, id=sid)]), delivery=delivery)
        result, request = self.exchange(json.dumps(one).encode() + b'\n', ['refit', '--slot', '3'])
        self.assertEqual(request, {'cmd': 'refit', 'slot': 3})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'refit requested\tslot 3\t{sid}', result.stdout)
        # No slot: the request names none, so the server refits every attached terminal.
        everything = dict(ok=True, refit=dict(all=True, terminals=[dict(slot=1, id=sid), dict(slot=3, id=sid)]),
                          delivery=delivery)
        result, request = self.exchange(json.dumps(everything).encode() + b'\n', ['refit'])
        self.assertEqual(request, {'cmd': 'refit'})
        self.assertEqual(result.stdout.count('refit requested'), 2)
        # Nothing attached is a successful no-op, not an error.
        empty = dict(ok=True, refit=dict(all=True, terminals=[]), delivery=delivery)
        result, _ = self.exchange(json.dumps(empty).encode() + b'\n', ['refit'])
        self.assertEqual(result.returncode, 0)
        self.assertIn('no terminals are attached', result.stdout)

    def test_refit_refusals_are_reported(self):
        for error in ['no session on slot 2', 'slot must be between 1 and 32']:
            result, request = self.exchange(json.dumps(dict(ok=False, error=error)).encode() + b'\n',
                                            ['refit', '--slot', '2'])
            self.assertEqual(request, {'cmd': 'refit', 'slot': 2})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(error, result.stderr)
            self.assertNotIn('refit requested', result.stdout)

    def test_refused_send_names_its_receipt_only_when_the_server_knows_it(self):
        rid = '66666666-6666-4666-8666-666666666666'
        args = ['message', '--from', '1', '--to', '2', '--receipt-id', rid, 'hello']
        worker = ('WorkerSenderUnsupportedError: background worker ID cannot send native inbox messages. '
                  'Nothing was queued.')
        # Refused before anything was queued: no receipt exists, so the id is not offered.
        unknown = dict(ok=False, error=worker, receiptId=rid, receiptKnown=False)
        result, request = self.exchange(json.dumps(unknown).encode() + b'\n', args)
        self.assertEqual(request['receiptId'], rid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('WorkerSenderUnsupportedError', result.stderr)
        self.assertIn(f'no receipt {rid} exists', result.stderr)
        self.assertNotIn(f'receiptId={rid}', result.stderr)
        # Refused after durable state changed: the id is a real receipt and is named.
        known = dict(ok=False, error='sync uncertain', receiptId=rid, receiptKnown=True)
        result, _ = self.exchange(json.dumps(known).encode() + b'\n', args)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f'receiptId={rid} (refused, but the server holds this receipt', result.stderr)
        # An older server sends no receiptKnown: no id is offered unless its error says to retry the same one.
        older = dict(ok=False, error='native host unsupported')
        result, _ = self.exchange(json.dumps(older).encode() + b'\n', args)
        self.assertNotIn('receiptId=', result.stderr)
        self.assertNotIn('no receipt', result.stderr)
        # An accepted send names its receipt.
        accepted = dict(ok=True, id='RECIPIENT', receiptId=rid, delivery='durably-queued')
        result, _ = self.exchange(json.dumps(accepted).encode() + b'\n', args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'receiptId={rid} (query receipt', result.stderr)

    def test_task_done_refusal_follows_the_same_receipt_rule(self):
        rid = '66666666-6666-4666-8666-666666666667'
        args = ['task-done', '--from-id', 'WORKER', '--summary', 'Done.', '--receipt-id', rid]
        refused = dict(ok=False, error='terminal 1 has no live agent host. Nothing was queued',
                       receiptId=rid, receiptKnown=False)
        result, request = self.exchange(json.dumps(refused).encode() + b'\n', args)
        self.assertEqual(request['cmd'], 'task.done')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('has no live agent host', result.stderr)
        self.assertIn(f'no receipt {rid} exists', result.stderr)

    def test_unknown_transport_outcome_still_names_the_receipt(self):
        rid = '66666666-6666-4666-8666-666666666668'
        result, _ = self.exchange(b'', ['message', '--from', '1', '--to', '2', '--receipt-id', rid, 'hello'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f'receiptId={rid} (outcome unknown', result.stderr)
        self.assertIn('mutation outcome unknown', result.stderr)

    def test_receipt_waits_for_the_recipient_model_to_read(self):
        rid = '55555555-5555-4555-8555-555555555555'
        read = dict(ok=True, receiptId=rid, recorded=True, modelRead=True, readAt=1790406005000,
                    agentAcknowledged=False, deliveryState='read', waitSupported=True, waitUntil='read', waitSatisfied=True)
        result, request = self.exchange(json.dumps(read).encode() + b'\n', ['receipt', rid, '--wait', '30', '--until', 'read'])
        self.assertEqual(request, {'cmd': 'message.receipt', 'receiptId': rid, 'waitMs': 30000, 'waitUntil': 'read'})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['modelRead'], True)
        # Not read within the wait: nonzero, and it says the state and why.
        unread = dict(read, modelRead=False, readAt=None, deliveryState='recorded-awaiting-read', waitSatisfied=False,
                      timedOut=True, guidance='Recorded, not yet read: the recipient is in the middle of a step.')
        result, _ = self.exchange(json.dumps(unread).encode() + b'\n', ['receipt', rid, '--wait', '5', '--until', 'read'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('did not reach read', result.stderr)
        self.assertIn('recorded-awaiting-read', result.stderr)
        self.assertIn('middle of a step', result.stderr)

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

    def test_inspect_shape_checked_before_output(self):
        for text in [None, 42, {}, []]:
            result, _ = self.exchange(json.dumps({'ok': True, 'text': text}).encode() + b'\n',
                                      ['inspect', '--slot', '2'])
            self.assertIn('expected text string', result.stderr)
        result, _ = self.exchange(b'{"ok":false,"error":"not attached"}\n', ['inspect', '--slot', '2'])
        self.assertIn('not attached', result.stderr)

    def test_explicit_id_is_never_dropped_for_slot(self):
        for args, reply in [(['send', '--slot', '2', '--id', 'SESSION-A', 'hello'], b'{"ok":true}\n'),
                            (['inspect', '--slot', '2', '--id', 'SESSION-A'],
                             b'{"ok":true,"text":"hello"}\n')]:
            with self.subTest(cmd=args[0]):
                result, request = self.exchange(reply, args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(request.get('id'), 'SESSION-A')
                self.assertNotIn('slot', request)

    def test_committed_close_failure_says_the_close_happened(self):
        reply = {'ok': False, 'committed': True, 'closed': {'slot': 3, 'id': 'S3'},
                 'error': 'pane cleanup failed'}
        result, request = self.exchange(json.dumps(reply).encode() + b'\n',
                                        ['close', '--slot', '3', '--expected-id', 'S3', '--confirm'])
        self.assertEqual(request['expectedId'], 'S3')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('pane cleanup failed', result.stderr)
        self.assertIn('committed', result.stderr)
        self.assertIn('do not retry', result.stderr)

    def test_inspect_returns_plain_text_without_external_codec(self):
        result, request = self.exchange(b'{"ok":true,"text":"hello"}\n', ['inspect', '--slot', '2'])
        self.assertEqual(request, {'cmd': 'inspect', 'lines': 80, 'raw': False, 'slot': 2})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'hello\n')
