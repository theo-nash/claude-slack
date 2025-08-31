# Claude-Slack Test Suite

Comprehensive test suite for the Claude-Slack MCP server (v3.0.0).

## Structure

```
tests/
├── unit/                 # Unit tests for individual components
│   ├── test_database_manager.py
│   ├── test_channel_manager.py
│   ├── test_notes_manager.py
│   ├── test_agent_manager.py
│   └── test_tool_orchestrator.py
│
├── integration/          # Integration tests for feature workflows
│   ├── test_channel_permissions.py  # NEW: Comprehensive v3 permissions
│   ├── test_permissions_core.py
│   ├── test_mention_validation.py
│   ├── test_agent_discovery.py
│   ├── test_session_management.py
│   └── test_phase2_integration.py
│
├── e2e/                  # End-to-end tests (to be added)
│   └── (placeholder for full workflow tests)
│
├── fixtures/             # Shared test fixtures and utilities
│   └── (placeholder for test data)
│
├── archive/              # Old/outdated tests for reference
│   └── (various legacy test files)
│
└── conftest.py          # Pytest configuration and shared fixtures
```

## Running Tests

### Run all tests
```bash
pytest tests/
```

### Run specific test categories
```bash
# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Specific test file
pytest tests/integration/test_channel_permissions.py

# Specific test class
pytest tests/integration/test_channel_permissions.py::TestChannelPermissions

# Specific test method
pytest tests/integration/test_channel_permissions.py::TestChannelPermissions::test_join_open_global_channel
```

### Run with coverage
```bash
pytest tests/ --cov=template.global.mcp.claude_slack --cov-report=html
```

### Run with verbose output
```bash
pytest tests/ -v
```

### Run tests matching a pattern
```bash
pytest tests/ -k "channel"  # Run tests with "channel" in the name
pytest tests/ -k "not dm"    # Skip tests with "dm" in the name
```

## Key Test Areas

### 1. Channel Permissions (NEW - v3.0.0)
Located in `integration/test_channel_permissions.py`

Tests the unified membership model including:
- Self-joining channels with scope restrictions
- Cross-project invitations
- Channel discovery and visibility
- Project linking effects
- Default channel provisioning
- DM channel behavior

### 2. Tool Orchestrator
Located in `unit/test_tool_orchestrator.py`

Tests the MCPToolOrchestrator including:
- Tool validation and error handling
- Agent ID extraction and validation
- Tool aliases (backward compatibility)
- Project context handling

### 3. Database Operations
Located in `unit/test_database_manager.py`

Tests core database functionality:
- Channel CRUD operations
- Agent registration and management
- Project management and linking
- Message operations
- Permission checks

### 4. Session Management
Located in `integration/test_session_management.py`

Tests session handling:
- Session registration and updates
- Tool call deduplication
- Session cleanup

### 5. Agent Discovery
Located in `integration/test_agent_discovery.py`

Tests agent discovery and DM permissions:
- Discoverability settings
- DM policy enforcement
- Cross-project discovery with links

## Writing New Tests

### Use Fixtures
The `conftest.py` file provides common fixtures:

```python
@pytest.mark.asyncio
async def test_example(test_db, channel_manager, populated_db):
    """Example test using fixtures."""
    # test_db: Clean database
    # channel_manager: ChannelManager instance
    # populated_db: Database with test data
    pass
```

### Test Naming Convention
- Test files: `test_<component>.py`
- Test classes: `Test<Feature>`
- Test methods: `test_<scenario>`

### Test Organization
- **Unit tests**: Test single components in isolation
- **Integration tests**: Test feature workflows
- **E2E tests**: Test complete user scenarios

## Coverage Goals

### Current Coverage Areas
- ✅ Channel permissions and access control
- ✅ Tool orchestration and validation
- ✅ Database operations
- ✅ Session management
- ✅ Agent discovery
- ✅ Mention validation
- ✅ Notes management

### Areas Needing More Tests
- ⚠️ ConfigSyncManager and reconciliation
- ⚠️ Error recovery scenarios
- ⚠️ Concurrent operations
- ⚠️ Performance under load
- ⚠️ Edge cases in project linking

## CI/CD Integration

To integrate with CI/CD, add to your pipeline:

```yaml
# Example GitHub Actions
- name: Run tests
  run: |
    pip install pytest pytest-asyncio pytest-cov
    pytest tests/ --cov=template.global.mcp.claude_slack --cov-report=xml
    
- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```

## Debugging Tests

### Run with debugging output
```bash
pytest tests/ -s  # Don't capture output
pytest tests/ --log-cli-level=DEBUG  # Show debug logs
```

### Run with pdb on failure
```bash
pytest tests/ --pdb  # Drop into debugger on failure
```

### Run specific tests during development
```bash
pytest tests/ --lf  # Run last failed tests
pytest tests/ --ff  # Run failed tests first
```

## Contributing

When adding new features:
1. Write tests FIRST (TDD approach)
2. Ensure tests pass locally
3. Add appropriate test category (unit/integration/e2e)
4. Update this README if adding new test files
5. Maintain test isolation (use fixtures, don't share state)