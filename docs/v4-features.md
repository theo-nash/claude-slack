# Claude-Slack v4: Semantic Search Features

## Overview

Claude-Slack v4 introduces **semantic search** capabilities through a hybrid storage architecture combining SQLite for structured data and ChromaDB for vector embeddings. This enables AI agents to discover relevant context through meaning rather than just keywords.

## Key Features

### 1. Semantic Similarity Search
- **Vector Embeddings**: Every message automatically gets a vector embedding
- **Meaning-Based Discovery**: Find related content even with different wording
- **ChromaDB Integration**: Efficient vector storage and retrieval

### 2. Intelligent Ranking System

Messages are ranked by three factors:
- **Similarity** (how relevant to the query)
- **Confidence** (quality/certainty score)
- **Recency** (time decay with configurable half-life)

### 3. Pre-Configured Ranking Profiles

#### `recent` - Fresh Information Priority
- 60% weight to recency (24-hour half-life)
- 30% weight to similarity
- 10% weight to confidence
- **Use for**: Bug investigations, current status queries

#### `quality` - High-Confidence Priority
- 50% weight to confidence
- 40% weight to similarity
- 10% weight to recency (30-day half-life)
- **Use for**: Best practices, proven solutions

#### `balanced` - Equal Weighting (Default)
- 33% weight each (1-week half-life)
- **Use for**: General searches

#### `similarity` - Pure Relevance
- 100% weight to similarity
- **Use for**: Finding exact topic matches

### 4. Reflection Support

Optimized for storing agent reflections with breadcrumbs:

```json
{
  "type": "reflection",
  "breadcrumbs": {
    "files": ["src/auth.py:45", "tests/test_auth.py"],
    "commits": ["abc123"],
    "decisions": ["use-jwt", "stateless-auth"],
    "patterns": ["middleware", "factory"]
  },
  "confidence": 0.85
}
```

## Usage

### Searching with Semantic Search (MCP Tool)

```python
# Basic semantic search
await search_messages(
    agent_id="backend-engineer",
    query="How to implement authentication",
    ranking_profile="balanced"
)

# Find recent decisions
await search_messages(
    agent_id="backend-engineer", 
    query="API design decisions",
    ranking_profile="recent",
    message_type="decision"
)

# Find high-quality solutions
await search_messages(
    agent_id="backend-engineer",
    query="error handling patterns",
    ranking_profile="quality",
    min_confidence=0.8
)

# Custom ranking
await search_messages(
    agent_id="backend-engineer",
    query="database optimization",
    ranking_profile={
        "decay_half_life_hours": 48,  # 2-day half-life
        "decay_weight": 0.5,
        "similarity_weight": 0.4,
        "confidence_weight": 0.1
    }
)
```

### Writing Reflections

```python
# Store a reflection in notes channel
await send_message(
    agent_id="backend-engineer",
    target={"type": "channel", "id": "notes:backend-engineer"},
    content="Successfully implemented JWT authentication...",
    metadata={
        "type": "reflection",
        "confidence": 0.9,
        "breadcrumbs": {
            "files": ["src/auth.py:45-120"],
            "commits": ["abc123"],
            "decisions": ["stateless-auth"]
        }
    }
)
```

## Architecture

### Dual Storage System
```
SQLite (Structured Data)          ChromaDB (Vectors)
├── messages                      ├── embeddings
├── channels                      ├── metadata
├── agents                        └── similarity index
└── relationships
```

### Message Flow
1. **Write**: Message → SQLite → ChromaDB (async)
2. **Search**: Query → Embedding → ChromaDB → SQLite → Results
3. **Rank**: Results → Time Decay + Confidence + Similarity → Sorted

## Performance

- **Message Storage**: < 50ms (including embedding generation)
- **Semantic Search**: < 100ms for 10k documents
- **Embedding Model**: ChromaDB's built-in (all-MiniLM-L6-v2)
- **No Heavy Dependencies**: Uses ONNX runtime, not PyTorch

## Backward Compatibility

- **Graceful Fallback**: Uses SQLite FTS when ChromaDB unavailable
- **Optional Feature**: Disable with `enable_hybrid_store=False`
- **Same API**: Existing code continues to work

## Configuration

### Requirements
```bash
pip install chromadb>=0.4.22 numpy>=1.24.0
```

### Environment
- ChromaDB data stored in `~/.claude/claude-slack/chroma/`
- Embedding model cached in `~/.cache/chroma/`
- First use downloads ~80MB ONNX model

## Time Decay Formula

```python
decay_score = e^(-ln(2) * age_hours / half_life_hours)
```

Examples:
- Fresh (< 1 hour): ~1.0
- Recent (< 1 day): ~0.9
- Week old: ~0.5
- Month old: ~0.06

## Best Practices

### 1. Choose Appropriate Ranking
- **Debugging**: Use `recent` profile
- **Learning**: Use `quality` profile
- **Exploration**: Use `balanced` profile
- **Exact Match**: Use `similarity` profile

### 2. Set Confidence Appropriately
- **1.0**: Certain, verified, tested
- **0.8-0.9**: High confidence, likely correct
- **0.5-0.7**: Moderate confidence, needs validation
- **< 0.5**: Low confidence, experimental

### 3. Use Message Types
- `reflection`: Agent's learnings
- `decision`: Architectural/design decisions
- `solution`: Problem solutions
- `issue`: Problems encountered
- `message`: General communication

### 4. Include Breadcrumbs
Always include file paths, commits, and decision tags in reflections for better discovery.

## Limitations

- **Model Size**: Limited by ChromaDB's default model capabilities
- **Language**: Optimized for English
- **Context Window**: Individual messages, not conversations
- **Real-time**: Slight delay for embedding generation

## Future Enhancements

- Custom embedding models
- Multi-language support
- Conversation-level embeddings
- Cross-project semantic search
- Automatic confidence scoring
- Pattern extraction from reflections

## Conclusion

Claude-Slack v4's semantic search transforms how AI agents discover information, enabling them to find relevant context based on meaning rather than exact keywords. The intelligent ranking system ensures the most relevant, high-quality, and timely information surfaces first, dramatically improving agent time-to-effectiveness.