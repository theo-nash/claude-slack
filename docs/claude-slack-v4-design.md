# Claude-Slack v4.0 Design Document
## Semantic Knowledge Infrastructure for AI Agent Intelligence

### Document Version
- **Version**: 1.1
- **Date**: January 2025
- **Status**: Final Design (Updated)
- **Authors**: Technical Product Management Team

---

## 1. Executive Summary

Claude-Slack v4.0 represents a fundamental architectural shift from a complex messaging system to a **semantic knowledge infrastructure**. Rather than managing conversations, topics, and state, v4.0 provides simple but powerful primitives for storing and discovering knowledge through semantic search and confidence scoring.

This design employs a **hybrid architecture** using ChromaDB for vector search and SQLite for message storage, enabling sophisticated context discovery while maintaining system simplicity.

### Key Changes from v3.x
- **Removed**: Topics, state tracking, complex relationships, lifecycle management
- **Added**: Vector embeddings (ChromaDB), semantic search, confidence scoring, breadcrumb metadata
- **Simplified**: Channel structure reduced to agent notes and project channels only
- **Philosophy**: Infrastructure for discovery, not orchestration

---

## 2. Problem Statement

### Current Limitations (v3.x)
1. **Over-Structured**: Mandatory topics and state tracking add friction without value
2. **Synchronous Assumptions**: Designed for real-time collaboration that doesn't exist
3. **Complex Maintenance**: Superseding relationships and lifecycle management require constant curation
4. **Discovery Challenges**: Rigid categorization prevents semantic discovery
5. **Central Bottlenecks**: Meta-agent coordination creates impossible omniscience requirements

### Core Challenge
AI agents are **stateless archaeologists** who must discover relevant context from previous work without knowing where it exists or what vocabulary was used to describe it. They cannot ask questions of other agents and must work with whatever artifacts they can discover.

### Success Metric
**Time-to-effectiveness**: How quickly an agent can discover relevant context and become productive on a task.

---

## 3. Solution Overview

### Architectural Principles

1. **Semantic-First Discovery**: Embeddings and similarity search are primary; structure is secondary
2. **Reflection-Based Knowledge**: Agents write complete narratives with breadcrumbs, not fragmented messages
3. **Confidence Over Status**: Quality emerges from confidence scores and temporal decay, not lifecycle management
4. **Multiple Perspectives**: Present diverse viewpoints, don't deduplicate to single "truth"
5. **Trust Agent Intelligence**: Provide rich context, let agents synthesize

### Core Components - Hybrid Architecture

```
┌─────────────────────────────────────────┐
│           Claude-Brain                   │
│     (Intelligence Layer - Separate)      │
│   • Context synthesis                    │
│   • Reflection guidance                  │
│   • Meta-agent curation                  │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│           Claude-Slack v4                │
│      (Infrastructure Layer)              │
├──────────────────────────────────────────┤
│  ChromaDB          │  SQLite             │
│  • Vector storage  │  • Message content  │
│  • Similarity      │  • Breadcrumbs      │
│  • Metadata filter │  • Full metadata    │
│  • Fast search     │  • ACID guarantees  │
└────────────────────────────────────────┘
```

---

## 4. Detailed Requirements

### 4.1 Data Model - Hybrid Storage

#### SQLite: Messages Table (Content Storage)
```sql
CREATE TABLE messages (
    -- Identity
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Location
    channel_id TEXT NOT NULL,           -- Where this knowledge lives
    
    -- Attribution
    sender_id TEXT NOT NULL,            -- Agent who created this
    sender_project_id TEXT,             -- Project context
    
    -- Content
    content TEXT NOT NULL,              -- The actual reflection/insight
    
    -- Quality Signal
    confidence FLOAT DEFAULT 0.5,       -- Quality signal (0.0-1.0)
    
    -- Breadcrumbs (Rich Metadata)
    metadata JSONB,                     -- Rich links to artifacts
    
    -- Temporal
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Optional but Useful
    mentions TEXT[],                    -- Extracted @agent references
    
    -- Indexes
    INDEX idx_channel_time (channel_id, created_at DESC),
    INDEX idx_confidence (confidence DESC),
    INDEX idx_sender (sender_id, created_at DESC)
);
```

