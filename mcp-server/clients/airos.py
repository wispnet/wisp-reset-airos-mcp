"""airOS direct device client wrapper around python-airos."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import aiohttp
from airos.airos8 import AirOS8
from fastmcp.exceptions import ToolError

from config import WispConfig

# Default timeout for direct device calls
DEVICE_TIMEOUT = 5.0


@asynccontextmanager
async def airos_session(ip: str, config: WispConfig):
    """Async context manager that connects to an airOS device and yields its status data.

    Usage:
        async with airos_session("192.168.1.20", config) as status:
            freq = status.wireless.frequency
    """
    username, password = config.get_device_credentials(ip)
    connector = aiohttp.TCPConnector(verify_ssl=config.airos_ssl_verify)
    session = aiohttp.ClientSession(connector=connector)

    try:
        device = AirOS8(
            host=ip,
            username=username,
            password=password,
            session=session,
        )

        try:
            async with asyncio.timeout(DEVICE_TIMEOUT):
                await device.login()
        except asyncio.TimeoutError:
            raise ToolError(f"Timeout connecting to {ip}. Device may be unreachable.")
        except aiohttp.ClientError as e:
            raise ToolError(
                f"Cannot connect to {ip}: {e}. Device may be down or not running airOS."
            )
        except Exception as e:
            if "auth" in str(e).lower() or "401" in str(e) or "403" in str(e):
                raise ToolError(f"Authentication failed for {ip}. Check airOS credentials.")
            raise ToolError(f"Error connecting to {ip}: {e}")

        try:
            async with asyncio.timeout(DEVICE_TIMEOUT):
                status = await device.status()
        except asyncio.TimeoutError:
            raise ToolError(f"Timeout fetching status from {ip}.")
        except Exception as e:
            raise ToolError(f"Error fetching status from {ip}: {e}")

        yield status

    finally:
        await session.close()


def extract_frequency_info(status: Any) -> dict[str, Any]:
    """Extract frequency information from airOS status data."""
    wireless = status.wireless
    return {
        "actual_mhz": getattr(wireless, "frequency", None),
        "channel_width_mhz": getattr(wireless, "chanbw", None),
        "center_freq_mhz": getattr(wireless, "center1_freq", None),
        "ieee_mode": str(getattr(wireless, "ieeemode", "unknown")),
    }


def extract_clients(status: Any) -> list[dict[str, Any]]:
    """Extract connected station/client list from airOS status data."""
    stations = getattr(status.wireless, "sta", None) or []
    clients = []

    for sta in stations:
        client = {
            "mac": getattr(sta, "mac", None),
            "ip": getattr(sta, "lastip", None),
            "signal_dbm": getattr(sta, "signal", None),
            "noise_floor_dbm": getattr(sta, "noisefloor", None),
            "rssi": getattr(sta, "rssi", None),
            "chain_rssi": getattr(sta, "chainrssi", None),
            "distance_m": getattr(sta, "distance", None),
            "uptime_seconds": getattr(sta, "uptime", None),
        }

        # Try to get remote hostname
        remote = getattr(sta, "remote", None)
        if remote:
            client["remote_hostname"] = getattr(remote, "hostname", None)

        clients.append(client)

    # Sort by signal strength descending (strongest first)
    clients.sort(key=lambda c: c.get("signal_dbm") or -999, reverse=True)
    return clients


def extract_device_stats(status: Any) -> dict[str, Any]:
    """Extract device statistics from airOS status data."""
    host = status.host

    total_ram = getattr(host, "totalram", None)
    free_ram = getattr(host, "freeram", None)
    memory_used_pct = None
    if total_ram and free_ram and total_ram > 0:
        memory_used_pct = round((1 - free_ram / total_ram) * 100, 1)

    return {
        "hostname": getattr(host, "hostname", None),
        "model": getattr(host, "devmodel", None),
        "firmware": getattr(host, "fwversion", None),
        "uptime_seconds": getattr(host, "uptime", None),
        "cpu_load_percent": getattr(host, "cpuload", None),
        "memory_total_bytes": total_ram,
        "memory_free_bytes": free_ram,
        "memory_used_percent": memory_used_pct,
        "temperature_c": getattr(host, "temperature", None),
    }
