"""Guard the audited privacy properties of the shipped client and docs.

UTP has no telemetry dependency and no network transport: every command talks to
the same-user Unix socket. This test fails if a telemetry/analytics package or
endpoint, an HTTP client import, or an internet socket is introduced into the
shipped client, examples, documentation or a future package manifest.
"""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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


def shipped_files():
    yield ROOT / "clients" / "python" / "utp"
    yield ROOT / "README.md"
    for directory in ("examples", "docs", "protocols"):
        base = ROOT / directory
        if base.is_dir():
            yield from sorted(path for path in base.rglob("*") if path.is_file())
    for name in MANIFESTS:
        path = ROOT / name
        if path.is_file():
            yield path


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
        source = (ROOT / "clients" / "python" / "utp").read_text(encoding="utf-8")
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

    def test_readme_install_checksum_matches_shipped_client(self):
        import hashlib
        digest = hashlib.sha256((ROOT / "clients" / "python" / "utp").read_bytes()).hexdigest()
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f'expected = "{digest}"', text)

    def test_readme_keeps_privacy_section_without_remote_badges(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Privacy", text)
        self.assertNotIn("img.shields.io", text)
        self.assertNotIn("<script", text)


if __name__ == "__main__":
    unittest.main()