#### ChromaDB: Vector Collection (Search Engine)
```python
# ChromaDB Collection Schema
collection = {
    "name": "messages",
    "metadata": {"hnsw:space": "cosine"},
    
    # Each document contains:
    "id": "msg_12345",  # String version of SQLite message.id
    "embedding": [...],  # 768-dimensional vector
    "metadata": {
        # Essential for filtering
        "channel_id": str,       # "agent-notes:backend-eng"
        "channel_type": str,     # "agent-notes" or "project"
        "agent_name": str,       # "backend-eng"
        "project_id": str,       # "proj_abc123" or ""
        
        # Temporal filtering
        "timestamp": float,      # Unix timestamp
        "age_days": int,        # Pre-calculated for convenience
        
        # Quality filtering
        "confidence": float,     # 0.0 to 1.0
        
        # Type filtering
        "message_type": str,    # "reflection", "decision", "pattern"
        
        # Search optimization
        "word_count": int,      # Filter tiny messages
        "has_breadcrumbs": bool # Has artifact links
    }
}
```

#### Channels Table (SQLite - Minimal Structure)
```sql
CREATE TABLE channels (
    id TEXT PRIMARY KEY,                -- e.g., "agent-notes:backend-eng"
    channel_type TEXT NOT NULL,         -- 'agent-notes' or 'project'
    name TEXT NOT NULL,
    description TEXT,
    
    -- For agent notes channels
    owner_agent_name TEXT,               
    owner_agent_project_id TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CHECK (channel_type IN ('agent-notes', 'project'))
);
```

#### Agents Table (SQLite - For Attribution)
```sql
CREATE TABLE agents (
    name TEXT NOT NULL,
    project_id TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP,
    PRIMARY KEY (name, project_id)
);
```

### 4.2 Channel Structure

```
Fixed Channel Types:
├── agent-notes:{agent_name}       # Personal reflections
├── agent-notes:{agent_name}:{project_id}  # Project-specific reflections
├── decisions                      # Architecture/project decisions
├── patterns                       # Proven solutions
└── policies                       # Active constraints

Total: ~4-5 project channels + N agent notes channels
```

### 4.3 Metadata Structure (SQLite JSONB)

```json
{
  "breadcrumbs": {
    "modified_files": ["src/auth/token.py", "src/middleware/auth.py"],
    "created_files": ["docs/auth-pattern.md"],
    "deleted_files": ["src/auth/old_handler.py"],
    "commits": ["abc123", "def456"],
    "pull_requests": ["#567"],
    "issues": ["#1234"],
    "tests": ["tests/auth/test_token.py"],
    "documentation": ["security/policies/token.md", "README.md"],
    "config_files": ["config/auth.yaml", ".env.example"],
    "logs": ["/var/log/auth/errors.log"],
    "external_refs": ["https://datatracker.ietf.org/doc/html/rfc7519"]
  },
  "task_context": {
    "type": "bugfix",              // bugfix, feature, refactor, investigation
    "complexity": "medium",        // low, medium, high
    "duration_minutes": 45,
    "test_results": "passed",
    "blockers_encountered": ["security policy limitation"]
  },
  "extraction_hints": {
    "key_decision": "Chose session cookies over JWT",
    "pattern_identified": "Proactive refresh pattern",
    "policy_discovered": "15 minute TTL limit"
  }
}
```

### 4.4 Core APIs - Hybrid Implementation

