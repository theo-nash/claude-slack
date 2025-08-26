# Claude-Slack v4: Clean Implementation Plan

## Core Philosophy

Claude-slack is **unopinionated infrastructure** for storing and retrieving messages with semantic search capabilities. It provides:
- Message storage (SQLite)
- Vector embeddings (ChromaDB)
- Semantic + keyword search
- Simple channels and notes

Claude-brain handles all intelligence:
- When/how to write reflections
- Insight extraction
- Context aggregation strategies
- Agent behavior patterns

## Architecture Overview

```
claude-slack (Infrastructure)
├── SQLite: Messages, channels, agents
├── ChromaDB: Vector embeddings
└── API: Store, search, retrieve

claude-brain (Intelligence)
├── Reflection generation
├── Insight extraction
├── Context synthesis
└── Agent orchestration
```

## Message Format (Supports Everything)

The existing message table with metadata field handles ALL message types:

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    channel_id TEXT NOT NULL,      -- Regular channel or notes channel
    sender_id TEXT NOT NULL,
    content TEXT NOT NULL,          -- The actual message/reflection text
    metadata JSON,                  -- Flexible: breadcrumbs, confidence, type, etc.
    confidence REAL,                -- Top-level for quick filtering
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Example: Regular Message
```json
{
  "content": "Fixed the authentication bug in PR #123",
  "metadata": {
    "type": "message",
    "mentions": ["@security-reviewer"]
  }
}
```

### Example: Reflection (Just Another Message in Notes Channel)
```json
{
  "content": "Successfully implemented JWT authentication...[full reflection text]",
  "metadata": {
    "type": "reflection",
    "breadcrumbs": {
      "files": ["src/auth.py:45-89", "config/jwt.yaml"],
      "commits": ["abc123", "def456"],
      "decisions": ["stateless-auth", "15min-expiry"],
      "patterns": ["middleware", "decorator"]
    },
    "session_context": "auth-implementation",
    "task_type": "feature",
    "complexity": "medium",
    "outcome": "success"
  },
  "confidence": 0.85
}
```

## Clean Implementation Phases

### Phase 1: Core Infrastructure (Week 1)

**Build the minimal dual-store system**

```python
# hybrid_store.py
class HybridStore:
    def __init__(self):
        self.sqlite = sqlite3.connect("claude-slack.db")
        self.chroma = chromadb.PersistentClient(path="./chroma")
        self.collection = self.chroma.get_or_create_collection("messages")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
    
    async def store_message(self, channel_id: str, sender_id: str, 
                          content: str, metadata: dict = None, 
                          confidence: float = None) -> int:
        # Write to SQLite
        cursor = self.sqlite.execute(
            "INSERT INTO messages (channel_id, sender_id, content, metadata, confidence) "
            "VALUES (?, ?, ?, ?, ?)",
            (channel_id, sender_id, content, json.dumps(metadata), confidence)
        )
        message_id = cursor.lastrowid
        
        # Generate embedding and write to ChromaDB
        embedding = self.embedder.encode(content)
        self.collection.add(
            ids=[str(message_id)],
            embeddings=[embedding],
            metadatas=[{
                "channel_id": channel_id,
                "sender_id": sender_id,
                "confidence": str(confidence or 0),
                "type": metadata.get("type", "message") if metadata else "message",
                "timestamp": datetime.now().isoformat()
            }],
            documents=[content]
        )
        
        return message_id
```

**Deliverables**:
- [ ] Simple SQLite schema (messages, channels, agents)
- [ ] ChromaDB integration
- [ ] Dual-write on every message
- [ ] Basic search (keyword + semantic)

### Phase 2: Search Capabilities with Intelligent Ranking (Week 2)

**Implement search with time decay and multi-factor ranking**

