# Databricks MCP Server
A production-ready MCP server that exposes 50+ Databricks workspace operations through the MCP for AI agents like Cursor, Claude Desktop, and more.

> **⚠️ DISCLAIMER**: This is **NOT** an official Databricks product and is **NOT** supported by Databricks. This is a community project that uses the Databricks SDK to provide MCP integration. Use at your own risk. For official Databricks support, please contact Databricks directly.

## 🚀 Quick Start — Claude Code (stdio)

This is the primary, recommended local setup: Claude Code launches the server as a stdio
subprocess and credentials come from a `.env` file.

### 1. Set Your Credentials

Copy `.env.example` to `.env` and fill it in. OAuth M2M (service principal) is preferred:

```bash
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_CLIENT_ID=<service-principal-application-id>
DATABRICKS_CLIENT_SECRET=<oauth-secret>
# — or, instead of the two lines above, a PAT:
# DATABRICKS_TOKEN=dapi...
```

### 2. Register the MCP Server

Add to your MCP client config (e.g. `~/.claude.json` under `mcpServers`):

```json
{
  "mcpServers": {
    "databricks": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory", "/path/to/databricks-mcp-server",
        "--env-file", "/path/to/databricks-mcp-server/.env",
        "mcp_stdio.py"
      ]
    }
  }
}
```

`uv run --env-file .env mcp_stdio.py` loads `.env`, starts the FastMCP server over stdio, and
`auth.py` resolves the credentials from the environment automatically.

### 3. Start Using!

```
"List my Databricks catalogs"
"Show me my SQL warehouses"
"Execute query: SELECT * FROM samples.nyctaxi.trips LIMIT 10"
```

### Alternative: HTTP transport (Cursor, remote clients)

For Cursor or any client that connects over HTTP, run the server with the streamable-http
transport instead and point the client at the URL:

```bash
uv run --env-file .env python server.py --port 8000   # serves http://localhost:8000/mcp
# or, PAT-from-env convenience wrapper on :8080:
python local_mcp_server.py
```

```json
{
  "mcpServers": {
    "databricks": { "url": "http://localhost:8000/mcp" }
  }
}
```

Over HTTP you can also pass credentials per request as `x-databricks-host` +
`x-databricks-client-id`/`x-databricks-client-secret` (or `x-databricks-token`) headers
instead of using `.env`.

---

## 📦 What You Get

### 50 Databricks Tools

- **Clusters** (7): Create, start, stop, list, manage
- **Jobs** (6): Create, run, cancel, monitor
- **SQL** (8): Execute queries, manage warehouses
- **Unity Catalog** (11): Catalogs, schemas, tables, volumes
- **Workspace** (6): Files, notebooks, directories
- **Notebooks** (5): Import, export, run
- **Repos** (5): Git integration
- **Secrets** (4): Secret management
- **Tasks** (2): Async operations

---

## 🏗️ Project Structure

```
databricks_cli_mcp/
├── README.md              # This file
├── server.py              # FastMCP server + tool registration (streamable-http transport)
├── mcp_stdio.py           # stdio entry point (Claude Code / local MCP clients)
├── app.py                 # ASGI app for Databricks Apps (uvicorn app:app)
├── local_mcp_server.py    # Local HTTP server with PAT auth
├── start_local_mcp.sh     # Quick start script
│
├── auth.py                # Authentication logic
├── databricks_client.py   # Databricks SDK wrapper
├── task_manager.py        # Async task management
├── tool_registry.py       # Tool schema converter
│
├── tools/                 # 50 Databricks tools
│   ├── clusters.py
│   ├── jobs.py
│   ├── sql.py
│   ├── unity_catalog.py
│   ├── workspace.py
│   ├── notebooks.py
│   ├── repos.py
│   └── secrets.py
│
├── app.yaml               # Databricks Apps deployment config
├── requirements.txt       # Python dependencies
└── pyproject.toml         # Package configuration
```

