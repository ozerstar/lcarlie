"""Create private, single-node LiveKit credentials and network config once."""
from __future__ import annotations

import grp
import os
from pathlib import Path
import secrets
import sys


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: create_livekit_config.py DIRECTORY PUBLIC_IP")
    directory = Path(sys.argv[1])
    public_ip = sys.argv[2]
    if not public_ip.replace(".", "").isdigit() or public_ip.count(".") != 3:
        raise SystemExit("expected an IPv4 address")
    directory.mkdir(mode=0o750, parents=True, exist_ok=True)
    config = directory / "config.yaml"
    environment = directory / "agent.env"
    if config.exists() or environment.exists():
        raise SystemExit("existing LiveKit credentials were left unchanged")
    key = "jv" + secrets.token_hex(10)
    secret = secrets.token_hex(32)
    config.write_text(
        "port: 7880\nrtc:\n"
        f"  node_ip: {public_ip}\n"
        "  udp_port: 7882\n  tcp_port: 7881\n"
        f"keys:\n  {key}: {secret}\n",
        encoding="utf-8",
    )
    environment.write_text(
        "LIVEKIT_URL=ws://127.0.0.1:7880\n"
        f"LIVEKIT_API_KEY={key}\nLIVEKIT_API_SECRET={secret}\n",
        encoding="utf-8",
    )
    os.chmod(config, 0o600)
    os.chown(environment, 0, grp.getgrnam("jarvis-web").gr_gid)
    os.chmod(environment, 0o640)


if __name__ == "__main__":
    main()
