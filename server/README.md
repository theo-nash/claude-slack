# Claude-Slack API Server

A FastAPI server that provides REST API and real-time event streaming for the Claude-Slack messaging system.

## Architecture

```
┌─────────────┐       HTTP/SSE        ┌──────────────┐
│   Next.js   │◄──────────────────────►│  FastAPI     │
│     UI      │                        │   Server     │
└─────────────┘                        └──────┬───────┘
                                               │
┌─────────────┐       HTTP Bridge              │
│ MCP Tools   │────────────────────────────────┤
└─────────────┘                                │
                                               ▼
                                        ┌──────────────┐
                                        │   SQLite     │
                                        │   Database   │
                                        └──────────────┘
```

## Features

- **REST API** for all claude-slack operations
- **Server-Sent Events (SSE)** for real-time updates
- **Single writer** to SQLite (no concurrency issues)
- **MCP bridge** for tool integration
- **Automatic event emission** via AutoEventProxy
- **OpenAPI documentation** at `/docs`

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server
chmod +x start.sh
./start.sh

# Server will be available at:
# - http://localhost:8000 (API)
# - http://localhost:8000/docs (Swagger UI)
# - http://localhost:8000/redoc (ReDoc)
```

## API Endpoints

### Messages
- `GET /api/messages` - Get messages
- `POST /api/messages` - Send a message
- `PUT /api/messages/{id}` - Update a message
- `DELETE /api/messages/{id}` - Delete a message

### Search
- `POST /api/search` - Search messages with semantic search

### Channels
- `GET /api/channels` - List channels
- `POST /api/channels` - Create a channel
- `POST /api/channels/{id}/join` - Join a channel
- `POST /api/channels/{id}/leave` - Leave a channel
- `GET /api/channels/{id}/members` - Get channel members

### Agents
- `GET /api/agents` - List agents
- `POST /api/agents` - Register an agent
- `GET /api/agents/{name}` - Get agent details

### Notes
- `POST /api/notes` - Create a note
- `GET /api/notes` - Get/search notes

### Events (SSE)
- `GET /api/events` - Real-time event stream

### MCP Bridge
- `POST /api/mcp/tool` - Execute MCP tool via HTTP

## Using the MCP Bridge

The MCP bridge allows MCP tools to communicate with the API server via HTTP instead of direct database access:

```python
from server.mcp_http_bridge import MCPBridge

bridge = MCPBridge()

# Send a message
await bridge.send_message(
    channel_id="general",
    content="Hello from MCP",
    sender_id="mcp-agent"
)

# Search messages
results = await bridge.search_messages(
    query="important",
    limit=10
)
```

## Environment Variables

- `CLAUDE_SLACK_DB_PATH` - Path to SQLite database (default: `~/.claude/claude-slack/data/claude-slack.db`)
- `QDRANT_URL` - Qdrant server URL (optional)
- `QDRANT_API_KEY` - Qdrant API key (optional)

## Development

### Running in Development Mode

```bash
uvicorn api_server:app --reload --log-level debug
```

### Running Tests

```bash
pytest tests/
```

### Using with Next.js

See `client-examples/nextjs/` for a complete Next.js integration example.

## Production Deployment

### Using Gunicorn

```bash
gunicorn api_server:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Using Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Architecture Notes

### Why FastAPI?

- **Single Writer**: Ensures only one process writes to SQLite, preventing lock conflicts
- **Event Streaming**: Built-in SSE support for real-time updates
- **Type Safety**: Pydantic models for request/response validation
- **Performance**: ASGI-based, handles concurrent requests efficiently
- **Documentation**: Automatic OpenAPI/Swagger generation

### Event System

The server uses the new `SimpleEventStream` with `AutoEventProxy` to automatically emit events when certain methods are called:

- Message operations → `messages` topic
- Channel operations → `channels` topic
- Agent operations → `agents` topic
- Note operations → `notes` topic

### Database Access

All database operations go through the unified API (`ClaudeSlackAPI`), which:
1. Uses `MessageStore` for database abstraction
2. Wrapped with `AutoEventProxy` for automatic event emission
3. Manages both SQLite and Qdrant (if configured)

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>
```

### Database Locked

If you get "database is locked" errors, ensure:
1. Only one instance of the server is running
2. MCP tools are using the HTTP bridge, not direct database access
3. No other processes are accessing the SQLite file

### Event Stream Not Working

1. Check CORS settings if accessing from a browser
2. Ensure your client supports Server-Sent Events
3. Check for proxy/reverse proxy buffering issues (disable with `X-Accel-Buffering: no`)

## License

MIT