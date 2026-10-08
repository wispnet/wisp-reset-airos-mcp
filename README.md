# dfs-reset

An MCP server for detecting DFS radar events on Ubiquiti airOS access points and resetting them to restore their configured frequencies. Built for WISP operators managing networks through UISP NMS.

## The Problem

When an airOS access point on a DFS-required 5 GHz channel detects radar, it's legally required to vacate that channel immediately. The radio auto-selects a different frequency — but this fallback channel is often suboptimal. It may interfere with neighboring APs, conflict with your frequency plan, or put clients on a congested channel. The device won't return to its configured frequency on its own.

The fix is simple (reboot the AP), but finding which devices have been hit across a network of dozens or hundreds of APs is tedious. That's what this tool automates.

## How It Works

dfs-reset is a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that gives Claude (or any MCP-compatible AI assistant) direct access to your UISP NMS and airOS devices. The core workflow is:

1. **Detect** — `detect_dfs` reads the frequency the operator configured (UISP's airMAX wireless config, `/devices/airmaxes/{id}/config/wireless`, which UISP reads from the device's saved configuration) and compares it against the frequency the AP is actually operating on, read directly from the radio. Control frequency is compared with control frequency, and center with center. If the control frequencies differ, a DFS event has occurred.

   Note: UISP's `overview.frequency` from `/devices` is the *current* operating frequency, so it follows the radio after a DFS move and cannot be used as the configured value.
2. **Report** — The assistant tells you which APs shifted, what channels they moved to, and whether action is needed.
3. **Reset** — `reset_device` reboots the AP (with your confirmation), forcing it back to its configured frequency.
4. **Verify** — `detect_dfs` again to confirm the device returned to the correct channel.

## Tools

| Tool | Description |
|------|-------------|
| `detect_dfs(identifier)` | Compare configured (UISP wireless config) vs. actual (device) control/center frequency; flag DFS radar events |
| `reset_device(identifier)` | Reboot a device to restore its configured frequency (requires confirmation) |
| `list_devices(site?)` | List managed devices from UISP, optionally filtered by site |
| `get_device(identifier)` | Get details for a specific device by name, IP, or UISP ID |
| `get_clients(ip)` | Get connected stations/CPEs from an AP, sorted by signal strength |
| `get_device_stats(ip)` | Get system health: CPU, memory, temperature, uptime |
| `sweep_clients(site?)` | Concurrent scan of all APs to collect a unified client table |
| `health_check()` | Check that UISP is reachable and the API token works; report response time, device count, and whether airOS credentials are configured |

## Setup

### Prerequisites

- A UISP NMS instance with API access
- airOS 8.x devices managed by UISP
- Python 3.11+

### Configuration

Copy the example config and fill in your UISP details:

```bash
cd mcp-server
cp config.json.example config.json
```

```json
{
  "uisp_url": "https://uisp.yourdomain.com",
  "uisp_token": "your-uisp-api-key",
  "airos_username": "ubnt",
  "airos_password": "your-password"
}
```

All settings can also be set via environment variables with the `WISP_` prefix (e.g., `WISP_UISP_URL`, `WISP_UISP_TOKEN`).

### Run Locally

```bash
cd mcp-server
pip install -r requirements.txt
python server.py
```

This starts the MCP server over stdio, ready for a local MCP client.

### Run with Docker

```bash
cd mcp-server
docker compose up -d
```

This runs the server over HTTP on port 8080 inside the container, published on the host at `127.0.0.1:18083`.

In HTTP mode the server also answers `GET /health` with `{"status": "ok", "server": "dfs-reset"}`. It makes no UISP or device calls, so it is safe for uptime monitors and reverse-proxy checks, and `docker compose` uses it as the container healthcheck. To check UISP connectivity and the API token, call the `health_check` tool.

### Connect to Claude Desktop

Add to your Claude Desktop MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "dfs-reset": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "/path/to/wisp-reset-airos-mcp/mcp-server",
      "env": {
        "WISP_UISP_URL": "https://uisp.yourdomain.com",
        "WISP_UISP_TOKEN": "your-api-key"
      }
    }
  }
}
```

## Safety

The server is designed with operator safety in mind:

- **`reset_device` never runs without confirmation.** The assistant is instructed to always ask before rebooting.
- **Detection is read-only.** `detect_dfs` and all other diagnostic tools make no changes to your devices.
- **Sweeps tolerate partial failures.** If some APs are unreachable, the sweep returns results for the rest rather than failing entirely.

## Project Structure

```
mcp-server/
  server.py           # FastMCP entry point
  config.py           # Configuration management
  clients/
    uisp.py           # UISP NMS API client
    airos.py          # Direct airOS device client
  tools/
    nms.py            # list_devices, get_device, reset_device
    radio.py          # detect_dfs, get_clients, get_device_stats
    sweep.py          # sweep_clients
    health.py         # health_check, GET /health
skill/
  SKILL.md            # Claude skill definition with workflows and guidelines
  examples/           # Example tool flows for common scenarios
```

## License

MIT
