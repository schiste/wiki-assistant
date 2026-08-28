import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "gateway" / "generate-api-server-key"


class GenerateApiServerKeyTest(unittest.TestCase):
    def test_provisions_an_exact_hex_key_without_exposing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary_directory = root / "bin"
            secret_directory = root / "secrets"
            binary_directory.mkdir()
            secret_directory.mkdir()
            captured_key = root / "captured-key"
            captured_arguments = root / "captured-arguments"
            fake_toolforge = binary_directory / "toolforge"
            fake_toolforge.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$*" > "$CAPTURED_ARGUMENTS"\n'
                'cat > "$CAPTURED_KEY"\ncat "$CAPTURED_KEY"\n'
            )
            fake_toolforge.chmod(0o700)
            environment = {
                **os.environ,
                "PATH": f"{binary_directory}:{os.environ['PATH']}",
                "TMPDIR": str(secret_directory),
                "CAPTURED_KEY": str(captured_key),
                "CAPTURED_ARGUMENTS": str(captured_arguments),
            }

            result = subprocess.run(
                ["/bin/sh", str(SCRIPT)],
                capture_output=True,
                text=True,
                check=False,
                env=environment,
            )

            key = captured_key.read_text()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(captured_arguments.read_text().strip(), "envvars create API_SERVER_KEY")
            self.assertRegex(key, r"^[0-9a-f]{64}$")
            self.assertEqual(result.stdout, "")
            self.assertNotIn(key, result.stderr)
            self.assertEqual(list(secret_directory.iterdir()), [])

    def test_fails_before_generation_when_toolforge_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["/bin/sh", str(SCRIPT)],
                capture_output=True,
                text=True,
                check=False,
                env={"PATH": directory},
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inside the Toolforge tool account", result.stderr)

    def test_cleans_up_the_key_when_toolforge_rejects_the_update(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary_directory = root / "bin"
            secret_directory = root / "secrets"
            binary_directory.mkdir()
            secret_directory.mkdir()
            captured_key = root / "captured-key"
            fake_toolforge = binary_directory / "toolforge"
            fake_toolforge.write_text(
                '#!/bin/sh\ncat > "$CAPTURED_KEY"\nexit 1\n'
            )
            fake_toolforge.chmod(0o700)
            environment = {
                **os.environ,
                "PATH": f"{binary_directory}:{os.environ['PATH']}",
                "TMPDIR": str(secret_directory),
                "CAPTURED_KEY": str(captured_key),
            }

            result = subprocess.run(
                ["/bin/sh", str(SCRIPT)],
                capture_output=True,
                text=True,
                check=False,
                env=environment,
            )

            key = captured_key.read_text()
            self.assertNotEqual(result.returncode, 0)
            self.assertRegex(key, r"^[0-9a-f]{64}$")
            self.assertNotIn(key, result.stderr)
            self.assertIn("Toolforge rejected", result.stderr)
            self.assertEqual(list(secret_directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