#### Writing Operations
```python
class HybridStore:
    def __init__(self):
        self.sqlite = sqlite3.connect("~/.claude/claude-slack/data/claude-slack.db")
        self.chroma = chromadb.PersistentClient(
            path="~/.claude/claude-slack/chroma"
        )
        self.collection = self.chroma.get_or_create_collection(
            name="messages",
            metadata={"hnsw:space": "cosine"}
        )
    
    async def write_note(
        self,
        agent_name: str,
        agent_project_id: Optional[str],
        content: str,
        confidence: float,
        metadata: dict  # Breadcrumbs and context
    ) -> int:
        """
        Writes a reflection to agent's notes channel.
        Stores in SQLite and indexes in ChromaDB.
        """
        # 1. Write to SQLite (source of truth)
        channel_id = f"agent-notes:{agent_name}"
        if agent_project_id:
            channel_id += f":{agent_project_id}"
            
        cursor = self.sqlite.execute(
            """INSERT INTO messages 
               (channel_id, sender_id, sender_project_id, content, confidence, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (channel_id, agent_name, agent_project_id, content, confidence, json.dumps(metadata))
        )
        msg_id = cursor.lastrowid
        
        # 2. Generate embedding
        embedding = await generate_embedding(content)
        
        # 3. Add to ChromaDB for search
        self.collection.add(
            ids=[str(msg_id)],
            embeddings=[embedding],
            metadatas=[{
                "channel_id": channel_id,
                "channel_type": "agent-notes",
                "agent_name": agent_name,
                "project_id": agent_project_id or "",
                "timestamp": datetime.now().timestamp(),
                "confidence": confidence,
                "message_type": "reflection",
                "word_count": len(content.split()),
                "has_breadcrumbs": bool(metadata.get("breadcrumbs"))
            }]
        )
        
        return msg_id
```

#### Discovery Operations
```python
    async def semantic_search(
        self,
        query: str,
        channel_filter: Optional[List[str]] = None,
        exclude_agent: Optional[str] = None,
        min_confidence: Optional[float] = None,
        max_age_days: Optional[int] = None,
        limit: int = 50
    ) -> List[Message]:
        """
        Primary discovery mechanism using ChromaDB for vector search
        and SQLite for content retrieval.
        """
        # 1. Build metadata filter for ChromaDB
        where = {}
        if channel_filter:
            where["channel_id"] = {"$in": channel_filter}
        if exclude_agent:
            where["agent_name"] = {"$ne": exclude_agent}
        if min_confidence:
            where["confidence"] = {"$gte": min_confidence}
        if max_age_days:
            min_timestamp = (datetime.now() - timedelta(days=max_age_days)).timestamp()
            where["timestamp"] = {"$gte": min_timestamp}
        
        # 2. Generate query embedding
        query_embedding = await generate_embedding(query)
        
        # 3. Search ChromaDB with metadata filters
        results = self.collection.query(
            query_embeddings=[query_embedding],
            where=where if where else None,
            n_results=limit,
            include=["metadatas", "distances"]
        )
        
        # 4. Extract message IDs
        if not results['ids'] or not results['ids'][0]:
            return []
        
        message_ids = [int(id) for id in results['ids'][0]]
        distances = results['distances'][0]
        
        # 5. Fetch full messages from SQLite
        placeholders = ','.join(['?' for _ in message_ids])
        cursor = self.sqlite.execute(f"""
            SELECT * FROM messages 
            WHERE id IN ({placeholders})
            ORDER BY created_at DESC
        """, message_ids)
        
        messages = cursor.fetchall()
        
        # 6. Combine with similarity scores
        id_to_similarity = {
            msg_id: (1 - distance)  # Convert distance to similarity
            for msg_id, distance in zip(message_ids, distances)
        }
        
        # 7. Apply temporal decay and ranking
        scored_messages = []
        for msg in messages:
            similarity = id_to_similarity[msg['id']]
            age_days = (datetime.now() - msg['created_at']).days
            recency_score = 0.95 ** age_days
            
            # Combined score: similarity * confidence * recency
            final_score = similarity * msg['confidence'] * recency_score
            
            scored_messages.append({
                'message': msg,
                'score': final_score,
                'similarity': similarity
            })
        
        # 8. Sort by final score
        scored_messages.sort(key=lambda x: x['score'], reverse=True)
        
        return scored_messages
    
    async def get_agent_notes(
        self,
        agent_name: str,
        agent_project_id: Optional[str],
        limit: int = 20
    ) -> List[Message]:
        """Get recent notes from specific agent using SQLite directly."""
        channel_id = f"agent-notes:{agent_name}"
        if agent_project_id:
            channel_id += f":{agent_project_id}"
            
        cursor = self.sqlite.execute("""
            SELECT * FROM messages
            WHERE channel_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (channel_id, limit))
        
        return cursor.fetchall()
    
    async def get_channel_messages(
        self,
        channel_id: str,
        max_age_days: Optional[int] = 30
    ) -> List[Message]:
        """Get project channel messages from SQLite."""
        query = "SELECT * FROM messages WHERE channel_id = ?"
        params = [channel_id]
        
        if max_age_days:
            query += " AND created_at > datetime('now', '-' || ? || ' days')"
            params.append(max_age_days)
            
        query += " ORDER BY created_at DESC"
        
        cursor = self.sqlite.execute(query, params)
        return cursor.fetchall()
```

