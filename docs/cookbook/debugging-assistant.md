# Building a Debugging Assistant with Memory

Learn how to create an AI debugging assistant that remembers past issues, solutions, and patterns to help solve problems faster.

## Use Case

Your team encounters similar bugs repeatedly. You want an assistant that:
- Remembers past debugging sessions
- Learns from solutions that worked
- Recognizes error patterns
- Suggests fixes based on history

## Implementation

### 1. Setup Debug Tracking Channel

```python
# Create a dedicated debugging channel
await api.create_channel(
    name="debugging",
    description="Bug tracking and solutions",
    scope="project"
)

# Create pattern recognition channel
await api.create_channel(
    name="error-patterns",
    description="Common error patterns and fixes",
    scope="project"
)
```

### 2. Log Debugging Sessions

When starting to debug an issue:

```python
async def start_debug_session(error_message, stack_trace, context):
    """Start a debugging session with full context"""
    
    # Create session ID for tracking
    session_id = f"debug_{datetime.now().isoformat()}"
    
    # Log the initial error
    await api.send_message(
        channel_id="proj:debugging",
        sender_id="debug-assistant",
        content=f"New debugging session: {error_message}",
        metadata={
            "type": "debug_start",
            "session_id": session_id,
            "error": {
                "message": error_message,
                "stack_trace": stack_trace,
                "file": context.get("file"),
                "line": context.get("line"),
                "function": context.get("function")
            },
            "environment": {
                "service": context.get("service"),
                "env": context.get("env", "development"),
                "version": context.get("version")
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    )
    
    # Search for similar past errors
    similar_errors = await search_similar_errors(error_message)
    
    return session_id, similar_errors
```

### 3. Search for Similar Past Issues

```python
async def search_similar_errors(error_message):
    """Find similar errors we've seen before"""
    
    # Semantic search for similar errors
    results = await api.search_messages(
        query=error_message,
        semantic_search=True,
        metadata_filters={
            "type": {"$in": ["debug_start", "error_pattern"]},
            "resolution.status": "solved"  # Only successful fixes
        },
        ranking_profile="quality",  # Prioritize proven solutions
        limit=5
    )
    
    # Extract solutions that worked
    solutions = []
    for result in results:
        if result.get("metadata", {}).get("resolution"):
            solutions.append({
                "error": result["metadata"]["error"]["message"],
                "solution": result["metadata"]["resolution"]["fix"],
                "confidence": result["metadata"].get("confidence", 0.5),
                "similarity": result.get("score", 0)
            })
    
    return solutions
```

### 4. Document Solutions with Confidence

When you solve the issue:

```python
async def document_solution(session_id, solution, fix_details):
    """Document what fixed the issue with confidence scoring"""
    
    # Determine confidence based on solution quality
    confidence = calculate_confidence(fix_details)
    
    # Update the debugging session
    await api.send_message(
        channel_id="proj:debugging",
        sender_id="debug-assistant",
        content=f"Session {session_id} resolved: {solution}",
        metadata={
            "type": "debug_resolved",
            "session_id": session_id,
            "resolution": {
                "status": "solved",
                "fix": solution,
                "code_changes": fix_details.get("code_changes"),
                "root_cause": fix_details.get("root_cause"),
                "time_to_fix_minutes": fix_details.get("time_spent")
            },
            "confidence": confidence,
            "reusable": fix_details.get("reusable", True)
        }
    )
    
    # If high confidence, create a pattern
    if confidence >= 0.8:
        await create_error_pattern(session_id, solution, fix_details)

def calculate_confidence(fix_details):
    """Calculate confidence in the solution"""
    confidence = 0.5  # Base confidence
    
    # Increase confidence based on factors
    if fix_details.get("root_cause"):
        confidence += 0.2
    if fix_details.get("tested"):
        confidence += 0.2
    if fix_details.get("time_spent", 0) < 30:  # Quick fix
        confidence += 0.1
    
    return min(confidence, 1.0)
```

### 5. Learn Error Patterns

Create reusable patterns from successful debugging:

```python
async def create_error_pattern(session_id, solution, fix_details):
    """Create a reusable error pattern"""
    
    # Write as a high-confidence note
    await api.write_note(
        agent_name="debug-assistant",
        content=f"Error Pattern: {fix_details['root_cause']}",
        confidence=0.9,
        breadcrumbs={
            "error_type": fix_details.get("error_type"),
            "symptoms": fix_details.get("symptoms", []),
            "root_cause": fix_details["root_cause"],
            "fix_pattern": solution,
            "files": fix_details.get("affected_files", []),
            "prevention": fix_details.get("prevention_tips", [])
        },
        tags=["error-pattern", "debugged", "proven-fix"]
    )
    
    # Also share in patterns channel
    await api.send_message(
        channel_id="proj:error-patterns",
        sender_id="debug-assistant",
        content=f"New Pattern Identified: {fix_details['root_cause']}",
        metadata={
            "type": "error_pattern",
            "pattern": {
                "name": fix_details.get("pattern_name"),
                "regex": fix_details.get("error_regex"),
                "solution_template": solution
            },
            "confidence": 0.9,
            "usage_count": 1
        }
    )
```

### 6. Real-Time Debugging Assistant

Use the accumulated knowledge in real-time:

