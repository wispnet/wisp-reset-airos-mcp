"""NMS-backed tools: list_devices, get_device, reset_device."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from clients.uisp import UISPClient


def _simplify_device(d: dict[str, Any]) -> dict[str, Any]:
    """Flatten a UISP device dict into a simplified summary."""
    ident = d.get("identification", {}) or {}
    overview = d.get("overview", {}) or {}
    site = ident.get("site") or {}

    return {
        "device_id": ident.get("id"),
        "name": ident.get("name"),
        "model": ident.get("model"),
        "ip": d.get("ipAddress") or ident.get("ipAddress"),
        "mac": ident.get("mac"),
        "site": site.get("name"),
        "status": overview.get("status"),
        "firmware": overview.get("firmwareVersion") or ident.get("firmwareVersion"),
        "frequency_mhz": overview.get("frequency"),
        "uptime_seconds": overview.get("uptime"),
    }


def register_nms_tools(mcp: FastMCP, uisp: UISPClient) -> None:
    """Register UISP NMS tools with the FastMCP server."""

    @mcp.tool
    async def list_devices(
        site: Annotated[
            str | None,
            Field(description="Filter by site name (case-insensitive partial match)"),
        ] = None,
    ) -> list[dict[str, Any]]:
        """List all UISP-managed devices. Optionally filter by site name.

        Returns a summary of each device including name, model, IP, site,
        status, firmware version, and configured frequency.
        """
        devices = await uisp.list_devices(site=site)
        return [_simplify_device(d) for d in devices]

    @mcp.tool
    async def get_device(
        identifier: Annotated[
            str,
            Field(description="Device name, IP address, or UISP device ID"),
        ],
    ) -> dict[str, Any]:
        """Get detailed information about a specific device from UISP.

        Accepts a device name (case-insensitive), IP address, or UISP device ID.
        Returns full device details including configuration, status, and overview.
        """
        device = await uisp.resolve_device(identifier)
        return _simplify_device(device)

    @mcp.tool
    async def reset_device(
        identifier: Annotated[
            str,
            Field(description="Device name or IP address to reset"),
        ],
    ) -> dict[str, str]:
        """Reset a device via UISP NMS to restore its configured frequency.

        Use this after detecting a DFS event to force the device back to its
        intended channel. The device will reboot and re-initialize on its
        configured frequency.

        WARNING: This will cause a brief service interruption for all clients
        connected to this device (~1-2 minutes). Always confirm with the
        operator before resetting.

        Accepts a device name or IP address. Resolves the device in UISP and
        sends a restart command.
        """
        device = await uisp.resolve_device(identifier)
        ident = device.get("identification", {}) or {}
        device_id = ident.get("id")
        device_name = ident.get("name", identifier)

        await uisp.restart_device(device_id)

        return {
            "status": "reset_initiated",
            "device": device_name,
            "device_id": device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
