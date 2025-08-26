# Test Modernization Plan

## Philosophy: Integration-First Testing

We're moving from scattered unit tests to comprehensive integration tests that validate real-world scenarios.

## Current State Analysis

### Good Tests (Keep & Enhance)
- ✅ `test_channel_permissions.py` - Comprehensive, uses fixtures properly
- ✅ `test_session_management.py` - Well structured, good coverage
- ⚠️ `test_agent_discovery.py` - Needs fixture updates
- ⚠️ `test_mention_validation.py` - Should merge into messaging tests

### Outdated Tests (Archive)
- ❌ `test_permissions_core.py` - Uses old v3 managers
- ❌ `test_phase2_integration.py` - Obsolete phase 2 tests
- ❌ Unit tests that test database operations in isolation

## New Test Structure

### 1. **test_channels.py** (Comprehensive Channel Operations)
Combines channel_permissions + creation + discovery
```python
class TestChannelLifecycle:
    - test_create_all_channel_types
    - test_channel_discovery_rules
    - test_default_channel_provisioning
    
class TestChannelAccess:
    - test_join_permissions_matrix  # All combinations
    - test_invitation_system
    - test_leave_restrictions
    
class TestChannelScopes:
    - test_global_vs_project_isolation
    - test_project_linking_effects
    - test_cross_project_operations
```

### 2. **test_messaging.py** (All Message Operations)
```python
class TestMessageSending:
    - test_send_with_permissions
    - test_send_validation_matrix
    - test_metadata_handling
    - test_threading
    
class TestDirectMessages:
    - test_dm_lifecycle
    - test_dm_permissions_matrix
    - test_dm_blocking
    
class TestMentions:
    - test_mention_formats
    - test_mention_validation
    - test_cross_project_mentions
```

### 3. **test_agents.py** (Agent Management)
```python
class TestAgentLifecycle:
    - test_registration_all_scopes
    - test_agent_updates
    - test_agent_deletion_cascades
    
class TestAgentDiscovery:
    - test_discoverability_matrix
    - test_project_scoped_discovery
    - test_linked_project_discovery
    
class TestAgentPermissions:
    - test_dm_policies
    - test_permission_inheritance
```

### 4. **test_projects.py** (Project Management)
```python
class TestProjectLifecycle:
    - test_project_creation
    - test_project_updates
    - test_project_deletion_cascades
    
class TestProjectLinking:
    - test_link_types_matrix
    - test_transitive_access
    - test_link_removal_effects
```

### 5. **test_orchestrator.py** (MCP Tool Integration)
```python
class TestToolOrchestration:
    - test_all_tool_endpoints
    - test_permission_enforcement
    - test_error_handling
    - test_tool_aliases
    
class TestProjectContext:
    - test_context_switching
    - test_context_persistence
```

### 6. **test_notes.py** (Notes Management)
```python
class TestNotesOperations:
    - test_note_creation
    - test_note_search
    - test_note_permissions
    - test_cross_agent_peeking
```

## Implementation Strategy

### Phase 1: Consolidate (Week 1)
1. Merge related tests into new structure
2. Update all fixtures to use current managers
3. Remove v3 manager references

### Phase 2: Enhance (Week 2)
1. Add missing test scenarios
2. Create test matrices for comprehensive coverage
3. Add performance benchmarks

### Phase 3: Clean Up (Week 3)
1. Archive old tests
2. Update CI/CD configuration
3. Create test documentation

## Test Fixtures (Shared)

### Core Fixtures in `conftest.py`:
```python
@pytest_asyncio.fixture
async def test_environment():
    """Complete test environment with all managers."""
    # Returns: db, channel_mgr, agent_mgr, notes_mgr, orchestrator
    
@pytest_asyncio.fixture
async def populated_environment(test_environment):
    """Environment with realistic test data."""
    # Includes: projects, agents, channels, messages, notes
    
@pytest_asyncio.fixture
async def linked_projects_environment(test_environment):
    """Environment with complex project linking."""
    # For testing cross-project operations
```

## Coverage Goals

### Must Have (90%+ coverage)
- Channel access control
- Message permissions
- Agent discovery
- Project linking
- Session management

### Nice to Have (70%+ coverage)
- Error handling paths
- Edge cases
- Performance scenarios

## Success Metrics

1. **Simplicity**: Fewer test files, better organization
2. **Coverage**: 90%+ coverage of critical paths
3. **Speed**: Full suite runs in < 60 seconds
4. **Reliability**: No flaky tests
5. **Maintainability**: Clear test names, good fixtures

## Next Steps

1. Start with `test_messaging.py` - consolidate all message tests
2. Then `test_agents.py` - modernize discovery tests
3. Continue with remaining test suites
4. Archive old tests once replacements are verified