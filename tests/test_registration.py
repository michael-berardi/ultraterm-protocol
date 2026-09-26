"""Deterministic native-identity registration and handoff CLI compatibility.

Every exchange runs against a private disposable Unix socket under a temporary
HOME; the installed app socket is never touched. No test needs the UltraTerm app,
tmux, an agent or the network.
"""
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1] / "clients/python/utp"

MANAGER_ID = "11111111-1111-4111-8111-111111111111"
WORKER_ID = "22222222-2222-4222-8222-222222222222"
OPENED_ID = "33333333-3333-4333-8333-333333333333"
SWITCHED_ID = "44444444-4444-4444-8444-444444444444"


def session(slot, session_id):
    return {"id": session_id, "slot": slot, "title": f"Terminal {slot}", "pid": 1000 + slot}


class MockControlSocket:
    """Serve one reply per client request, recording every request in order."""

    def __init__(self, home, handler):
        self.home = home
        self.handler = handler
        self.requests = []
        self.errors = []
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(home / ".ultraterm" / "utp.sock"))
        self._server.listen(8)
        self._server.settimeout(0.25)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve)
        self._thread.start()

    def _serve(self):
        try:
            while not self._stop.is_set():
                try:
                    connection, _ = self._server.accept()
                except socket.timeout:
                    continue
                with connection:
                    data = b""
                    while not data.endswith(b"\n"):
                        chunk = connection.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                    request = json.loads(data)
                    self.requests.append(request)
                    connection.sendall(self.handler(request))
        except Exception as exc:  # pragma: no cover - surfaced as a test failure
            self.errors.append(exc)

    def stop(self):
        self._stop.set()
        self._thread.join(3)
        self._server.close()


class RegistrationTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        (self.home / ".ultraterm").mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def run_client(self, args, env=None, server=None):
        if server is not None:
            self.addCleanup(server.stop)
        # Tests must not inherit the caller's terminal identity: running the
        # suite inside UltraTerm or tmux would otherwise change slot resolution.
        inherited = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("ULTRATERM_", "TMUX"))
        }
        environment = {
            **inherited,
            "HOME": str(self.home),
            "TMUX_PANE": "",
            "UC_BIN": str(self.home / "uc"),
            **(env or {}),
        }
        result = subprocess.run(
            [str(CLIENT), *args], env=environment, text=True, capture_output=True, timeout=30
        )
        if server is not None:
            server.stop()
            self.assertEqual(server.errors, [])
        return result

    def test_registration_flags_are_required(self):
        result = subprocess.run(
            [str(CLIENT), "register-manager", "--slot", "1"], text=True, capture_output=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--from-id", result.stderr)
        self.assertIn("--expected-id", result.stderr)

        result = subprocess.run(
            [str(CLIENT), "task-done", "--summary", "done"], text=True, capture_output=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--from-id", result.stderr)

    def test_registration_help_documents_captured_ids(self):
        for command in ("register-manager", "task-done"):
            result = subprocess.run(
                [str(CLIENT), command, "--help"], text=True, capture_output=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--from-id", result.stdout)
        help_text = " ".join(
            subprocess.run(
                [str(CLIENT), "register-manager", "--help"], text=True, capture_output=True
            ).stdout.split()
        )
        self.assertIn("never infer from a slot", help_text)

    def test_task_done_to_requires_expected_id_without_sending(self):
        result = self.run_client(
            ["task-done", "--from-id", WORKER_ID, "--to", "1", "--summary", "done"],
            env={"ULTRATERM_SLOT": "2"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--to requires --expected-id", result.stderr)
        self.assertIn("never guess a replacement manager", result.stderr)

    def test_register_manager_sends_both_ids(self):
        def handler(request):
            self.assertEqual(
                request,
                {
                    "cmd": "register.manager",
                    "from": 2,
                    "fromId": WORKER_ID,
                    "expectedId": MANAGER_ID,
                    "to": 1,
                },
            )
            return json.dumps(
                {"ok": True, "from": 2, "managerSlot": 1, "fromId": WORKER_ID, "managerId": MANAGER_ID}
            ).encode() + b"\n"

        server = MockControlSocket(self.home, handler)
        result = self.run_client(
            [
                "register-manager",
                "--slot",
                "1",
                "--from-id",
                WORKER_ID,
                "--expected-id",
                MANAGER_ID,
            ],
            env={"ULTRATERM_SLOT": "2"},
            server=server,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("manager slot 1 registered for worker slot 2", result.stdout)
        self.assertEqual([request["cmd"] for request in server.requests], ["register.manager"])

    def test_register_manager_rejects_changed_session(self):
        def handler(request):
            return json.dumps(
                {"ok": False, "error": "registration session changed; no route was registered"}
            ).encode() + b"\n"

        server = MockControlSocket(self.home, handler)
        result = self.run_client(
            [
                "register-manager",
                "--slot",
                "1",
                "--from-id",
                WORKER_ID,
                "--expected-id",
                MANAGER_ID,
            ],
            env={"ULTRATERM_SLOT": "2"},
            server=server,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no route was registered", result.stderr)

    def test_task_done_uses_identity_route_and_never_types_into_a_pty(self):
        receipt = {
            "ok": True,
            "id": MANAGER_ID,
            "receiptId": "55555555-5555-4555-8555-555555555555",
            "delivery": "durably-queued",
            "recorded": False,
            "entryId": None,
            "acceptedByHost": False,
            "agentAcknowledged": False,
            "modelRead": False,
        }

        def handler(request):
            self.assertEqual(request["cmd"], "task.done")
            self.assertEqual(request["fromId"], WORKER_ID)
            self.assertEqual(request["text"], "Focused regression suite passed.")
            self.assertNotIn("to", request)
            return json.dumps(receipt).encode() + b"\n"

        server = MockControlSocket(self.home, handler)
        result = self.run_client(
            ["task-done", "--from-id", WORKER_ID, "--summary", "Focused regression suite passed."],
            env={"ULTRATERM_SLOT": "2"},
            server=server,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([request["cmd"] for request in server.requests], ["task.done"])
        self.assertNotIn("send", [request["cmd"] for request in server.requests])
        self.assertIn("receiptId=", result.stderr)
        self.assertEqual(json.loads(result.stdout), receipt)

    def test_task_done_override_checks_the_manager_id(self):
        def handler(request):
            self.assertEqual(request["to"], 1)
            self.assertEqual(request["expectedId"], MANAGER_ID)
            return json.dumps(
                {"ok": False, "error": "manager session changed; register the intended manager again"}
            ).encode() + b"\n"

        server = MockControlSocket(self.home, handler)
        result = self.run_client(
            [
                "task-done",
                "--from-id",
                WORKER_ID,
                "--to",
                "1",
                "--expected-id",
                MANAGER_ID,
                "--summary",
                "done",
            ],
            env={"ULTRATERM_SLOT": "2"},
            server=server,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("register the intended manager again", result.stderr)


class HandoffRegistrationTestCase(RegistrationTestCase):
    def packet(self):
        path = self.home / "handoff.md"
        path.write_text("# Goal\nContinue the verified task.\n")
        path.chmod(0o600)
        return path

    def test_new_slot_handoff_registers_the_opened_worker_before_submitting(self):
        def handler(request):
            command = request["cmd"]
            if command == "list":
                return json.dumps(
                    {"ok": True, "sessions": [session(1, MANAGER_ID)]}
                ).encode() + b"\n"
            if command == "open":
                return json.dumps(
                    {"ok": True, "confirmed": True, "session": session(3, OPENED_ID)}
                ).encode() + b"\n"
            if command == "inspect":
                return json.dumps({"ok": True, "slot": 3, "text": "agent ready"}).encode() + b"\n"
            if command == "register.manager":
                return json.dumps(
                    {"ok": True, "from": 3, "managerSlot": 1, "fromId": OPENED_ID, "managerId": MANAGER_ID}
                ).encode() + b"\n"
            if command == "send":
                return json.dumps({"ok": True, "id": OPENED_ID}).encode() + b"\n"
            raise AssertionError(f"unexpected command {command}")

        server = MockControlSocket(self.home, handler)
        result = self.run_client(
            [
                "handoff",
                "--new-slot",
                "--profile",
                "quality",
                "--packet",
                str(self.packet()),
                "--manager-slot",
                "1",
                "--confirm",
                "--user-authorized",
            ],
            server=server,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [request["cmd"] for request in server.requests],
            ["list", "open", "inspect", "inspect", "register.manager", "send"],
        )
        registration = server.requests[4]
        self.assertEqual(
            registration,
            {
                "cmd": "register.manager",
                "from": 3,
                "fromId": OPENED_ID,
                "to": 1,
                "expectedId": MANAGER_ID,
            },
        )
        self.assertIn("handoff submitted to worker slot 3", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_failed_registration_submits_nothing(self):
        """A failed registration must never submit a packet or a completion.

        The opened session is closed with its captured identity before any
        packet submission; a replacement at the same slot must not be closed.
        """
        def handler(request):
            command = request["cmd"]
            if command == "list":
                return json.dumps(
                    {"ok": True, "sessions": [session(1, MANAGER_ID)]}
                ).encode() + b"\n"
            if command == "open":
                return json.dumps(
                    {"ok": True, "confirmed": True, "session": session(3, OPENED_ID)}
                ).encode() + b"\n"
            if command == "inspect":
                return json.dumps({"ok": True, "slot": 3, "text": "agent ready"}).encode() + b"\n"
            if command == "register.manager":
                return json.dumps(
                    {"ok": False, "error": "native conversation not authenticated"}
                ).encode() + b"\n"
            if command == "close":
                self.assertEqual(request["expectedId"], OPENED_ID)
                self.assertEqual(request["slot"], 3)
                return json.dumps({"ok": True}).encode() + b"\n"
            raise AssertionError(f"unexpected command {command}")

        server = MockControlSocket(self.home, handler)
        result = self.run_client(
            [
                "handoff",
                "--new-slot",
                "--profile",
                "quality",
                "--packet",
                str(self.packet()),
                "--manager-slot",
                "1",
                "--confirm",
                "--user-authorized",
            ],
            server=server,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("native conversation not authenticated", result.stderr)
        commands = [request["cmd"] for request in server.requests]
        self.assertEqual(
            commands, ["list", "open", "inspect", "inspect", "register.manager", "close"]
        )
        self.assertNotIn("send", commands)
        self.assertNotIn("handoff submitted", result.stdout)

    def test_in_place_handoff_registers_the_replacement_session(self):
        def handler(request):
            command = request["cmd"]
            if command == "list":
                return json.dumps(
                    {"ok": True, "sessions": [session(1, MANAGER_ID), session(2, WORKER_ID)]}
                ).encode() + b"\n"
            if command == "profile.switch":
                self.assertEqual(request["expectedId"], WORKER_ID)
                return json.dumps(
                    {"ok": True, "confirmed": True, "session": session(2, SWITCHED_ID)}
                ).encode() + b"\n"
            if command == "inspect":
                return json.dumps({"ok": True, "slot": 2, "text": "agent ready"}).encode() + b"\n"
            if command == "register.manager":
                return json.dumps(
                    {"ok": True, "from": 2, "managerSlot": 1, "fromId": SWITCHED_ID, "managerId": MANAGER_ID}
                ).encode() + b"\n"
            if command == "send":
                return json.dumps({"ok": True, "id": SWITCHED_ID}).encode() + b"\n"
            raise AssertionError(f"unexpected command {command}")

        server = MockControlSocket(self.home, handler)
        result = self.run_client(
            [
                "handoff",
                "--slot",
                "2",
                "--profile",
                "quality",
                "--packet",
                str(self.packet()),
                "--manager-slot",
                "1",
                "--expected-id",
                WORKER_ID,
                "--confirm",
                "--user-authorized",
            ],
            env={"ULTRATERM_SLOT": "1"},
            server=server,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [request["cmd"] for request in server.requests],
            ["list", "profile.switch", "inspect", "inspect", "register.manager", "send"],
        )
        registration = server.requests[4]
        self.assertEqual(registration["fromId"], SWITCHED_ID)
        self.assertEqual(registration["expectedId"], MANAGER_ID)

    def test_in_place_confirmation_requires_the_dry_run_id(self):
        def handler(request):
            self.assertEqual(request["cmd"], "list")
            return json.dumps(
                {"ok": True, "sessions": [session(1, MANAGER_ID), session(2, WORKER_ID)]}
            ).encode() + b"\n"

        server = MockControlSocket(self.home, handler)
        result = self.run_client(
            [
                "handoff",
                "--slot",
                "2",
                "--profile",
                "quality",
                "--packet",
                str(self.packet()),
                "--manager-slot",
                "1",
                "--confirm",
                "--user-authorized",
            ],
            env={"ULTRATERM_SLOT": "1"},
            server=server,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires --expected-id", result.stderr)
        self.assertNotIn("profile.switch", [request["cmd"] for request in server.requests])

    def test_handoff_confirmation_requires_user_authorization(self):
        started = time.monotonic()
        result = self.run_client(
            [
                "handoff",
                "--new-slot",
                "--profile",
                "quality",
                "--packet",
                str(self.packet()),
                "--manager-slot",
                "1",
                "--confirm",
            ],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--user-authorized", result.stderr)
        self.assertLess(time.monotonic() - started, 5)


if __name__ == "__main__":
    unittest.main()
