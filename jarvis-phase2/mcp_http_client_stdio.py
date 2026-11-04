"""SSH stdio client adapter for the authenticated loopback MCP HTTP endpoint.

Runs on the Jarvis host. The existing remote MCP client retains its stdio
interface, while this adapter reads the bearer from the local protected file.
"""

from __future__ import annotations

import anyio
import httpx2 as httpx
import os
from mcp.client.streamable_http import streamable_http_client
from mcp.server.stdio import stdio_server

from mcp_network import PORT, TOKEN


async def main() -> None:
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + TOKEN.decode("ascii")}) as client:
        async with streamable_http_client(
            f"http://127.0.0.1:{PORT}/mcp", http_client=client
        ) as (remote_read, remote_write):
            async with stdio_server() as (local_read, local_write):
                async with anyio.create_task_group() as group:

                    async def from_local() -> None:
                        async for message in local_read:
                            await remote_write.send(message)
                        group.cancel_scope.cancel()

                    async def from_remote() -> None:
                        async for message in remote_read:
                            if isinstance(message, Exception):
                                raise message
                            await local_write.send(message)

                    async def watch_parent() -> None:
                        # SSH can disappear before stdio reports EOF. Avoid an
                        # idle, root-owned adapter left behind by that client.
                        while True:
                            await anyio.sleep(5)
                            if os.getppid() == 1:
                                group.cancel_scope.cancel()
                                return

                    group.start_soon(from_local)
                    group.start_soon(from_remote)
                    group.start_soon(watch_parent)


if __name__ == "__main__":
    anyio.run(main)
