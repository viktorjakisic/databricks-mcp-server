# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An MCP server exposing ~50 Databricks workspace operations (clusters, jobs, SQL, Unity Catalog, workspace files, notebooks, repos, secrets) as tools, built on **FastMCP** + the **Databricks SDK**. Not an official Databricks product.

## Commands

Dependencies are managed with `uv` (see `uv.lock`); `requirements.txt` exists for pip-based deploys.

```bash
uv sync                                      # install (incl. dev extras: pytest, ruff, black, mypy)

# Run the server — all entry points share the same tools, differing only by transport:
uv run --env-file .env mcp_stdio.py          # stdio — for Claude Code / local MCP clients (this is how it's wired here)
uv run --env-file .env python server.py --port 8000   # streamable-http — for Databricks Apps / remote clients
python local_mcp_server.py                   # streamable-http on :8080, PAT from env (Cursor-oriented)

# Quality
ruff check .          # lint  (line-length 100, E501 ignored)
black .               # format (line-length 100)
mypy .                # type check

# Tests
pytest                          # configured: testpaths=tests/, asyncio_mode=auto
pytest tests/test_deployed_now.py::test_deployed_mcp   # single test
```

Note: `tests/` and `test_local.py` are **live integration tests** that hit a real/deployed Databricks workspace via the SDK (and need extra deps like `databricks_mcp`, `mcp`). They are not hermetic unit tests — expect them to require working credentials and network access.

## Architecture

**One server, many entry points.** `server.py` builds the single `FastMCP` instance named `mcp`, registers every tool on it, and is the source of truth. The other top-level files are thin shims that import that same `mcp` and only choose a transport:
- `mcp_stdio.py` → `mcp.run(transport="stdio")` — **the active path for Claude Code** (configured globally as the `databricks` MCP server: `uv run --directory <repo> --env-file <repo>/.env mcp_stdio.py`).
- `server.py:main()` → `streamable-http` (CLI flags `--host/--port`).
- `app.py` → exposes `mcp.streamable_http_app` as an ASGI app; `app.yaml` runs it via `uvicorn app:app` on Databricks Apps.
- `local_mcp_server.py` → `streamable-http` on :8080, forces PAT creds into `os.environ`.

When adding tools or changing tool wiring, edit `server.py` (and the relevant `tools/` module) — the change automatically applies to all transports.

**Tool registration pattern.** Each module in `tools/` (`clusters`, `jobs`, `notebooks`, `workspace`, `repos`, `secrets`, `sql`, `unity_catalog`) exposes a `register_tools(mcp, get_wrapper)` function. `server.py` calls each one, passing its `get_databricks_wrapper` factory. Inside, tools are inner functions decorated with `@mcp.tool()` that take a trailing `context=None` parameter (FastMCP injects the MCP context) and call `get_wrapper(context)` to obtain an authenticated client. To add a tool: add it to the relevant module's `register_tools`, or create a new module and register it in `server.py`.

**Authentication (`auth.py`).** `get_client_from_context(context)` → `extract_auth_from_context(context)` resolves credentials in a fixed order:
1. **Environment variables first** (`_credentials_from_env`) — `DATABRICKS_HOST` + `DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET` (OAuth M2M) or `DATABRICKS_HOST` + `DATABRICKS_TOKEN` (PAT). Used by the stdio/local entry points.
2. **Per-request headers** (`_credentials_from_context`) — `x-databricks-host` + `x-databricks-client-id`/`-client-secret` or `-token`. Used by the HTTP transport for multi-tenant use.

OAuth M2M is **preferred over PAT** whenever both are present. Because env is checked first, setting credentials in `.env` overrides any per-request headers — relevant when debugging "wrong credentials" vs "missing credentials."

**TLS / corporate proxy ordering constraint.** `server.py` calls `truststore.inject_into_ssl()` at the very top, *before importing the Databricks SDK or any HTTPS client*. This makes Python verify against the **OS trust store** instead of bundled `certifi`, which is required behind TLS-intercepting proxies (e.g. Zscaler) — otherwise OAuth/API calls fail with `CERTIFICATE_VERIFY_FAILED`. Do not move this below the SDK imports. (An alternative/complementary setup is pointing `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` at a PEM bundle containing the proxy root CA.)

**Stateful session context (`databricks_client.py`).** A process-global `context_manager` (in-memory `ContextManager`) maps a session id → `SessionContext` holding a "current" workspace path, cluster, job, and warehouse. `DatabricksClientWrapper` wraps the SDK client plus that context. SQL/cluster tools fall back to these "current" values when an id isn't passed (e.g. `set_current_warehouse` then `execute_query` without `warehouse_id`). Session id comes from `session-id`/`x-session-id` metadata, defaulting to `'default'` — so over stdio everything shares one `'default'` session.

**Async tasks (`task_manager.py`).** In-memory `task_manager` for long-running operations, surfaced via the `get_task_status` / `cancel_task` tools; entries auto-expire after ~1 hour. Also in-memory, so state is lost on restart.

**Not wired up.** `transports/websocket.py` exists but FastMCP WebSocket integration is a TODO in `server.py` — there is currently no WebSocket endpoint. `tool_registry.py` (MCP→OpenAI/Anthropic schema converter) is a standalone utility, not part of the request path.

## Conventions

- Tools return plain `dict`s (JSON-serializable), typically including a `count` alongside list results.
- `auth.py` normalizes a bare host into `https://...` via `_normalize_host`; pass hosts with or without scheme.
- `.env` is git-ignored and contains live credentials — never commit it; `.env.example` documents the variables.
