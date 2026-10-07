"""airOS direct radio tools: detect_dfs, get_clients, get_device_stats."""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from clients.airos import (
    airos_session,
    extract_clients,
    extract_device_stats,
    extract_frequency_info,
)
from clients.uisp import UISPClient, get_device_ip
from config import WispConfig


def register_radio_tools(
    mcp: FastMCP, config: WispConfig, uisp: UISPClient
) -> None:
    """Register airOS direct radio tools with the FastMCP server."""

    @mcp.tool(timeout=30.0)
    async def detect_dfs(
        identifier: Annotated[
            str,
            Field(description="Device name, IP address, or UISP device ID"),
        ],
    ) -> dict[str, Any]:
        """Detect DFS radar events and frequency changes on an airOS device.

        Accepts a device name, IP address, or UISP ID — resolves the device in
        UISP and connects to its management IP.

        The configured frequency comes from the airMAX wireless config the
        operator saved (UISP /devices/airmaxes/{id}/config/wireless). The
        actual frequency is read directly from the device. Like is compared
        with like: configured control frequency vs the radio's control
        frequency, and configured center frequency vs the radio's center
        frequency (only when the configured and actual channel widths match).

        If the control frequencies differ, dfs_event is true: the device was
        forced off its configured channel, typically by a DFS radar detection,
        and needs a reset to return to its intended frequency. dfs_event is
        null when the comparison could not be made (e.g. the device is a
        station, or UISP has no saved frequency for it); reason says why.

        Returns configured_mhz / configured_center_mhz /
        configured_channel_width_mhz (from UISP config), actual_mhz /
        center_freq_mhz / channel_width_mhz (from the device), the dfs_event
        flag, center_mismatch, reason, and IEEE mode.
        """
        device = await uisp.resolve_device(identifier)
        ident = device.get("identification", {}) or {}
        ip = get_device_ip(device)
        if not ip:
            raise ToolError(
                f"Device '{ident.get('name', identifier)}' found in UISP but has no IP address."
            )

        # Operator-configured settings, from UISP's airMAX wireless config
        configured: dict[str, Any] = {}
        config_error = None
        try:
            configured = await uisp.get_configured_frequency(ident.get("id"))
        except ToolError as e:
            config_error = str(e)

        # Current operating settings, read directly from the device
        async with airos_session(ip, config) as status:
            freq_info = extract_frequency_info(status)

        configured_mhz = configured.get("control_mhz")
        configured_center_mhz = configured.get("center_mhz")
        configured_width_mhz = configured.get("channel_width_mhz")
        mode = str(configured.get("mode") or "")

        actual_mhz = freq_info.get("actual_mhz")
        center_freq_mhz = freq_info.get("center_freq_mhz")
        channel_width_mhz = freq_info.get("channel_width_mhz")

        # The center frequency only lines up when both sides use the same width.
        center_mismatch = None
        if (
            configured_center_mhz
            and center_freq_mhz
            and configured_width_mhz
            and configured_width_mhz == channel_width_mhz
        ):
            center_mismatch = configured_center_mhz != center_freq_mhz

        reason = None
        if config_error:
            dfs_event = None
            reason = f"Could not read configured frequency from UISP: {config_error}"
        elif mode.startswith("sta"):
            dfs_event = None
            reason = "Device is a station; it follows its AP's channel."
        elif not configured_mhz:
            dfs_event = None
            reason = "UISP config has no configured control frequency for this device."
        elif not actual_mhz:
            dfs_event = None
            reason = "Device did not report its operating frequency."
        else:
            dfs_event = configured_mhz != actual_mhz
            if dfs_event:
                reason = (
                    f"Operating on {actual_mhz} MHz, configured for {configured_mhz} MHz."
                )
            elif center_mismatch:
                reason = (
                    f"Control frequency matches, but center is {center_freq_mhz} MHz "
                    f"vs configured {configured_center_mhz} MHz."
                )

        return {
            "ip": ip,
            "device_id": ident.get("id"),
            "name": ident.get("name"),
            "configured_mhz": configured_mhz,
            "configured_center_mhz": configured_center_mhz,
            "configured_channel_width_mhz": configured_width_mhz,
            "actual_mhz": actual_mhz,
            "center_freq_mhz": center_freq_mhz,
            "channel_width_mhz": channel_width_mhz,
            "dfs_event": dfs_event,
            "center_mismatch": center_mismatch,
            "reason": reason,
            "ieee_mode": freq_info.get("ieee_mode"),
        }

    @mcp.tool(timeout=30.0)
    async def get_clients(
        identifier: Annotated[
            str,
            Field(description="Device name, IP address, or UISP device ID"),
        ],
    ) -> list[dict[str, Any]]:
        """Get all connected clients/stations for an airOS access point.

        Accepts a device name, IP address, or UISP ID — resolves to the
        management IP automatically before connecting.

        Connects directly to the AP and returns the station table sorted by
        signal strength (strongest first).

        Each client includes: MAC address, IP, signal (dBm), noise floor (dBm),
        RSSI, chain RSSI, distance (meters), uptime, and remote hostname.

        Signal interpretation for airMAX:
        - Good: > -65 dBm
        - Fair: -65 to -75 dBm
        - Poor: -75 to -80 dBm
        - Unusable: < -80 dBm
        """
        ip = await uisp.resolve_ip(identifier)
        async with airos_session(ip, config) as status:
            return extract_clients(status)

    @mcp.tool(timeout=30.0)
    async def get_device_stats(
        identifier: Annotated[
            str,
            Field(description="Device name, IP address, or UISP device ID"),
        ],
    ) -> dict[str, Any]:
        """Get system statistics for an airOS device.

        Accepts a device name, IP address, or UISP ID — resolves to the
        management IP automatically before connecting.

        Connects directly to the device and returns hostname, model, firmware
        version, uptime, CPU load, memory usage, and temperature.
        """
        ip = await uisp.resolve_ip(identifier)
        async with airos_session(ip, config) as status:
            return extract_device_stats(status)
