# Test Modernization Plan for Claude-Slack v4.1 API Integration

## Executive Summary

The recent architectural overhaul moved core managers (DatabaseManager, ChannelManager, NotesManager) from the template into a unified API layer. The existing tests contain valuable business logic that needs to be preserved but must be updated to work with the new ClaudeSlackAPI interface. This plan outlines a systematic approach to modernize the test suite while maintaining comprehensive coverage.

## Current State Analysis

### Test Structure
```
tests/
├── api/                    # NEW: API-specific tests (already modernized)
│   ├── test_unified_api.py        ✅ Uses ClaudeSlackAPI
│   ├── test_message_store.py      ✅ Direct API component testing
│   ├── test_qdrant_integration.py ✅ Semantic search testing
│   └── test_sqlite_store.py       ✅ Storage layer testing
│
├── integration/            # OLD: Template integration tests (need updating)
│   ├── test_channel_permissions.py ❌ Uses old ChannelManager
│   ├── test_database_manager.py    ❌ Uses old DatabaseManager  
│   ├── test_messaging.py           ❌ Uses old managers
│   ├── test_agents.py              ❌ Uses old AgentManager
│   ├── test_projects.py            ❌ Uses old DatabaseManager
│   ├── test_config_sync_manager.py ⚠️  May need API integration
│   ├── test_session_management.py  ⚠️  May need API integration
│   ├── test_tool_orchestrator.py   ⚠️  Uses old db_path pattern
│   └── test_hybrid_store.py        ❌ Obsolete (replaced by API)
│
└── conftest.py             # ❌ Uses old manager imports
```

### Key Issues Identified

1. **Import Problems**: Tests import managers that no longer exist in template:
   - `from db.manager import DatabaseManager` → Should use API
   - `from channels.manager import ChannelManager` → Should use API
   - `from notes.manager import NotesManager` → Should use API

2. **Fixture Dependencies**: conftest.py creates old manager instances instead of API

3. **Direct Database Access**: Some tests directly manipulate database, should go through API

4. **Path Issues**: API components are now bundled in `/api` subdirectory

## Migration Strategy

### Phase 1: Update Core Infrastructure (Priority: HIGH)

#### 1.1 Update conftest.py
```python
# OLD PATTERN (Remove)
from db.manager import DatabaseManager
from channels.manager import ChannelManager
from notes.manager import NotesManager

# NEW PATTERN (Add)
from api.unified_api import ClaudeSlackAPI

# Update fixtures
@pytest_asyncio.fixture
async def api():
    """Provide ClaudeSlackAPI instance for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        qdrant_path = Path(tmpdir) / "qdrant"
        
        api = ClaudeSlackAPI(
            db_path=str(db_path),
            qdrant_path=str(qdrant_path),
            enable_semantic_search=True
        )
        await api.initialize()
        yield api
        await api.close()

# Compatibility shim for gradual migration
@pytest_asyncio.fixture
async def test_db(api):
    """Legacy fixture - returns API's db for compatibility."""
    return api.db

@pytest_asyncio.fixture
async def channel_manager(api):
    """Legacy fixture - returns API's channel manager."""
    return api.channels

@pytest_asyncio.fixture
async def notes_manager(api):
    """Legacy fixture - returns API's notes manager."""
    return api.notes
```

### Phase 2: Migrate Integration Tests (Priority: HIGH)

#### 2.1 Test Migration Mapping

| Old Test File | Migration Approach | Priority |
|--------------|-------------------|----------|
| test_channel_permissions.py | Update to use `api.join_channel()`, `api.leave_channel()` | HIGH |
| test_database_manager.py | Split: Core DB → test_sqlite_store.py, Business → test_unified_api.py | HIGH |
| test_messaging.py | Update to use `api.send_message()`, `api.get_messages()` | HIGH |
| test_agents.py | Update to use `api.register_agent()`, `api.list_agents()` | MEDIUM |
| test_projects.py | Update to use `api.db.register_project()` | MEDIUM |
| test_tool_orchestrator.py | Update to pass API instance instead of db_path | HIGH |
| test_config_sync_manager.py | May need to import API for initialization | LOW |
| test_session_management.py | Check if needs API integration | LOW |
| test_hybrid_store.py | DELETE - replaced by test_message_store.py | N/A |

#### 2.2 Method Translation Guide

**Channel Operations:**
```python
# OLD
channel_manager.join_channel(agent_name, agent_project_id, channel_id)
channel_manager.leave_channel(agent_name, agent_project_id, channel_id)
channel_manager.create_channel(...)

# NEW
api.join_channel(agent_name, agent_project_id, channel_id)
api.leave_channel(agent_name, agent_project_id, channel_id)
api.create_channel(name, description, created_by, created_by_project_id, scope, ...)
```

**Message Operations:**
```python
# OLD
db.send_message(channel_id, sender_id, content, ...)
db.get_channel_messages(channel_id, limit)

# NEW
api.send_message(channel_id, sender_id, sender_project_id, content, metadata, ...)
api.get_messages(channel_id, limit, since, agent_name, agent_project_id)
```

**Agent Operations:**
```python
# OLD
db.register_agent(name, project_id, description, dm_policy, discoverable)
agent_manager.list_agents(...)

# NEW
api.register_agent(name, project_id, description, dm_policy, discoverable, ...)
api.list_agents(project_id, include_global, only_discoverable)
```

