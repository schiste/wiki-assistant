import unittest
from pathlib import Path

PROCFILE = Path(__file__).resolve().parents[1] / "Procfile"


class ProcfileTest(unittest.TestCase):
    def test_gunicorn_matches_the_decided_toolforge_concurrency(self):
        command = PROCFILE.read_text(encoding="utf-8").strip()

        # --workers 1 is deliberate, not a typo: the proxy's in-process admission gate and
        # session rate limiter are only global across threads within one process, not across
        # separate gunicorn worker processes (architecture §12, corrected during #35).
        self.assertIn("--workers 1", command)
        self.assertIn("--worker-class gthread", command)
        self.assertIn("--threads 32", command)
        self.assertIn("--timeout 100", command)
        self.assertIn("--graceful-timeout 30", command)