### 4.5 Embedding Pipeline

```python
class EmbeddingPipeline:
    """Handles embedding generation and storage"""
    
    def __init__(self):
        self.model = "text-embedding-3-small"  # 768 dimensions
        
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using OpenAI or local model"""
        # Implementation depends on chosen embedding service
        pass
        
    async def batch_process(self, messages: List[Message]):
        """
        Batch process messages for efficiency.
        Useful for migration or bulk operations.
        """
        embeddings = await self.generate_batch([m.content for m in messages])
        
        # Add to ChromaDB in batch
        self.collection.add(
            ids=[str(m.id) for m in messages],
            embeddings=embeddings,
            metadatas=[self.extract_metadata(m) for m in messages]
        )
```

### 4.6 Search Ranking

```python
def rank_results(results: List[ChromaResult], current_time: datetime) -> List[ScoredMessage]:
    """
    Ranking formula:
    score = similarity * confidence * recency_decay
    
    Where:
    - similarity: 1 - cosine_distance (from ChromaDB)
    - confidence: Author's confidence (from metadata)
    - recency_decay: 0.95 ^ age_in_days
    
    Note: ChromaDB pre-filters by metadata, so we only rank returned results.
    """
    scored = []
    for result in results:
        similarity = 1 - result.distance  # Convert distance to similarity
        confidence = result.metadata['confidence']
        age_days = (current_time.timestamp() - result.metadata['timestamp']) / 86400
        recency = 0.95 ** age_days
        
        final_score = similarity * confidence * recency
        scored.append(ScoredMessage(result.message, final_score))
    
    return sorted(scored, key=lambda x: x.score, reverse=True)
```

---

## 5. ChromaDB Integration Details

### 5.1 Collection Configuration
```python
# Initialize ChromaDB
chroma_client = chromadb.PersistentClient(
    path="~/.claude/claude-slack/chroma"
)

# Create or get collection
collection = chroma_client.get_or_create_collection(
    name="messages",
    metadata={
        "hnsw:space": "cosine",  # Use cosine similarity
        "hnsw:construction_ef": 200,  # Higher = better quality, slower indexing
        "hnsw:search_ef": 100  # Higher = better quality, slower search
    }
)
```

### 5.2 Metadata Schema for Filtering
```python
CHROMA_METADATA_SCHEMA = {
    "channel_id": str,        # Full channel identifier
    "channel_type": str,      # "agent-notes" or "project"
    "agent_name": str,        # Agent who created message
    "project_id": str,        # Project context (empty string if global)
    "timestamp": float,       # Unix timestamp for temporal filtering
    "confidence": float,      # 0.0 to 1.0 quality signal
    "message_type": str,      # "reflection", "decision", "pattern", "policy"
    "word_count": int,        # For filtering tiny messages
    "has_breadcrumbs": bool   # Whether message has artifact links
}
```

### 5.3 Query Optimization Patterns
```python
# Pre-filter aggressively in ChromaDB before similarity search
# This reduces the search space and improves performance

# Example: Find recent high-confidence solutions from others
where = {
    "$and": [
        {"confidence": {"$gte": 0.7}},
        {"timestamp": {"$gte": week_ago_timestamp}},
        {"agent_name": {"$ne": current_agent}},
        {"message_type": {"$in": ["reflection", "pattern"]}}
    ]
}
```

---

## 6. Out of Scope

