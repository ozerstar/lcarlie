"""Live loopback transport check. Prints statuses only; never prints bearer values."""

import base64
import json
import os
import socket
import struct

import requests


HOST = "127.0.0.1"
PORT = 8765
TOKEN = open("/etc/lcarlie/jarvis-mcp-token", encoding="ascii").read().strip()
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-03-26", "capabilities": {},
    "clientInfo": {"name": "jarvis-transport-check", "version": "1"}}}


def http_case(label, bearer, expected):
    headers = {"Accept": "application/json, text/event-stream",
               "Content-Type": "application/json"}
    if bearer is not None:
        headers["Authorization"] = "Bearer " + bearer
    response = requests.post(f"http://{HOST}:{PORT}/mcp", headers=headers,
                             json=INIT, timeout=8)
    assert response.status_code == expected, (label, response.status_code)
    if expected == 200:
        assert '"result"' in response.text and '"serverInfo"' in response.text
    print("HTTP", label, response.status_code)


def recv_until(sock, marker):
    data = b""
    while marker not in data:
        data += sock.recv(4096)
        if len(data) > 65536:
            raise AssertionError("handshake too large")
    return data


def websocket_case(label, bearer, expected):
    with socket.create_connection((HOST, PORT), timeout=8) as sock:
        sock.settimeout(8)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        lines = ["GET /ws HTTP/1.1", f"Host: {HOST}:{PORT}", "Upgrade: websocket",
                 "Connection: Upgrade", f"Sec-WebSocket-Key: {key}",
                 "Sec-WebSocket-Version: 13"]
        if bearer is not None:
            lines.append("Authorization: Bearer " + bearer)
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
        handshake = recv_until(sock, b"\r\n\r\n")
        status = int(handshake.split(b" ", 2)[1])
        assert status == expected, (label, status)
        if status == 101:
            payload = json.dumps(INIT).encode("utf-8")
            mask = os.urandom(4)
            length = len(payload)
            if length < 126:
                header = bytes([0x81, 0x80 | length])
            else:
                header = bytes([0x81, 0xFE]) + struct.pack("!H", length)
            sock.sendall(header + mask + bytes(x ^ mask[i % 4]
                                                 for i, x in enumerate(payload)))
            first = sock.recv(2)
            assert first and first[0] & 0x0F == 1, first
            size = first[1] & 0x7F
            if size == 126:
                size = struct.unpack("!H", sock.recv(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", sock.recv(8))[0]
            body = b""
            while len(body) < size:
                body += sock.recv(size - len(body))
            response = json.loads(body)
            assert response.get("id") == 1 and "result" in response
            assert "serverInfo" in response["result"]
        print("WebSocket", label, status)


http_case("no_token", None, 401)
http_case("wrong_token", "invalid-token", 401)
http_case("correct_token", TOKEN, 200)
websocket_case("no_token", None, 403)
websocket_case("wrong_token", "invalid-token", 403)
websocket_case("correct_token", TOKEN, 101)