```python
import math
from datetime import datetime, timedelta

class HybridStore:
    async def search(self, 
                     query: str = None,           # Semantic search
                     channel_ids: List[str] = None,
                     sender_ids: List[str] = None,
                     message_type: str = None,     # From metadata
                     min_confidence: float = None,
                     since: datetime = None,
                     limit: int = 20,
                     # Time decay parameters
                     decay_half_life_hours: float = 168,  # 1 week default
                     decay_weight: float = 0.3,            # 30% weight to recency
                     similarity_weight: float = 0.5,       # 50% weight to similarity
                     confidence_weight: float = 0.2        # 20% weight to confidence
                     ) -> List[Message]:
        
        results = []
        
        # Semantic search via ChromaDB if query provided
        if query:
            embedding = self.embedder.encode(query)
            chroma_results = self.collection.query(
                query_embeddings=[embedding],
                n_results=limit * 3,  # Get extra for re-ranking
                where=self._build_where_clause(
                    channel_ids, sender_ids, message_type, min_confidence, since
                )
            )
            message_ids = chroma_results['ids'][0]
            distances = chroma_results['distances'][0]
            
            # Fetch full messages from SQLite and calculate scores
            now = datetime.now()
            scored_results = []
            
            for msg_id, distance in zip(message_ids, distances):
                msg = await self.get_message(int(msg_id))
                
                # Calculate component scores
                similarity_score = 1 - distance  # Convert distance to similarity [0,1]
                confidence_score = msg.get('confidence', 0.5)  # Default 0.5 if not set
                
                # Calculate time decay
                msg_time = datetime.fromisoformat(msg['timestamp'])
                age_hours = (now - msg_time).total_seconds() / 3600
                decay_score = math.exp(-math.log(2) * age_hours / decay_half_life_hours)
                
                # Combine scores with weights (normalized)
                total_weight = similarity_weight + confidence_weight + decay_weight
                final_score = (
                    (similarity_score * similarity_weight +
                     confidence_score * confidence_weight +
                     decay_score * decay_weight) / total_weight
                )
                
                # Add scoring details to message
                msg['search_scores'] = {
                    'final_score': final_score,
                    'similarity': similarity_score,
                    'confidence': confidence_score,
                    'recency': decay_score,
                    'age_hours': age_hours
                }
                
                scored_results.append((final_score, msg))
            
            # Sort by final score and return top results
            scored_results.sort(key=lambda x: x[0], reverse=True)
            results = [msg for _, msg in scored_results[:limit]]
        
        # Pure filter search via SQLite if no query
        else:
            sql = """
                SELECT *, 
                       julianday('now') - julianday(timestamp) as age_days
                FROM messages 
                WHERE 1=1
            """
            params = []
            
            if channel_ids:
                sql += " AND channel_id IN ({})".format(','.join('?' * len(channel_ids)))
                params.extend(channel_ids)
            
            if min_confidence is not None:
                sql += " AND confidence >= ?"
                params.append(min_confidence)
            
            if since:
                sql += " AND timestamp >= ?"
                params.append(since.isoformat())
            
            # Order by recency and confidence for non-semantic search
            sql += " ORDER BY timestamp DESC, confidence DESC LIMIT ?"
            params.append(limit)
            
            cursor = self.sqlite.execute(sql, params)
            results = []
            now = datetime.now()
            
            for row in cursor.fetchall():
                msg = dict(row)
                # Add decay score even for filter-only search
                age_hours = msg['age_days'] * 24
                decay_score = math.exp(-math.log(2) * age_hours / decay_half_life_hours)
                msg['search_scores'] = {
                    'recency': decay_score,
                    'confidence': msg.get('confidence', 0.5),
                    'age_hours': age_hours
                }
                results.append(msg)
        
        return results
    
    def calculate_decay(self, age_hours: float, half_life_hours: float) -> float:
        """
        Calculate exponential decay score based on age.
        
        Args:
            age_hours: Age of the message in hours
            half_life_hours: Half-life for decay calculation
            
        Returns:
            Decay score between 0 and 1 (1 = fresh, 0 = very old)
        """
        return math.exp(-math.log(2) * age_hours / half_life_hours)
```

**Advanced Ranking Options**

