# V3 Configuration Implementation Roadmap

## Overview

This roadmap outlines the step-by-step implementation plan for the new configuration synchronization architecture, including ConfigSyncManager, AgentDiscoveryService, and unified `is_default` behavior.

## Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal**: Establish core infrastructure without breaking existing functionality

#### 1.1 Database Schema Updates
```sql
-- Add tracking columns for default provisioning
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS
    is_from_default BOOLEAN DEFAULT FALSE,
    opted_out BOOLEAN DEFAULT FALSE,
    opted_out_at TIMESTAMP;

ALTER TABLE channel_members ADD COLUMN IF NOT EXISTS
    is_from_default BOOLEAN DEFAULT FALSE,
    opted_out BOOLEAN DEFAULT FALSE,
    opted_out_at TIMESTAMP;

-- Add configuration sync history table
CREATE TABLE IF NOT EXISTS config_sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_hash TEXT NOT NULL,
    config_snapshot JSON NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    scope TEXT,
    project_id TEXT,
    actions_taken JSON,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT
);
```

**Tasks**:
- [ ] Create migration script for schema updates
- [ ] Test schema changes with existing data
- [ ] Deploy schema updates to development environment

#### 1.2 AgentDiscoveryService Implementation
**Location**: `template/global/mcp/claude-slack/agents/discovery.py`

**Tasks**:
- [ ] Create `discovery.py` with AgentDiscoveryService class
- [ ] Implement `discover_project_agents()` method
- [ ] Implement `discover_global_agents()` method
- [ ] Create DiscoveredAgent and DiscoveryResult dataclasses
- [ ] Write unit tests for discovery logic
- [ ] Update `agents/__init__.py` to export new classes

#### 1.3 Configuration File Updates
**Location**: `template/global/config/claude-slack.config.yaml`

**Tasks**:
- [ ] Add `access_type` field to all default channels
- [ ] Add `is_default` field to all default channels
- [ ] Remove old `default_agent_subscriptions` section
- [ ] Document new structure in comments
- [ ] Create example configuration for testing

### Phase 2: Core Implementation (Week 2)

#### 2.1 ReconciliationPlan Infrastructure
**Location**: `template/global/mcp/claude-slack/config/reconciliation.py`

**Tasks**:
- [ ] Create ReconciliationPlan class with phase management
- [ ] Implement Action base class and concrete actions:
  - [ ] CreateChannelAction
  - [ ] RegisterAgentAction
  - [ ] AddSubscriptionAction
  - [ ] AddMembershipAction
- [ ] Implement plan execution with rollback capability
- [ ] Add plan validation and dependency checking
- [ ] Write unit tests for plan execution

#### 2.2 ConfigSyncManager Core
**Location**: `template/global/mcp/claude-slack/config/sync_manager.py`

**Tasks**:
- [ ] Create ConfigSyncManager class structure
- [ ] Implement `reconcile_all()` method
- [ ] Implement `_plan_channels()` method
- [ ] Implement `_plan_agents()` method
- [ ] Implement `_plan_default_access()` method
- [ ] Add configuration change detection
- [ ] Write integration tests

#### 2.3 DatabaseManager Updates
**Location**: `template/global/mcp/claude-slack/db/manager.py`

**Tasks**:
- [ ] Add `apply_default_channel_access()` method
- [ ] Add `get_default_channels()` method
- [ ] Add `mark_access_opted_out()` method
- [ ] Update `create_channel()` to handle `is_default`
- [ ] Add methods for config sync history tracking

### Phase 3: Integration (Week 3)

#### 3.1 ChannelManager Updates
**Location**: `template/global/mcp/claude-slack/channels/manager.py`

**Tasks**:
- [ ] Add `apply_default_channels()` method
- [ ] Update channel creation to respect `access_type` and `is_default`
- [ ] Remove hardcoded defaults
- [ ] Update tests for new behavior

#### 3.2 SubscriptionManager Updates
**Location**: `template/global/mcp/claude-slack/subscriptions/manager.py`

**Tasks**:
- [ ] Update `apply_default_subscriptions()` to use config
- [ ] Remove hardcoded channel lists
- [ ] Add support for frontmatter exclusions
- [ ] Handle both subscriptions and memberships based on access_type
- [ ] Update tests

#### 3.3 AgentManager Integration
**Location**: `template/global/mcp/claude-slack/agents/manager.py`

**Tasks**:
- [ ] Add `register_discovered_agent()` method
- [ ] Add `bulk_register()` for multiple agents
- [ ] Update registration to work with DiscoveredAgent objects
- [ ] Ensure DM policies are set during registration

### Phase 4: Migration (Week 4)

#### 4.1 ProjectSetupManager Migration
**Location**: `template/global/mcp/claude-slack/projects/setup_manager.py`

**Tasks**:
- [ ] Add ConfigSyncManager as internal component
- [ ] Update `setup_new_project()` to delegate to ConfigSyncManager
- [ ] Update `initialize_session()` to use ConfigSyncManager
- [ ] Update `setup_global_environment()` to use ConfigSyncManager
- [ ] Keep existing interface for backward compatibility
- [ ] Add deprecation warnings

#### 4.2 Hook Updates
**Tasks**:
- [ ] Update `slack_session_start.py` to use ConfigSyncManager
- [ ] Update any project initialization hooks
- [ ] Test hook integration with new system
- [ ] Document hook changes

