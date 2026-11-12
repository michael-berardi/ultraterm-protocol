"""UTP is a neutral tool. Its shipped protocol, client, examples and README carry no
built-in model id, provider route or fallback choice and no person's, client's or
project's name: those belong in the operator's own configuration. This test keeps it
that way. Modelled on Carl's test/neutrality.test.ts.

Model choices are checked in shipped files; personal terms are also checked in tests
and docs, except this test itself. LICENSE copyright and
package metadata author fields are excluded from the scan on purpose: legal attribution
stays. Provider-adapter files that must name their own provider catalog and product
technical identity (bundle ids) may stay when allowlisted below with a comment.
"""

import os
import re
import tempfile
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
    r"Mike|Berardi|Felix|Mouseia|Liberty Design|"
    r"libertydesign|/Users/",
    re.IGNORECASE,
)

# The repository's own canonical GitHub URL forms are the only place the owner name may
# appear. Anything else containing the name still fails.
OWN_URL = re.compile(
    r"github\.com/michael-berardi/ultraterm-protocol(?![\w-])|"
    r"img\.shields\.io/github/[a-z/-]+/michael-berardi/ultraterm-protocol(?![\w-])"
)

# Placeholder owners that must never appear in a README URL.
PLACEHOLDER_OWNER = re.compile(
    r"https?://[^\s)\"'>]*(example-user|your-org|your-github-username|Alex/|OWNER|<owner>)"
)

# Allowlisted provider-adapter files (relative to ROOT). Empty today.
ADAPTERS: tuple = ()

# Allowlisted product technical identity strings, each with a reason. Empty today.
TECHNICAL_IDENTITY: tuple = ()

# Shipped trees scanned for choices and names.
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


def load_private_terms(path=None):
    path = Path(path) if path is not None else Path(
        os.environ.get("OSS_PRIVATE_TERMS", "~/.config/oss-audit/names.txt")
    ).expanduser()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    terms = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]
    alternatives = []
    for term in terms:
        alternatives.append((r"(?<!\w)" if re.match(r"\w", term[0]) else "")
                            + re.escape(term)
                            + (r"(?!\w)" if re.match(r"\w", term[-1]) else ""))
    return re.compile("|".join(alternatives), re.IGNORECASE) if alternatives else None


def personal_files():
    yield from shipped_files()
    seen = set()
    for name in ("tests", "test", "Tests", "docs"):
        base = ROOT / name
        if not base.is_dir() or (base.stat().st_dev, base.stat().st_ino) in seen:
            continue
        seen.add((base.stat().st_dev, base.stat().st_ino))
        for path in base.rglob("*"):
            rel = path.relative_to(ROOT)
            if (path.is_file() and not path.samefile(__file__)
                    and path.suffix not in SKIP_SUFFIXES):
                yield path


def scan_personal(pattern):
    hits = []
    if pattern is None:
        return hits
    for path in personal_files():
        rel = str(path.relative_to(ROOT))
        if rel in ADAPTERS or any(rel.endswith(a) for a in ADAPTERS):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(OWN_URL.sub("", line)):
                hits.append(f"{rel}:{number}")
    return hits


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
        hits = scan_personal(PERSONAL) + scan_personal(load_private_terms())
        self.assertEqual(hits, [], "Personal or project name in shipped files")

    def test_readme_has_no_placeholder_owner_in_urls(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(PLACEHOLDER_OWNER.findall(text), [])
        self.assertTrue(PLACEHOLDER_OWNER.search("https://github.com/Alex/x"))
        self.assertTrue(PLACEHOLDER_OWNER.search("https://github.com/<owner>/x"))

    def test_own_url_allowed_but_other_uses_fail(self):
        own = "https://github.com/michael-berardi/ultraterm-protocol/releases"
        self.assertEqual(PERSONAL.sub("", OWN_URL.sub("", own)).count("Berardi"), 0)
        self.assertIsNotNone(PERSONAL.search(OWN_URL.sub("", "by michael-berardi")))
        self.assertIsNotNone(PERSONAL.search(OWN_URL.sub("", "github.com/michael-berardi/other")))

    def test_private_terms_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            terms = Path(tmp) / "terms.txt"
            terms.write_text("# comment\n\nzzqx-private-term\n", encoding="utf-8")
            pattern = load_private_terms(terms)
            sample = Path(tmp) / "sample.txt"
            sample.write_text("A ZZQX-private-term here", encoding="utf-8")
            self.assertIsNotNone(pattern.search(sample.read_text(encoding="utf-8")))
            sample.write_text("ordinary text", encoding="utf-8")
            self.assertIsNone(pattern.search(sample.read_text(encoding="utf-8")))
            self.assertIsNone(pattern.search("xzzqx-private-term"))

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
