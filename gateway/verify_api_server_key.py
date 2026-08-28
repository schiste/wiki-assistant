#!/usr/bin/env python3

import os


def main() -> None:
    from gateway.run import _read_required_api_server_key

    _read_required_api_server_key(os.environ)
    print("Verified API_SERVER_KEY is present")


if __name__ == "__main__":
    main()
