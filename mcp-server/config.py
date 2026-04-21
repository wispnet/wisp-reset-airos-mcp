"""Configuration for the dfs-reset MCP server."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DeviceCredentials:
    username: str
    password: str


@dataclass
class WispConfig:
    uisp_url: str
    uisp_token: str
    airos_username: str = "ubnt"
    airos_password: str = "ubnt"
    airos_ssl_verify: bool = False
    sweep_concurrency: int = 10
    sweep_timeout: int = 15
    device_overrides: dict[str, DeviceCredentials] = field(default_factory=dict)

    def get_device_credentials(self, ip: str) -> tuple[str, str]:
        """Return (username, password) for a device, using overrides if present."""
        if ip in self.device_overrides:
            creds = self.device_overrides[ip]
            return creds.username, creds.password
        return self.airos_username, self.airos_password


def load_config() -> WispConfig:
    """Load configuration from config.json and/or WISP_* environment variables."""
    config_path = os.environ.get("WISP_CONFIG_PATH", "config.json")
    file_data: dict = {}

    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            file_data = json.load(f)

    # Environment variables override file values (WISP_ prefix)
    env_map = {
        "WISP_UISP_URL": "uisp_url",
        "WISP_UISP_TOKEN": "uisp_token",
        "WISP_AIROS_USERNAME": "airos_username",
        "WISP_AIROS_PASSWORD": "airos_password",
        "WISP_AIROS_SSL_VERIFY": "airos_ssl_verify",
        "WISP_SWEEP_CONCURRENCY": "sweep_concurrency",
        "WISP_SWEEP_TIMEOUT": "sweep_timeout",
    }

    for env_key, config_key in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            file_data[config_key] = val

    # Validate required fields
    uisp_url = file_data.get("uisp_url")
    uisp_token = file_data.get("uisp_token")

    if not uisp_url or not uisp_token:
        print(
            "Error: uisp_url and uisp_token are required.\n"
            "Set them in config.json or via WISP_UISP_URL / WISP_UISP_TOKEN env vars.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Parse device overrides
    raw_overrides = file_data.get("device_overrides", {})
    overrides = {}
    for ip, creds in raw_overrides.items():
        overrides[ip] = DeviceCredentials(
            username=creds.get("username", "ubnt"),
            password=creds.get("password", "ubnt"),
        )

    # Parse boolean/int fields
    ssl_verify = file_data.get("airos_ssl_verify", False)
    if isinstance(ssl_verify, str):
        ssl_verify = ssl_verify.lower() in ("true", "1", "yes")

    concurrency = int(file_data.get("sweep_concurrency", 10))
    timeout = int(file_data.get("sweep_timeout", 15))

    return WispConfig(
        uisp_url=uisp_url,
        uisp_token=uisp_token,
        airos_username=file_data.get("airos_username", "ubnt"),
        airos_password=file_data.get("airos_password", "ubnt"),
        airos_ssl_verify=ssl_verify,
        sweep_concurrency=concurrency,
        sweep_timeout=timeout,
        device_overrides=overrides,
    )
