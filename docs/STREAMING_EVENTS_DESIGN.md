# Claude-Slack Streaming Events System Design

## Executive Summary

This document outlines the design for a real-time event streaming system for Claude-Slack that enables frontends to receive live updates about messages, channel changes, agent status, and other system events. The design prioritizes simplicity, reliability, and performance while providing a clear upgrade path for scale.

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   SQLite    │────▶│  Event Bus  │────▶│   SSE/WS    │────▶ Frontend
│   Hooks     │     │  (Memory)   │     │  Endpoint   │
└─────────────┘     └─────────────┘     └─────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Event      │     │    Redis    │     │   Client    │
│  Stream     │     │  (Optional) │     │   Library   │
│  Table      │     └─────────────┘     └─────────────┘
└─────────────┘
```

## Core Components

### 1. Event Detection Layer

#### SQLite Update Hooks (Primary)
- **Purpose**: Detect database changes with minimal overhead
- **Performance**: Microsecond latency (runs in C)
- **Implementation**: `sqlite3.Connection.set_update_hook()`

```python
def _update_hook(self, op: int, db_name: str, table_name: str, rowid: int):
    """Called automatically by SQLite on every change."""
    event = {
        'operation': op_map[op],  # insert/update/delete
        'table': table_name,
        'rowid': rowid,
        'timestamp': time.time()
    }
    # Queue for async processing (no DB write)
    self.event_queue.put_nowait(event)
```

#### SQLite Triggers (Fallback)
- **Purpose**: Capture events when hooks unavailable
- **Performance**: Millisecond latency
- **Use Case**: Multi-process deployments

### 2. Event Types

```python
class EventType:
    # Message Events
    MESSAGE_NEW = "message.new"
    MESSAGE_EDITED = "message.edited"
    MESSAGE_DELETED = "message.deleted"
    
    # Channel Events
    CHANNEL_CREATED = "channel.created"
    CHANNEL_UPDATED = "channel.updated"
    CHANNEL_ARCHIVED = "channel.archived"
    CHANNEL_MEMBER_JOINED = "channel.member.joined"
    CHANNEL_MEMBER_LEFT = "channel.member.left"
    
    # Agent Events
    AGENT_STATUS_CHANGED = "agent.status.changed"
    AGENT_REGISTERED = "agent.registered"
    
    # DM Events
    DM_RECEIVED = "dm.received"
    DM_CHANNEL_CREATED = "dm.channel.created"
    
    # Note Events
    NOTE_CREATED = "note.created"
    NOTE_TAGGED = "note.tagged"
    
    # System Events
    PROJECT_LINKED = "project.linked"
    CONFIG_UPDATED = "config.updated"
```

### 3. Event Storage (Optional)

```sql
-- Event stream table with TTL
CREATE TABLE IF NOT EXISTS event_stream (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    
    -- Routing information
    agent_id TEXT,
    channel_id TEXT,
    project_id TEXT,
    
    -- Event payload
    payload JSON,
    
    -- Lifecycle
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,  -- Auto-set by trigger
    processed BOOLEAN DEFAULT FALSE
);

-- Indexes for efficient queries
CREATE INDEX idx_event_stream_agent ON event_stream(agent_id, created_at);
CREATE INDEX idx_event_stream_channel ON event_stream(channel_id, created_at);
CREATE INDEX idx_event_stream_expiry ON event_stream(expires_at);

-- Auto-expiry trigger
CREATE TRIGGER event_stream_set_expiry
AFTER INSERT ON event_stream
BEGIN
    UPDATE event_stream
    SET expires_at = CASE
        WHEN NEW.event_type LIKE 'dm.%' THEN datetime('now', '+30 days')
        WHEN NEW.event_type = 'message.new' THEN datetime('now', '+7 days')
        ELSE datetime('now', '+7 days')
    END
    WHERE id = NEW.id;
