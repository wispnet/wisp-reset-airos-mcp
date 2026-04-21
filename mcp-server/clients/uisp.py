"""UISP NMS REST API client."""

from __future__ import annotations

import re
from typing import Any

import httpx
from fastmcp.exceptions import ToolError

from config import WispConfig

# UUID pattern for UISP device IDs
_UUID_RE = re.compile(r"^[0-9a-f]{24,}$", re.IGNORECASE)
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
                if _get_ip(d) == identifier
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

    async def get_configured_frequency(self, identifier: str) -> int | None:
        """Get the configured frequency for a device from UISP.

        Returns frequency in MHz or None if not available.
        """
        device = await self.resolve_device(identifier)
        overview = device.get("overview", {}) or {}
        freq = overview.get("frequency")
        if freq is not None:
            return int(freq)
        return None


def _get_ip(device: dict) -> str | None:
    """Extract IP address from a UISP device dict."""
    return device.get("ipAddress") or (
        device.get("identification", {}).get("ipAddress")
    )
