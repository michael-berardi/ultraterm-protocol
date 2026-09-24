import subprocess
import sys
import unittest
from pathlib import Path


CLIENT = Path(__file__).resolve().parents[1] / "clients" / "python" / "utp"


class StartupTests(unittest.TestCase):
    def test_common_commands_do_not_import_handoff_or_receipt_modules(self) -> None:
        # Agents invoke utp constantly; tempfile and uuid are only needed by
        # handoff and receipt-bearing messages, so they stay deferred.
        probe = (
            "import runpy, sys\n"
            f"sys.argv = ['utp', '--version']\n"
            "try:\n"
            f"    runpy.run_path({str(CLIENT)!r}, run_name='__main__')\n"
            "except SystemExit:\n"
            "    pass\n"
            "print(sorted(m for m in ('tempfile', 'uuid') if m in sys.modules))\n"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", probe], capture_output=True, text=True, check=True
        )
        self.assertEqual(result.stdout.strip().splitlines()[-1], "[]")


if __name__ == "__main__":
    unittest.main()
