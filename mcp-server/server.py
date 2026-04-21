"""dfs-reset MCP server entry point."""

from __future__ import annotations

import sys

from fastmcp import FastMCP

from clients.uisp import UISPClient
from config import load_config
from tools.nms import register_nms_tools
from tools.radio import register_radio_tools
from tools.sweep import register_sweep_tools

config = load_config()
uisp = UISPClient(config)

mcp = FastMCP(
    name="dfs-reset",
    instructions=(
        "DFS detection and recovery tools for Ubiquiti airOS devices managed by UISP NMS. "
        "Use list_devices to discover devices, get_device for details, "
        "detect_dfs to check for DFS radar events and frequency drift, "
        "get_clients/get_device_stats for real-time radio data, "
        "sweep_clients for a network-wide signal scan, "
        "and reset_device (with operator confirmation) to restore a device to its configured frequency."
    ),
)

register_nms_tools(mcp, uisp)
register_radio_tools(mcp, config, uisp)
register_sweep_tools(mcp, config, uisp)

if __name__ == "__main__":
    transport = "stdio"
    port = 8080

    args = sys.argv[1:]
    if "--http" in args:
        transport = "streamable-http"
    for i, arg in enumerate(args):
        if arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])

    if transport == "streamable-http":
        mcp.run(transport=transport, host="0.0.0.0", port=port)
    else:
        mcp.run()