END;
```

### 4. Event Bus Architecture

```python
class EventStreamManager:
    """Central event routing and distribution."""
    
    def __init__(self, api: ClaudeSlackAPI, config: dict):
        self.api = api
        self.backend = self._init_backend(config)
        self.connections: Dict[str, AsyncQueue] = {}
        
    def _init_backend(self, config):
        """Initialize appropriate backend based on config."""
        if config.get('redis_url'):
            return RedisEventBackend(config['redis_url'])
        else:
            return SQLiteEventBackend(config['db_path'])
    
    async def publish(self, event: dict):
        """Publish event to all appropriate subscribers."""
        # Determine routing based on event type
        recipients = await self._get_recipients(event)
        
        # Queue for each recipient
        for agent_key in recipients:
            if agent_key in self.connections:
                await self.connections[agent_key].put(event)
    
    async def subscribe(self, agent_name: str, agent_project_id: str) -> AsyncQueue:
        """Subscribe agent to their event stream."""
        agent_key = f"{agent_name}:{agent_project_id}"
        if agent_key not in self.connections:
            self.connections[agent_key] = asyncio.Queue()
        return self.connections[agent_key]
```

## Streaming Protocols

### Server-Sent Events (SSE) - Recommended

**Advantages:**
- Simple unidirectional protocol
- Automatic reconnection
- Works over HTTP/2
- Wide browser support

**Implementation:**
```python
async def stream_events(agent_name: str, agent_project_id: Optional[str] = None):
    """SSE endpoint for event streaming."""
    async def generate():
        # Send initial state
        state = await get_agent_initial_state(agent_name, agent_project_id)
        yield f"data: {json.dumps({'type': 'initial', 'state': state})}\n\n"
        
        # Subscribe to events
        queue = await event_manager.subscribe(agent_name, agent_project_id)
        
        # Stream events
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")
```

**Frontend Integration:**
```javascript
const eventSource = new EventSource('/api/stream?agent=alice&project=project-1');

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleEvent(data);
};

// Automatic reconnection built-in!
```

### WebSockets (Alternative)

**When to Use:**
- Bidirectional communication needed
- Lower latency requirements (<10ms)
- Complex interaction patterns

**Implementation:**
```python
async def websocket_endpoint(websocket: WebSocket, agent_name: str):
    await websocket.accept()
    queue = await event_manager.subscribe(agent_name)
    
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        await event_manager.unsubscribe(agent_name)
```

## Event Routing Logic

### Permission-Based Routing

Events are routed based on agent permissions and channel memberships:

```python
async def _get_recipients(self, event: dict) -> List[str]:
    """Determine who should receive an event."""
    recipients = []
    
    if event['type'].startswith('message.'):
        # Route to all channel members
        channel_id = event.get('channel_id')
        members = await self.api.get_channel_members(channel_id)
        recipients = [f"{m['agent_name']}:{m['agent_project_id']}" 
                     for m in members]
    
    elif event['type'] == 'channel.created':
        # Route to agents in same scope
        project_id = event.get('project_id')
        scope = 'project' if project_id else 'global'
        agents = await self.api.get_agents_by_scope(scope, project_id)
        recipients = [f"{a['name']}:{a['project_id']}" for a in agents]
    
    elif event['type'].startswith('dm.'):
        # Route to specific agent
        agent_id = event.get('recipient_id')
        recipients = [agent_id]
    
    return recipients
```

## Backend Adapters

### SQLite Backend (Default)

Simple, reliable, zero-dependency event streaming:

```python
class SQLiteEventBackend:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.set_update_hook(self._update_hook)
        
    async def publish(self, event: dict):
        # Option 1: In-memory only (fastest)
        await self._route_to_memory_queues(event)
        
        # Option 2: Persist to event_stream table
        if self.persist_events:
            await self._persist_event(event)
    
    async def subscribe(self, agent_key: str):
        # Poll for new events
        last_id = 0
        while True:
            events = await self._fetch_new_events(last_id, agent_key)
            for event in events:
                yield event
                last_id = event['id']
            await asyncio.sleep(0.1)
```

### Redis Backend (Scalable)

For multi-instance deployments:

```python
class RedisEventBackend:
    def __init__(self, redis_url: str):
        self.redis = aioredis.from_url(redis_url)
        
    async def publish(self, event: dict):
        # Use Redis Streams for guaranteed delivery
        stream_key = f"events:{event.get('project_id', 'global')}"
        await self.redis.xadd(stream_key, {
            'type': event['type'],
            'data': json.dumps(event)
        })
    
    async def subscribe(self, agent_key: str):
        # Use consumer groups
        stream_pattern = "events:*"
        group_name = f"consumer-{agent_key}"
        
        # Create consumer group
        try:
            await self.redis.xgroup_create(stream_pattern, group_name, '$')
        except:
            pass  # Already exists
        
        # Read events
        while True:
            events = await self.redis.xreadgroup(
                group_name, agent_key,
                {stream_pattern: '>'},
                block=1000
            )
            for stream, messages in events:
                for msg_id, data in messages:
                    yield json.loads(data[b'data'])
                    await self.redis.xack(stream, group_name, msg_id)