### Explicitly NOT Implementing
1. **Topics**: Messages stand alone as complete reflections
2. **State Tracking**: Agents are stateless, no read/unread concept
3. **Relationship Management**: No superseding, conflicts, or dependencies
4. **Lifecycle Management**: No active/resolved/archived states
5. **Complex Permissions**: Notes channels are private by definition
6. **Real-time Collaboration**: All work is asynchronous
7. **Message Threading**: Each reflection is self-contained
8. **Notification System**: Agents pull, not push
9. **Edit/Delete**: Reflections are immutable records
10. **Vector Database Migration**: SQLite remains the source of truth

---

## 7. Migration Strategy

### From v3.x to v4.0

```python
# Step 1: Keep existing SQLite database
# No schema changes needed for existing tables

# Step 2: Install ChromaDB
pip install chromadb

# Step 3: Create ChromaDB collection
chroma = chromadb.PersistentClient(path="~/.claude/claude-slack/chroma")
collection = chroma.create_collection("messages")

# Step 4: Migrate existing messages to ChromaDB
async def migrate_to_chroma():
    # Fetch all messages from SQLite
    messages = sqlite.execute("SELECT * FROM messages").fetchall()
    
    # Batch generate embeddings
    for batch in chunks(messages, 100):
        embeddings = await generate_embeddings([m.content for m in batch])
        
        # Add to ChromaDB
        collection.add(
            ids=[str(m.id) for m in batch],
            embeddings=embeddings,
            metadatas=[extract_metadata(m) for m in batch]
        )

# Step 5: Update write operations to dual-write
# All new messages go to both SQLite and ChromaDB
```

---

## 8. Acceptance Criteria

### Functional Requirements
- [ ] ChromaDB collection created with cosine similarity
- [ ] Messages dual-written to SQLite and ChromaDB
- [ ] Semantic search uses ChromaDB for filtering and similarity
- [ ] SQLite provides full message content after ChromaDB search
- [ ] Metadata filtering reduces search space before similarity calculation
- [ ] Embeddings generated for all new messages
- [ ] Agent notes channels are auto-created on first write
- [ ] Project channels (decisions, patterns, policies) are accessible
- [ ] Confidence and temporal decay applied in ranking

### Performance Requirements
- [ ] ChromaDB search < 50ms for 100K vectors
- [ ] SQLite content retrieval < 20ms for 50 messages
- [ ] Combined search operation < 100ms end-to-end
- [ ] Dual-write overhead < 30ms
- [ ] Batch embedding > 100 messages/second
- [ ] ChromaDB handles 1M+ embeddings

### Quality Requirements
- [ ] Search precision > 70% (relevant results)
- [ ] Search recall > 60% (finds most relevant)
- [ ] Metadata filters correctly applied
- [ ] Similarity scores properly normalized
- [ ] No data inconsistency between SQLite and ChromaDB

---

## 9. Success Metrics

### Primary Metrics
1. **Time-to-effectiveness**: < 2 minutes from task start to productivity
2. **Discovery precision**: > 70% of returned results are relevant
3. **Search latency**: p95 < 100ms including SQLite retrieval
4. **System simplicity**: < 2000 lines of code
5. **Storage efficiency**: ChromaDB size < 2x SQLite message content

### Secondary Metrics
1. **Filter effectiveness**: > 80% reduction in search space via metadata
2. **Temporal relevance**: Recent content scored appropriately higher
3. **Cross-agent discovery**: Agents find others' relevant work
4. **Breadcrumb validity**: > 90% of breadcrumb links are valid

---

## 10. Technical Decisions

### Database: SQLite + ChromaDB Hybrid
**Reasoning**: 
- SQLite: Existing infrastructure, ACID guarantees, complex metadata
- ChromaDB: Purpose-built vector search, metadata filtering, persistence
- No migration needed, best of both worlds

### Embedding Model: text-embedding-3-small
**Reasoning**: Good balance of quality and performance, 768 dimensions

### Vector Storage: ChromaDB
**Reasoning**: 
- Embedded database (no separate service)
- Built-in persistence
- Metadata filtering before similarity search
- Easy to operate

### Search Strategy: Filter First, Then Similarity
**Reasoning**: Metadata filtering dramatically reduces search space, improving both speed and relevance

---

## 11. Risks and Mitigations

### Risk: SQLite/ChromaDB Sync Issues
**Mitigation**: SQLite is source of truth; ChromaDB can be rebuilt from SQLite

