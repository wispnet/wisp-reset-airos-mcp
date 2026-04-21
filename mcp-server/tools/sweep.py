"""Sweep tool: get_all_client_signals — concurrent multi-AP client scan."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from pydantic import Field

from clients.airos import airos_session, extract_clients
from clients.uisp import UISPClient
from config import WispConfig


def register_sweep_tools(
    mcp: FastMCP, config: WispConfig, uisp: UISPClient
) -> None:
    """Register the sweep tool with the FastMCP server."""

    @mcp.tool(timeout=120.0)
    async def sweep_clients(
        ctx: Context,
        site: Annotated[
            str | None,
            Field(description="Filter APs by site name (case-insensitive partial match)"),
        ] = None,
    ) -> dict[str, Any]:
        """Sweep all access points and return a unified table of connected clients.

        Connects to each AP concurrently and collects the station table.
        Useful after a DFS reset to verify clients have reconnected, or for
        auditing signal quality across the network.

        Unreachable APs are reported with status "error" in the results —
        the sweep never fails entirely due to individual device issues.

        Returns a summary (total APs, successful, failed, total clients)
        and per-AP results with their client lists.
        """
        # Get AP list from UISP
        devices = await uisp.list_devices(site=site)
        if not devices:
            return {
                "summary": {
                    "aps_total": 0,
                    "aps_ok": 0,
                    "aps_failed": 0,
                    "total_clients": 0,
                },
                "results": [],
            }

        await ctx.info(f"Sweeping {len(devices)} devices...")

        semaphore = asyncio.Semaphore(config.sweep_concurrency)
        results: list[dict[str, Any]] = []

        async def scan_device(device: dict) -> dict[str, Any]:
            ident = device.get("identification", {}) or {}
            name = ident.get("name", "unknown")
            ip = device.get("ipAddress") or ident.get("ipAddress")

            if not ip:
                return {
                    "ap": name,
                    "ip": None,
                    "status": "error",
                    "error": "No IP address found in UISP",
                    "clients": [],
                }

            async with semaphore:
                try:
                    async with asyncio.timeout(config.sweep_timeout):
                        async with airos_session(ip, config) as status:
                            clients = extract_clients(status)
                    return {
                        "ap": name,
                        "ip": ip,
                        "status": "ok",
                        "client_count": len(clients),
                        "clients": clients,
                    }
                except Exception as e:
                    return {
                        "ap": name,
                        "ip": ip,
                        "status": "error",
                        "error": str(e),
                        "clients": [],
                    }

        # Run all scans concurrently
        tasks = [scan_device(d) for d in devices]
        results = await asyncio.gather(*tasks)

        # Build summary
        aps_ok = sum(1 for r in results if r["status"] == "ok")
        aps_failed = sum(1 for r in results if r["status"] == "error")
        total_clients = sum(len(r["clients"]) for r in results)

        await ctx.info(
            f"Sweep complete: {aps_ok}/{len(results)} APs responding, "
            f"{total_clients} total clients"
        )

        return {
            "summary": {
                "aps_total": len(results),
                "aps_ok": aps_ok,
                "aps_failed": aps_failed,
                "total_clients": total_clients,
            },
            "results": results,
        }