```python
class RankingProfiles:
    """Pre-defined ranking profiles for different use cases"""
    
    RECENT_PRIORITY = {
        'decay_half_life_hours': 24,      # Rapid decay - 1 day half-life
        'decay_weight': 0.6,               # 60% weight to recency
        'similarity_weight': 0.3,          # 30% weight to similarity
        'confidence_weight': 0.1           # 10% weight to confidence
    }
    
    QUALITY_PRIORITY = {
        'decay_half_life_hours': 720,     # Slow decay - 30 days half-life
        'decay_weight': 0.1,               # 10% weight to recency
        'similarity_weight': 0.4,          # 40% weight to similarity
        'confidence_weight': 0.5           # 50% weight to confidence
    }
    
    BALANCED = {
        'decay_half_life_hours': 168,     # 1 week half-life
        'decay_weight': 0.33,              # Equal weights
        'similarity_weight': 0.34,
        'confidence_weight': 0.33
    }
    
    SIMILARITY_ONLY = {
        'decay_half_life_hours': 8760,    # 1 year (essentially no decay)
        'decay_weight': 0.0,               # No recency factor
        'similarity_weight': 1.0,          # Pure similarity
        'confidence_weight': 0.0           # No confidence factor
    }

# Usage examples
async def find_recent_decisions(query: str):
    """Find recent decisions - heavily weight recency"""
    return await store.search(
        query=query,
        message_type="decision",
        **RankingProfiles.RECENT_PRIORITY
    )

async def find_best_solutions(query: str):
    """Find high-quality solutions - weight confidence heavily"""
    return await store.search(
        query=query,
        message_type="reflection",
        **RankingProfiles.QUALITY_PRIORITY
    )
```

**Deliverables**:
- [ ] Semantic search with query
- [ ] Filter by channel, sender, type
- [ ] Confidence filtering
- [ ] Temporal filtering
- [ ] Combined semantic + filter search

### Phase 3: Channel Management (Week 3)

**Simple channel system for organization**

```python
class ChannelManager:
    async def create_channel(self, channel_id: str, channel_type: str = "channel"):
        # Just tracks channels, no complex permissions
        pass
    
    async def ensure_notes_channel(self, agent_id: str) -> str:
        # Create/get agent's private notes channel
        channel_id = f"notes:{agent_id}"
        # ... create if not exists
        return channel_id
```

**Channels are just namespaces**:
- Regular channels: `global:general`, `project:backend`
- Notes channels: `notes:agent-name`
- No complex permissions (claude-brain handles access control)

### Phase 4: MCP Tools (Week 4)

**Minimal tool set focused on infrastructure**

```python
# Core Tools Only
async def store_message(channel_id: str, sender_id: str, 
                        content: str, metadata: dict = None,
                        confidence: float = None) -> int:
    """Store any type of message"""
    return await hybrid_store.store_message(...)

async def search_messages(query: str = None,
                         filters: dict = None,
                         limit: int = 20,
                         ranking_profile: str = "balanced") -> List[Message]:
    """
    Unified search with intelligent ranking
    
    Args:
        query: Semantic search query (optional)
        filters: {
            'channel_ids': List[str],
            'sender_ids': List[str], 
            'message_type': str,
            'min_confidence': float,
            'since': datetime
        }
        limit: Maximum results to return
        ranking_profile: One of 'recent', 'quality', 'balanced', 'similarity'
                        Or custom dict with decay/weight parameters
    
    Returns:
        Messages ranked by similarity + confidence + recency
    """
    # Get profile or use custom parameters
    if isinstance(ranking_profile, str):
        params = RankingProfiles.get_profile(ranking_profile)
    else:
        params = ranking_profile
    
    return await hybrid_store.search(
        query=query,
        limit=limit,
        **filters,
        **params
    )

async def get_notes_channel(agent_id: str) -> str:
    """Get agent's notes channel ID"""
    return f"notes:{agent_id}"

async def list_channels(scope: str = "all") -> List[str]:
    """List available channels"""
    return await channel_manager.list_channels(scope)
```

**NOT in claude-slack**:
- ❌ Insight extraction
- ❌ Reflection formatting rules
- ❌ Context aggregation logic
- ❌ Agent behavior patterns

### Phase 5: Performance Optimization (Week 5)

**Ensure infrastructure scales**

```python
# Optimizations
class HybridStore:
    def __init__(self):
        # Connection pooling
        self.sqlite_pool = SqlitePool(max_connections=10)
        
        # Batch embedding generation
        self.embedding_queue = Queue()
        self.start_embedding_worker()
        
        # Caching
        self.search_cache = LRUCache(maxsize=100)
    
    async def batch_embed(self, messages: List[str]):
        # Process multiple messages at once
        embeddings = self.embedder.encode(messages)
        # ... store in ChromaDB
```

**Performance Targets**:
- Message storage: < 50ms
- Semantic search: < 100ms
- Batch operations: 100+ messages/second

## What Claude-Slack v4 IS

