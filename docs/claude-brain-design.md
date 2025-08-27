# Claude-Brain: Intelligence Layer Design & Integration Plan

## Executive Summary

Claude-Brain is the **intelligence layer** that sits on top of claude-slack's infrastructure, transforming raw data into actionable context for AI agents. While claude-slack provides unopinionated storage and retrieval, claude-brain adds synthesis, pattern extraction, context assembly, and expertise tracking to dramatically reduce agent time-to-effectiveness.

## Core Philosophy

**"Infrastructure stores, Intelligence understands"**

- Claude-slack: Stores messages, provides search, manages channels
- Claude-brain: Synthesizes context, extracts patterns, tracks expertise, guides agents

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│            AI Agents                        │
│  (Use both MCP tool sets as needed)         │
└────────────┬───────────────┬────────────────┘
             │               │
             v               v
┌─────────────────┐ ┌────────────────────────┐
│  Claude-Brain   │ │    Claude-Slack        │
│  MCP Tools      │ │    MCP Tools           │
├─────────────────┤ ├────────────────────────┤
│ get_task_context│ │ send_channel_message   │
│ find_solutions  │ │ search_messages        │
│ identify_patterns│ │ write_note            │
│ capture_insight │ │ get_messages          │
└────────┬────────┘ └────────────────────────┘
         │
         v
┌─────────────────────────────────────────────┐
│         Claude-Brain Intelligence           │
│  ┌──────────────────────────────────────┐   │
│  │  Context Engine                      │   │
│  │  - Task analysis                     │   │
│  │  - Progressive disclosure            │   │
│  │  - Relevance scoring                 │   │
│  └──────────────────────────────────────┘   │
│  ┌──────────────────────────────────────┐   │
│  │  Pattern Extractor                   │   │
│  │  - Common approaches                 │   │
│  │  - Success indicators                │   │
│  │  - Failure patterns                  │   │
│  └──────────────────────────────────────┘   │
│  ┌──────────────────────────────────────┐   │
│  │  Expertise Tracker                   │   │
│  │  - Who knows what                    │   │
│  │  - Success rates                     │   │
│  │  - Domain mapping                    │   │
│  └──────────────────────────────────────┘   │
│  ┌──────────────────────────────────────┐   │
│  │  Solution Curator                    │   │
│  │  - Proven approaches                 │   │
│  │  - Prerequisites                     │   │
│  │  - Pitfall warnings                  │   │
│  └──────────────────────────────────────┘   │
└─────────────────┬───────────────────────────┘
                  │
                  v
┌─────────────────────────────────────────────┐
│     Claude-Slack Infrastructure API         │
│  - query_by_metadata()                      │
│  - search_with_custom_ranker()              │
│  - aggregate_by_metadata()                  │
│  - find_by_breadcrumbs()                    │
└─────────────────────────────────────────────┘
```

## Key Components

### 1. Context Engine

**Purpose**: Assemble relevant context for agent tasks

```python
class ContextEngine:
    """
    Build multi-layered context for agent effectiveness.
    """
    
    async def build_context(self, task: str, depth: str = "normal") -> Context:
        """
        Progressive context assembly based on task needs.
        
        Layers:
        1. Immediate: Current task definition + recent related
        2. Related: Similar work in last 24-48 hours
        3. Historical: Proven patterns from past
        4. Broader: Project conventions and decisions
        """
        
    async def analyze_task(self, task: str) -> TaskAnalysis:
        """
        Understand what the agent is trying to do.
        - Task type (bug fix, feature, refactor, etc.)
        - Domain (auth, database, UI, etc.)
        - Complexity estimate
        - Required expertise
        """
        
    async def find_precedents(self, task: str) -> List[Precedent]:
        """
        Find similar tasks and their outcomes.
        """
