"""Client update tests (docs/updates.md): a local release server only, never the network."""
import builtins
import hashlib
import http.server
import importlib.machinery
import importlib.util
import io
import json
import os
import pty
import re
import select
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "clients" / "python" / "utp"
CLIENT_SOURCE = CLIENT.read_bytes()
CURRENT = re.search(rb'^CLIENT_VERSION = "([^"]+)"$', CLIENT_SOURCE, re.M).group(1).decode()
NEW = "2.99.0"
NEWER = "2.99.1"
SILENCING_ENV = ("CI", "CLAUDECODE", "UTP_NO_UPDATE_CHECK", "NO_COLOR")


def client_source(version):
    return CLIENT_SOURCE.replace(
        f'CLIENT_VERSION = "{CURRENT}"'.encode(), f'CLIENT_VERSION = "{version}"'.encode(), 1)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_client_module():
    loader = importlib.machinery.SourceFileLoader("utp_updates_under_test", str(CLIENT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class ReleaseHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.calls.append((self.path, dict(self.headers)))
        body = self.server.routes.get(self.path)
        self.send_response(200 if body is not None else 404)
        self.send_header("Content-Length", str(len(body or b"")))
        self.end_headers()
        self.wfile.write(body or b"")

    def log_message(self, format, *args):
        pass


class Terminal(io.StringIO):
    """A captured stream that reports itself as a terminal (or not)."""

    def __init__(self, tty=True):
        super().__init__()
        self.tty = tty

    def isatty(self):
        return self.tty


class UpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_client_module()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir="/tmp", prefix="utpu-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ReleaseHandler)
        self.server.routes, self.server.calls = self.release(NEW), []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        base = f"http://127.0.0.1:{self.server.server_port}"
        self.env = {key: value for key, value in os.environ.items() if key not in SILENCING_ENV}
        self.env.update({
            "HOME": str(self.home), "XDG_CACHE_HOME": str(self.home / ".cache"), "TERM": "dumb",
            "UTP_UPDATE_API": base + "/release", "UTP_UPDATE_DOWNLOAD": base,
        })
        patcher = mock.patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        # In-process checks act as a standalone copy (this checkout itself is a git clone).
        standalone = mock.patch.object(self.module, "current_client",
                                       return_value=str(self.home / "utp"))
        standalone.start()
        self.addCleanup(standalone.stop)
        self.cache = Path(self.module.update_dir())
        self.assertTrue(str(self.cache).startswith(str(self.home)))

    # -- fixtures ---------------------------------------------------------------

    def release(self, version, source=None, sums=None, **record):
        source = client_source(version) if source is None else source
        sums = f"{sha256(source)}  clients/python/utp\n".encode() if sums is None else sums
        body = {"tag_name": "v" + version, "draft": False, "prerelease": False,
                "body": "First note.\n\n\x1b[31mSecond note.\n", **record}
        return {
            "/release": json.dumps(body).encode(),
            f"/v{version}/clients/python/utp": source,
            f"/v{version}/clients/python/SHA256SUMS": sums,
        }

    def client_copy(self, *parts):
        target = self.home.joinpath(*(parts or ("utp",)))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CLIENT, target)
        target.chmod(0o755)
        return target

    def install_dir(self):
        """Files beside the client copy, ignoring the platform cache root."""
        cache_root = self.cache.relative_to(self.home).parts[0]
        return sorted(path.name for path in self.home.iterdir() if path.name != cache_root)

    def state(self):
        return self.module.load_update_state()

    def save_state(self, **values):
        self.module.save_update_state({**self.module.UPDATE_DEFAULTS, **values})

    def run_client(self, target, *args, env=None):
        return subprocess.run([sys.executable, str(target), *args], env={**self.env, **(env or {})},
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)

    def run_on_terminals(self, target, *args):
        """Run with stdout and stderr on two separate pseudo-terminals."""
        out_master, out_slave = pty.openpty()
        err_master, err_slave = pty.openpty()
        try:
            process = subprocess.Popen([sys.executable, str(target), *args], env=self.env,
                                       stdin=subprocess.DEVNULL, stdout=out_slave, stderr=err_slave)
        finally:
            os.close(out_slave)
            os.close(err_slave)
        output = {out_master: b"", err_master: b""}
        open_fds, deadline = set(output), time.time() + 30
        while open_fds and time.time() < deadline:
            ready = select.select(list(open_fds), [], [], 0.2)[0]
            for fd in ready:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    chunk = b""
                output[fd] += chunk
                if not chunk:
                    open_fds.discard(fd)
            if not ready and process.poll() is not None:
                break
        process.wait(timeout=30)
        for fd in output:
            os.close(fd)
        text = [output[fd].decode().replace("\r\n", "\n") for fd in (out_master, err_master)]
        return process.returncode, text[0], text[1]

    def run_interactive(self, target, *args, answers=()):
        """Run on one pseudo-terminal, typing each answer when its prompt appears."""
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen([sys.executable, str(target), *args], env=self.env,
                                       stdin=slave, stdout=slave, stderr=slave)
        finally:
            os.close(slave)
        output, pending, deadline = b"", list(answers), time.time() + 30
        while time.time() < deadline:
            if select.select([master], [], [], 0.2)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    chunk = b""
                if not chunk:
                    break
                output += chunk
                if pending and output.rstrip().endswith(pending[0][0].encode()):
                    os.write(master, pending.pop(0)[1].encode())
            elif process.poll() is not None:
                break
        process.wait(timeout=30)
        os.close(master)
        return process.returncode, output.decode().replace("\r\n", "\n")

    def background_check(self, stdout=True, stderr=True):
        """The in-process path that runs around every non-update command."""
        out, err = Terminal(stdout), Terminal(stderr)
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            pending = self.module.start_update_check()
            if pending:
                self.module.finish_update_check(pending)
        return pending, out.getvalue(), err.getvalue()

    def notice(self, latest=NEW):
        return (f"utp {latest} available (you have {CURRENT}) · run: utp update\n"
                "turn on automatic updates: utp update --auto on · skip: utp update --skip\n")

    # -- contract §5 ------------------------------------------------------------

    def test_version_comparison(self):
        for candidate, expected in (
            (NEW, True), ("v" + NEW, True), (CURRENT, False), ("v" + CURRENT, False),
            ("0.0.1", False), ("garbage", False), (NEW + "-rc1", False), (NEW + ".1", False),
            ("", False), (None, False),
        ):
            with self.subTest(candidate=candidate):
                self.assertEqual(self.module.is_newer(candidate), expected)
        self.assertTrue(self.module.is_newer("2.10.0", "2.9.9"), "numeric, not lexical")

    def test_release_record_is_one_anonymous_get_of_stable_releases(self):
        for record, expected in (
            ({}, NEW), ({"prerelease": True}, None), ({"draft": True}, None),
            ({"tag_name": "v3.0.0-beta.1"}, None), ({"tag_name": "nightly"}, None),
        ):
            with self.subTest(record=record):
                self.server.routes = self.release(NEW, **record)
                self.assertEqual(self.module.fetch_latest_release()[0], expected)
        path, headers = self.server.calls[0]
        self.assertEqual(path, "/release")
        self.assertEqual(headers["User-Agent"], "utp-update-check")
        self.assertLessEqual({name.lower() for name in headers},
                             {"host", "user-agent", "accept", "accept-encoding", "connection"})

    def test_daily_cache_and_recorded_failure(self):
        self.background_check()
        self.assertEqual(len(self.server.calls), 1)
        self.background_check()
        self.assertEqual(len(self.server.calls), 1, "a second check within 24 h stays local")
        self.save_state(**{**self.state(), "checkedAt": int(time.time()) - 25 * 3600})
        self.background_check()
        self.assertEqual(len(self.server.calls), 2)

        os.environ["UTP_UPDATE_API"] = "http://127.0.0.1:9/release"
        self.save_state(**{**self.state(), "checkedAt": 0})
        self.assertEqual(self.background_check()[1:], ("", ""), "a failure is never printed")
        self.assertIn("URLError", self.state()["error"])
        failed = self.run_client(self.client_copy(), "update", "--check",
                                 env={"UTP_UPDATE_API": "http://127.0.0.1:9/release"})
        self.assertEqual(failed.returncode, 1)
        self.assertIn("check failed: URLError", failed.stderr)

    def test_one_private_state_file(self):
        self.background_check()
        self.assertEqual(sorted(path.name for path in self.cache.iterdir()), ["update.json"])
        self.assertEqual(stat.S_IMODE(self.cache.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.cache / "update.json").stat().st_mode), 0o600)
        self.assertEqual(set(json.loads((self.cache / "update.json").read_text())),
                         set(self.module.UPDATE_DEFAULTS))

    def test_silent_off_a_terminal_in_ci_under_agents_and_when_opted_out(self):
        for overrides in ({"CI": "true"}, {"CLAUDECODE": "1"}, {"UTP_NO_UPDATE_CHECK": "1"}):
            with self.subTest(overrides=overrides), mock.patch.dict(os.environ, overrides):
                self.assertEqual(self.background_check(), (None, "", ""))
        for stdout, stderr in ((False, True), (True, False)):
            self.assertEqual(self.background_check(stdout, stderr), (None, "", ""))
        self.save_state(checks=False)
        self.assertEqual(self.background_check()[1:], ("", ""))
        self.assertEqual(self.server.calls, [])
        shutil.rmtree(self.cache)

        piped = self.run_client(self.client_copy(), "--version")
        self.assertEqual((piped.returncode, piped.stdout, piped.stderr), (0, CURRENT + "\n", ""))
        self.assertEqual(self.server.calls, [])
        self.assertFalse(self.cache.exists(), "a silenced run writes nothing")

    def test_notice_follows_json_output_on_stderr_once_per_day(self):
        socket_dir = self.home / ".ultraterm"
        socket_dir.mkdir(mode=0o700)
        reply = {"ok": True, "protocolVersion": "2.2.0", "wireVersion": 2}

        def serve_once():
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(str(socket_dir / "utp.sock"))
                listener.listen(1)
                connection, _ = listener.accept()
                with connection:
                    connection.recv(65536)
                    connection.sendall((json.dumps(reply) + "\n").encode())

        threading.Thread(target=serve_once, daemon=True).start()
        target = self.client_copy()
        for _ in range(50):
            if (socket_dir / "utp.sock").exists():
                break
            time.sleep(0.02)
        code, out, err = self.run_on_terminals(target, "diagnose")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), reply, "stdout stays pure JSON Lines")
        self.assertEqual(err, self.notice())
        self.assertEqual(self.run_on_terminals(target, "--version"), (0, CURRENT + "\n", ""),
                         "the same version is not announced twice within 24 h")
        self.assertEqual(len(self.server.calls), 1)

    def test_skip_hides_only_that_version(self):
        self.background_check()
        skipped = self.run_client(self.client_copy(), "update", "--skip")
        self.assertEqual(skipped.returncode, 0, skipped.stderr)
        self.assertEqual(skipped.stdout, f"utp {NEW} skipped; a newer release will notify again\n")
        self.assertEqual(len(self.server.calls), 1, "--skip reuses the version the notice showed")
        self.save_state(**{**self.state(), "notifiedAt": 0})
        self.assertEqual(self.background_check()[2], "")
        self.server.routes = self.release(NEWER)
        self.save_state(**{**self.state(), "checkedAt": 0})
        self.assertEqual(self.background_check()[2], self.notice(NEWER))

    def test_check_exit_codes(self):
        target = self.client_copy()
        available = self.run_client(target, "update", "--check")
        self.assertEqual(available.returncode, 10, available.stderr)
        self.assertEqual(available.stdout,
                         f"utp {CURRENT} → {NEW}\n  First note.\n  [31mSecond note.\n")
        self.server.routes = self.release(CURRENT)
        current = self.run_client(target, "update", "--check")
        self.assertEqual((current.returncode, current.stdout), (0, f"utp {CURRENT} is current\n"))
        self.server.routes = {"/release": b"{not json"}
        broken = self.run_client(target, "update", "--check")
        self.assertEqual(broken.returncode, 1)
        self.assertIn("check failed: JSONDecodeError", broken.stderr)
        self.assertEqual(self.run_client(target, "update").returncode, 1)

    def test_auto_is_off_by_default_persists_and_off_removes_state(self):
        target = self.client_copy()
        status = self.run_client(target, "update", "--auto", "status")
        self.assertEqual(status.stdout, "automatic updates: off\n")
        self.assertFalse(self.cache.exists(), "status alone writes nothing")
        self.assertEqual(self.run_client(target, "update", "--auto", "on").stdout,
                         "automatic updates: on\n")
        self.assertTrue(self.state()["auto"])
        self.assertEqual(self.run_client(target, "update", "--auto", "status").stdout,
                         "automatic updates: on\n")
        self.module.log_update("one line")
        self.assertEqual(self.run_client(target, "update", "--checks", "off").stdout,
                         "update checks: off\n")
        off = self.run_client(target, "update", "--auto", "off")
        self.assertEqual(off.stdout, "automatic updates: off; update state removed\n")
        self.assertEqual(sorted(path.name for path in self.cache.iterdir()), ["update.json"],
                         "only the checks-off choice survives")
        self.assertEqual((self.state()["auto"], self.state()["checks"]), (False, False))
        self.run_client(target, "update", "--checks", "on")
        self.run_client(target, "update", "--auto", "off")
        self.assertFalse(self.cache.exists(), "--auto off before uninstall leaves nothing")

    def test_install_question_defaults(self):
        for answer, default, expected in (
            ("", True, True), ("n", True, False), ("", False, False), ("y", False, True),
            ("yes", False, True), (EOFError, False, False), (EOFError, True, False),
        ):
            with self.subTest(answer=answer, default=default):
                reply = mock.Mock(side_effect=answer) if answer is EOFError else mock.Mock(
                    return_value=answer)
                with mock.patch.object(builtins, "input", reply), \
                        mock.patch.object(sys, "stderr", io.StringIO()):
                    self.assertEqual(self.module.ask("? ", default), expected)

    def test_interactive_update_asks_first_and_offers_automatic_updates_once(self):
        target = self.client_copy()
        code, text = self.run_interactive(target, "update", answers=[("[Y/n]", "n\n")])
        self.assertEqual(code, 0, text)
        self.assertEqual(target.read_bytes(), CLIENT_SOURCE, "declined: nothing changes")
        code, text = self.run_interactive(target, "update",
                                          answers=[("[Y/n]", "\n"), ("[y/N]", "n\n")])
        self.assertEqual(code, 0, text)
        self.assertIn(f"utp {CURRENT} → {NEW}\n  First note.", text)
        self.assertIn("Install future updates automatically? [y/N]", text)
        self.assertEqual(target.read_bytes(), client_source(NEW))
        self.assertEqual((self.state()["auto"], self.state()["autoAsked"]), (False, True))
        self.server.routes = self.release(NEWER)
        code, text = self.run_interactive(target, "update", answers=[("[Y/n]", "y\n")])
        self.assertEqual(code, 0, text)
        self.assertNotIn("[y/N]", text, "never asked again after no")
        self.assertEqual(target.read_bytes(), client_source(NEWER))

    # -- install safety -----------------------------------------------------------

    def test_verified_install_rollback_and_rollback_cleanup(self):
        target = self.client_copy()
        installed = self.run_client(target, "update")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertIn(f"installed utp {NEW}; undo with: utp update --rollback", installed.stdout)
        self.assertNotIn("[y/N]", installed.stdout, "no questions off a terminal")
        self.assertEqual(target.read_bytes(), client_source(NEW))
        self.assertTrue(os.access(target, os.X_OK))
        previous = Path(str(target) + ".previous")
        self.assertEqual(previous.read_bytes(), CLIENT_SOURCE)
        self.assertEqual(self.install_dir(), ["utp", "utp.previous"],
                         "the download directory is gone")

        restored = self.run_client(target, "update", "--rollback")
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(restored.stdout, f"restored the previous client; utp {NEW} is skipped\n")
        self.assertEqual(target.read_bytes(), CLIENT_SOURCE)
        self.assertFalse(previous.exists())
        self.assertEqual(self.state()["skip"], NEW, "no automatic reinstall of a rolled-back version")

        self.assertEqual(self.run_client(target, "update").returncode, 0)
        self.assertEqual(self.run_client(target, "--version").stdout, NEW + "\n")
        self.assertFalse(previous.exists(), "the first good run of the new client drops it")

    def test_unverified_downloads_are_refused_before_any_swap(self):
        target = self.client_copy()
        wrong = client_source(NEW)
        for name, routes, cause in (
            ("mismatch", self.release(NEW, sums=b"0" * 64 + b"  clients/python/utp\n"),
             "checksum mismatch"),
            ("no entry", self.release(NEW, sums=sha256(wrong).encode() + b"  other\n"),
             "SHA256SUMS has no entry for utp"),
            ("missing sums", {**self.release(NEW), f"/v{NEW}/clients/python/SHA256SUMS": None},
             "HTTPError"),
            ("wrong version", self.release(NEW, source=client_source(NEWER)),
             f"the downloaded client is not version {NEW}"),
        ):
            with self.subTest(name):
                self.server.routes = {path: body for path, body in routes.items() if body}
                result = self.run_client(target, "update")
                self.assertEqual(result.returncode, 1)
                self.assertIn(cause, result.stderr)
                self.assertIn("the installed client is unchanged", result.stderr)
                self.assertEqual(target.read_bytes(), CLIENT_SOURCE)
                self.assertEqual(self.install_dir(), ["utp"], "no rollback, no temporary files")

    def test_failed_swap_keeps_the_client_and_removes_temporary_files(self):
        target = self.client_copy()
        real_replace = os.replace

        def failing_replace(source, destination):
            if os.fspath(destination) == str(target):
                raise OSError("disk full")
            return real_replace(source, destination)

        with mock.patch.object(self.module.os, "replace", side_effect=failing_replace):
            with self.assertRaises(OSError):
                self.module.install_client(NEW, str(target))
        self.assertEqual(target.read_bytes(), CLIENT_SOURCE)
        self.assertEqual(list(self.home.glob("utp-update-*")), [])

    def test_rollback_expires_after_a_good_run_or_seven_days(self):
        target = self.client_copy()
        previous = Path(str(target) + ".previous")
        with mock.patch.object(self.module, "current_client", return_value=str(target)):
            previous.write_bytes(CLIENT_SOURCE)
            self.module.remove_rollback(after_success=True)
            self.assertTrue(previous.exists(), "an install during this run keeps its rollback")
            before = self.module.PROCESS_STARTED - 60
            os.utime(previous, (before, before))
            self.module.remove_rollback(after_success=False)
            self.assertTrue(previous.exists(), "a failing run keeps it")
            self.module.remove_rollback(after_success=True)
            self.assertFalse(previous.exists())
            previous.write_bytes(CLIENT_SOURCE)
            old = time.time() - 8 * 24 * 3600
            os.utime(previous, (old, old))
            self.module.remove_rollback(after_success=False)
            self.assertFalse(previous.exists(), "never kept beyond seven days")

    def test_automatic_install_and_fallback_to_the_notice(self):
        self.save_state(auto=True)
        with mock.patch.object(self.module, "start_auto_install") as start:
            self.assertEqual(self.background_check()[1:], ("", ""))
        start.assert_called_once_with()

        target = self.client_copy()
        self.server.routes = self.release(NEW, sums=b"0" * 64 + b"  utp\n")
        self.assertEqual(self.run_client(target, "update", "--auto-install").returncode, 1)
        self.assertEqual(target.read_bytes(), CLIENT_SOURCE)
        state = self.state()
        self.assertEqual((state["installFailed"], state["installError"]),
                         (NEW, "UpdateError: checksum mismatch"))
        self.assertIn(f"automatic install of utp {NEW} failed: UpdateError: checksum mismatch",
                      (self.cache / "update.log").read_text())
        status = self.run_client(target, "update", "--auto", "status").stdout
        self.assertIn("last automatic install failed: UpdateError: checksum mismatch", status)
        with mock.patch.object(self.module, "start_auto_install") as start:
            self.assertEqual(self.background_check()[2], self.notice())
        start.assert_not_called()

        self.server.routes = self.release(NEW)
        self.assertEqual(self.run_client(target, "update", "--auto-install").returncode, 0)
        self.assertEqual(target.read_bytes(), client_source(NEW))
        self.assertIn(f"installed utp {NEW}", (self.cache / "update.log").read_text())

    def test_update_log_is_bounded(self):
        limit = self.module.UPDATE_LOG_LIMIT
        self.assertLessEqual(limit, 256 * 1024)
        self.cache.mkdir(parents=True)
        (self.cache / "update.log").write_bytes(b"x" * (limit + 4096))
        for index in range(3):
            self.module.log_update(f"line {index}")
        data = (self.cache / "update.log").read_bytes()
        self.assertLessEqual(len(data), limit)
        self.assertTrue(data.endswith(b" line 2\n"))
        self.assertEqual(sorted(path.name for path in self.cache.iterdir()), ["update.log"])

    def test_git_checkouts_pull_instead_of_overwriting(self):
        target = self.client_copy("src", "utp-checkout", "clients", "python", "utp")
        checkout = target.parents[2]
        (checkout / ".git").mkdir()
        tools = self.home / "bin"
        tools.mkdir()
        (tools / "git").write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$HOME/git-args"\n')
        (tools / "git").chmod(0o755)
        manager = self.module.client_manager(str(target))
        first, second = self.module.update_notice(NEW, manager)
        self.assertTrue(first.endswith(f"run: git -C {checkout} pull --ff-only"))
        self.assertEqual(second, "skip: utp update --skip")
        result = self.run_client(target, "update",
                                 env={"PATH": f"{tools}{os.pathsep}{self.env.get('PATH', '')}"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home / "git-args").read_text().split(),
                         ["-C", str(checkout), "pull", "--ff-only"])
        self.assertEqual(target.read_bytes(), CLIENT_SOURCE)
        self.assertFalse(Path(str(target) + ".previous").exists())

    def test_ultraterm_managed_copy_updates_with_the_app(self):
        target = self.client_copy(".ultraterm", "bin", "utp")
        result = self.run_client(target, "update")
        self.assertEqual(result.returncode, 1)
        self.assertIn("managed by UltraTerm; update UltraTerm instead", result.stderr)
        self.assertEqual(target.read_bytes(), CLIENT_SOURCE)
        with mock.patch.object(self.module, "current_client", return_value=str(target)):
            self.assertEqual(self.background_check(), (None, "", ""))

    def test_committed_checksum_matches_the_client(self):
        sums = (CLIENT.parent / "SHA256SUMS").read_text().split()
        self.assertEqual(sums, [sha256(CLIENT_SOURCE), "clients/python/utp"],
                         "regenerate clients/python/SHA256SUMS (see docs/updates.md)")


if __name__ == "__main__":
    unittest.main()