### Risk: ChromaDB Corruption
**Mitigation**: Regular backups, ability to regenerate from SQLite

### Risk: Embedding Model Changes
**Mitigation**: Store model version, support multiple collections during transition

### Risk: Search Quality Degradation
**Mitigation**: Monitor precision/recall metrics, tune metadata filters

### Risk: Storage Growth
**Mitigation**: Periodic cleanup of old low-confidence messages

---

## 12. Implementation Phases

### Phase 1: Core Infrastructure (Week 1)
- [ ] Install and configure ChromaDB
- [ ] Create message collection with metadata schema
- [ ] Implement dual-write to SQLite and ChromaDB
- [ ] Basic semantic search with ChromaDB

### Phase 2: Advanced Search (Week 2)
- [ ] Implement metadata filtering
- [ ] Add confidence and temporal ranking
- [ ] Optimize query patterns
- [ ] Add batch operations

### Phase 3: Production Readiness (Week 3)
- [ ] Monitoring and metrics
- [ ] Backup and recovery procedures
- [ ] Performance optimization
- [ ] Documentation and examples

---

## 13. Example Usage Flow

```python
# Initialize hybrid store
store = HybridStore()

# 1. Agent writes reflection
msg_id = await store.write_note(
    agent_name="backend-eng",
    content="""
    Fixed JWT timeout issue in upload service.
    
    Problem: Tokens expiring during long uploads (>15 min).
    Solution: Implemented proactive refresh at 80% TTL with mutex protection.
    Learning: Security policy prevents extending TTL beyond 15 minutes.
    
    This is the third time we've hit this - should consider session cookies.
    """,
    confidence=0.85,
    metadata={
        "breadcrumbs": {
            "modified_files": ["src/auth/refresh.py"],
            "commits": ["abc123"],
            "issues": ["#1234"]
        }
    }
)

# 2. Later, another agent searches
results = await store.semantic_search(
    query="authentication timeout during file upload",
    min_confidence=0.7,
    exclude_agent="frontend-eng",  # Find others' solutions
    max_age_days=30,
    limit=10
)

# 3. Results include similarity scores and full content
for result in results:
    print(f"Score: {result['score']:.3f}")
    print(f"From: {result['message']['sender_id']}")
    print(f"Solution: {result['message']['content'][:200]}...")
    print(f"Breadcrumbs: {result['message']['metadata']['breadcrumbs']}")
```

---

## Appendix A: ChromaDB vs Alternatives

### Why ChromaDB over other vector databases:

| Feature | ChromaDB | Pinecone | Weaviate | Qdrant |
|---------|----------|----------|----------|---------|
| Deployment | Embedded | Cloud | Docker | Docker/Cloud |
| Persistence | Built-in | Cloud | Required | Built-in |
| Metadata Filter | Before search | After search | Before search | Before search |
| Open Source | Yes | No | Yes | Yes |
| Operational Complexity | Low | Low | Medium | Medium |
| Cost | Free | Paid | Free | Free |

**Decision**: ChromaDB provides the best balance of simplicity, features, and operational overhead for our use case.

---

## Appendix B: Database Sync Strategy

```python
class SyncManager:
    """Ensures consistency between SQLite and ChromaDB"""
    
    async def health_check(self):
        """Verify sync status"""
        sqlite_count = self.sqlite.execute(
            "SELECT COUNT(*) FROM messages"
        ).fetchone()[0]
        
        chroma_count = self.collection.count()
        
        if sqlite_count != chroma_count:
            await self.resync_missing()
    
    async def resync_missing(self):
        """Rebuild ChromaDB from SQLite if needed"""
        # Get all SQLite IDs
        sqlite_ids = set(self.sqlite.execute(
            "SELECT id FROM messages"
        ).fetchall())
        
        # Get all ChromaDB IDs
        chroma_ids = set(self.collection.get()['ids'])
        
        # Find missing
        missing = sqlite_ids - chroma_ids
        
        # Add missing to ChromaDB
        for msg_id in missing:
            message = self.sqlite.execute(
                "SELECT * FROM messages WHERE id = ?", 
                (msg_id,)
            ).fetchone()
            
            await self.add_to_chroma(message)
```