#### 4.3 Testing & Validation
**Tasks**:
- [ ] Create comprehensive test suite for ConfigSyncManager
- [ ] Test migration from old to new system
- [ ] Test `is_default` behavior for all channel types
- [ ] Test agent discovery in various scenarios
- [ ] Performance testing with large configurations
- [ ] Integration testing with existing workflows

### Phase 5: Cleanup & Optimization (Week 5)

#### 5.1 Remove Legacy Code
**Tasks**:
- [ ] Remove ProjectSetupManager (after verification)
- [ ] Remove hardcoded defaults from all managers
- [ ] Clean up unused imports and methods
- [ ] Update all documentation

#### 5.2 Performance Optimization
**Tasks**:
- [ ] Add caching for configuration loading
- [ ] Optimize reconciliation plan execution
- [ ] Add database indexes for new columns
- [ ] Implement batch operations where possible

#### 5.3 Monitoring & Observability
**Tasks**:
- [ ] Add metrics for reconciliation operations
- [ ] Implement configuration drift detection
- [ ] Add logging for all configuration changes
- [ ] Create admin tools for viewing sync history

## Testing Strategy

### Unit Tests
```python
# tests/test_agent_discovery.py
- test_discover_project_agents()
- test_discover_global_agents()
- test_discovery_with_missing_directory()
- test_discovery_with_invalid_frontmatter()

# tests/test_config_sync_manager.py
- test_reconcile_empty_state()
- test_reconcile_with_existing_channels()
- test_is_default_open_channels()
- test_is_default_members_channels()
- test_agent_exclusions()
- test_opt_out_persistence()

# tests/test_reconciliation_plan.py
- test_plan_phases_execution_order()
- test_plan_rollback_on_error()
- test_action_idempotency()
```

### Integration Tests
```python
# tests/test_config_integration.py
- test_full_project_setup_flow()
- test_session_initialization()
- test_config_file_changes_applied()
- test_agent_discovery_to_registration()
- test_default_provisioning_flow()
```

### Migration Tests
```python
# tests/test_migration.py
- test_backward_compatibility()
- test_projectsetupmanager_delegation()
- test_schema_migration()
- test_data_preservation()
```

## Rollout Strategy

### Development Environment (Week 1-3)
1. Deploy schema changes
2. Deploy new components alongside existing
3. Test with development projects

### Staging Environment (Week 4)
1. Run migration tests
2. Parallel run with old system
3. Validate configuration sync
4. Performance testing

### Production Rollout (Week 5)
1. **Phase A**: Deploy new code with feature flag disabled
2. **Phase B**: Enable for new projects only
3. **Phase C**: Migrate existing projects gradually
4. **Phase D**: Remove old code and feature flags

## Success Criteria

### Functional Requirements
- [ ] All existing functionality preserved
- [ ] Configuration changes detected and applied
- [ ] `is_default` works for both open and members channels
- [ ] Agent discovery finds all agents correctly
- [ ] Reconciliation is idempotent

### Performance Requirements
- [ ] Reconciliation completes in < 5 seconds for typical project
- [ ] No performance regression vs ProjectSetupManager
- [ ] Configuration loading cached appropriately

### Quality Requirements
- [ ] 90% test coverage for new code
- [ ] No increase in error rates
- [ ] Clear logging for all operations
- [ ] Documentation complete and accurate

## Risk Mitigation

### Risk: Breaking Existing Functionality
**Mitigation**:
- Implement alongside existing code
- Extensive testing before migration
- Feature flags for gradual rollout
- Easy rollback plan

### Risk: Performance Issues
**Mitigation**:
- Benchmark before and after
- Optimize database queries
- Add caching where appropriate
- Monitor performance metrics

### Risk: Configuration Complexity
**Mitigation**:
- Provide migration tools
- Clear documentation
- Validation of configuration files
- Good error messages

## Documentation Updates

### User Documentation
- [ ] Update README with new configuration format
- [ ] Create migration guide from old format
- [ ] Document `is_default` behavior
- [ ] Add troubleshooting guide

### Developer Documentation
- [ ] Document ConfigSyncManager API
- [ ] Document AgentDiscoveryService API
- [ ] Create architecture diagrams
- [ ] Add code examples

### Operations Documentation
- [ ] Document monitoring approach
- [ ] Create runbook for common issues
- [ ] Document database schema changes
- [ ] Add performance tuning guide

## Timeline Summary

| Week | Phase | Key Deliverables |
|------|-------|-----------------|
| 1 | Foundation | Schema updates, AgentDiscoveryService, Config updates |
| 2 | Core Implementation | ReconciliationPlan, ConfigSyncManager core |
| 3 | Integration | Manager updates, unified behavior |
| 4 | Migration | ProjectSetupManager migration, hook updates |
| 5 | Cleanup | Remove legacy code, optimization, monitoring |

## Next Steps

1. **Immediate**: Review and approve this roadmap
2. **Day 1**: Create feature branch for development
3. **Day 2**: Begin Phase 1.1 (Database Schema Updates)
4. **Week 1**: Complete Foundation phase
5. **Week 2+**: Continue per roadmap

## Conclusion

This implementation roadmap provides a clear path from the current fragmented configuration system to a unified, reconciliation-based approach. The phased implementation ensures we can maintain system stability while gradually introducing new functionality.

The key innovations are:
- **ConfigSyncManager**: Centralized configuration orchestration
- **AgentDiscoveryService**: Clean separation of discovery from management
- **Unified `is_default`**: Consistent behavior across channel types
- **Reconciliation Pattern**: Idempotent, trackable configuration application

By following this roadmap, we'll achieve a more maintainable, predictable, and powerful configuration system for Claude-Slack V3.