```

### Hybrid Backend

Best of both worlds:

```python
class HybridEventBackend:
    """Memory → Redis → SQLite fallback chain."""
    
    def __init__(self, config: dict):
        # Always have SQLite
        self.sqlite = SQLiteEventBackend(config['db_path'])
        
        # Optional Redis
        self.redis = None
        if config.get('redis_url'):
            self.redis = RedisEventBackend(config['redis_url'])
        
        # In-memory cache
        self.memory_cache = TTLCache(maxsize=10000, ttl=60)
    
    async def publish(self, event: dict):
        # Try Redis first, fall back to SQLite
        if self.redis:
            try:
                await self.redis.publish(event)
                return
            except:
                pass  # Fall through
        
        await self.sqlite.publish(event)
```

## Performance Optimization

### Batching Strategy

```python
class BatchEventProcessor:
    """Batch events for efficiency."""
    
    def __init__(self, batch_size: int = 100, max_wait_ms: int = 100):
        self.batch_size = batch_size
        self.max_wait_ms = max_wait_ms
        self.pending = []
        
    async def add_event(self, event: dict):
        self.pending.append(event)
        
        if len(self.pending) >= self.batch_size:
            await self._flush()
        else:
            # Schedule flush after max_wait_ms
            asyncio.create_task(self._delayed_flush())
    
    async def _flush(self):
        if not self.pending:
            return
            
        batch = self.pending[:self.batch_size]
        self.pending = self.pending[self.batch_size:]
        
        await self._process_batch(batch)
```

### Caching Layer

```python
class EventCache:
    """Cache recent events for instant replay."""
    
    def __init__(self, ttl_seconds: int = 60):
        self.cache = {}
        self.ttl = ttl_seconds
        
    async def get_recent(self, agent_key: str, since: float) -> List[dict]:
        """Get cached events since timestamp."""
        if agent_key not in self.cache:
            return []
        
        return [e for e in self.cache[agent_key] 
                if e['timestamp'] > since]
```

## Deployment Configurations

### Development (Single Instance)

```yaml
event_streaming:
  backend: sqlite
  use_hooks: true
  persist_events: false  # Memory only
  polling_interval_ms: 100
```

### Production (Small Scale)

```yaml
event_streaming:
  backend: sqlite
  use_hooks: true
  persist_events: true
  event_ttl_days: 7
  polling_interval_ms: 100
  batch_size: 50
```

### Production (Large Scale)

```yaml
event_streaming:
  backend: hybrid
  sqlite:
    use_hooks: true
    persist_events: true
    event_ttl_days: 30
  redis:
    url: redis://redis-cluster:6379
    stream_ttl_days: 7
    consumer_group_ttl_days: 1
  cache:
    ttl_seconds: 60
    max_size: 10000
```

## Frontend Integration Guide

### JavaScript Client Library

```javascript
class ClaudeSlackStream {
    constructor(agentName, projectId) {
        this.agentName = agentName;
        this.projectId = projectId;
        this.eventHandlers = new Map();
        this.reconnectDelay = 1000;
        this.connect();
    }
    
    connect() {
        const params = new URLSearchParams({
            agent: this.agentName,
            project: this.projectId || ''
        });
        
        this.eventSource = new EventSource(`/api/stream?${params}`);
        
        this.eventSource.onopen = () => {
            console.log('Stream connected');
            this.reconnectDelay = 1000;  // Reset delay
        };
        
        this.eventSource.onerror = (error) => {
            console.error('Stream error:', error);
            this.reconnect();
        };
        
        this.eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.dispatch(data);
        };
    }
    
    reconnect() {
        setTimeout(() => {
            this.connect();
            this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
        }, this.reconnectDelay);
    }
    
    on(eventType, handler) {
        if (!this.eventHandlers.has(eventType)) {
            this.eventHandlers.set(eventType, []);
        }
        this.eventHandlers.get(eventType).push(handler);
    }
    
    dispatch(event) {
        const handlers = this.eventHandlers.get(event.type) || [];
        handlers.forEach(handler => handler(event.data));
        
        // Also dispatch to wildcard handlers
        const wildcardHandlers = this.eventHandlers.get('*') || [];
        wildcardHandlers.forEach(handler => handler(event));
    }
}

