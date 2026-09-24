#!/usr/bin/env python3
"""Focused regression tests for the canonical `utp handoff` CLI composition.

Covers the new-slot handoff cleanup contract:
  * a pre-submit failure (readiness timeout, registration failure) closes the
    pane this handoff opened, bound to the session ID it opened;
  * an attempted-but-unconfirmed packet submission never closes the worker,
    because the packet may already be in the PTY;
  * submission is pinned to the captured session ID for both new-slot and
    in-place flows.

Every test runs `utp.main()` against a scripted Unix-socket server, so only the
canonical client and its JSON Lines transport are exercised; no live app, no
network, no HOME state.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

CLI = Path(__file__).resolve().parents[1] / "clients" / "python" / "utp"
LOADER = importlib.machinery.SourceFileLoader("utp_cli", str(CLI))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
UTP = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(UTP)

MANAGER = {"slot": 1, "id": "manager-id"}
WORKER = {"slot": 2, "id": "worker-id"}
IN_PLACE_WORKER = {"slot": 2, "id": "worker-old"}


def by_command(replies: dict, special: dict | None = None):
    """Scripted server handler: reply by request cmd, with per-cmd specials first.

    A reply value is one of: dict (JSON reply), None (close without a reply),
    ("stall", seconds) (hold the connection open past the client deadline).
    """
    queues = {cmd: list(values) for cmd, values in (special or {}).items()}

    def handler(request: dict, _index: int):
        cmd = request.get("cmd")
        queued = queues.get(cmd)
        if queued:
            return queued.pop(0)
        if cmd in replies:
            return replies[cmd]
        raise AssertionError(f"unexpected request: {request}")

    return handler


class ScriptedServer:
    """One-shot-per-connection Unix-socket server that records every request."""

    def __init__(self, handler):
        self.handler = handler
        self.requests: list[dict] = []
        self.root = tempfile.mkdtemp(dir=tempfile.gettempdir())
        self.path = os.path.join(self.root, "utp.sock")
        self._stop = False
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener.bind(self.path)
        self._listener.listen(16)
        self._listener.settimeout(0.2)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop:
            try:
                connection, _ = self._listener.accept()
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(5)
                payload = b""
                while b"\n" not in payload:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    payload += chunk
                if b"\n" not in payload:
                    continue
                request = json.loads(payload.split(b"\n", 1)[0])
                reply = self.handler(request, len(self.requests))
                self.requests.append(request)
                if reply is None:
                    continue
                if isinstance(reply, tuple) and reply and reply[0] == "stall":
                    time.sleep(reply[1])
                    continue
                connection.sendall(json.dumps(reply).encode() + b"\n")

    def close(self) -> None:
        self._stop = True
        self._thread.join(timeout=5)
        self._listener.close()

    def commands(self) -> list[str]:
        return [request.get("cmd") for request in self.requests]

    def last(self, cmd: str) -> dict:
        for request in reversed(self.requests):
            if request.get("cmd") == cmd:
                return request
        raise AssertionError(f"no {cmd} request in {self.commands()}")


class ClockStub:
    """Real monotonic clock with sleeps removed (readiness polling is 60 rounds)."""

    def __init__(self) -> None:
        self._real = time

    def monotonic(self) -> float:
        return self._real.monotonic()

    def sleep(self, _seconds: float) -> None:
        return None


class HandoffCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=tempfile.gettempdir())
        self.root = Path(self.temporary.name)
        self.packet = self.root / "handoff.md"
        self.packet.write_text("# Goal\nContinue the verified task.\n")
        self.packet.chmod(0o600)
        self.server: ScriptedServer | None = None
        self.environment = mock.patch.dict(
            os.environ, {"ULTRATERM_SLOT": ""}, clear=False
        )
        patched = self.environment.start()
        patched.pop("TMUX_PANE", None)
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.temporary.cleanup)

    def start(self, handler) -> ScriptedServer:
        self.server = ScriptedServer(handler)
        self.addCleanup(self.server.close)
        self.socket_patch = mock.patch.object(UTP, "SOCKET_PATH", self.server.path)
        self.socket_patch.start()
        self.addCleanup(self.socket_patch.stop)
        return self.server

    def run_cli(self, args: list[str], expect_exit: bool):
        argv = ["utp", *args]
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", argv), mock.patch.object(UTP, "time", ClockStub()):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                if not expect_exit:
                    UTP.main()
                    return None, stdout.getvalue(), stderr.getvalue()
                with self.assertRaises(SystemExit) as caught:
                    UTP.main()
        return caught.exception, stdout.getvalue(), stderr.getvalue()

    def handoff(self, *extra: str) -> list[str]:
        return [
            "handoff",
            "--profile",
            "quality",
            "--packet",
            str(self.packet),
            "--manager-slot",
            "1",
            "--confirm",
            "--user-authorized",
            *extra,
        ]

    # --- pre-submit failures close the pane this handoff opened ---------------

    def test_readiness_timeout_closes_the_opened_pane(self):
        server = self.start(
            by_command(
                {
                    "list": {"ok": True, "sessions": [MANAGER]},
                    "open": {"ok": True, "session": WORKER},
                    "inspect": {"ok": True, "text": ""},
                    "close": {"ok": True},
                }
            )
        )

        error, _, _ = self.run_cli(self.handoff("--new-slot"), expect_exit=True)

        self.assertIn("did not produce stable output", str(error))
        self.assertNotIn("register.manager", server.commands())
        self.assertNotIn("send", server.commands())
        self.assertEqual(
            server.last("close"),
            {"cmd": "close", "slot": 2, "expectedId": "worker-id", "confirm": True},
        )

    def test_registration_systemexit_closes_the_opened_pane(self):
        server = self.start(
            by_command(
                {
                    "list": {"ok": True, "sessions": [MANAGER]},
                    "open": {"ok": True, "session": WORKER},
                    "inspect": {"ok": True, "text": "ready"},
                    "register.manager": {"ok": False, "error": "no such session"},
                    "close": {"ok": True},
                }
            )
        )

        error, _, _ = self.run_cli(self.handoff("--new-slot"), expect_exit=True)

        self.assertIn("no such session", str(error))
        self.assertNotIn("send", server.commands())
        self.assertEqual(server.last("close")["expectedId"], "worker-id")

    def test_cleanup_failure_reports_and_preserves_the_original_error(self):
        self.start(
            by_command(
                {
                    "list": {"ok": True, "sessions": [MANAGER]},
                    "open": {"ok": True, "session": WORKER},
                    "inspect": {"ok": True, "text": ""},
                    "close": {"ok": False, "error": "target changed"},
                }
            )
        )

        error, _, stderr = self.run_cli(self.handoff("--new-slot"), expect_exit=True)

        self.assertIn("did not produce stable output", str(error))
        self.assertIn("cleanup failed for slot 2 (worker-id)", stderr)
        self.assertIn("target changed", stderr)

    def test_committed_cleanup_is_not_reported_as_failed(self):
        self.start(
            by_command(
                {
                    "list": {"ok": True, "sessions": [MANAGER]},
                    "open": {"ok": True, "session": WORKER},
                    "inspect": {"ok": True, "text": ""},
                    "close": {
                        "ok": False,
                        "committed": True,
                        "closed": WORKER,
                        "error": "pane cleanup failed",
                    },
                }
            )
        )

        error, _, stderr = self.run_cli(self.handoff("--new-slot"), expect_exit=True)

        self.assertIn("did not produce stable output", str(error))
        self.assertNotIn("cleanup failed for slot", stderr)
        self.assertIn("cleanup closed slot 2 (worker-id)", stderr)
        self.assertIn("pane cleanup failed", stderr)

    # --- identity-bound submission -------------------------------------------

    def test_new_slot_submission_is_pinned_to_the_opened_session_id(self):
        server = self.start(
            by_command(
                {
                    "list": {"ok": True, "sessions": [MANAGER]},
                    "open": {"ok": True, "session": WORKER},
                    "inspect": {"ok": True, "text": "ready"},
                    "register.manager": {"ok": True},
                    "send": {"ok": True},
                }
            )
        )

        error, stdout, _ = self.run_cli(self.handoff("--new-slot"), expect_exit=False)

        self.assertIsNone(error)
        self.assertIn("handoff submitted to worker slot 2", stdout)
        self.assertEqual(
            server.commands(),
            ["list", "open", "inspect", "inspect", "register.manager", "send"],
        )
        sent = server.last("send")
        self.assertEqual(sent["slot"], 2)
        self.assertEqual(sent["expectedId"], "worker-id")
        self.assertIn(str(self.packet), sent["text"])
        self.assertTrue(sent["enter"])

    def test_in_place_submission_is_pinned_to_the_replacement_session_id(self):
        server = self.start(
            by_command(
                {
                    "list": {"ok": True, "sessions": [MANAGER, IN_PLACE_WORKER]},
                    "profile.switch": {"ok": True, "session": {"slot": 2, "id": "worker-new"}},
                    "inspect": {"ok": True, "text": "ready"},
                    "register.manager": {"ok": True},
                    "send": {"ok": True},
                }
            )
        )

        error, stdout, _ = self.run_cli(
            self.handoff("--slot", "2", "--expected-id", "worker-old"), expect_exit=False
        )

        self.assertIsNone(error)
        self.assertIn("handoff submitted to worker slot 2", stdout)
        self.assertEqual(server.last("send")["expectedId"], "worker-new")
        self.assertEqual(server.last("send")["slot"], 2)

    # --- attempted submission never closes the worker -------------------------

    def _assert_ambiguous_submission_keeps_worker(self, error, stderr, server):
        self.assertIn("mutation outcome unknown", str(error))
        self.assertNotIn("close", server.commands())
        self.assertIn("may already be delivering", stderr)
        self.assertIn("--expected-id worker-id", stderr)

    def test_ambiguous_send_failure_disconnected_reply_retains_worker(self):
        server = self.start(
            by_command(
                {
                    "list": {"ok": True, "sessions": [MANAGER]},
                    "open": {"ok": True, "session": WORKER},
                    "inspect": {"ok": True, "text": "ready"},
                    "register.manager": {"ok": True},
                },
                special={"send": [None]},
            )
        )

        error, _, stderr = self.run_cli(self.handoff("--new-slot"), expect_exit=True)

        self._assert_ambiguous_submission_keeps_worker(error, stderr, server)

    def test_ambiguous_send_failure_timeout_retains_worker(self):
        server = self.start(
            by_command(
                {
                    "list": {"ok": True, "sessions": [MANAGER]},
                    "open": {"ok": True, "session": WORKER},
                    "inspect": {"ok": True, "text": "ready"},
                    "register.manager": {"ok": True},
                },
                special={"send": [("stall", 0.6)]},
            )
        )

        with mock.patch.object(UTP, "TRANSPORT_TIMEOUT", 0.2):
            error, _, stderr = self.run_cli(self.handoff("--new-slot"), expect_exit=True)

        self.assertIn("transport timeout", str(error))
        self._assert_ambiguous_submission_keeps_worker(error, stderr, server)

    def test_ambiguous_in_place_submission_retains_worker(self):
        server = self.start(
            by_command(
                {
                    "list": {"ok": True, "sessions": [MANAGER, IN_PLACE_WORKER]},
                    "profile.switch": {"ok": True, "session": {"slot": 2, "id": "worker-new"}},
                    "inspect": {"ok": True, "text": "ready"},
                    "register.manager": {"ok": True},
                },
                special={"send": [None]},
            )
        )

        error, _, stderr = self.run_cli(
            self.handoff("--slot", "2", "--expected-id", "worker-old"), expect_exit=True
        )

        self.assertIn("mutation outcome unknown", str(error))
        self.assertNotIn("close", server.commands())
        self.assertIn("may already be delivering", stderr)
        self.assertIn("--expected-id worker-new", stderr)


if __name__ == "__main__":
    unittest.main()
