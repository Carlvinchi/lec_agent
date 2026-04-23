# spike_mcp.py — run once, then delete
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient

async def main():
    client = MultiServerMCPClient({
        "test": {
            "command": "python",
            "args": ["-c", """
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

app = Server("test")

@app.list_tools()
async def list_tools(): return [Tool(name="ping", description="ping", inputSchema={"type":"object","properties":{}})]

@app.call_tool()
async def call_tool(name, arguments): return [TextContent(type="text", text="pong")]

async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

asyncio.run(main())
"""],
            "transport": "stdio",
        }
    })
    tools = await client.get_tools()
    print("MCP spike OK — tools:", [t.name for t in tools])

asyncio.run(main())