---

## 🔐 Authentication

### Option 1: PAT (Personal Access Token) — simplest

**Best for**: Quick experiments, personal use. Note PATs expire (90 days) and must be renewed manually.

```bash
# Get your PAT from Databricks UI
# Settings → Developer → Access tokens → Generate new token

export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="dapi..."

./start_local_mcp.sh
```

**Pros**: ✅ Simple, ✅ Quick, ✅ Works immediately  
**Cons**: ⚠️ 90-day expiry, ⚠️ Manual renewal

### Option 2: M2M OAuth (recommended)

**Best for**: Production, teams, CI/CD — and the default for the local stdio setup above (auto-refreshing, no manual token renewal).

1. Create service principal in Databricks
2. Generate OAuth secret
3. Set environment variables:

```bash
export DATABRICKS_APP_URL="https://your-app.databricksapps.com"
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_CLIENT_ID="<service-principal-id>"
export DATABRICKS_CLIENT_SECRET="<oauth-secret>"

./start_oauth_proxy.sh
```

**Pros**: ✅ Auto-refresh, ✅ Better security, ✅ Team sharing  
**Cons**: ⚠️ Requires service principal setup

> **Local / stdio server (e.g. Claude Code):** `auth.py` reads `DATABRICKS_CLIENT_ID` +
> `DATABRICKS_CLIENT_SECRET` (M2M) or `DATABRICKS_TOKEN` (PAT) directly from the
> environment — typically via `uv run --env-file .env mcp_stdio.py`. No OAuth proxy is
> needed for local use; the same credentials can also be supplied per-request over the
> HTTP transport as `x-databricks-client-id` / `x-databricks-client-secret` (or
> `x-databricks-token`) headers.

---

## ☁️ Deploy to Databricks Apps

### 1. Authenticate

```bash
databricks auth login
```

### 2. Deploy

```bash
./deploy_correct.sh
```

### 3. Get Your App URL

```bash
databricks apps get databricks-mcp-server | jq -r .url
```

---

## 🧪 Testing

### Test Locally

```bash
python test_local.py
```

### Test from Notebook

Upload `notebooks/simple_test.py` to Databricks and run it.

---

## 💡 Example Usage

### In Cursor

```
"Create a cluster named 'test' with 2 workers"
"Start cluster 0730-172948-runts698"
"Execute SQL: SELECT current_database()"
"List tables in catalog main"
"Export notebook /Users/me/analysis"
"Show me my job runs"
```

### Programmatically

```python
from databricks.sdk import WorkspaceClient

client = WorkspaceClient()

# List clusters
clusters = list(client.clusters.list())
print(f"Found {len(clusters)} clusters")

# Execute SQL
result = client.sql.execute_query(
    warehouse_id="abc123",
    query="SELECT * FROM samples.nyctaxi.trips LIMIT 10"
)
```

---

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABRICKS_HOST` | Workspace URL | ✅ Yes |
| `DATABRICKS_TOKEN` | Personal Access Token | ✅ Yes (PAT mode) |
| `DATABRICKS_CLIENT_ID` | Service principal ID | For OAuth |
| `DATABRICKS_CLIENT_SECRET` | OAuth secret | For OAuth |
| `DATABRICKS_APP_URL` | Deployed app URL | For OAuth |

### Server Configuration

The server runs on port `8080` by default. Change in `start_local_mcp.sh`:

```bash
python3 local_mcp_server.py --port 8080
```

---

## 🐛 Troubleshooting

### Server won't start

```bash
# Check if port is in use
lsof -i :8080

# Kill existing process
kill -9 <PID>

# Restart
./start_local_mcp.sh
```

### Authentication failed

```bash
# Verify credentials
echo $DATABRICKS_HOST
echo $DATABRICKS_TOKEN

# Test manually
curl -H "Authorization: Bearer $DATABRICKS_TOKEN" \
  $DATABRICKS_HOST/api/2.0/clusters/list
