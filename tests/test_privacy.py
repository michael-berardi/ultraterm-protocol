"""Guard the audited privacy properties of the shipped client and docs.

UTP has no telemetry dependency and no network transport: every command talks to
the same-user Unix socket. This test fails if a telemetry/analytics package or
endpoint, an HTTP client import, an internet socket, a remote README badge, a
client-side file/log write, or an overlong README Privacy section is introduced.
"""

import ast
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "clients" / "python" / "utp"

FORBIDDEN = re.compile(
    r"(?i)\b(?:posthog|sentry[_-]sdk|sentry\.io|segment\.io|analytics\.js|"
    r"mixpanel|amplitude|datadog|bugsnag|google[-_]analytics|google-analytics\.com|"
    r"gtag\.js|googletagmanager|opentelemetry|honeycomb\.io|statsig|plausible\.io|"
    r"count\.vercel\.com|heap\.io)\b"
)

NETWORK_IMPORTS = {
    "urllib", "http", "requests", "httpx", "aiohttp", "boto3", "socketserver",
}

MANIFESTS = ("package.json", "pyproject.toml", "setup.py", "requirements.txt")

# The shipped client may validate a packet path with tempfile.gettempdir(), but
# it must never create, modify or delete a file or a log itself.
WRITE_MODULE_CALLS = {
    "os": {
        "open", "fdopen", "mkdir", "makedirs", "remove", "unlink", "rename",
        "renames", "replace", "rmdir", "truncate", "chmod", "chown", "symlink",
        "link", "mkfifo", "mknod", "utime", "setxattr", "removexattr",
    },
    "io": {"open"},
    "shutil": None,  # every shutil call in the client would be a write
    "tempfile": {
        "mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryFile",
        "SpooledTemporaryFile", "TemporaryDirectory",
    },
    "logging": {"basicConfig"},
    "sqlite3": {"connect"},
    "shelve": {"open"},
    "dbm": {"open"},
}
WRITE_METHODS = {
    "open", "write", "writelines", "write_text", "write_bytes", "touch",
    "mkdir", "makedirs", "rmdir", "unlink", "remove", "rename", "replace",
    "truncate", "chmod", "chown", "symlink_to", "hardlink_to",
}
FILE_LOG_CLASSES = {
    "FileHandler", "RotatingFileHandler", "TimedRotatingFileHandler",
    "WatchedFileHandler", "SysLogHandler", "NTEventLogHandler",
}


def shipped_files():
    yield CLIENT
    yield ROOT / "README.md"
    yield ROOT / "PRIVACY.md"
    for directory in ("examples", "docs", "protocols"):
        base = ROOT / directory
        if base.is_dir():
            yield from sorted(path for path in base.rglob("*") if path.is_file())
    for name in MANIFESTS:
        path = ROOT / name
        if path.is_file():
            yield path


def readme_privacy_lines():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    start = text.index("## Privacy")
    end = text.find("\n## ", start + len("## Privacy"))
    if end < 0:
        end = len(text)
    return [line.strip() for line in text[start:end].splitlines()[1:] if line.strip()]


def mode_argument(call):
    if len(call.args) >= 2:
        return call.args[1]
    for keyword in call.keywords:
        if keyword.arg == "mode":
            return keyword.value
    return None


def is_read_only_open(call):
    mode = mode_argument(call)
    if mode is None:
        return True  # open() defaults to read mode
    return (
        isinstance(mode, ast.Constant)
        and isinstance(mode.value, str)
        and "r" in mode.value
        and not set(mode.value) & set("wax+")
    )


def client_write_hits(source=None):
    if source is None:
        source = CLIENT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        label = f"line {node.lineno}"
        if isinstance(func, ast.Name):
            if func.id == "open" and not is_read_only_open(node):
                hits.append(f"{label}: open() with a write mode")
            if func.id in FILE_LOG_CLASSES:
                hits.append(f"{label}: {func.id}")
        if isinstance(func, ast.Attribute):
            name = func.attr
            if name == "open" and not is_read_only_open(node):
                hits.append(f"{label}: .open() with a write mode")
            if name in WRITE_METHODS:
                hits.append(f"{label}: .{name}()")
            if name in FILE_LOG_CLASSES:
                hits.append(f"{label}: {name}")
            if isinstance(func.value, ast.Name):
                module = func.value.id
                forbidden = WRITE_MODULE_CALLS.get(module)
                if forbidden is None and module in WRITE_MODULE_CALLS:
                    hits.append(f"{label}: {module}.{name}()")
                elif forbidden and name in forbidden:
                    hits.append(f"{label}: {module}.{name}()")
    return hits


