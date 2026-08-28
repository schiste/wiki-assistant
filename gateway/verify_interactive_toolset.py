#!/usr/bin/env python3

from collections.abc import Mapping

EXPECTED_SELECTION = ["no_mcp"]


def verify_interactive_toolset(config: Mapping[object, object]) -> None:
    platform_toolsets = config.get("platform_toolsets")
    if not isinstance(platform_toolsets, Mapping):
        raise TypeError("platform_toolsets must be configured as a mapping")

    selection = platform_toolsets.get("api_server")
    if selection != EXPECTED_SELECTION:
        raise RuntimeError("platform_toolsets.api_server must be exactly ['no_mcp']")

    from hermes_cli.tools_config import _get_platform_tools
    from toolsets import resolve_toolset

    enabled_toolsets = set(
        _get_platform_tools(
            dict(config),
            "api_server",
            include_default_mcp_servers=True,
        )
    )
    resolved_tools = {
        tool for toolset in enabled_toolsets for tool in resolve_toolset(toolset)
    }

    if enabled_toolsets or resolved_tools:
        raise RuntimeError(
            "interactive Hermes authority is not empty: "
            f"toolsets={sorted(enabled_toolsets)!r}, tools={sorted(resolved_tools)!r}"
        )


def main() -> None:
    from gateway.run import _load_gateway_config

    verify_interactive_toolset(_load_gateway_config())
    print("Verified empty Hermes interactive toolset")


if __name__ == "__main__":
    main()
