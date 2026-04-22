---
name: dfs-reset
description: Detect DFS radar events and reset Ubiquiti airOS devices to restore configured frequencies, managed by UISP NMS
---

# DFS Reset Tools

You have access to tools for detecting DFS (Dynamic Frequency Selection) radar events on a WISP network and resetting affected devices to restore their configured frequencies. The network runs Ubiquiti airOS/airMAX access points managed by UISP NMS.

## What is a DFS Event?

When an airOS access point operating on a DFS-required channel (typically 5.2–5.6 GHz) detects radar, it is legally required to vacate that channel immediately. The device auto-selects a different frequency — but this new channel may cause interference with neighboring APs, degrade client performance, or conflict with your frequency plan. A **reset** (reboot) forces the device back to its originally configured frequency.

## Core Workflow: Detect → Report → Reset → Verify

1. **Detect** — Use `detect_dfs` on an AP to compare its configured vs. actual frequency
2. **Report** — Tell the operator which APs shifted and what channels they moved to
3. **Reset** — Use `reset_device` (with operator confirmation) to reboot the AP back to its configured frequency
4. **Verify** — After ~60 seconds, use `detect_dfs` again to confirm the device returned to the correct channel

## Tool Reference

### DFS Detection

**`detect_dfs(identifier)`**
The primary detection tool. Accepts a device name, IP address, or UISP ID. Resolves to the management IP automatically, then connects directly to the device and compares its actual operating frequency against the UISP-configured frequency.
- `configured_mhz`: What UISP says the device should be on
- `actual_mhz`: What the device is actually running on
- `dfs_event`: `true` if configured ≠ actual — the device was forced to a different channel by radar detection
- Also returns `channel_width_mhz`, `center_freq_mhz`, and `ieee_mode`

### Device Reset

**`reset_device(identifier)`**
Restart a device via UISP to restore its configured frequency. **Always confirm with the operator before calling this.** The device will reboot and re-initialize on its configured channel. Accepts device name or IP.

### Inventory & Lookup (via UISP NMS)

**`list_devices(site=None)`**
List all managed devices. Filter by site name (partial match). Returns: name, model, IP, site, status, firmware, configured frequency.

**`get_device(identifier)`**
Get detail for one device. Accepts device name (case-insensitive), IP address, or UISP ID. Returns full device summary.

### Supporting Radio Tools (direct airOS connection)

**`get_clients(identifier)`**
Get the station table from an AP — all connected CPEs/clients. Accepts a device name, IP, or UISP ID. Sorted by signal strength (strongest first). Each entry includes MAC, IP, signal (dBm), noise floor (dBm), RSSI, distance, uptime, and remote hostname.

**`get_device_stats(identifier)`**
Get system health: hostname, model, firmware, uptime, CPU load, memory usage, temperature. Accepts a device name, IP, or UISP ID.

**`sweep_clients(site=None)`**
Sweep all APs (optionally filtered by site), connecting to each concurrently to collect client tables. Useful after a DFS reset to verify clients have reconnected. Unreachable APs are included with `status: "error"` — the sweep always returns partial results rather than failing.

## Signal Strength Interpretation (airMAX)

| Range | Quality | Action |
|-------|---------|--------|
| > -65 dBm | Good | Normal operation |
| -65 to -75 dBm | Fair | Acceptable, monitor for degradation |
| -75 to -80 dBm | Poor | Alignment or antenna issue, investigate |
| < -80 dBm | Unusable | Link at risk of dropping, intervention needed |

Noise floor is typically -90 to -95 dBm in clean RF environments. Noise above -85 dBm suggests interference.

## Common Workflows

### "Did any AP hit a DFS event?" (Primary Use Case)
1. `list_devices` to get all APs (or filter by site)
2. `detect_dfs` on each AP
3. Any result where `dfs_event: true` means the AP was forced off its configured channel by radar
4. Report which APs are affected, their configured frequency, and what channel they moved to
5. If the operator wants to restore frequencies → proceed to the reset workflow below

### "Reset an AP after a DFS event"
1. `detect_dfs` to confirm the DFS event (configured ≠ actual)
2. Present findings to the operator: device name, configured frequency, current frequency
3. **Ask the operator to confirm the reset** — never reset without explicit approval
4. `reset_device` to reboot the AP
5. Wait ~60 seconds
6. `detect_dfs` again to verify the device returned to its configured frequency
7. Optionally `get_clients` to verify clients reconnected with acceptable signal levels

### "Frequency audit — are all APs on their assigned channels?"
1. `list_devices` to get all APs (or filter by site)
2. `detect_dfs` on each AP
3. Build a report of configured vs. actual frequencies across the network
4. Flag any mismatches — whether caused by DFS or other frequency drift

### "Why is customer X slow?"
1. `get_device` with the customer's AP name to find its IP
2. `detect_dfs` to check if the AP shifted channels (frequency change can cause performance issues)
3. `get_clients` on that AP IP to find the customer's CPE by MAC or hostname
4. Check their signal, noise floor, and distance
5. If the AP is on a DFS-shifted channel, a reset may resolve the issue

### "Post-reset verification"
1. After resetting a device, wait ~60 seconds
2. `detect_dfs` to confirm it returned to the configured frequency
3. `get_clients` to verify clients reconnected
4. `get_device_stats` to confirm the device is healthy (CPU, memory, temperature normal)

### "Is this device healthy?"
1. `get_device_stats` for system health
2. Check CPU (>80% sustained = overloaded), memory, temperature
3. Check uptime — very short uptime may indicate crash/reboot loops or recent DFS resets

## Safety Rules

1. **Never reset without operator confirmation.** Always present the device name, current frequency, and configured frequency before calling `reset_device`.
2. **Don't sweep and reset in the same action.** If detection reveals DFS events, report findings first — let the operator decide which devices to reset.
3. **DFS events are informational until acted on.** The device auto-selected a new channel and is still operational. Only reset if the new channel is causing problems (interference, poor client signals, frequency plan conflicts).
4. **Verify after every reset.** Always run `detect_dfs` after a reset to confirm the device returned to its configured frequency.
5. **Partial sweep results are normal.** Some APs may be temporarily unreachable. Don't alarm the operator unless many APs fail simultaneously.

## Network Context

<!-- Fill in your network-specific details below -->
<!--
- Site naming convention: e.g., "TOWER-01", "POP-EAST"
- VLAN scheme: e.g., management on VLAN 10, customer traffic on VLAN 100+
- Frequency plan: e.g., 5 GHz backhaul, 5 GHz PtMP access
- DFS channels in use: e.g., 5500, 5520, 5580 MHz
- Non-DFS channels available: e.g., 5745, 5785, 5805 MHz
- Typical AP models: e.g., Rocket 5AC Prism, LiteAP AC
- Typical CPE models: e.g., NanoStation 5AC, LiteBeam 5AC
- Reset policy: e.g., "reset DFS-affected APs during maintenance windows only"
-->
