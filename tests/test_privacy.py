"""Guard the audited privacy properties of the shipped client and docs.

UTP has no telemetry. Every command talks to the same-user Unix socket; the only
network use is the anonymous update check and the update download (docs/updates.md),
and the only files the client writes are its update state, the bounded automatic-install
log, the rollback copy and the staged download. This test fails if a telemetry/analytics
package or endpoint, an internet socket, an HTTP import or a file/log write outside the
named update functions, a non-GitHub endpoint, a remote README badge, an overlong README
Privacy section or an undocumented local write is introduced.
"""

import ast
import hashlib
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

# The update check and the update download are the only network code. They may import
# urllib.request, and nothing else from NETWORK_IMPORTS, inside these functions only.
NETWORK_FUNCTIONS = {"fetch_latest_release", "download_release_file"}
ALLOWED_NETWORK_MODULES = {"urllib.request"}
ALLOWED_HOSTS = {"github.com", "api.github.com", "raw.githubusercontent.com"}

MANIFESTS = ("package.json", "pyproject.toml", "setup.py", "requirements.txt")

# Update functions that may write: the 0600 state/log writer, the verified swap with its
# staging directory and rollback copy, rollback expiry, and the update command's own
# rollback/opt-out deletions. A write anywhere else in the client fails.
WRITE_FUNCTIONS = {"write_private", "install_client", "remove_rollback", "run_update"}
# write_private only ever receives the update state or the bounded update log.
WRITE_PRIVATE_CALLERS = {"save_update_state", "log_update"}

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