```

### 2. Pattern Extractor

**Purpose**: Identify recurring patterns and approaches

```python
class PatternExtractor:
    """
    Extract patterns from collective agent work.
    """
    
    async def extract_patterns(self, 
                              time_window: str = "7d",
                              min_occurrences: int = 3) -> PatternSet:
        """
        Find recurring patterns in recent work.
        - Common file combinations
        - Repeated decision sequences
        - Convergent approaches
        """
        
    async def identify_conventions(self) -> Conventions:
        """
        Detect emerging team conventions.
        - Naming patterns
        - Architecture choices
        - Tool preferences
        """
        
    async def find_anti_patterns(self) -> List[AntiPattern]:
        """
        Identify approaches that consistently fail.
        """
```

### 3. Expertise Tracker

**Purpose**: Map agent expertise and track success rates

```python
class ExpertiseTracker:
    """
    Track who knows what and how well they perform.
    """
    
    async def update_expertise(self, 
                              agent_id: str,
                              domain: str,
                              outcome: str) -> None:
        """
        Update agent's expertise score for a domain.
        """
        
    async def find_experts(self, domain: str) -> List[Expert]:
        """
        Find agents with proven expertise in a domain.
        """
        
    async def get_expertise_map(self) -> ExpertiseMap:
        """
        Complete map of agent capabilities.
        """
```

### 4. Solution Curator

**Purpose**: Curate and validate successful solutions

```python
class SolutionCurator:
    """
    Maintain a curated library of proven solutions.
    """
    
    async def find_solutions(self, 
                            problem: str,
                            min_confidence: float = 0.8) -> List[Solution]:
        """
        Find validated solutions for a problem.
        """
        
    async def validate_solution(self, 
                               solution_id: int,
                               outcome: str) -> None:
        """
        Update solution validation based on new usage.
        """
        
    async def extract_prerequisites(self, 
                                   solution: Solution) -> List[Prerequisite]:
        """
        Identify what's needed for a solution to work.
        """
```

## MCP Tools Interface

### Intelligence Tools (claude-brain)

```python
@app.tool()
async def get_task_context(
    task_description: str,
    depth: str = "normal",  # minimal, normal, comprehensive
    include_warnings: bool = True
) -> dict:
    """
    Get synthesized context for a task.
    
    Returns:
        {
            "task_analysis": {
                "type": "bug_fix",
                "domain": "authentication",
                "complexity": "medium"
            },
            "immediate_context": [...],
            "similar_tasks": [...],
            "proven_solutions": [...],
            "pitfalls": [...],
            "suggested_approach": {...},
            "experts": [...]
        }
    """

@app.tool()
async def find_proven_solutions(
    problem: str,
    min_confidence: float = 0.8,
    include_prerequisites: bool = True
) -> dict:
    """
    Find validated solutions that actually worked.
    
    Returns:
        {
            "solutions": [...],
            "most_successful": {...},
            "prerequisites": [...],
            "success_rate": 0.85
        }
    """

@app.tool()
async def identify_patterns(
    scope: str = "recent",  # recent, project, all
    pattern_type: str = "all"  # approaches, conventions, anti_patterns
) -> dict:
    """
    Identify patterns in the codebase.
    
    Returns:
        {
            "emerging_patterns": [...],
            "established_conventions": [...],
            "anti_patterns": [...],
            "recommendations": [...]
        }
    """

@app.tool()
async def capture_insight(
    task: str,
    outcome: str,
    key_learnings: List[str],
    artifacts: List[str],
    success_factors: Optional[List[str]] = None,
    failure_reasons: Optional[List[str]] = None
) -> dict:
    """
    Capture and analyze an insight from completed work.
    
    This goes beyond simple reflection storage:
    - Extracts patterns
    - Updates expertise
    - Links to related insights
    - Validates against past solutions
    
    Returns:
        {
            "insight_id": 123,
            "patterns_extracted": [...],
            "expertise_updated": {...},
            "related_insights": [...],
            "impact_score": 0.92
        }
    """

@app.tool()
async def get_expertise_map(
    domain: Optional[str] = None,
    min_expertise: float = 0.7
) -> dict:
    """
    Get map of agent expertise.
    
    Returns:
        {
            "experts": {
                "authentication": ["security-expert", "backend-lead"],
                "database": ["data-engineer", "backend-lead"],
                ...
            },
            "rising_experts": [...],
            "knowledge_gaps": [...]
        }
    """
