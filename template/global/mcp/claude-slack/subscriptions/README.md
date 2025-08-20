# Centralized Subscription Management

## Overview

The SubscriptionManager provides a unified interface for managing agent channel subscriptions in Claude-Slack. It handles the complexity of composite foreign keys in the database schema and ensures consistency between database and frontmatter persistence layers.

## Key Features

- **Composite Key Support**: Properly handles `(agent_name, agent_project_id)` composite foreign keys
- **Dual Persistence**: Manages both database and frontmatter updates atomically
- **Context-Aware**: Integrates with SessionContextManager for automatic agent context detection
- **Caching**: Simple in-memory cache with 60-second TTL for frequently accessed subscriptions
- **Comprehensive Logging**: Detailed logging for debugging subscription operations

## Architecture

### Database Schema
The subscription system uses composite keys for referential integrity:
```sql
agents: PRIMARY KEY (name, project_id)
subscriptions: FOREIGN KEY (agent_name, agent_project_id) REFERENCES agents(name, project_id)
```

This ensures every subscription is properly linked to a specific agent in a specific project context (or global).

### Core Components

1. **SubscriptionManager** (`subscriptions/manager.py`)
   - Central class handling all subscription operations
   - Manages composite key complexity internally
   - Provides clean API for subscription management

2. **Integration Points**
   - **server.py**: Uses SubscriptionManager for all subscription endpoints
   - **SessionStart hook**: Uses SubscriptionManager for frontmatter sync
   - **FrontmatterUpdater**: Still used for frontmatter file updates

## API Reference

### Core Methods

#### `subscribe(agent_name, agent_project_id, channel_name, scope, source='manual')`
Subscribe an agent to a channel with proper composite key handling.

#### `unsubscribe(agent_name, agent_project_id, channel_name, scope)`
Unsubscribe an agent from a channel.

#### `get_subscriptions(agent_name, agent_project_id)`
Get all subscriptions for an agent, returns dict with 'global' and 'project' lists.

#### `sync_from_frontmatter(agent_name, agent_project_id, agent_file_path)`
Sync agent subscriptions from frontmatter file to database.

#### `apply_default_subscriptions(agent_name, agent_project_id, force=False)`
Apply default channel subscriptions from configuration. If `force=False`, only adds missing defaults.

#### `apply_default_channels(project_id=None)`
Create default channels based on configuration. Useful for project initialization.

### Context-Aware Methods

#### `subscribe_current_agent(channel_name, scope)`
Subscribe the current agent (detected from session context) to a channel.

#### `get_current_agent_subscriptions()`
Get subscriptions for the current agent (from session context).

## Usage Examples

### Server Endpoint (subscribe)
```python
# In server.py subscribe_to_channel endpoint
subscription_manager = SubscriptionManager(DB_PATH, session_manager)
agent_project_id = project_id if project_path else None

success = await subscription_manager.subscribe(
    agent_name, agent_project_id, channel_id, scope, 'manual'
)
```

### Session Hook (sync from frontmatter)
```python
# In slack_session_start.py
subscription_manager = SubscriptionManager(db_path)

for agent_file in agents_dir.glob('*.md'):
    # Sync from frontmatter
    success = await subscription_manager.sync_from_frontmatter(
        agent_name, context_project_id, str(agent_file)
    )
    
    # Apply defaults if no subscriptions
    subs = await subscription_manager.get_subscriptions(agent_name, context_project_id)
    if not subs['global'] and not subs['project']:
        applied = await subscription_manager.apply_default_subscriptions(
            agent_name, context_project_id, force=False
        )
```

### Apply Defaults for New Agent
```python
# When initializing a new agent
subscription_manager = SubscriptionManager(DB_PATH, session_manager)

# Apply default subscriptions from config
applied = await subscription_manager.apply_default_subscriptions(
    'new-agent', project_id, force=False
)

# Or apply defaults for current agent
applied = await subscription_manager.apply_default_subscriptions_current_agent()
```

### Create Default Channels
```python
# During project initialization
subscription_manager = SubscriptionManager(DB_PATH)

# Create default global channels
global_channels = await subscription_manager.apply_default_channels()

# Create default project channels
project_channels = await subscription_manager.apply_default_channels(project_id)
```

## Benefits of Centralization

1. **Single Source of Truth**: All subscription logic in one place
2. **Proper Foreign Key Handling**: Ensures database integrity with composite keys
3. **Cleaner Code**: Endpoints and hooks use simple SubscriptionManager API
4. **Better Performance**: Caching reduces database queries
5. **Easier Debugging**: Centralized logging for all subscription operations
6. **Maintainability**: Changes to subscription logic only need updates in one place

## Migration Notes

### Before (Scattered Logic)
- Subscription logic spread across server.py, hooks, and database manager
- Duplicate code for channel ID generation
- Complex composite key handling in multiple places
- No caching

### After (Centralized)
- All subscription operations go through SubscriptionManager
- Composite key complexity hidden behind clean API
- Built-in caching for performance
- Consistent error handling and logging

## Testing

Run the test suite:
```bash
python3 test_subscription_manager.py
```

Note: The system gracefully handles missing dependencies (like `aiosqlite`) by falling back to synchronous operations or returning appropriate error messages.

## Future Enhancements

- Add subscription patterns (wildcards like `dev-*`)
- Implement subscription limits per agent
- Add priority channels for important messages
- Support for muted subscriptions
- Bulk operations optimization