```python
class DebugAssistant:
    def __init__(self, api):
        self.api = api
        self.current_session = None
    
    async def analyze_error(self, error_text):
        """Analyze a new error and suggest solutions"""
        
        # Start session
        self.current_session, similar_errors = await start_debug_session(
            error_text, 
            stack_trace=extract_stack_trace(error_text),
            context=extract_context(error_text)
        )
        
        # Get suggestions
        suggestions = await self.get_suggestions(error_text, similar_errors)
        
        return suggestions
    
    async def get_suggestions(self, error_text, similar_errors):
        """Generate ranked suggestions"""
        
        suggestions = []
        
        # 1. Check exact pattern matches
        patterns = await self.api.search_my_notes(
            agent_name="debug-assistant",
            query=error_text,
            tags=["error-pattern"],
            ranking_profile="similarity"
        )
        
        for pattern in patterns[:3]:
            suggestions.append({
                "type": "known_pattern",
                "solution": pattern["breadcrumbs"]["fix_pattern"],
                "confidence": pattern.get("confidence", 0.8),
                "source": "pattern_library"
            })
        
        # 2. Add similar error solutions
        for error in similar_errors[:3]:
            suggestions.append({
                "type": "similar_issue",
                "solution": error["solution"],
                "confidence": error["confidence"] * error["similarity"],
                "source": "historical"
            })
        
        # 3. Sort by confidence
        suggestions.sort(key=lambda x: x["confidence"], reverse=True)
        
        return suggestions
    
    async def mark_solution_used(self, suggestion, worked):
        """Update confidence based on whether suggestion worked"""
        
        if worked:
            # Increase confidence for future
            await self.api.send_message(
                channel_id="proj:debugging",
                sender_id="debug-assistant",
                content=f"Solution confirmed working",
                metadata={
                    "type": "solution_feedback",
                    "session_id": self.current_session,
                    "solution": suggestion["solution"],
                    "feedback": "positive",
                    "confidence_boost": 0.1
                }
            )
        else:
            # Decrease confidence
            await self.api.send_message(
                channel_id="proj:debugging",
                sender_id="debug-assistant",
                content=f"Solution didn't work",
                metadata={
                    "type": "solution_feedback",
                    "session_id": self.current_session,
                    "solution": suggestion["solution"],
                    "feedback": "negative",
                    "confidence_penalty": 0.2
                }
            )
```

## Usage Example

```python
# Initialize the debugging assistant
debug_assistant = DebugAssistant(api)

# When you encounter an error
error = """
ConnectionRefusedError: [Errno 111] Connection refused
  File "app.py", line 45, in connect_to_redis
    redis_client.ping()
"""

# Get suggestions from past experience
suggestions = await debug_assistant.analyze_error(error)

print("Debugging suggestions based on past experience:")
for i, suggestion in enumerate(suggestions, 1):
    print(f"{i}. {suggestion['solution']} (confidence: {suggestion['confidence']:.0%})")

# After trying a solution
await debug_assistant.mark_solution_used(suggestions[0], worked=True)

# Document the complete fix
await document_solution(
    debug_assistant.current_session,
    solution="Started Redis service with 'sudo systemctl start redis'",
    fix_details={
        "root_cause": "Redis service not running",
        "code_changes": None,
        "tested": True,
        "time_spent": 5,
        "error_type": "ConnectionRefusedError",
        "symptoms": ["Connection refused", "Errno 111"],
        "affected_files": ["app.py"],
        "prevention_tips": ["Add Redis health check on startup"],
        "reusable": True
    }
)
```

## Advanced Features

### Auto-Pattern Detection

```python
async def detect_patterns():
    """Automatically detect recurring error patterns"""
    
    # Get all debugging sessions from last week
    recent_errors = await api.search_messages(
        metadata_filters={
            "type": "debug_start",
            "timestamp": {"$gte": (datetime.now() - timedelta(days=7)).isoformat()}
        }
    )
    
    # Group by error similarity
    error_clusters = cluster_by_similarity(recent_errors)
    
    # Create patterns for clusters with 3+ occurrences
    for cluster in error_clusters:
        if len(cluster) >= 3:
            await create_pattern_from_cluster(cluster)
```

### Team Learning

Share debugging knowledge across the team:

```python
# Broadcast important patterns to team
await api.send_channel_message(
    channel_id="general",
    sender_id="debug-assistant",
    content="🐛 New debugging pattern identified that affected 5+ team members",
    metadata={
        "type": "pattern_announcement",
        "pattern_name": "Docker container DNS issues",
        "occurrence_count": 5,
        "average_time_to_fix": 45,  # minutes
        "solution": "Restart Docker daemon or use host networking"
    }
)
```

## Benefits

1. **Faster debugging**: Similar issues solved in minutes instead of hours
2. **Knowledge retention**: Solutions aren't lost when developers leave
3. **Pattern recognition**: Identifies recurring issues automatically
4. **Confidence scoring**: Learn which solutions actually work
5. **Team learning**: Everyone benefits from debugging experience

## Next Steps

- Integrate with error monitoring tools (Sentry, Rollbar)
- Add automatic stack trace analysis
- Create debugging dashboards
- Build preventive suggestions based on patterns
- Add code fix suggestions with diff generation