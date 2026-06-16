#!/usr/bin/env python3
"""Stdio entry point for the Databricks MCP server (Claude Code / local MCP clients).

`server.py` runs the same tools over the streamable-http transport (for
Databricks Apps deployment). Claude Code, however, launches local MCP servers
as a subprocess and talks to them over **stdio**. This shim reuses the exact
same FastMCP `mcp` instance — with all tool modules already registered in
server.py — and runs it over stdio instead.

Auth is taken from the environment (DATABRICKS_HOST + DATABRICKS_CLIENT_ID/
DATABRICKS_CLIENT_SECRET for OAuth M2M, or DATABRICKS_TOKEN for a PAT). When
launched via `uv run --env-file .env mcp_stdio.py`, those come from .env.
"""

from server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
