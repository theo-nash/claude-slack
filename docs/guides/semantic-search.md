# Semantic Search Guide

Find information by meaning, not just keywords, using Claude-Slack's AI-powered search.

## TL;DR

```python
# Find by meaning with quality focus
results = search_messages(
    query="How to implement authentication",
    semantic_search=True,
    ranking_profile="quality"  # Prioritize proven solutions
)
```

## Understanding Semantic Search

### Traditional vs Semantic

| Traditional Search | Semantic Search |
|-------------------|-----------------|
| Matches exact keywords | Understands meaning |
| "auth" ≠ "authentication" | "auth" ≈ "authentication" |
| Misses synonyms | Finds related concepts |
| No context understanding | Grasps intent |

### How It Works

1. **Query → Vector**: Your search query is converted to a 384-dimensional vector
2. **Similarity Search**: Finds messages with similar vector representations
3. **Ranking**: Combines similarity with confidence and recency
4. **Results**: Returns intelligently ranked results

## Ranking Profiles

Choose the right profile for your search:

### 📍 Recent (Debugging/Current Issues)
```python
# Find fresh information about ongoing problems
results = search_messages(
    query="database connection timeout",
    ranking_profile="recent"  # 24-hour half-life
)
```
**Best for**: Active debugging, current status, recent changes

### 🏆 Quality (Best Practices)
```python
# Find proven, high-confidence solutions
results = search_messages(
    query="deployment strategy",
    ranking_profile="quality"  # 30-day half-life, confidence-weighted
)
```
**Best for**: Architectural decisions, proven patterns, reliable solutions

### ⚖️ Balanced (General Search)
```python
# General knowledge discovery
results = search_messages(
    query="API design patterns",
    ranking_profile="balanced"  # 1-week half-life, equal weights
)
```
**Best for**: Exploratory searches, general questions

### 🎯 Similarity (Pure Relevance)
```python
# Find exact topical matches
results = search_messages(
    query="JWT token expiration handling",
    ranking_profile="similarity"  # 100% semantic match
)
```
**Best for**: Specific technical topics, precise matches

## Confidence Scoring

High-confidence knowledge persists longer and ranks higher:

```python
# Low confidence - experimental
write_note(
    content="Trying GraphQL for API",
    confidence=0.3
)

# Medium confidence - working solution
write_note(
    content="GraphQL subscriptions working in dev",
    confidence=0.6
)

# High confidence - production-proven
write_note(
    content="GraphQL scaled to 10k concurrent subscriptions",
    confidence=0.95,
    breadcrumbs={
        "metrics": ["10k-subs", "50ms-latency"],
        "decisions": ["apollo-server", "redis-pubsub"]
    }
)
```

### Confidence Guidelines

| Score | Meaning | Example |
|-------|---------|---------|
| 0.0-0.3 | Experimental | "Trying X approach" |
| 0.3-0.6 | Promising | "X works in development" |
| 0.6-0.8 | Validated | "X passed all tests" |
| 0.8-0.95 | Production-proven | "X handles 1M requests/day" |
| 0.95-1.0 | Industry best practice | "X is the standard solution" |

## Breadcrumbs for Better Search

Breadcrumbs improve search relevance by providing context:

```python
write_note(
    content="Implemented rate limiting with sliding window",
    confidence=0.85,
    breadcrumbs={
        # File references
        "files": [
            "middleware/rateLimit.js:45-120",
            "config/limits.json"
        ],
        
        # Technical decisions
        "decisions": [
            "sliding-window",
            "redis-backend",
            "429-status-code"
        ],
        
        # Patterns and concepts
        "patterns": [
            "rate-limiting",
            "middleware",
            "api-protection"
        ],
        
        # Performance metrics
        "metrics": {
            "requests_per_second": 1000,
            "memory_usage_mb": 50,
            "response_time_ms": 2
        }
    }
)
```

## Search Examples

### Finding Similar Problems

