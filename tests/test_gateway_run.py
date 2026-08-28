import unittest
from pathlib import Path
from unittest.mock import patch

from gateway.run import _load_gateway_config, _read_required_api_server_key


class LoadGatewayConfigTest(unittest.TestCase):
    def test_loads_the_real_shipped_config(self):
        config = _load_gateway_config()

        self.assertEqual(
            config["platform_toolsets"]["api_server"],
            ["no_mcp"],
        )

    def test_raises_when_the_file_is_missing(self):
        missing_path = Path("/nonexistent/gateway/config.yaml")

        with patch("gateway.run.CONFIG_PATH", missing_path):
            with self.assertRaisesRegex(RuntimeError, "cannot read gateway config"):
                _load_gateway_config()

    def test_raises_when_the_parsed_content_is_not_a_mapping(self):
        with patch("pathlib.Path.read_text", return_value="- just\n- a\n- list\n"):
            with self.assertRaisesRegex(TypeError, "must parse to a mapping"):
                _load_gateway_config()


class ReadRequiredApiServerKeyTest(unittest.TestCase):
    def test_returns_a_sufficiently_strong_key(self):
        key = _read_required_api_server_key({"API_SERVER_KEY": "a" * 32})

        self.assertEqual(key, "a" * 32)

    def test_rejects_a_missing_key(self):
        with self.assertRaisesRegex(RuntimeError, "is not set"):
            _read_required_api_server_key({})

    def test_rejects_an_empty_key(self):
        with self.assertRaisesRegex(RuntimeError, "is not set"):
            _read_required_api_server_key({"API_SERVER_KEY": ""})

    def test_rejects_a_key_shorter_than_the_minimum(self):
        with self.assertRaisesRegex(RuntimeError, "shorter than 16"):
            _read_required_api_server_key({"API_SERVER_KEY": "short"})

    def test_accepts_a_key_at_exactly_the_minimum_length(self):
        key = _read_required_api_server_key({"API_SERVER_KEY": "a" * 16})

        self.assertEqual(key, "a" * 16)


if __name__ == "__main__":
    unittest.main()