```

## Integration with Claude-Slack

### 1. Dual MCP Server Architecture

```json
// ~/.claude.json
{
  "mcpServers": {
    "claude-slack": {
      "command": "python",
      "args": ["~/.claude/claude-slack/mcp/server.py"]
    },
    "claude-brain": {
      "command": "python",
      "args": ["~/.claude/claude-brain/mcp/server.py"],
      "env": {
        "CLAUDE_SLACK_DB": "~/.claude/claude-slack/data/claude-slack.db"
      }
    }
  }
}
```

### 2. Metadata Conventions (Claude-Brain Defines These)

```python
# claude-brain/conventions.py

class MetadataConventions:
    """
    Claude-brain's conventions for metadata structure.
    
    These are NOT known to claude-slack - the infrastructure
    just stores and queries arbitrary JSON.
    """
    
    @staticmethod
    def create_reflection_metadata(task, outcome, decisions, files, patterns, confidence):
        """Our convention for reflection metadata."""
        return {
            "type": "reflection",
            "outcome": outcome,
            "confidence": confidence,
            "breadcrumbs": {
                "task": task,
                "decisions": decisions or [],
                "files": files or [],
                "patterns": patterns or []
            },
            "timestamp": datetime.now().isoformat()
        }
    
    @staticmethod
    def create_insight_metadata(domain, insight_type, impact_score):
        """Our convention for insights."""
        return {
            "type": "insight",
            "domain": domain,
            "insight_type": insight_type,
            "impact_score": impact_score
        }
    
    @staticmethod
    def query_for_breadcrumbs(decisions=None, files=None, patterns=None):
        """Build metadata query using our breadcrumb convention."""
        filters = {}
        if decisions:
            filters["metadata.breadcrumbs.decisions"] = {"$in": decisions}
        if files:
            filters["metadata.breadcrumbs.files"] = {"$contains": files[0]}
        if patterns:
            filters["metadata.breadcrumbs.patterns"] = {"$in": patterns}
        return filters
```

### 3. Schema Registration and API Usage

```python
# claude-brain/intelligence/context_engine.py

from claude_slack import ClaudeSlackAPI
from conventions import MetadataConventions

class ContextEngine:
    def __init__(self):
        self.slack = ClaudeSlackAPI(
            db_path=os.environ["CLAUDE_SLACK_DB"]
        )
        self.conventions = MetadataConventions
        
        # Register our schemas for optimal performance
        self._register_schemas()
    
    def _register_schemas(self):
        """Register claude-brain's metadata schemas with infrastructure."""
        
        # Register reflection schema
        self.slack.register_schema(
            "reflection",
            schema_def={
                "type": "string",
                "outcome": "string",
                "confidence": "float",
                "breadcrumbs": {
                    "task": "string",
                    "files": ["string"],
                    "decisions": ["string"],  
                    "patterns": ["string"]
                },
                "session_context": "string",
                "timestamp": "datetime"
            },
            indexed_fields=[
                "type",
                "outcome",
                "confidence",
                "breadcrumbs.task",
                "breadcrumbs.decisions[]",  # Flatten array for search
                "breadcrumbs.patterns[0]"   # Index first pattern
            ]
        )
        
        # Register insight schema  
        self.slack.register_schema(
            "insight",
            schema_def={
                "type": "string",
                "domain": "string",
                "insight_type": "string",
                "impact_score": "float",
                "related_tasks": ["string"]
            },
            indexed_fields=[
                "type",
                "domain",
                "insight_type",
                "impact_score"
            ]
        )
        
        # Register expertise schema
        self.slack.register_schema(
            "expertise_update",
            schema_def={
                "type": "string",
                "agent_id": "string",
                "domain": "string",
                "expertise_delta": "float"
            },
            indexed_fields=["type", "agent_id", "domain"]
        )
    
    async def build_context(self, task: str, depth: str) -> Context:
        # Use infrastructure API with our registered schemas
        # Queries now use natural paths and are automatically optimized
        
        # 1. Get recent related work
        recent = await self.slack.search(
            query=task,
            ranking_profile="recent",
            limit=20
        )
        
        # 2. Find high-confidence solutions (uses registered schema)
        solutions = await self.slack.query_by_metadata({
            "outcome": "success",           # Natural path
            "confidence": {"$gte": 0.8}     # Automatically optimized
        })
        
        # 3. Query by breadcrumbs (registered fields)
        related = await self.slack.query_by_metadata({
            "breadcrumbs.decisions": {"$in": ["authentication", "jwt"]},
            "breadcrumbs.patterns": {"$contains": "middleware"}
        })
        # Infrastructure automatically uses ChromaDB pre-filtering
        
        # 4. Apply custom intelligence ranking
        ranked = await self.slack.search_with_custom_ranker(
            query=task,
            ranker=self._intelligence_ranker
        )
        
        # 5. Synthesize into context
        return self._synthesize(recent, solutions, related, ranked, depth)
    
    def _intelligence_ranker(self, message: Message, scores: Dict) -> float:
        """Custom ranker that understands our metadata conventions."""
        score = scores["similarity"]
        
        # We know about our "breadcrumbs" convention
        breadcrumbs = message.metadata.get("breadcrumbs", {})
        if "security" in breadcrumbs.get("decisions", []):
            score *= 1.3
        
        # We know about our "outcome" convention
        if message.metadata.get("outcome") == "success":
            score *= 1.2
            
        return score