```

### TLS error: `CERTIFICATE_VERIFY_FAILED` behind a corporate proxy

If auth fails with `SSL: CERTIFICATE_VERIFY_FAILED — unable to get local issuer
certificate`, you're behind a TLS-intercepting proxy (e.g. **Zscaler**) whose root CA
is trusted by your OS but not by Python's bundled `certifi`. The server calls
`truststore.inject_into_ssl()` at startup so Python verifies against the **OS trust
store** — just ensure the `truststore` dependency is installed (`uv sync` /
`pip install -r requirements.txt`). If you manage certificates manually instead, point
`SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` at a PEM bundle containing the proxy's root CA.

### Cursor not connecting

1. Check server is running: `curl http://localhost:8080/health`
2. Verify Cursor config: `cat ~/.cursor/mcp.json`
3. Restart Cursor
4. Check logs: `tail -f mcp_server.log`

### Permission errors

- **Can't create clusters?** Ask your admin for permissions
- **Can't access catalogs?** Check Unity Catalog permissions
- **Can't run queries?** Verify SQL warehouse access

---

## 📚 Key Concepts

### MCP (Model Context Protocol)

An open protocol that lets AI assistants connect to external data sources and tools. Think of it as "API for AIs".

### FastMCP

A Python framework for building MCP servers. Makes it easy to expose Python functions as tools for AI agents.

### Databricks SDK

Official Python library for interacting with Databricks APIs. Powers all the tools in this server.

---

## 🔗 Resources

- **Databricks API Docs**: https://docs.databricks.com/api/
- **MCP Protocol**: https://modelcontextprotocol.io/
- **FastMCP**: https://github.com/jlowin/fastmcp
- **Databricks SDK**: https://github.com/databricks/databricks-sdk-py

---

## 📝 Requirements

- Python 3.11+
- Databricks workspace with API access
- Personal Access Token or Service Principal
- Cursor IDE (or any MCP-compatible client)

---

## 🎯 Common Tasks

### Start a cluster

```python
# In Cursor
"Start cluster <cluster-id>"

# Or directly
from databricks.sdk import WorkspaceClient
client = WorkspaceClient()
client.clusters.start(cluster_id="...")
```

### Run a SQL query

```python
# In Cursor
"Execute query: SELECT * FROM my_table LIMIT 10"

# Or directly
result = client.sql.execute_query(
    warehouse_id="...",
    query="SELECT * FROM my_table"
)
```

### Create a job

```python
# In Cursor
"Create a job that runs notebook /path/to/notebook daily"

# Or use the Databricks UI - easier for complex jobs!
```

---

## ⚙️ Advanced Configuration

### Custom Tools

Add your own tools in `tools/` directory:

```python
# tools/custom.py
from fastmcp import Context

@mcp.tool()
async def my_custom_tool(param: str, context: Context):
    """My custom Databricks operation."""
    client = get_databricks_client(context)
    # Your logic here
    return {"result": "success"}
```

Then register in `server.py`:

```python
from tools import custom
```

### Production Deployment

For production use:
1. Use M2M OAuth (not PAT)
2. Deploy to Databricks Apps
3. Enable monitoring (`/metrics` endpoint)
4. Set up proper logging
5. Configure auto-scaling

---

## 🎉 Success!

You now have a fully functional Databricks MCP server! 

**Next steps**:
1. ✅ Start the server
2. ✅ Configure Cursor  
3. ✅ Try listing your clusters
4. ✅ Execute your first SQL query
5. 🚀 Automate all the things!

---

## 📄 License

MIT

## 🤝 Contributing

Issues and PRs welcome! This project follows standard GitHub workflow.

## 💬 Support

- Check logs: `tail -f mcp_server.log`
- Review error messages in Cursor
- Verify Databricks permissions
- Test API access directly with `curl`

---

**Built with ❤️ for Databricks automation**
