"""Authentication handler for Databricks MCP Server.

Supports two auth modes, resolved in this order:

1. Environment variables (used by the stdio entry point via `uv run --env-file .env`):
   - OAuth M2M:  DATABRICKS_HOST + DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET
   - PAT:        DATABRICKS_HOST + DATABRICKS_TOKEN
2. Per-request headers (used by the streamable-http transport for multi-tenant use):
   - OAuth M2M:  x-databricks-host + x-databricks-client-id + x-databricks-client-secret
   - PAT:        x-databricks-host + x-databricks-token
"""

import os
import sys
from typing import Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


def _normalize_host(host: str) -> str:
    """Ensure the workspace host has an https:// scheme."""
    if host and not host.startswith("http"):
        host = f"https://{host}"
    return host


def _build_credentials(host: Optional[str],
                       token: Optional[str],
                       client_id: Optional[str],
                       client_secret: Optional[str]) -> Optional[dict]:
    """Assemble Databricks Config kwargs, preferring OAuth M2M over PAT.

    Returns None if `host` is missing or no usable credential pair is present.
    """
    if not host:
        return None
    if client_id and client_secret:
        return {
            "host": _normalize_host(host),
            "client_id": client_id,
            "client_secret": client_secret,
        }
    if token:
        return {
            "host": _normalize_host(host),
            "token": token,
        }
    return None


def _credentials_from_env() -> Optional[dict]:
    """Resolve credentials from environment variables (M2M or PAT)."""
    return _build_credentials(
        host=os.getenv("DATABRICKS_HOST"),
        token=os.getenv("DATABRICKS_TOKEN"),
        client_id=os.getenv("DATABRICKS_CLIENT_ID"),
        client_secret=os.getenv("DATABRICKS_CLIENT_SECRET"),
    )


def _collect_metadata(context) -> dict:
    """Gather request metadata/headers from a FastMCP context object."""
    metadata = {}

    if hasattr(context, "meta"):
        metadata = context.meta or {}
    elif hasattr(context, "metadata"):
        metadata = context.metadata or {}
    elif hasattr(context, "request_context"):
        metadata = getattr(context.request_context, "meta", {}) or {}

    if hasattr(context, "request"):
        headers = getattr(context.request, "headers", {}) or {}
        metadata = {**metadata, **dict(headers)}

    return metadata


def _credentials_from_context(context) -> tuple[Optional[dict], list]:
    """Resolve credentials from request headers (M2M or PAT).

    Returns a tuple of (credentials_or_None, available_keys) so callers can
    surface the keys that *were* present when authentication fails.
    """
    metadata = _collect_metadata(context)
    lower = {str(k).lower(): v for k, v in metadata.items()}

    def pick(*keys):
        for key in keys:
            value = lower.get(key)
            if value:
                return value
        return None

    creds = _build_credentials(
        host=pick("x-databricks-host", "databricks-host"),
        token=pick("x-databricks-token", "databricks-token"),
        client_id=pick("x-databricks-client-id", "databricks-client-id"),
        client_secret=pick("x-databricks-client-secret", "databricks-client-secret"),
    )
    return creds, list(metadata.keys())


def extract_auth_from_context(context) -> dict:
    """Extract Databricks Config kwargs from env vars or MCP context headers.

    Args:
        context: MCP context object containing request metadata

    Returns:
        Dict of Config kwargs (host + token, or host + client_id + client_secret)

    Raises:
        AuthenticationError: If no usable credentials are found
    """
    env_creds = _credentials_from_env()
    if env_creds:
        return env_creds

    header_creds, available_keys = _credentials_from_context(context)
    if header_creds:
        return header_creds

    raise AuthenticationError(
        "Missing Databricks credentials. Provide either OAuth M2M "
        "(DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET) or a PAT "
        "(DATABRICKS_TOKEN), along with DATABRICKS_HOST — via the .env file for "
        "the stdio server, or via x-databricks-* request headers for the HTTP "
        f"transport. Available header keys: {available_keys}"
    )


def create_client(host: str,
                  token: Optional[str] = None,
                  client_id: Optional[str] = None,
                  client_secret: Optional[str] = None) -> WorkspaceClient:
    """Create a Databricks WorkspaceClient for PAT or OAuth M2M auth.

    Args:
        host: Databricks workspace URL (e.g., https://my-workspace.cloud.databricks.com)
        token: Personal access token (PAT auth)
        client_id: Service principal application ID (OAuth M2M auth)
        client_secret: OAuth client secret (OAuth M2M auth)

    Returns:
        Configured WorkspaceClient instance

    Raises:
        AuthenticationError: If no usable credential pair is provided
    """
    config_kwargs = _build_credentials(host, token, client_id, client_secret)
    if not config_kwargs:
        raise AuthenticationError(
            "No usable Databricks credentials: need a PAT (token) or an OAuth "
            "M2M pair (client_id + client_secret) together with a host."
        )
    return WorkspaceClient(config=Config(**config_kwargs))


def get_client_from_context(context) -> WorkspaceClient:
    """Get authenticated Databricks client from MCP context.

    Args:
        context: MCP context object

    Returns:
        Configured WorkspaceClient instance

    Raises:
        AuthenticationError: If authentication fails
    """
    return create_client(**extract_auth_from_context(context))