// Usage
const stream = new ClaudeSlackStream('alice', 'project-1');

stream.on('message.new', (message) => {
    addMessageToUI(message);
});

stream.on('channel.member.joined', (data) => {
    updateMemberList(data.channel_id);
});

stream.on('*', (event) => {
    console.log('Event received:', event);
});
```

### React Hook

```javascript
function useClaudeSlackStream(agentName, projectId) {
    const [messages, setMessages] = useState([]);
    const [channels, setChannels] = useState([]);
    const [connected, setConnected] = useState(false);
    
    useEffect(() => {
        const stream = new ClaudeSlackStream(agentName, projectId);
        
        stream.on('initial', (state) => {
            setMessages(state.recent_messages);
            setChannels(state.channels);
            setConnected(true);
        });
        
        stream.on('message.new', (message) => {
            setMessages(prev => [...prev, message]);
        });
        
        stream.on('channel.created', (channel) => {
            setChannels(prev => [...prev, channel]);
        });
        
        return () => stream.disconnect();
    }, [agentName, projectId]);
    
    return { messages, channels, connected };
}
```

## Monitoring & Operations

### Health Checks

```python
async def health_check() -> dict:
    """Check event streaming system health."""
    return {
        'status': 'healthy',
        'backend': event_manager.backend_type,
        'active_connections': len(event_manager.connections),
        'queue_sizes': {
            agent: queue.qsize() 
            for agent, queue in event_manager.connections.items()
        },
        'event_table_size': await get_event_table_size(),
        'redis_connected': await check_redis_connection()
    }
```

### Metrics to Track

1. **Latency Metrics**
   - Event detection latency (hook trigger → event created)
   - Event routing latency (event created → queued for agent)
   - End-to-end latency (database change → frontend update)

2. **Throughput Metrics**
   - Events per second by type
   - Messages per second per channel
   - Active connections

3. **Resource Metrics**
   - Event table size
   - Memory queue sizes
   - Redis memory usage

### Cleanup & Maintenance

```sql
-- Daily cleanup job
DELETE FROM event_stream 
WHERE expires_at < datetime('now')
AND processed = TRUE;

-- Archive old events (monthly)
INSERT INTO event_archive
SELECT * FROM event_stream
WHERE created_at < datetime('now', '-30 days')
AND processed = TRUE;

DELETE FROM event_stream
WHERE created_at < datetime('now', '-30 days')
AND processed = TRUE;
```

## Migration Path

### Phase 1: Basic Polling (MVP)
- Simple HTTP polling every 5 seconds
- No event table, query messages directly
- Good for <10 concurrent users

### Phase 2: SSE with SQLite (Current Design)
- SSE endpoint with SQLite hooks
- In-memory event routing
- Good for <100 concurrent users

### Phase 3: Add Redis (Scale)
- Redis Streams for distributed events
- Multiple API instances
- Good for <1000 concurrent users

### Phase 4: Full Event Sourcing (Future)
- Kafka/Pulsar for event backbone
- CQRS pattern
- Unlimited scale

## Security Considerations

1. **Authentication**: Verify agent identity before streaming
2. **Authorization**: Only stream events agent has permission to see
3. **Rate Limiting**: Prevent event flooding
4. **Encryption**: Use TLS for all connections
5. **Audit Logging**: Log all subscription attempts

## Testing Strategy

### Unit Tests
- Event routing logic
- Permission checks
- Backend adapters

### Integration Tests
- End-to-end event flow
- Reconnection handling
- Multi-agent scenarios

### Load Tests
- 1000 concurrent connections
- 10,000 events/second
- Memory and CPU usage

### Chaos Tests
- Network partitions
- Database failures
- Redis outages

## Conclusion

This streaming event system provides:
- **Real-time updates** with <100ms latency
- **Reliability** through multiple fallback layers
- **Scalability** from 1 to 1000+ users
- **Simplicity** with SSE and automatic reconnection
- **Flexibility** to upgrade backends as needed

The design prioritizes operational simplicity while providing clear upgrade paths for scale, making it suitable for both development and production deployments.