def client_constants():
    """Module-level constant assignments of the shipped client, evaluated literally."""
    values = {}
    for node in ast.parse(CLIENT.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                values[node.targets[0].id] = eval(compile(ast.Expression(node.value), "utp", "eval"), {})
            except Exception:
                pass
    return values


def calls_with_function(tree):
    """Yield (enclosing top-level function name or None, call node)."""
    for node in tree.body:
        name = node.name if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else None
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                yield name, child


def imports_with_function(tree):
    for node in tree.body:
        name = node.name if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else None
        for child in ast.walk(node):
            if isinstance(child, ast.Import):
                for alias in child.names:
                    yield name, alias.name
            elif isinstance(child, ast.ImportFrom) and child.module:
                yield name, child.module


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


def write_label(call):
    """A description of the write performed by call, or None for a non-writing call."""
    func = call.func
    if isinstance(func, ast.Name):
        if func.id == "open" and not is_read_only_open(call):
            return "open() with a write mode"
        if func.id in FILE_LOG_CLASSES:
            return func.id
    if isinstance(func, ast.Attribute):
        name = func.attr
        if name == "open" and not is_read_only_open(call):
            return ".open() with a write mode"
        if name in FILE_LOG_CLASSES:
            return name
        if isinstance(func.value, ast.Name) and func.value.id in WRITE_MODULE_CALLS:
            forbidden = WRITE_MODULE_CALLS[func.value.id]
            if forbidden is None or name in forbidden:
                return f"{func.value.id}.{name}()"
        if name in WRITE_METHODS:
            return f".{name}()"
    return None


def client_write_hits(source=None):
    """Writes outside WRITE_FUNCTIONS, and write_private calls from anywhere unexpected."""
    if source is None:
        source = CLIENT.read_text(encoding="utf-8")
    hits = []
    for function, call in calls_with_function(ast.parse(source)):
        where = f"line {call.lineno} in {function or 'module scope'}"
        label = write_label(call)
        if label and function not in WRITE_FUNCTIONS:
            hits.append(f"{where}: {label}")
        if (isinstance(call.func, ast.Name) and call.func.id == "write_private"
                and function not in WRITE_PRIVATE_CALLERS):
            hits.append(f"{where}: write_private()")
    return hits


def client_network_hits(source=None):
    if source is None:
        source = CLIENT.read_text(encoding="utf-8")
    hits = []
    for function, module in imports_with_function(ast.parse(source)):
        if module.split(".")[0] not in NETWORK_IMPORTS:
            continue
        if function not in NETWORK_FUNCTIONS or module not in ALLOWED_NETWORK_MODULES:
            hits.append(f"{module} imported in {function or 'module scope'}")
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

    def test_network_imports_only_in_the_update_functions(self):
        self.assertEqual(client_network_hits(), [])
        tree = ast.parse(CLIENT.read_text(encoding="utf-8"))
        used = {function for function, module in imports_with_function(tree)
                if module in ALLOWED_NETWORK_MODULES}
        self.assertEqual(used, NETWORK_FUNCTIONS, "the network guard must not go vacuous")
        source = CLIENT.read_text(encoding="utf-8")
        for planted in ("import urllib.request\n", "def ping():\n    import http.client\n",
                        "def fetch_latest_release():\n    import requests\n"):
            self.assertTrue(client_network_hits(source + "\n" + planted), f"guard missed {planted!r}")

    def test_client_endpoints_are_github_release_records_only(self):
        source = CLIENT.read_text(encoding="utf-8")
        hosts = set(re.findall(r"https?://([A-Za-z0-9.-]+)", source))
        self.assertTrue(hosts, "the endpoint guard must not go vacuous")
        self.assertLessEqual(hosts, ALLOWED_HOSTS, f"unexpected endpoints: {sorted(hosts - ALLOWED_HOSTS)}")
        self.assertNotIn("http://", source, "update traffic must use HTTPS")

    def test_client_creates_only_unix_sockets(self):
        tree = ast.parse(CLIENT.read_text(encoding="utf-8"))
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("socket", "create_connection", "create_server", "socketpair")
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "socket"
        ]
        self.assertTrue(calls, "the socket transport guard must not go vacuous")
        for call in calls:
            self.assertEqual(call.func.attr, "socket")
            self.assertTrue(call.args, "socket.socket() must name its family")
            family = call.args[0]
            self.assertEqual(
                (getattr(family.value, "id", None), getattr(family, "attr", None)),
                ("socket", "AF_UNIX"),
            )

    def test_client_writes_only_in_the_update_functions(self):
        hits = client_write_hits()
        self.assertEqual(hits, [], f"client file or log write outside the update code: {hits}")

    def test_write_guard_catches_planted_writes(self):
        source = CLIENT.read_text(encoding="utf-8")
        planted = (
            'with open("/tmp/utp.log", "w") as fh:\n    fh.write("x")\n',
            'logging.FileHandler("/tmp/utp.log")\n',
            'tempfile.NamedTemporaryFile()\n',
            'Path("/tmp/utp-state").write_text("x")\n',
            'def remember(text):\n    write_private("/tmp/utp-history", text.encode())\n',
            'def run_command_log():\n    os.replace("a", "b")\n',
        )
        for snippet in planted:
            self.assertTrue(client_write_hits(source + "\n" + snippet), f"guard missed {snippet!r}")

    def test_commands_off_a_terminal_create_no_files_in_a_private_home(self):
        for argv in (["--help"], ["--version"]):
            with self.subTest(argv=argv), tempfile.TemporaryDirectory(dir="/tmp") as home:
                root = Path(home)
                env = dict(os.environ, HOME=home, TMPDIR=home, XDG_CACHE_HOME=str(root / "cache"))
                for name in ("UTP_REPORT_HOOK", "CI", "CLAUDECODE", "UTP_NO_UPDATE_CHECK"):
                    env.pop(name, None)
                before = {str(path.relative_to(root)) for path in root.rglob("*")}
                result = subprocess.run(
                    [sys.executable, str(CLIENT), *argv],
                    cwd=home, env=env, capture_output=True, text=True, timeout=10,
                    stdin=subprocess.DEVNULL,
                )
                after = {str(path.relative_to(root)) for path in root.rglob("*")}
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(after, before, f"client {argv} wrote into HOME or TMPDIR off a terminal")

    def test_readme_privacy_is_short_true_and_linked(self):
        lines = readme_privacy_lines()
        self.assertTrue(3 <= len(lines) <= 6, f"README Privacy has {len(lines)} non-empty lines")
        text = " ".join(lines)
        self.assertIn("[PRIVACY.md](PRIVACY.md)", text)
        self.assertIn("no telemetry", text.lower())
        self.assertIn("anonymous", text.lower())
        self.assertIn("`UTP_NO_UPDATE_CHECK=1`", text)
        self.assertIn("`utp update --checks off`", text)
        self.assertIn("`utp update --auto off`", text)
        self.assertNotRegex(text.lower(), r"no update checks?\b|nothing to opt out|sends nothing over the network")

    def test_privacy_doc_documents_network_and_write_bounds(self):
        text = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
        constants = client_constants()
        for marker in (
            "## Local-only protocol facts",
            "## Update check and download",
            "## Dependencies and installation",
            "## Local writes",
            "## Removing local data",
            "[docs/updates.md](docs/updates.md)",
            f"User-Agent `{constants['UPDATE_USER_AGENT']}`",
            "At most once per 24 hours",
            f"{constants['UPDATE_TIMEOUT']:g}-second timeout",
            "`CI` or `CLAUDECODE`",
            "`UTP_NO_UPDATE_CHECK=1`",
            "`utp update --checks off`",
            "api.github.com",
            "raw.githubusercontent.com",
            "`CACHE/utp/update.json`",
            "`CACHE/utp/update.log`",
            f"{constants['UPDATE_LOG_LIMIT'] // 1024} KB",
            "`<client>.previous`",
            "seven days",
            "`utp-update-*`",
            "Removed on success and on failure",
            "`utp update --auto off`",
            f"pinned to release {constants['CLIENT_VERSION']}",
        ):
            self.assertIn(marker, text)
        self.assertEqual(constants["UPDATE_INTERVAL"], 24 * 60 * 60)
        self.assertEqual(constants["ROLLBACK_MAX_AGE"], 7 * 24 * 60 * 60)
        for column in ("Writer", "Path", "Contents", "Lifetime / bound", "Cleanup", "Deletion"):
            self.assertIn(column, text)
        lowered = text.lower()
        for stale in ("no update check runs", "writes no files", "nothing to opt out", "no http"):
            self.assertNotIn(stale, lowered)

    def test_readme_install_checksum_matches_shipped_client(self):
        digest = hashlib.sha256(CLIENT.read_bytes()).hexdigest()
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f'expected = "{digest}"', text)
        version = client_constants()["CLIENT_VERSION"]
        self.assertIn(f"/ultraterm-protocol/v{version}/clients/python/utp -o utp", text)
        self.assertIn(f"pinned to release **{version}**", text)

    def test_readme_keeps_privacy_section_without_remote_badges(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Privacy", text)
        self.assertNotIn("img.shields.io", text)
        self.assertNotIn("<script", text)


if __name__ == "__main__":
    unittest.main()
