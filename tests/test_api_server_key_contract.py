import os
import unittest
from unittest.mock import patch

from gateway.run import _read_required_api_server_key
from proxy.app import ProxyConfig


class ApiServerKeyContractTest(unittest.TestCase):
    def test_gateway_and_proxy_preserve_the_same_valid_value(self):
        for key in ["a" * 16, "0123456789abcdef" * 4]:
            with self.subTest(key_length=len(key)):
                gateway_key = _read_required_api_server_key({"API_SERVER_KEY": key})

                with patch.dict(
                    os.environ,
                    {
                        "HERMES_BASE_URL": "http://hermes.internal:8642",
                        "API_SERVER_KEY": key,
                    },
                    clear=True,
                ):
                    proxy_key = ProxyConfig.from_environment().api_server_key

                self.assertEqual(gateway_key, key)
                self.assertEqual(proxy_key, key)

    def test_gateway_and_proxy_reject_the_same_invalid_values(self):
        invalid_keys = [
            "",
            "short",
            f" {'a' * 16}",
            f"{'a' * 16} ",
            f"{'a' * 16}\n",
            f"{'a' * 16}\t{'b' * 16}",
        ]

        for key in invalid_keys:
            with self.subTest(key=repr(key)):
                with self.assertRaises(RuntimeError):
                    _read_required_api_server_key({"API_SERVER_KEY": key})

                with patch.dict(
                    os.environ,
                    {
                        "HERMES_BASE_URL": "http://hermes.internal:8642",
                        "API_SERVER_KEY": key,
                    },
                    clear=True,
                ):
                    with self.assertRaises(RuntimeError):
                        ProxyConfig.from_environment()


if __name__ == "__main__":
    unittest.main()
