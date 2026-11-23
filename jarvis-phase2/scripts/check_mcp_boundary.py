#!/usr/bin/env python3
"""Local real-SDK stdio check. No database queries or external business actions."""
import asyncio
import json
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    root = Path(__file__).resolve().parents[1]
    params = StdioServerParameters(command=sys.executable, args=[str(root / 'mcp_server.py')])
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            expected = {'sirket_sorgulari', 'sirket_verisi', 'gundem', 'kreatif_performansi'}
            if {tool.name for tool in tools.tools} != expected:
                raise RuntimeError('Unexpected MCP tool set')
            for tool, args, expected_status in (
                ('sirket_verisi', {'sorgu': 'DROP TABLE core.karar'}, 'IZINLI_DEGIL'),
                ('gundem', {'limit': -1}, 'GECERSIZ_ISTEK'),
            ):
                response = await session.call_tool(tool, args)
                if response.is_error or json.loads(response.content[0].text)['durum'] != expected_status:
                    raise RuntimeError('MCP request boundary failed')
    print('PASS: stdio initialization, tool set, allowlist rejection, invalid limit')


if __name__ == '__main__':
    asyncio.run(asyncio.wait_for(main(), timeout=30))