**Notes Operations:**
```python
# OLD
notes_manager.write_note(agent_name, agent_project_id, content, ...)
notes_manager.search_notes(agent_name, agent_project_id, query, ...)

# NEW
api.write_note(agent_name, agent_project_id, content, tags, session_context, ...)
api.search_notes(agent_name, agent_project_id, query, tags, limit, ...)
```

### Phase 3: Update Tool Orchestrator Tests (Priority: HIGH)

The MCPToolOrchestrator now accepts an API instance instead of db_path:

```python
# OLD
orchestrator = MCPToolOrchestrator(test_db.db_path)

# NEW  
orchestrator = MCPToolOrchestrator(api)
```

Update test_tool_orchestrator.py fixtures:
```python
@pytest_asyncio.fixture
async def orchestrator(api):
    """Provide MCPToolOrchestrator with API."""
    return MCPToolOrchestrator(api)
```

### Phase 4: Add New API Tests (Priority: MEDIUM)

Create new tests for v4.1 features:

1. **test_semantic_search.py**: Test Qdrant integration without Docker dependency
2. **test_metadata_queries.py**: Test nested JSON queries
3. **test_ranking_profiles.py**: Test different ranking strategies
4. **test_api_performance.py**: Benchmark query performance

### Phase 5: Clean Up (Priority: LOW)

1. Remove obsolete test files (test_hybrid_store.py)
2. Remove old manager imports from remaining tests
3. Update documentation references in tests
4. Add deprecation warnings to compatibility shims

## Implementation Plan

### Week 1: Core Infrastructure
- [ ] Day 1: Update conftest.py with new fixtures
- [ ] Day 1: Add compatibility shims for gradual migration
- [ ] Day 2: Migrate test_channel_permissions.py
- [ ] Day 3: Migrate test_messaging.py
- [ ] Day 4: Migrate test_tool_orchestrator.py
- [ ] Day 5: Run full test suite, fix breaking changes

### Week 2: Complete Migration
- [ ] Day 1: Migrate test_database_manager.py logic
- [ ] Day 2: Migrate test_agents.py and test_projects.py
- [ ] Day 3: Add new semantic search tests
- [ ] Day 4: Add metadata query tests
- [ ] Day 5: Clean up and documentation

## Testing Strategy

### Parallel Testing Approach
1. Keep old tests running with compatibility shims
2. Gradually migrate test by test
3. Run both old and new tests during transition
4. Remove compatibility shims once migration complete

### Validation Checklist
- [ ] All existing test logic preserved
- [ ] New API methods properly tested
- [ ] Semantic search capabilities tested
- [ ] Performance benchmarks established
- [ ] Integration with tool orchestrator verified
- [ ] Cross-project isolation tested

## Risk Mitigation

### Potential Issues
1. **Import Path Confusion**: API is now in `/api` subdirectory
   - Solution: Update sys.path in tests or use proper package imports

2. **Async Method Changes**: Some methods may have changed from sync to async
   - Solution: Audit all test methods for proper async/await usage

3. **Missing Functionality**: Some old manager methods might not exist in API
   - Solution: Either add to API or refactor tests to use different approach

4. **Fixture Dependencies**: Tests may have complex fixture dependencies
   - Solution: Create compatibility layer during transition

## Success Criteria

1. **100% Test Pass Rate**: All tests pass after migration
2. **No Coverage Loss**: Maintain or improve test coverage
3. **Performance**: Tests run in < 30 seconds
4. **Clear Documentation**: All tests have clear docstrings
5. **No Technical Debt**: Remove all compatibility shims after migration

## Quick Start Commands

```bash
# Run specific test suites during migration
pytest tests/api/ -v                    # Test new API layer
pytest tests/integration/ -v -W ignore  # Test old integration (ignore warnings)
pytest tests/ -v                        # Run all tests

# Check test coverage
pytest tests/ --cov=api --cov=template/global/mcp/claude-slack

# Run only fast tests during development
pytest tests/ -m "not slow" -v
```

## Notes for Implementation

1. **Start with High Priority**: Focus on tests that block development
2. **Use Compatibility Shims**: Allow gradual migration without breaking everything
3. **Test in Isolation**: Migrate one test file at a time
4. **Document Changes**: Update test docstrings to reflect new patterns
5. **Benchmark Performance**: Ensure new API doesn't regress performance

## Appendix: Common Patterns

### Pattern 1: API Initialization
```python
async def test_something(api):
    # API is already initialized by fixture
    result = await api.some_method()
    assert result is not None
```

### Pattern 2: Testing with Projects
```python
async def test_project_isolation(api):
    # Setup projects
    await api.db.register_project("proj1", "/path1", "Project 1")
    await api.db.register_project("proj2", "/path2", "Project 2")
    
    # Test isolation
    # ... test logic
```

### Pattern 3: Testing Semantic Search
```python
async def test_semantic_search(api):
    # Store messages with metadata
    await api.send_message(
        channel_id="test:channel",
        sender_id="bot",
        sender_project_id=None,
        content="Implementation completed",
        metadata={"type": "status", "confidence": 0.9}
    )
    
    # Search semantically
    results = await api.search_messages(
        query="finished work",
        semantic_search=True,
        limit=10
    )
    assert len(results) > 0
```

---

This modernization plan provides a clear path forward for updating the test suite to work with the new API-integrated architecture while preserving all valuable test logic.