```

## Data Storage

### Claude-Brain's Own Database

```sql
-- expertise.db (claude-brain's intelligence data)

CREATE TABLE expertise (
    agent_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_updated TIMESTAMP,
    expertise_score REAL,
    PRIMARY KEY (agent_id, domain)
);

CREATE TABLE patterns (
    id INTEGER PRIMARY KEY,
    pattern_type TEXT,  -- 'approach', 'convention', 'anti_pattern'
    pattern_name TEXT,
    description TEXT,
    occurrences INTEGER,
    confidence REAL,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    metadata JSON
);

CREATE TABLE solutions (
    id INTEGER PRIMARY KEY,
    problem_signature TEXT,
    solution_hash TEXT,
    success_count INTEGER,
    failure_count INTEGER,
    prerequisites JSON,
    validation_status TEXT,
    last_validated TIMESTAMP
);

CREATE TABLE task_contexts (
    id INTEGER PRIMARY KEY,
    task_hash TEXT UNIQUE,
    task_type TEXT,
    domain TEXT,
    complexity TEXT,
    context_cache JSON,
    created_at TIMESTAMP,
    expires_at TIMESTAMP
);
```

## Agent Workflow Integration

### Example: Agent Starting a New Task

```python
# 1. Agent receives task from user
task = "Implement rate limiting for API endpoints"

# 2. Get intelligent context (claude-brain)
context = await get_task_context(
    task_description=task,
    depth="comprehensive"
)
# Returns:
# - This is a security/performance task
# - 3 similar tasks were done recently
# - Middleware pattern worked best
# - Redis-based solutions had 90% success
# - Warning: Check existing middleware order

# 3. Search for specific implementation details (claude-slack)
details = await search_messages(
    query="rate limiting middleware Redis",
    ranking_profile="quality"
)

# 4. Begin implementation using context.suggested_approach

# 5. Capture the outcome (claude-brain)
await capture_insight(
    task=task,
    outcome="success",
    key_learnings=[
        "Redis-based rate limiting scales well",
        "Middleware order matters for performance"
    ],
    artifacts=["src/middleware/rateLimit.js"],
    success_factors=["Used established Redis pattern"]
)
```

### How Claude-Brain Stores Using Its Conventions

```python
# Inside claude-brain's capture_insight implementation

async def capture_insight_impl(task, outcome, key_learnings, artifacts, ...):
    # 1. Use our metadata conventions
    metadata = MetadataConventions.create_reflection_metadata(
        task=task,
        outcome=outcome,
        decisions=key_learnings,  # Our convention
        files=artifacts,
        patterns=identify_patterns(key_learnings),
        confidence=0.9 if outcome == "success" else 0.5
    )
    
    # 2. Store via infrastructure (claude-slack is agnostic)
    message_id = await slack_api.store_message(
        channel_id=f"notes:{agent_id}",
        sender_id=agent_id,
        content=format_reflection(task, outcome, key_learnings),
        metadata=metadata,  # Our structured JSON
        confidence=metadata["confidence"]
    )
    
    # 3. Intelligence layer processing (claude-brain specific)
    patterns = await extract_patterns_from_learnings(key_learnings)
    expertise = await update_expertise_scores(agent_id, task, outcome)
    related = await find_related_insights(metadata)
    
    return {
        "stored_id": message_id,
        "patterns": patterns,
        "expertise": expertise,
        "related": related
    }
```

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [ ] Setup claude-brain project structure
- [ ] Implement ClaudeSlackAPI integration
- [ ] Create basic Context Engine
- [ ] Develop initial MCP tools

### Phase 2: Core Intelligence (Weeks 3-4)
- [ ] Pattern Extractor implementation
- [ ] Expertise Tracker development
- [ ] Solution Curator basics
- [ ] Custom ranker functions

### Phase 3: Advanced Features (Weeks 5-6)
- [ ] Progressive context disclosure
- [ ] Anti-pattern detection
- [ ] Prerequisite extraction
- [ ] Success prediction

### Phase 4: Optimization (Weeks 7-8)
- [ ] Context caching strategies
- [ ] Performance optimization
- [ ] Batch processing for patterns
- [ ] Intelligence metrics dashboard

### Phase 5: Integration & Testing (Weeks 9-10)
- [ ] Full integration testing
- [ ] Performance benchmarking
- [ ] Documentation completion
- [ ] Agent workflow validation

## Success Metrics

### Primary Metrics
- **Time-to-First-Context**: < 2 seconds
- **Context Relevance Score**: > 80%
- **Pattern Detection Accuracy**: > 75%
- **Expertise Prediction Accuracy**: > 70%

### Secondary Metrics
- **Agent Productivity Increase**: 30-50%
- **Mistake Repetition Reduction**: > 60%
- **Solution Reuse Rate**: > 40%
- **Context Cache Hit Rate**: > 50%

### Long-term Metrics
- **Collective Intelligence Growth**: Measurable monthly
- **Pattern Library Size**: Growing consistently
- **Expertise Map Coverage**: > 80% of domains

## Key Differentiators

### What Claude-Brain IS
✅ **Intelligence Layer**: Synthesis, analysis, pattern extraction
✅ **Context Assembly**: Multi-layered, task-appropriate context
✅ **Pattern Recognition**: Identifying what works and what doesn't
✅ **Expertise Mapping**: Knowing who knows what
✅ **Solution Validation**: Tracking what actually works

### What Claude-Brain IS NOT
❌ **Not Storage**: Doesn't duplicate claude-slack's storage
❌ **Not Messaging**: Doesn't handle channels or messages
❌ **Not Search**: Uses claude-slack's search capabilities
❌ **Not Embeddings**: Leverages existing vector infrastructure

## Integration Benefits

### For Agents
1. **Instant Context**: No more cold starts
2. **Guided Implementation**: Suggested approaches that work
3. **Mistake Avoidance**: Warnings about known pitfalls
4. **Expert Access**: Know who to learn from

### For the System
1. **Collective Learning**: Every agent contributes to intelligence
2. **Pattern Emergence**: Conventions develop naturally
3. **Quality Improvement**: Solutions get validated over time
4. **Knowledge Preservation**: Nothing is lost between sessions

## Conclusion

Claude-Brain transforms claude-slack's raw infrastructure into actionable intelligence. By maintaining clean separation of concerns—infrastructure below, intelligence above—we create a system where:

1. **Agents become immediately effective** through intelligent context
2. **Patterns emerge and propagate** through the collective
3. **Knowledge compounds** rather than being lost
4. **The system gets smarter** with every interaction

This two-layer architecture provides the foundation for true collective intelligence while maintaining the flexibility for each layer to evolve independently.