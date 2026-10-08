"""Health tools: health_check (MCP tool) and GET /health (HTTP liveness route)."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from clients.uisp import UISPClient
from config import WispConfig

# airOS factory-default login
_DEFAULT_AIROS_CREDENTIALS = ("ubnt", "ubnt")


def register_health_tools(
    mcp: FastMCP, config: WispConfig, uisp: UISPClient
) -> None:
    """Register the health_check tool and the GET /health route."""

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        """Liveness probe for Docker, reverse proxies and uptime monitors.

        Only shows the server is up and serving HTTP. It makes no UISP or
        device calls, so it is cheap to poll.
        """
        return JSONResponse({"status": "ok", "server": mcp.name})

    @mcp.tool(timeout=30.0)
    async def health_check() -> dict[str, Any]:
        """Check that this server can reach UISP NMS and that its API token works.

        Run this first when other tools fail with UISP errors, or when
        detect_dfs returns dfs_event null because the UISP config could not
        be read. It tells "UISP is down or the token was rejected" apart from
        a problem with a specific device.

        Makes one UISP call (the device list) and logs in to no devices.

        Returns status ("ok" when UISP answered with a device list, otherwise
        "error"); uisp: reachable, authenticated, latency_ms, device_count and
        error; airos: credentials_configured (false when the airOS factory
        default login is in use) and device_overrides (number of per-device
        credential overrides). Credentials themselves are never returned.
        """
        uisp_health = await uisp.health()
        credentials = (config.airos_username, config.airos_password)
        return {
            "status": "ok" if uisp_health["authenticated"] else "error",
            "uisp": uisp_health,
            "airos": {
                "credentials_configured": credentials != _DEFAULT_AIROS_CREDENTIALS,
                "device_overrides": len(config.device_overrides),
            },
        }
