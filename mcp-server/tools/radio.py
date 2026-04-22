"""airOS direct radio tools: detect_dfs, get_clients, get_device_stats."""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from clients.airos import (
    airos_session,
    extract_clients,
    extract_device_stats,
    extract_frequency_info,
)
from clients.uisp import UISPClient
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

        Accepts a device name, IP address, or UISP ID — resolves to the
        management IP automatically before connecting.

        Connects directly to the device to read the actual operating frequency,
        and compares it against the configured frequency from UISP NMS.

        If configured and actual frequencies differ, dfs_event is set to true,
        indicating the device was forced off its configured channel by
        a DFS radar detection event and needs a reset to return to its
        intended frequency.

        Returns configured_mhz (from UISP), actual_mhz (from device),
        dfs_event flag, channel_width, and IEEE mode.
        """
        # Resolve identifier to IP address
        ip = await uisp.resolve_ip(identifier)

        # Get configured frequency from UISP
        configured_mhz = await uisp.get_configured_frequency(ip)

        # Get actual frequency from device
        async with airos_session(ip, config) as status:
            freq_info = extract_frequency_info(status)

        actual_mhz = freq_info.get("actual_mhz")
        center_freq_mhz = freq_info.get("center_freq_mhz")
        observed_mhz = center_freq_mhz if center_freq_mhz is not None else actual_mhz

        # airOS can report the control-side frequency separately from the channel
        # center frequency on wider channels (for example VHT40 can appear +/-10 MHz).
        # Compare UISP configured frequency to the observed center frequency when
        # available, falling back to the raw radio frequency only when no center is
        # reported.
        dfs_event = (
            configured_mhz is not None
            and observed_mhz is not None
            and configured_mhz != observed_mhz
        )

        return {
            "ip": ip,
            "configured_mhz": configured_mhz,
            "actual_mhz": actual_mhz,
            "dfs_event": dfs_event,
            "channel_width_mhz": freq_info.get("channel_width_mhz"),
            "center_freq_mhz": center_freq_mhz,
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
