import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from gateway.verify_interactive_toolset import verify_interactive_toolset


class InteractiveToolsetVerificationTest(unittest.TestCase):
    def test_accepts_the_exact_empty_runtime_authority(self):
        modules = self.hermes_modules(set())

        with patch.dict(sys.modules, modules):
            verify_interactive_toolset(self.config())

    def test_rejects_missing_explicit_selection(self):
        with self.assertRaisesRegex(TypeError, "must be configured"):
            verify_interactive_toolset({})

    def test_rejects_empty_list_that_would_enable_default_mcp_servers(self):
        with self.assertRaisesRegex(RuntimeError, "exactly"):
            verify_interactive_toolset({"platform_toolsets": {"api_server": []}})

    def test_rejects_any_effective_toolset(self):
        modules = self.hermes_modules({"terminal"})

        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(RuntimeError, "terminal"):
                verify_interactive_toolset(self.config())

    def test_startup_does_not_run_hermes_after_verification_failure(self):
        repo_root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as temporary_directory:
            bin_directory = Path(temporary_directory)
            marker = bin_directory / "hermes-ran"
            self.make_executable(bin_directory / "python3", "#!/bin/sh\nexit 23\n")
            self.make_executable(
                bin_directory / "hermes",
                f"#!/bin/sh\ntouch {marker}\n",
            )
            environment = os.environ.copy()
            environment["PATH"] = f"{bin_directory}{os.pathsep}{environment['PATH']}"

            result = subprocess.run(
                ["/bin/sh", str(repo_root / "gateway" / "run-hermes")],
                env=environment,
                check=False,
            )
            self.assertEqual(result.returncode, 23)
            self.assertFalse(marker.exists())

    @staticmethod
    def config():
        return {"platform_toolsets": {"api_server": ["no_mcp"]}}

    @staticmethod
    def hermes_modules(enabled_toolsets):
        hermes_cli = types.ModuleType("hermes_cli")
        tools_config = types.ModuleType("hermes_cli.tools_config")
        toolsets = types.ModuleType("toolsets")
        tools_config._get_platform_tools = lambda *args, **kwargs: enabled_toolsets
        toolsets.resolve_toolset = lambda name: [name]
        return {
            "hermes_cli": hermes_cli,
            "hermes_cli.tools_config": tools_config,
            "toolsets": toolsets,
        }

    @staticmethod
    def make_executable(path, content):
        path.write_text(content)
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
