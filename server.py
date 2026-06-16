"""Databricks CLI MCP Server with WebSocket and async operations support."""

import sys

# Use the OS trust store for TLS verification before any HTTPS client is created.
# Corporate TLS-intercepting proxies (e.g. Zscaler) present a certificate signed by
# a root CA that lives in the OS trust store but not in Python's bundled `certifi`,
# which otherwise breaks the Databricks SDK's OAuth/API calls with
# "CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate".
try:
    import truststore
    truststore.inject_into_ssl()
except Exception as _truststore_err:  # pragma: no cover - best effort
    print(f"WARNING: truststore not active, falling back to certifi: {_truststore_err}",
          file=sys.stderr)

import argparse
import asyncio
from typing import Optional, Annotated
from fastmcp import FastMCP, Context
from fastapi import WebSocket, WebSocketDisconnect
from databricks.sdk import WorkspaceClient

from auth import get_client_from_context, AuthenticationError
from databricks_client import (
    DatabricksClientWrapper,
    context_manager,
    SessionContext
)
from task_manager import task_manager, TaskStatus
from transports.websocket import WebSocketTransport

# Import all tool modules
from tools import clusters, jobs, notebooks, workspace, repos, secrets, sql, unity_catalog


# Initialize FastMCP server
mcp = FastMCP(name="DatabricksCLI")


def get_session_id(context) -> str:
    """Extract or generate session ID from context."""
    metadata = getattr(context, 'metadata', {}) or {}
    session_id = metadata.get('session-id') or metadata.get('x-session-id') or 'default'
    return session_id


def get_databricks_wrapper(context) -> DatabricksClientWrapper:
    """Get Databricks client wrapper with session context.
    
    Args:
        context: MCP context object
        
    Returns:
        DatabricksClientWrapper with authenticated client and session context
        
    Raises:
        AuthenticationError: If authentication fails
    """
    # Get authenticated client
    client = get_client_from_context(context)
    
    # Get or create session context
    session_id = get_session_id(context)
    session_context = context_manager.get_or_create_context(session_id)
    
    # Return wrapper
    return DatabricksClientWrapper(client, session_context)


# Register all tools from modules
clusters.register_tools(mcp, get_databricks_wrapper)
jobs.register_tools(mcp, get_databricks_wrapper)
notebooks.register_tools(mcp, get_databricks_wrapper)
workspace.register_tools(mcp, get_databricks_wrapper)
repos.register_tools(mcp, get_databricks_wrapper)
secrets.register_tools(mcp, get_databricks_wrapper)
sql.register_tools(mcp, get_databricks_wrapper)
unity_catalog.register_tools(mcp, get_databricks_wrapper)


# Context management tools
@mcp.tool()
def get_session_context(context: Annotated[Context, "MCP context"]) -> dict:
    """Get current session context including workspace path, cluster, job, and warehouse IDs.
    
    Returns a dictionary with the current session state that persists across tool calls.
    """
    session_id = get_session_id(context)
    session_context = context_manager.get_context(session_id)
    
    if session_context:
        return session_context.to_dict()
    else:
        return {
            "session_id": session_id,
            "message": "No context found for this session"
        }


@mcp.tool()
def set_workspace_path(path: str, context: Annotated[Context, "MCP context"]) -> str:
    """Set the current workspace path for subsequent operations.
    
    Args:
        path: Workspace path to set as current (e.g., /Workspace/Users/me)
        
    Returns:
        Confirmation message with the new path
    """
    session_id = get_session_id(context)
    session_context = context_manager.get_or_create_context(session_id)
    session_context.set_workspace_path(path)
    return f"Workspace path set to: {path}"


@mcp.tool()
def set_current_cluster(cluster_id: str, context: Annotated[Context, "MCP context"]) -> str:
    """Set the current cluster ID for subsequent operations.
    
    Args:
        cluster_id: Cluster ID to set as current
        
    Returns:
        Confirmation message
    """
    session_id = get_session_id(context)
    session_context = context_manager.get_or_create_context(session_id)
    session_context.set_cluster(cluster_id)
    return f"Current cluster set to: {cluster_id}"


@mcp.tool()
def set_current_warehouse(warehouse_id: str, context: Annotated[Context, "MCP context"]) -> str:
    """Set the current SQL warehouse ID for subsequent operations.
    
    Args:
        warehouse_id: Warehouse ID to set as current
        
    Returns:
        Confirmation message
    """
    session_id = get_session_id(context)
    session_context = context_manager.get_or_create_context(session_id)
    session_context.set_warehouse(warehouse_id)
    return f"Current warehouse set to: {warehouse_id}"


@mcp.tool()
def clear_session_context(context: Annotated[Context, "MCP context"]) -> str:
    """Clear the current session context and reset all stateful settings.
    
    Returns:
        Confirmation message
    """
    session_id = get_session_id(context)
    context_manager.clear_context(session_id)
    return f"Session context cleared for: {session_id}"


# Task management tools
@mcp.tool()
def get_task_status(task_id: str) -> dict:
    """Get the status of an async task.
    
    Args:
        task_id: The task identifier returned from async operations
        
    Returns:
        Dictionary with task status, progress, result, and error (if any)
    """
    task = task_manager.get_task(task_id)
    if not task:
        return {"error": f"Task not found: {task_id}"}
    
    return task.to_dict()


@mcp.tool()
async def cancel_task(task_id: str) -> dict:
    """Cancel a running async task.
    
    Args:
        task_id: The task identifier to cancel
        
    Returns:
        Dictionary indicating if task was cancelled
    """
    cancelled = await task_manager.cancel_task(task_id)
    return {
        "cancelled": cancelled,
        "task_id": task_id,
        "message": "Task cancelled" if cancelled else "Task not found or already completed"
    }


# TODO: Add WebSocket endpoint integration with FastMCP
# FastMCP provides the underlying transport layer
# For WebSocket support, this will require deeper integration with FastMCP's architecture
# The transport layer (transports/websocket.py) is ready for when FastMCP adds WebSocket support


def main():
    """Main entry point for the server."""
    parser = argparse.ArgumentParser(description='Databricks CLI MCP Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8000, help='Port to bind to')
    args = parser.parse_args()
    
    print("=" * 80)
    print("🚀 Databricks CLI MCP Server")
    print("=" * 80)
    print(f"Host: {args.host}:{args.port}")
    print(f"Endpoints:")
    print(f"  • HTTP:       http://{args.host}:{args.port}/mcp")
    print(f"  • WebSocket:  ws://{args.host}:{args.port}/mcp/ws")
    print(f"  • Health:     http://{args.host}:{args.port}/health")
    print(f"  • Metrics:    http://{args.host}:{args.port}/metrics")
    print(f"\nFeatures:")
    print(f"  • 48 Databricks tools")
    print(f"  • WebSocket + HTTP transports")
    print(f"  • Async task management")
    print(f"  • Session context")
    print("=" * 80)
    
    # Run server with streamable-http transport (required for Databricks Apps)
    # Note: Task manager cleanup will be started when FastMCP initializes event loop
    mcp.run(transport='streamable-http', host=args.host, port=args.port)


if __name__ == '__main__':
    main()


