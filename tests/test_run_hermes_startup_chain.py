import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class RunHermesStartupChainTest(unittest.TestCase):
    """run-hermes must run BOTH verification steps, in order, before exec'ing hermes.

    test_interactive_toolset.py's end-to-end test proves a failing FIRST check blocks
    startup; it doesn't prove a second check exists or is reached. This proves the chain
    actually has two distinct gates, not just one.
    """

    def test_second_check_runs_only_after_the_first_succeeds_and_still_blocks_hermes(self):
        repo_root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as temporary_directory:
            bin_directory = Path(temporary_directory)
            call_count_file = bin_directory / "python3-call-count"
            hermes_marker = bin_directory / "hermes-ran"

            # Fake python3: succeeds (exit 0) on the first invocation (the toolset check),
            # fails (exit 42) on the second (the key check) — proving both are actually
            # invoked, in order, and that the second one's failure still blocks hermes.
            self.make_executable(
                bin_directory / "python3",
                "#!/bin/sh\n"
                f"count=$(cat {call_count_file} 2>/dev/null || echo 0)\n"
                f"echo $((count + 1)) > {call_count_file}\n"
                'if [ "$count" -eq 0 ]; then exit 0; else exit 42; fi\n',
            )
            self.make_executable(
                bin_directory / "hermes",
                f"#!/bin/sh\ntouch {hermes_marker}\n",
            )
            environment = os.environ.copy()
            environment["PATH"] = f"{bin_directory}{os.pathsep}{environment['PATH']}"

            result = subprocess.run(
                ["/bin/sh", str(repo_root / "gateway" / "run-hermes")],
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 42)
            self.assertEqual(call_count_file.read_text().strip(), "2")
            self.assertFalse(hermes_marker.exists())

    @staticmethod
    def make_executable(path, content):
        path.write_text(content)
        path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
