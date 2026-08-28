import re
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "gateway" / "generate-api-server-key"

TEMP_FILE_PATTERN = re.compile(r"in (\S+)\)")


class GenerateApiServerKeyTest(unittest.TestCase):
    def test_never_prints_the_key_value_to_stdout(self):
        result = subprocess.run(
            ["/bin/sh", str(SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_prints_the_provisioning_command_and_cleans_up_the_key_file(self):
        result = subprocess.run(
            ["/bin/sh", str(SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertIn("toolforge envvars create API_SERVER_KEY <", result.stderr)

        match = TEMP_FILE_PATTERN.search(result.stderr)
        self.assertIsNotNone(match, result.stderr)
        temp_path = Path(match.group(1))
        # The script's own exit trap must have removed it — nothing sensitive left behind.
        self.assertFalse(temp_path.exists())

    def test_generated_key_is_well_over_the_minimum_strength(self):
        # The script never prints the key value itself, but it does report the generated file's
        # byte count — read that back rather than asserting on unobservable internal state.
        result = subprocess.run(
            ["/bin/sh", str(SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )

        size_match = re.search(r"\((\d+) bytes,", result.stderr)
        self.assertIsNotNone(size_match, result.stderr)
        reported_bytes = int(size_match.group(1))

        # Hermes's own api_server startup guard requires >=16 chars; openssl rand -hex 32
        # produces 64 hex characters (plus a trailing newline) — comfortably over that floor.
        self.assertGreaterEqual(reported_bytes, 16)


if __name__ == "__main__":
    unittest.main()
