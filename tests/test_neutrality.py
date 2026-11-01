"""UTP is a neutral tool. Its shipped protocol, client, examples and README carry no
built-in model id, provider route or fallback choice and no person's, client's or
project's name: those belong in the operator's own configuration. This test keeps it
that way. Modelled on Carl's test/neutrality.test.ts.

Tests' synthetic fixtures and test data are excluded from the scan by construction:
only protocols/, clients/, examples/ and the root docs are read. LICENSE copyright and
package metadata author fields are excluded from the scan on purpose: legal attribution
stays. Provider-adapter files that must name their own provider catalog and product
technical identity (bundle ids) may stay when allowlisted below with a comment.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Concrete model ids and provider routes that only an operator should choose. This
# mirrors the job's audit regex. Adapter code that lists a provider's own catalog and
# product technical identity are the only exceptions, and both allowlists are empty
# today because this repository ships neither.
MODEL_CHOICE = re.compile(
    r"gpt-[56][a-z0-9.-]*|deepseek[a-z0-9.-]*|opencode-go/|openrouter/|:exacto|"
    r"mimo-v[0-9][a-z0-9.-]*|glm-[0-9][a-z0-9.-]*|"
    r"claude-[a-z0-9.-]*-5-5|(haiku|sonnet|opus)[ -]?5[.-]5",
    re.IGNORECASE,
)

# Names of the people and organisations UTP was first built for: never shipped.
PERSONAL = re.compile(
    r"Mike|Berardi|Dana|Felix|acme|acme|Mouseia|Liberty Design|"
    r"libertydesign|acme|/Users/",
    re.IGNORECASE,
)

# Allowlisted provider-adapter files (relative to ROOT). Empty today.
ADAPTERS: tuple = ()

# Allowlisted product technical identity strings, each with a reason. Empty today.
TECHNICAL_IDENTITY: tuple = ()

# Shipped trees scanned for choices and names. tests/ is deliberately excluded: its
# synthetic fixtures legitimately use placeholder harness and profile names.
SHIPPED_DIRS = ("protocols", "clients", "examples")

# Shipped documentation at the repository root. SECURITY.md is included so a personal
# reporting URL cannot return either.
SHIPPED_DOCS = ("README.md", "SECURITY.md")

SKIP_SUFFIXES = {".pyc", ".pyo", ".so", ".dylib"}


def shipped_files():
    for name in SHIPPED_DIRS:
        base = ROOT / name
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            # Skip caches and hidden files inside the shipped trees.
            if any(part.startswith("__") or part.startswith(".") for part in rel.parts):
                continue
            if path.suffix in SKIP_SUFFIXES:
                continue
            yield path
    for name in SHIPPED_DOCS:
        doc = ROOT / name
        if doc.is_file():
            yield doc


def scan(pattern):
    hits = []
    for path in shipped_files():
        rel = str(path.relative_to(ROOT))
        if rel in ADAPTERS or any(rel.endswith(a) for a in ADAPTERS):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{rel}:{number}: {line.strip()[:120]}")
    return hits


class NeutralityTests(unittest.TestCase):
    def test_shipped_files_ship_no_model_or_provider_choice(self):
        hits = scan(MODEL_CHOICE)
        self.assertEqual(hits, [], "Built-in model or provider choice in shipped files")

    def test_shipped_files_name_no_person_or_project(self):
        hits = scan(PERSONAL)
        self.assertEqual(hits, [], "Personal or project name in shipped files")

    def test_scan_actually_reads_the_shipped_files(self):
        # Guard against a vacuous pass: the scan set must be non-empty, must include the
        # known shipped files, and the matchers must catch planted samples.
        files = list(shipped_files())
        self.assertGreater(len(files), 0)
        names = {str(p.relative_to(ROOT)) for p in files}
        for expected in ("README.md", "protocols/v2.md", "clients/python/utp",
                         "examples/manager-delegate.sh"):
            self.assertIn(expected, names)
        self.assertTrue(MODEL_CHOICE.search("gpt-5.5 and openrouter/auto"))
        self.assertTrue(PERSONAL.search("/Users/alex/thing"))


if __name__ == "__main__":
    unittest.main()
