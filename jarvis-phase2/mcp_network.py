"""Loopback-only, bearer-protected HTTP and WebSocket transports for Jarvis MCP.

The existing SSH/stdio transport remains in mcp_server.py. No tool or database
permission is changed here. The bearer value is read from a root-owned file and
never written to a response or log.
"""

from __future__ import annotations

import hmac
import os

import anyio
import uvicorn
from mcp import types
from mcp.shared.message import SessionMessage
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from mcp_server import mcp


TOKEN_FILE = os.environ.get("JARVIS_MCP_TOKEN_FILE", "/etc/lcarlie/jarvis-mcp-token")
BIND_HOST = "127.0.0.1"
PORT = int(os.environ.get("JARVIS_MCP_PORT", "8765"))


def _load_token() -> bytes:
    with open(TOKEN_FILE, "rb") as handle:
        token = handle.read().strip()
    if len(token) < 32 or any(c in token for c in (b"\r", b"\n")):
        raise RuntimeError("MCP token file is missing a valid token")
    return token


TOKEN = _load_token()


def _authorized(headers: list[tuple[bytes, bytes]]) -> bool:
    values = [value for name, value in headers if name.lower() == b"authorization"]
    if len(values) != 1 or not values[0].startswith(b"Bearer "):
        return False
    return hmac.compare_digest(values[0][7:], TOKEN)


async def websocket_mcp(websocket: WebSocket) -> None:
    await websocket.accept()
    to_server, from_client = anyio.create_memory_object_stream[SessionMessage | Exception](0)
    to_client, from_server = anyio.create_memory_object_stream[SessionMessage](0)

    async def reader() -> None:
        async with to_server:
            try:
                async for payload in websocket.iter_text():
                    try:
                        message = types.jsonrpc_message_adapter.validate_json(payload, by_name=False)
                        await to_server.send(SessionMessage(message))
                    except Exception as exc:  # malformed JSON-RPC is handled by MCP  # noqa: BLE001
                        await to_server.send(exc)
            except WebSocketDisconnect:
                pass

    async def writer() -> None:
        async with from_server:
            async for session_message in from_server:
                await websocket.send_text(
                    session_message.message.model_dump_json(by_alias=True, exclude_unset=True)
                )

    async with anyio.create_task_group() as group:
        group.start_soon(reader)
        group.start_soon(writer)
        group.start_soon(
            mcp._lowlevel_server.run,
            from_client,
            to_client,
            mcp._lowlevel_server.create_initialization_options(),
        )


app = mcp.streamable_http_app(host=BIND_HOST, streamable_http_path="/mcp")
app.router.routes.append(WebSocketRoute("/ws", websocket_mcp))


async def authenticated_app(scope, receive, send):
    if scope["type"] not in ("http", "websocket"):
        await app(scope, receive, send)
        return
    if not _authorized(scope.get("headers", [])):
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"text/plain"),
                                    (b"www-authenticate", b"Bearer")]})
            await send({"type": "http.response.body", "body": b"Unauthorized"})
        else:
            await send({"type": "websocket.close", "code": 1008})
        return
    await app(scope, receive, send)


if __name__ == "__main__":
    uvicorn.run(authenticated_app, host=BIND_HOST, port=PORT, access_log=False,
                log_level="warning")