class PrivacyTests(unittest.TestCase):
    def test_no_telemetry_packages_or_endpoints_in_shipped_files(self):
        hits = []
        for path in shipped_files():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if FORBIDDEN.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{number}")
        self.assertEqual(hits, [], "telemetry or analytics reintroduced")

    def test_client_only_imports_standard_library_and_creates_unix_sockets(self):
        source = CLIENT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertFalse(imports & NETWORK_IMPORTS, f"network imports: {sorted(imports & NETWORK_IMPORTS)}")
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "socket"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "socket"
        ]
        self.assertTrue(calls, "the socket transport guard must not go vacuous")
        for call in calls:
            self.assertTrue(call.args, "socket.socket() must name its family")
            family = call.args[0]
            self.assertEqual(
                (getattr(family.value, "id", None), getattr(family, "attr", None)),
                ("socket", "AF_UNIX"),
            )

    def test_client_introduces_no_file_or_log_write(self):
        hits = client_write_hits()
        self.assertEqual(hits, [], f"client file or log write introduced: {hits}")

    def test_write_guard_catches_planted_writes(self):
        source = CLIENT.read_text(encoding="utf-8")
        planted = (
            'with open("/tmp/utp.log", "w") as fh:\n    fh.write("x")\n',
            'logging.FileHandler("/tmp/utp.log")\n',
            'tempfile.NamedTemporaryFile()\n',
            'Path("/tmp/utp-state").write_text("x")\n',
        )
        for snippet in planted:
            self.assertTrue(client_write_hits(source + "\n" + snippet), f"guard missed {snippet!r}")

    def test_help_creates_no_files_in_a_private_home(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as home:
            root = Path(home)
            env = dict(os.environ, HOME=home, TMPDIR=home)
            env.pop("UTP_REPORT_HOOK", None)
            before = {str(path.relative_to(root)) for path in root.rglob("*")}
            result = subprocess.run(
                [sys.executable, str(CLIENT), "--help"],
                cwd=home, env=env, capture_output=True, text=True, timeout=10,
            )
            after = {str(path.relative_to(root)) for path in root.rglob("*")}
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(after, before, "client --help wrote into HOME or TMPDIR")

    def test_readme_privacy_is_short_linked_and_has_one_update_line(self):
        lines = readme_privacy_lines()
        self.assertTrue(3 <= len(lines) <= 6, f"README Privacy has {len(lines)} lines")
        self.assertTrue(any("[PRIVACY.md](PRIVACY.md)" in line for line in lines))
        update_lines = [line for line in lines if "update" in line.lower()]
        self.assertEqual(len(update_lines), 1, "update status must be one README line")
        self.assertIn("no update checks run", update_lines[0].lower())
        self.assertIn("opt out", update_lines[0].lower())

    def test_privacy_doc_has_documented_write_bounds(self):
        text = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
        for marker in (
            "## Local-only protocol facts",
            "## Dependencies and installation",
            "## Local writes",
            "writes no files and creates no logs",
            "No update check runs",
        ):
            self.assertIn(marker, text)
        for column in ("Writer", "Path", "Contents", "Lifetime / bound", "Cleanup", "Deletion"):
            self.assertIn(column, text)

    def test_readme_install_checksum_matches_shipped_client(self):
        import hashlib
        digest = hashlib.sha256(CLIENT.read_bytes()).hexdigest()
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f'expected = "{digest}"', text)

    def test_readme_keeps_privacy_section_without_remote_badges(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Privacy", text)
        self.assertNotIn("img.shields.io", text)
        self.assertNotIn("<script", text)


if __name__ == "__main__":
    unittest.main()
