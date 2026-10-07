"""UISP NMS REST API client."""

from __future__ import annotations

import math
import re
from typing import Any

import httpx
from fastmcp.exceptions import ToolError

from config import WispConfig

# UUID pattern for UISP device IDs (hyphenated GUIDs, or bare hex)
_UUID_RE = re.compile(
    r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{24,})$",
    re.IGNORECASE,
)
# Simple IPv4 pattern
_IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


class UISPClient:
    """Async client for the UISP NMS API."""

    def __init__(self, config: WispConfig) -> None:
        self._base_url = config.uisp_url.rstrip("/") + "/nms/api/v2.1"
        self._headers = {"x-auth-token": config.uisp_token}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            verify=False,
            timeout=15.0,
        )

    async def list_devices(self, site: str | None = None) -> list[dict[str, Any]]:
        """List all devices, optionally filtered by site name (case-insensitive partial match)."""
        async with self._client() as client:
            resp = await client.get("/devices")
            resp.raise_for_status()
            devices = resp.json()

        if site:
            site_lower = site.lower()
            devices = [
                d for d in devices
                if (d.get("identification", {}).get("site", {}) or {})
                .get("name", "").lower().find(site_lower) != -1
            ]

        return devices

    async def get_device(self, device_id: str) -> dict[str, Any]:
        """Get a single device by its UISP ID."""
        async with self._client() as client:
            resp = await client.get(f"/devices/{device_id}")
            if resp.status_code == 404:
                raise ToolError(f"Device not found: {device_id}")
            resp.raise_for_status()
            return resp.json()

    async def restart_device(self, device_id: str) -> dict[str, Any]:
        """Restart a device by its UISP ID."""
        async with self._client() as client:
            resp = await client.post(f"/devices/{device_id}/restart")
            resp.raise_for_status()
            return resp.json()

    async def resolve_device(self, identifier: str) -> dict[str, Any]:
        """Resolve a device by name, IP, or UISP ID.

        Returns the full device dict from UISP.
        Raises ToolError if no match or ambiguous match.
        """
        # Try as UISP device ID first
        if _UUID_RE.match(identifier):
            try:
                return await self.get_device(identifier)
            except ToolError:
                pass  # Fall through to search

        # Fetch all devices and search
        devices = await self.list_devices()

        # Try IP match
        if _IP_RE.match(identifier):
            matches = [
                d for d in devices
                if get_device_ip(d) == identifier
            ]
        else:
            # Try name match (case-insensitive exact, then partial)
            id_lower = identifier.lower()
            matches = [
                d for d in devices
                if (d.get("identification", {}).get("name") or "").lower() == id_lower
            ]
            if not matches:
                matches = [
                    d for d in devices
                    if id_lower in (d.get("identification", {}).get("name") or "").lower()
                ]

        if not matches:
            raise ToolError(
                f"No device matching '{identifier}'. "
                "Use list_devices to see available devices."
            )

        if len(matches) > 1:
            names = [
                d.get("identification", {}).get("name", "unknown")
                for d in matches[:5]
            ]
            raise ToolError(
                f"Multiple devices match '{identifier}': {', '.join(names)}. "
                "Be more specific."
            )

        return matches[0]

    async def resolve_ip(self, identifier: str) -> str:
        """Resolve any device identifier (name, IP, or UISP ID) to its management IP.

        If the identifier is already a valid IP, it is returned as-is.
        Otherwise, resolves via UISP and extracts the IP address.
        Raises ToolError if the device cannot be found or has no IP.
        """
        if _IP_RE.match(identifier):
            return identifier

        device = await self.resolve_device(identifier)
        ip = get_device_ip(device)
        if not ip:
            name = device.get("identification", {}).get("name", identifier)
            raise ToolError(
                f"Device '{name}' found in UISP but has no IP address."
            )
        return ip

    async def get_wireless_config(self, device_id: str) -> dict[str, Any]:
        """Get the saved airMAX wireless config for a device by its UISP ID.

        This is the operator-configured state (UISP reads the device's
        /tmp/system.cfg), not what the radio is currently operating on.
        Raises ToolError if UISP cannot return it (device offline, not airMAX, ...).
        """
        async with self._client() as client:
            try:
                resp = await client.get(f"/devices/airmaxes/{device_id}/config/wireless")
            except httpx.HTTPError as e:
                raise ToolError(f"Error fetching wireless config from UISP: {e}")
        if resp.status_code != 200:
            raise ToolError(
                f"UISP returned HTTP {resp.status_code} for the wireless config "
                f"of device {device_id}."
            )
        try:
            data = resp.json()
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise ToolError(f"UISP returned no wireless config for device {device_id}.")
        return data

    async def get_configured_frequency(self, device_id: str) -> dict[str, Any]:
        """Get the operator-configured frequency settings for an airMAX device.

        Reads GET /devices/airmaxes/{id}/config/wireless. Do not use
        overview.frequency from /devices for this: UISP documents it as the
        *current* frequency, so it moves along with the radio after a DFS hit.

        Returns control_mhz, center_mhz and channel_width_mhz (MHz, or None when
        not set; UISP reports 0 for unset values and for stations) and mode.
        """
        wireless = await self.get_wireless_config(device_id)
        return {
            "control_mhz": _mhz(wireless.get("controlFrequency")),
            "center_mhz": _mhz(wireless.get("centerFrequency")),
            "channel_width_mhz": _mhz(wireless.get("channelWidth")),
            "mode": wireless.get("mode"),
        }


def _mhz(value: Any) -> int | None:
    """Coerce a UISP frequency/width value to int MHz; 0 or non-numeric -> None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    mhz = int(value)
    return mhz if mhz > 0 else None


def get_device_ip(device: dict) -> str | None:
    """Extract IP address from a UISP device dict (strips CIDR notation)."""
    ip = device.get("ipAddress") or (
        device.get("identification", {}).get("ipAddress")
    )
    return ip.split("/")[0] if ip else None
