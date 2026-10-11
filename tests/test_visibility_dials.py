"""Profile visibility and usage-dial commands against private disposable Unix sockets; never the app socket."""
import json
import os
import socket
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1] / 'clients/python/utp'


def dial(dial_id, enabled, kind='http', order=0, name=None):
    # Shaped like the server's dials: a built-in names itself as its provider, an http dial has an endpoint and windows.
    extra = dict(builtinProvider=dial_id, endpoint=None, windows=[]) if kind == 'builtin' else dict(
        builtinProvider=None, endpoint='https://usage.example.invalid/v1', windows=[{'label': 'primary'}],
        credentialRef=None, authHeader=None, authScheme=None)
    return dict(id=dial_id, name=name or dial_id.title(), enabled=enabled, kind=kind, order=order, **extra)


def catalog(revision, *dials):
    return dict(ok=True, catalog=dict(schemaVersion=1, revision=revision, dials=list(dials)))


class VisibilityAndDialTests(unittest.TestCase):
    def run_cli(self, replies, args):
        """Serve one reply per connection, in order; return the result and the requests received.

        A reply of None accepts the connection, reads the request and closes without answering; a str reply is sent raw.
        With no replies scripted, the server still listens and records any connection as an error.
        """
        requests, errors, accepted = [], [], []
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / '.ultraterm'
            path.mkdir()
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(str(path / 'utp.sock'))
                server.listen(8)
                server.settimeout(3)

                def serve():
                    try:
                        if not replies:
                            try:
                                conn, _ = server.accept()
                            except socket.timeout:
                                return
                            conn.close()
                            accepted.append(True)
                            errors.append(AssertionError('client connected although no request was expected'))
                            return
                        for reply in replies:
                            conn, _ = server.accept()
                            accepted.append(True)
                            with conn:
                                data = b''
                                while not data.endswith(b'\n'):
                                    data += conn.recv(65536)
                                requests.append(json.loads(data))
                                if isinstance(reply, str):
                                    conn.sendall(reply.encode())
                                elif reply is not None:
                                    conn.sendall(json.dumps(reply).encode() + b'\n')
                    except Exception as exc:
                        errors.append(exc)

                thread = threading.Thread(target=serve)
                thread.start()
                env = {**os.environ, 'HOME': home, 'TMUX_PANE': ''}
                result = subprocess.run([str(CLIENT), *args], env=env, capture_output=True, text=True, timeout=14)
                thread.join(4)
                self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertNotIn('Traceback', result.stderr)
        self.last_accepted = len(accepted)
        return result, requests

    def test_hidden_lists_sorted_keys_or_says_none(self):
        # Sorted by the 'harness/profile' text: '-' sorts before '/', so pi-a/x comes before pi/x.
        reply = dict(ok=True, hidden=[dict(harnessId='steak-pi', profileId='b'), dict(harnessId='pi', profileId='x'),
                                      dict(harnessId='pi-a', profileId='x'), dict(harnessId='pi', profileId='a')])
        result, requests = self.run_cli([reply], ['profiles', 'hidden'])
        self.assertEqual(requests, [{'cmd': 'profiles.visibility', 'action': 'list'}])
        self.assertEqual(result.stdout.split(), ['pi-a/x', 'pi/a', 'pi/x', 'steak-pi/b'])
        result, _ = self.run_cli([dict(ok=True, hidden=[])], ['profiles', 'hidden'])
        self.assertEqual(result.returncode, 0)
        self.assertIn('no hidden profiles', result.stderr)

    def test_hide_is_a_dry_run_until_confirmed(self):
        plan = dict(ok=True, confirmed=False, hidden=[],
                    would=dict(action='hide', harnessId='steak-pi', profile='mimo', change=True))
        result, requests = self.run_cli([plan], ['profiles', 'hide', 'steak-pi/mimo'])
        self.assertEqual(requests, [dict(cmd='profiles.visibility', action='hide', harnessId='steak-pi',
                                         profile='mimo', confirm=False)])
        self.assertIn('would hide steak-pi/mimo; dry run, re-run with --confirm to apply', result.stdout)
        done = dict(ok=True, confirmed=True, action='hide', harnessId='steak-pi', profile='mimo', changed=True,
                    hidden=[dict(harnessId='steak-pi', profileId='mimo')])
        result, requests = self.run_cli([done], ['profiles', 'hide', 'steak-pi/mimo', '--confirm'])
        self.assertEqual(requests[0]['confirm'], True)
        self.assertIn('hidden steak-pi/mimo', result.stdout)

    def test_show_reports_when_nothing_changes(self):
        plan = dict(ok=True, confirmed=False, hidden=[],
                    would=dict(action='show', harnessId='pi', profile='x', change=False))
        result, _ = self.run_cli([plan], ['profiles', 'show', 'pi/x'])
        self.assertIn('pi/x is already shown; dry run, nothing to change', result.stdout)
        done = dict(ok=True, confirmed=True, action='show', harnessId='pi', profile='x', changed=False, hidden=[])
        result, requests = self.run_cli([done], ['profiles', 'show', 'pi/x', '--confirm'])
        self.assertEqual(requests, [dict(cmd='profiles.visibility', action='show', harnessId='pi', profile='x',
                                         confirm=True)])
        self.assertIn('pi/x was already shown', result.stdout)

    def test_hide_dry_run_notes_an_already_hidden_profile(self):
        plan = dict(ok=True, confirmed=False, hidden=[dict(harnessId='pi', profileId='x')],
                    would=dict(action='hide', harnessId='pi', profile='x', change=False))
        result, _ = self.run_cli([plan], ['profiles', 'hide', 'pi/x'])
        self.assertIn('pi/x is already hidden; dry run, nothing to change', result.stdout)

    def test_bad_target_is_refused_before_anything_is_sent(self):
        for target in ['pi', 'pi/', '/x', 'Pi/x', 'pi/-x', 'pi/x y']:
            result, requests = self.run_cli([], ['profiles', 'hide', target])
            self.assertNotEqual(result.returncode, 0, target)
            self.assertIn('HiddenProfileError', result.stderr)
            # run_cli records any connection as an error; this count is a second, explicit check.
            self.assertEqual(self.last_accepted, 0, target)

    def test_read_only_and_unknown_outcome_wording(self):
        result, _ = self.run_cli([None], ['profiles', 'hidden'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('read-only request failed', result.stderr)
        self.assertNotIn('mutation outcome unknown', result.stderr)
        result, _ = self.run_cli([None], ['profiles', 'hide', 'pi/x'])
        self.assertIn('read-only request failed', result.stderr)
        self.assertNotIn('mutation outcome unknown', result.stderr)
        result, _ = self.run_cli([None], ['profiles', 'show', 'pi/x', '--confirm'])
        self.assertIn('mutation outcome unknown', result.stderr)
        self.assertNotIn('read-only request failed', result.stderr)
        result, _ = self.run_cli([None], ['profiles', 'hide', 'pi/x', '--confirm'])
        self.assertIn('mutation outcome unknown', result.stderr)
        self.assertNotIn('read-only request failed', result.stderr)
        result, _ = self.run_cli([None], ['dials', 'list'])
        self.assertIn('read-only request failed', result.stderr)
        self.assertNotIn('mutation outcome unknown', result.stderr)
        result, requests = self.run_cli([None], ['dials', 'enable', 'acme'])
        self.assertIn('read-only request failed', result.stderr)
        self.assertEqual(len(requests), 1)
        self.assertNotIn('mutation outcome unknown', result.stderr)
        result, requests = self.run_cli([catalog(1, dial('acme', True)), None],
                                        ['dials', 'disable', 'acme', '--confirm'])
        self.assertEqual(requests[1]['action'], 'upsert')
        self.assertIn('mutation outcome unknown', result.stderr)
        self.assertNotIn('read-only request failed', result.stderr)
        result, requests = self.run_cli([None], ['dials', 'enable', 'acme', '--confirm'])
        self.assertIn('read-only request failed', result.stderr)
        self.assertEqual(requests[0]['action'], 'list')
        self.assertNotIn('mutation outcome unknown', result.stderr)
        result, _ = self.run_cli([catalog(1, dial('acme', False)), None],
                                 ['dials', 'enable', 'acme', '--confirm'])
        self.assertIn('mutation outcome unknown', result.stderr)
        self.assertNotIn('read-only request failed', result.stderr)
        result, _ = self.run_cli([catalog(1, dial('acme', False)), dict(ok=True)],
                                 ['dials', 'enable', 'acme', '--confirm'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('malformed dial catalog reply', result.stderr)
        self.assertNotIn('dial acme enabled', result.stdout)

    def test_truncated_and_malformed_replies_keep_the_outcome_wording(self):
        result, requests = self.run_cli(['{"ok": tr'], ['profiles', 'hidden'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('truncated reply', result.stderr)
        self.assertIn('read-only request failed', result.stderr)
        self.assertEqual(len(requests), 1)
        result, requests = self.run_cli(['not json\n'], ['profiles', 'hide', 'pi/x', '--confirm'])
        self.assertIn('malformed JSON reply', result.stderr)
        self.assertIn('mutation outcome unknown', result.stderr)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['confirm'], True)

    def test_server_refusal_is_reported(self):
        error = 'at most 128 profiles can be hidden'
        result, _ = self.run_cli([dict(ok=False, error=error)], ['profiles', 'hide', 'pi/x'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(error, result.stderr)

    def test_dials_list_is_ordered(self):
        # Sorting by order must differ from sorting by id, and the order=1 tie must break by id.
        reply = catalog(4, dial('beta', True, 'builtin', 1, 'Beta'), dial('zeta', False, order=0, name='Zeta'),
                        dial('alpha', True, 'builtin', 1, 'Alpha'))
        result, requests = self.run_cli([reply], ['dials', 'list'])
        self.assertEqual(requests, [{'cmd': 'provider.dials', 'action': 'list'}])
        self.assertEqual(result.stdout.splitlines(), ['zeta\tdisabled\thttp\t0\tZeta',
                                                      'alpha\tenabled\tbuiltin\t1\tAlpha',
                                                      'beta\tenabled\tbuiltin\t1\tBeta'])

    def test_dial_toggle_dry_run_then_confirmed_upsert_keeps_the_dial(self):
        current = dial('acme', False, order=3)
        result, requests = self.run_cli([catalog(7, current)], ['dials', 'enable', 'acme'])
        self.assertEqual(len(requests), 1)
        self.assertIn('would enable dial acme; dry run, re-run with --confirm to apply', result.stdout)
        result, requests = self.run_cli([catalog(7, current), catalog(8, dial('acme', True, order=3))],
                                        ['dials', 'enable', 'acme', '--confirm'])
        self.assertEqual(requests[1], dict(cmd='provider.dials', action='upsert',
                                           config={**current, 'enabled': True}, expectedRevision=7))
        self.assertIn('dial acme enabled', result.stdout)
        enabled = dial('acme', True, order=3)
        result, requests = self.run_cli([catalog(7, enabled), catalog(8, dial('acme', False, order=3))],
                                        ['dials', 'disable', 'acme', '--confirm'])
        self.assertEqual(requests[1], dict(cmd='provider.dials', action='upsert',
                                           config={**enabled, 'enabled': False}, expectedRevision=7))
        self.assertIn('dial acme disabled', result.stdout)

    def test_dial_toggle_noop_unknown_and_conflict(self):
        result, requests = self.run_cli([catalog(1, dial('acme', True))], ['dials', 'enable', 'acme', '--confirm'])
        self.assertEqual(len(requests), 1)
        self.assertIn('already enabled', result.stdout)
        result, _ = self.run_cli([catalog(1, dial('acme', True))], ['dials', 'disable', 'nope'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no dial with that id', result.stderr)
        conflict = dict(ok=False, error='Dial revision conflict; reload and retry')
        result, _ = self.run_cli([catalog(1, dial('acme', True)), conflict], ['dials', 'disable', 'acme', '--confirm'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DialRevisionConflictError', result.stderr)
        self.assertIn('nothing was changed', result.stderr)

    def test_malformed_catalog_is_rejected(self):
        cases = [
            (dict(ok=True, catalog=dict(revision='1', dials=[])), 'malformed dial catalog reply'),
            (catalog(2 ** 64, dial('a', True)), 'malformed dial catalog reply'),
            (catalog(1, dict(id='a', name='A', enabled='yes', kind='http', order=0)), 'malformed dial in catalog reply'),
            (catalog(1, dial('a', True), dial('a', False)), 'malformed dial in catalog reply'),
            (catalog(1, dial('a', True, kind='plugin')), 'malformed dial in catalog reply'),
            (catalog(1, dial('x' * 65, True)), 'malformed dial in catalog reply'),
        ]
        for bad, message in cases:
            result, _ = self.run_cli([bad], ['dials', 'list'])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(message, result.stderr)
            self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
