import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_SCRIPT = REPO_ROOT / "gateway" / "init"

REQUIRED_DIRECTORIES = [
    "backups",
    "cron",
    "sessions",
    "logs",
    "logs/gateways",
    "hooks",
    "memories",
    "skills",
    "skins",
    "plans",
    "workspace",
    "home",
    "pairing",
    "platforms/pairing",
    "lazy-packages",
]


class GatewayInitTest(unittest.TestCase):
    def test_fails_without_hermes_home(self):
        environment = self.base_environment(hermes_home=None)

        result = subprocess.run(
            ["/bin/sh", str(INIT_SCRIPT)],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HERMES_HOME", result.stderr)

    def test_creates_all_required_directories(self):
        with tempfile.TemporaryDirectory() as hermes_home:
            with self.fake_bin(always_succeed=True) as bin_directory:
                environment = self.base_environment(
                    hermes_home=hermes_home, bin_directory=bin_directory
                )

                result = subprocess.run(
                    ["/bin/sh", str(INIT_SCRIPT)],
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                for relative in REQUIRED_DIRECTORIES:
                    self.assertTrue(
                        (Path(hermes_home) / relative).is_dir(),
                        f"missing directory: {relative}",
                    )

    def test_key_validation_failure_blocks_seeding_and_skills_sync(self):
        with tempfile.TemporaryDirectory() as hermes_home:
            with self.fake_bin(always_succeed=False) as bin_directory:
                call_count_file = bin_directory / "python3-call-count"
                environment = self.base_environment(
                    hermes_home=hermes_home, bin_directory=bin_directory
                )

                result = subprocess.run(
                    ["/bin/sh", str(INIT_SCRIPT)],
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                self.assertNotEqual(result.returncode, 0)
                # Only the key-validation step ran — seeding and skills sync never started.
                self.assertEqual(call_count_file.read_text().strip(), "1")

    def test_skips_seeding_without_install_dir_but_still_runs_skills_sync(self):
        with tempfile.TemporaryDirectory() as hermes_home:
            with self.fake_bin(always_succeed=True) as bin_directory:
                call_count_file = bin_directory / "python3-call-count"
                environment = self.base_environment(
                    hermes_home=hermes_home, bin_directory=bin_directory
                )
                environment.pop("HERMES_INSTALL_DIR", None)

                result = subprocess.run(
                    ["/bin/sh", str(INIT_SCRIPT)],
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("skipping first-boot config seeding", result.stderr)
                # Key validation + skills sync both still ran (2 python3 calls), just no seeding.
                self.assertEqual(call_count_file.read_text().strip(), "2")

    def test_seeds_config_files_once_and_never_overwrites_on_rerun(self):
        with tempfile.TemporaryDirectory() as hermes_home, tempfile.TemporaryDirectory() as install_dir:
            (Path(install_dir) / "docker").mkdir()
            (Path(install_dir) / ".env.example").write_text("EXAMPLE=1\n")
            (Path(install_dir) / "cli-config.yaml.example").write_text("example: true\n")
            (Path(install_dir) / "docker" / "SOUL.md").write_text("# example soul\n")

            with self.fake_bin(always_succeed=True) as bin_directory:
                environment = self.base_environment(
                    hermes_home=hermes_home, bin_directory=bin_directory
                )
                environment["HERMES_INSTALL_DIR"] = install_dir

                first = subprocess.run(
                    ["/bin/sh", str(INIT_SCRIPT)],
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(first.returncode, 0, first.stderr)

                seeded_env = Path(hermes_home) / ".env"
                seeded_config = Path(hermes_home) / "config.yaml"
                seeded_soul = Path(hermes_home) / "SOUL.md"
                self.assertEqual(seeded_env.read_text(), "EXAMPLE=1\n")
                self.assertEqual(seeded_config.read_text(), "example: true\n")
                self.assertEqual(seeded_soul.read_text(), "# example soul\n")

                # Simulate the operator having since edited the seeded file.
                seeded_env.write_text("EXAMPLE=operator-edited\n")

                second = subprocess.run(
                    ["/bin/sh", str(INIT_SCRIPT)],
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(seeded_env.read_text(), "EXAMPLE=operator-edited\n")

    @staticmethod
    def base_environment(hermes_home, bin_directory=None):
        environment = os.environ.copy()
        if hermes_home is None:
            environment.pop("HERMES_HOME", None)
        else:
            environment["HERMES_HOME"] = hermes_home
        environment.setdefault("HERMES_INSTALL_DIR", "/nonexistent-by-default")
        if bin_directory is not None:
            environment["PATH"] = f"{bin_directory}{os.pathsep}{environment['PATH']}"
        return environment

    @staticmethod
    def fake_bin(*, always_succeed):
        import contextlib

        @contextlib.contextmanager
        def manager():
            with tempfile.TemporaryDirectory() as directory:
                bin_directory = Path(directory)
                call_count_file = bin_directory / "python3-call-count"
                exit_code = "0" if always_succeed else "1"
                (bin_directory / "python3").write_text(
                    "#!/bin/sh\n"
                    f"count=$(cat {call_count_file} 2>/dev/null || echo 0)\n"
                    f"echo $((count + 1)) > {call_count_file}\n"
                    f"exit {exit_code}\n"
                )
                (bin_directory / "python3").chmod(0o755)
                yield bin_directory

        return manager()


if __name__ == "__main__":
    unittest.main()
