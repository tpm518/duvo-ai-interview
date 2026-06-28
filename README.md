# duvo-ai-interview

## Step 1 decisions

- Start with an in-memory `MockStoreLinkClient` instead of an HTTP mock server. The MCP server can call it directly now, and the same method boundary can later be backed by real StoreLink HTTP calls.
- Expose only the StoreLink operations needed for the buyer workflow: list stores, get current on-hand, get recent POS transactions, raise replenishment, and check order status.
- Return plain JSON-serializable dictionaries and lists so MCP tool responses can pass through the data without translation.
- Keep per-store API key loading outside the mock StoreLink client. The MCP server enforces credentials before calling StoreLink so the same boundary can later wrap the real HTTP client.
- Run the local MCP server over stdio from the host Python environment. Docker is the right deployment artifact later, but for local Codex or Claude Code iteration it adds friction without improving the StoreLink mock.

## Step 3 observability decisions

- Write local observability to files, not stdout. The MCP server runs over stdio, so stdout must stay reserved for MCP protocol messages.
- Keep two logs because they serve different readers:
  - `logs/operational.jsonl` is structured tool-call telemetry for an FDE: correlation ID, MCP request ID, tool name, selected business identifiers, status, duration, and error type.
  - `logs/audit.jsonl` is a buyer-facing audit trail: plain-language records of what the agent checked or changed.
- Use the MCP request ID as the correlation ID when FastMCP provides one; otherwise generate one for the tool call. The operational record and audit record for the same tool call share that ID.
- Do not log StoreLink API keys or raw secrets. When the real HTTP client replaces the mock, StoreLink status code and latency should be added to the operational log under the same correlation ID.

## Step 4 credential decisions

- Load StoreLink credentials from one strict JSON file, configured by `STORELINK_CREDENTIALS_PATH`.
- Assume this local server has access to one store: store `47`. The checked-in file uses a mock key only.
- Filter `list_stores` to credentialed stores so the agent sees only stores this server can actually operate on.
- Before any store-scoped StoreLink operation, require credentials for that exact `store_id`. Missing credentials return a structured `missing_store_credentials` error; no fallback key is attempted.
- Reread the credentials file on each credential lookup. If Korral IT rotates the file atomically, the next MCP tool call uses the new key without restarting the server.
- Treat expired credentials as a safe stop before StoreLink is called. Credentials within 24 hours of `expires_at` report `rotation_due` internally so the server can surface that in logs without exposing the key.

Credential file shape:

```json
{
  "stores": {
    "47": {
      "api_key": "mock-storelink-key-store-47",
      "version": "mock-2026-06-24",
      "expires_at": "2030-01-01T00:00:00Z"
    }
  }
}
```

## Mock StoreLink client

```python
from duvo.storelink_mock import MockStoreLinkClient

client = MockStoreLinkClient()
stores = client.get_stores()
inventory = client.get_current_on_hand("47", "8847291")
transactions = client.get_recent_pos_transactions(
    "47",
    "8847291",
    "2026-06-27T09:00:00+00:00",
)
order = client.raise_replenishment("47", "8847291", 24)
status = client.get_order_status("47", order["order_id"])
```

## MCP server

Install the project into a local virtual environment:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run tests with:

```bash
pytest
```

The MCP server entry point is:

```bash
python -m duvo.mcp_server
```

This starts a stdio MCP process, so in normal use the MCP client should spawn it rather than you running it directly in a terminal.

### Local logs

By default the server writes JSONL logs under:

```text
logs/operational.jsonl
logs/audit.jsonl
```

Set `DUVO_LOG_DIR` before starting the MCP server to write logs somewhere else.

### Codex local config

Add this to `~/.codex/config.toml` or `.codex/config.toml` in this trusted project:

```toml
[mcp_servers.korral_storelink]
command = "/Users/tommurray/Documents/projects/duvo/.venv/bin/python"
args = ["-m", "duvo.mcp_server"]
startup_timeout_sec = 20
tool_timeout_sec = 60

[mcp_servers.korral_storelink.env]
STORELINK_CREDENTIALS_PATH = "/Users/tommurray/Documents/projects/duvo/config/storelink_credentials.json"
```

You can also add it with the Codex CLI:

```bash
codex mcp add korral_storelink -- /Users/tommurray/Documents/projects/duvo/.venv/bin/python -m duvo.mcp_server
```

Then restart Codex or open a new session and use `/mcp` to confirm the server is connected.

### Claude Code local config

Claude Code can add the same stdio server with:

```bash
claude mcp add --transport stdio korral_storelink -- /Users/tommurray/Documents/projects/duvo/.venv/bin/python -m duvo.mcp_server
```

Inside Claude Code, use `/mcp` to confirm the server is connected.