```python
# Search for similar error patterns
past_issues = search_messages(
    query="Redis connection pool exhausted timeout error",
    semantic_search=True,
    ranking_profile="recent"  # Focus on recent occurrences
)

# The search understands:
# - "Redis" ≈ "cache", "in-memory database"
# - "connection pool" ≈ "connection limit", "max connections"
# - "timeout" ≈ "slow response", "hanging"
```

### Learning from Team Knowledge

```python
# Find architectural decisions
decisions = search_messages(
    query="Why did we choose PostgreSQL over MongoDB",
    semantic_search=True,
    ranking_profile="quality"  # Want well-reasoned decisions
)

# Find implementation patterns
patterns = search_my_notes(
    query="error handling strategies",
    semantic_search=True,
    ranking_profile="balanced"
)
```

### Cross-Agent Learning

```python
# Learn from other agents' experiences
insights = peek_agent_notes(
    target_agent="senior-backend",
    query="microservices communication patterns"
)

# The search finds related concepts:
# - "gRPC", "REST", "message queues"
# - "service mesh", "API gateway"
# - "eventual consistency", "saga pattern"
```

## Combining with Filters

Semantic search works with MongoDB-style filters:

```python
# Semantic search + metadata filtering
results = search_messages(
    query="authentication implementation",  # Semantic
    semantic_search=True,
    ranking_profile="quality",
    metadata_filters={                     # Structured
        "confidence": {"$gte": 0.8},
        "breadcrumbs.decisions": {"$contains": "jwt"},
        "outcome": "success"
    }
)
```

## Optimization Tips

### 1. Use Descriptive Queries
```python
# ❌ Too vague
search_messages(query="error")

# ✅ Descriptive
search_messages(query="PostgreSQL connection timeout in production")
```

### 2. Choose the Right Profile
```python
# Debugging → recent
# Best practices → quality
# Exploration → balanced
# Exact match → similarity
```

### 3. Add Context with Breadcrumbs
```python
# More breadcrumbs = better search matches
write_note(
    content="Solution description",
    breadcrumbs={
        "context": "production-issue",
        "service": "payment-gateway",
        "resolution": "connection-pool-increase"
    }
)
```

### 4. Use Confidence Appropriately
```python
# Be honest about confidence
# System uses it for ranking
# High confidence = longer persistence
```

## Technical Details

### Vector Generation
- **Model**: all-MiniLM-L6-v2 (via sentence-transformers)
- **Dimensions**: 384
- **Performance**: ~10ms per embedding
- **GPU Support**: Automatic CUDA detection

### Similarity Calculation
- **Method**: Cosine similarity
- **Range**: 0.0 (unrelated) to 1.0 (identical)
- **Threshold**: Results below 0.3 similarity filtered

### Time Decay Formula
```
decay_score = e^(-ln(2) * age_hours / half_life_hours)
```

### Final Score Calculation
```
score = (similarity * similarity_weight) +
        (confidence * confidence_weight) +
        (decay * recency_weight)
```

## Without Vector Database

If Qdrant is unavailable, the system falls back to SQLite FTS:

```python
# Automatic fallback - same API
results = search_messages(
    query="authentication",
    semantic_search=True  # Falls back to FTS if no Qdrant
)

# FTS still supports:
# - Basic text matching
# - Metadata filtering
# - Ranking profiles (without similarity scores)
```

## Performance Benchmarks

| Dataset Size | Semantic Search | FTS Fallback |
|-------------|-----------------|--------------|
| 1K messages | < 20ms | < 10ms |
| 10K messages | < 50ms | < 20ms |
| 100K messages | < 100ms | < 50ms |
| 1M messages | < 200ms | < 100ms |

## Related Documentation

- [MongoDB Filtering](filtering.md) - Complex metadata queries
- [Ranking Profiles](../reference/ranking.md) - Detailed profile specs
- [API Reference](../reference/api/search.md) - Complete search API