✅ **Simple Infrastructure**
- Store messages with metadata
- Generate embeddings automatically
- Search by semantic similarity and/or filters
- Provide channels for organization

✅ **Unopinionated**
- Any message format via metadata field
- No rules about reflection structure
- No insight extraction logic
- No agent behavior enforcement

✅ **Fast & Scalable**
- ChromaDB for vector search
- SQLite for structured queries
- Minimal overhead
- Clear performance targets

## What Claude-Slack v4 IS NOT

❌ **Not Intelligence**
- No insight extraction
- No reflection generation rules
- No context aggregation strategies
- No agent orchestration

❌ **Not Opinionated**
- No required reflection format
- No message type validation
- No workflow enforcement
- No quality scoring logic

## Implementation Timeline

| Week | Focus | Deliverable |
|------|-------|------------|
| 1 | Core | SQLite + ChromaDB dual store |
| 2 | Search | Semantic + filter search |
| 3 | Channels | Simple channel management |
| 4 | API | Minimal MCP tool set |
| 5 | Performance | Optimization & benchmarks |

## Success Metrics

**Infrastructure Performance**:
- Store message: < 50ms
- Search (semantic): < 100ms  
- Search (filters): < 20ms
- Throughput: 100+ msg/sec

**Simplicity**:
- < 1000 lines of core code
- < 5 MCP tools
- No complex business logic
- Clear separation from claude-brain

## Example Usage (from claude-brain)

```python
# claude-brain decides to write a reflection
async def complete_task(task_id: str, outcome: str):
    # Generate reflection (claude-brain logic)
    reflection_content = generate_reflection(task_id, outcome)
    
    # Create breadcrumbs (claude-brain logic)
    breadcrumbs = extract_breadcrumbs(task_context)
    
    # Store in claude-slack (just infrastructure)
    await claude_slack.store_message(
        channel_id=f"notes:{agent_id}",
        sender_id=agent_id,
        content=reflection_content,
        metadata={
            "type": "reflection",
            "breadcrumbs": breadcrumbs,
            "task_id": task_id,
            "outcome": outcome
        },
        confidence=calculate_confidence(outcome)
    )

# claude-brain searches for context with different strategies
async def get_task_context(current_task: str):
    # 1. Find recent similar work (for fresh context)
    recent_similar = await claude_slack.search_messages(
        query=current_task,
        filters={"message_type": "reflection"},
        limit=5,
        ranking_profile="recent"  # Heavy recency weight
    )
    
    # 2. Find high-quality solutions (for best practices)
    best_solutions = await claude_slack.search_messages(
        query=current_task,
        filters={"message_type": "reflection", "min_confidence": 0.8},
        limit=5,
        ranking_profile="quality"  # Heavy confidence weight
    )
    
    # 3. Custom ranking for specific need
    custom_search = await claude_slack.search_messages(
        query=current_task,
        filters={"message_type": "reflection"},
        limit=10,
        ranking_profile={
            'decay_half_life_hours': 48,    # 2 day half-life for urgent task
            'decay_weight': 0.5,             # 50% weight to very recent
            'similarity_weight': 0.4,        # 40% weight to relevance
            'confidence_weight': 0.1         # 10% weight to confidence
        }
    )
    
    # Synthesize multiple perspectives (claude-brain logic)
    context = synthesize_perspectives(
        recent_similar + best_solutions + custom_search
    )
    return context

# Example: Finding relevant decisions that are still valid
async def find_active_decisions(topic: str):
    return await claude_slack.search_messages(
        query=topic,
        filters={"message_type": "decision"},
        ranking_profile={
            'decay_half_life_hours': 720,   # 30 day half-life (decisions age slowly)
            'decay_weight': 0.4,             # Still care about recency
            'similarity_weight': 0.5,        # Most important: relevance
            'confidence_weight': 0.1         # Some weight to confidence
        }
    )
```

## Conclusion

Claude-slack v4 becomes a **thin, fast infrastructure layer** that:
1. Stores messages with flexible metadata
2. Generates embeddings automatically
3. Provides semantic + structured search
4. Offers simple channel organization

All intelligence lives in claude-brain:
- How to format reflections
- When to write them
- How to extract insights
- How to aggregate context

This clean separation allows both projects to evolve independently while maintaining a clear contract through the simple message + metadata structure.