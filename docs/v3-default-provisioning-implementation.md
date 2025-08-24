# V3 Default Provisioning Implementation Guide

## Overview

This guide provides concrete implementation details for the unified `is_default` behavior in the V3 architecture. It includes code changes needed, database modifications, and step-by-step implementation instructions.

## Current State vs. Target State

### Current State (Problem)
- `is_default` field exists but has no functional behavior
- Default subscriptions are hardcoded in `SubscriptionManager`
- No automatic membership for `members` type channels
- Config defines defaults but they're not consistently applied

### Target State (Solution)
- `is_default` triggers automatic access provisioning
- Unified behavior across `open` and `members` channels  
- Config-driven defaults with frontmatter overrides
- Clear tracking of default vs. explicit access

## Implementation Plan

### Phase 1: Database Schema Updates

Add tracking columns for default provisioning:

```sql
-- Track default provisioning in subscriptions (for open channels)
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS
    is_from_default BOOLEAN DEFAULT FALSE,
    opted_out BOOLEAN DEFAULT FALSE,
    opted_out_at TIMESTAMP;

-- Track default provisioning in channel_members (for members channels)
ALTER TABLE channel_members ADD COLUMN IF NOT EXISTS
    is_from_default BOOLEAN DEFAULT FALSE,
    opted_out BOOLEAN DEFAULT FALSE,
    opted_out_at TIMESTAMP;

-- Add indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_subscriptions_defaults 
    ON subscriptions(is_from_default, opted_out);
CREATE INDEX IF NOT EXISTS idx_channel_members_defaults 
    ON channel_members(is_from_default, opted_out);
```

### Phase 2: Core Implementation Changes

#### 2.1 Update DatabaseManager (`db/manager.py`)

Add methods to handle default provisioning:

```python
@with_connection(writer=True)
async def apply_default_channel_access(self, conn,
                                      agent_name: str,
                                      agent_project_id: Optional[str],
                                      channel_id: str,
                                      access_type: str) -> bool:
    """
    Apply default access for an agent to a channel based on access type.
    
    Args:
        agent_name: Agent name
        agent_project_id: Agent's project ID
        channel_id: Channel to grant access to
        access_type: Channel's access type (open/members)
    
    Returns:
        True if access granted, False otherwise
    """
    try:
        if access_type == 'open':
            # Add to subscriptions
            await conn.execute("""
                INSERT INTO subscriptions 
                (agent_name, agent_project_id, channel_id, is_from_default, source)
                VALUES (?, ?, ?, TRUE, 'default')
                ON CONFLICT (agent_name, agent_project_id, channel_id) 
                DO UPDATE SET 
                    is_from_default = TRUE
                WHERE opted_out = FALSE
            """, (agent_name, agent_project_id, channel_id))
            
        elif access_type == 'members':
            # Add to channel_members
            await conn.execute("""
                INSERT INTO channel_members
                (channel_id, agent_name, agent_project_id, role, 
                 can_send, is_from_default)
                VALUES (?, ?, ?, 'member', TRUE, TRUE)
                ON CONFLICT (channel_id, agent_name, agent_project_id)
                DO UPDATE SET
                    is_from_default = TRUE
                WHERE opted_out = FALSE
            """, (channel_id, agent_name, agent_project_id))
            
        return True
        
    except Exception as e:
        self.logger.error(f"Error applying default access: {e}")
        return False

@with_connection(writer=False)
async def get_default_channels(self, conn,
                              agent_project_id: Optional[str] = None) -> List[Dict]:
    """
    Get all channels where is_default=true and agent is eligible.
    
    Args:
        agent_project_id: Agent's project ID for eligibility check
        
    Returns:
        List of channels that should be default for this agent
    """
    if agent_project_id:
        # Get both global and project-specific defaults
        cursor = await conn.execute("""
            SELECT id, channel_type, access_type, scope, name, project_id
            FROM channels
            WHERE is_default = TRUE
            AND is_archived = FALSE
            AND (
                scope = 'global' OR 
                (scope = 'project' AND project_id = ?)
            )
        """, (agent_project_id,))
    else:
        # Global agent - only global defaults
        cursor = await conn.execute("""
            SELECT id, channel_type, access_type, scope, name, project_id
            FROM channels
            WHERE is_default = TRUE
            AND is_archived = FALSE
            AND scope = 'global'
        """)
    
    rows = await cursor.fetchall()
    return [
        {
            'id': row[0],
            'channel_type': row[1],
            'access_type': row[2],
            'scope': row[3],
            'name': row[4],
            'project_id': row[5]
        }
        for row in rows
    ]

@with_connection(writer=True)
async def mark_access_opted_out(self, conn,
                               agent_name: str,
                               agent_project_id: Optional[str],
                               channel_id: str) -> bool:
    """
    Mark that an agent has opted out of default access to a channel.
    
    This prevents the system from re-adding them during sync operations.
    """
    try:
        # Check channel access type
        cursor = await conn.execute("""
            SELECT access_type FROM channels WHERE id = ?
        """, (channel_id,))
        row = await cursor.fetchone()
        
        if not row:
            return False
            
        access_type = row[0]
        
        if access_type == 'open':
            await conn.execute("""
                UPDATE subscriptions
                SET opted_out = TRUE, opted_out_at = CURRENT_TIMESTAMP
                WHERE agent_name = ? 
                AND agent_project_id IS NOT DISTINCT FROM ?
                AND channel_id = ?
            """, (agent_name, agent_project_id, channel_id))
        else:
            await conn.execute("""
                UPDATE channel_members
                SET opted_out = TRUE, opted_out_at = CURRENT_TIMESTAMP
                WHERE agent_name = ?
                AND agent_project_id IS NOT DISTINCT FROM ?
                AND channel_id = ?
            """, (agent_name, agent_project_id, channel_id))
        
        return True
        
    except Exception as e:
        self.logger.error(f"Error marking opt-out: {e}")
        return False
```

#### 2.2 Update ChannelManager (`channels/manager.py`)

Add method to create default channels with proper access types:

```python
async def apply_default_channels(self, 
                                scope: str = 'global',
                                project_id: Optional[str] = None,
                                created_by: str = 'system') -> List[str]:
    """
    Create default channels from configuration with V3 access types.
    
    Args:
        scope: 'global' or 'project'
        project_id: Required for project scope
        created_by: Who is creating these channels
        
    Returns:
        List of channel IDs created
    """
    if scope == 'project' and not project_id:
        self.logger.error("project_id required for project scope")
        return []
    
    created_channels = []
    
    # Get channel configs from ConfigManager
    config = get_config_manager().get_default_channels(scope)
    channel_configs = config.get(scope, [])
    
    for channel_config in channel_configs:
        name = channel_config.get('name')
        if not name:
            continue
            
        # Generate channel ID based on scope
        channel_id = self.get_scoped_channel_id(name, scope, project_id)
        
        # Extract V3 properties
        access_type = channel_config.get('access_type', 'open')
        is_default = channel_config.get('is_default', False)
        description = channel_config.get('description', f'{scope.title()} {name} channel')
        
        # Create the channel
        created_id = await self.create_channel(
            name=name,
            scope=scope,
            access_type=access_type,
            project_id=project_id,
            description=description,
            created_by=created_by,
            is_default=is_default
        )
        
        if created_id:
            created_channels.append(created_id)
            self.logger.info(f"Created default channel: {created_id} "
                           f"(access_type={access_type}, is_default={is_default})")
    
    return created_channels
```

#### 2.3 Update SubscriptionManager (`subscriptions/manager.py`)

Replace hardcoded defaults with config-driven approach:

```python
async def apply_default_subscriptions(self,
                                     agent_name: str,
                                     agent_project_id: Optional[str],
                                     force: bool = False,
                                     respect_exclusions: bool = True) -> List[str]:
    """
    Apply default channel access based on is_default flags.
    
    This method now handles both subscriptions (open channels) and 
    memberships (members channels) based on the channel's access_type.
    
    Args:
        agent_name: Agent name
        agent_project_id: Agent's project ID
        force: If True, reapply even if already exists
        respect_exclusions: If True, check frontmatter exclusions
        
    Returns:
        List of channel IDs where access was granted
    """
    applied_channels = []
    
    # Get agent's exclusions from frontmatter if needed
    exclusions = []
    if respect_exclusions:
        agent_file = self._get_agent_file_path(agent_name, agent_project_id)
        if agent_file and os.path.exists(agent_file):
            agent_data = FrontmatterParser.parse_file(agent_file)
            exclusions = agent_data.get('channels', {}).get('exclude', [])
    
    # Get all default channels for this agent
    default_channels = await self.db.get_default_channels(agent_project_id)
    
    for channel in default_channels:
        channel_id = channel['id']
        channel_name = channel['name']
        
        # Check exclusions
        if channel_name in exclusions:
            self.logger.debug(f"Skipping excluded channel: {channel_name}")
            continue
        
        # Check if already has access (unless forcing)
        if not force:
            if channel['access_type'] == 'open':
                # Check existing subscription
                is_subscribed = await self.db.is_subscribed(
                    agent_name, agent_project_id, channel_id
                )
                if is_subscribed:
                    continue
            elif channel['access_type'] == 'members':
                # Check existing membership
                is_member = await self.channel_manager.is_channel_member(
                    channel_id, agent_name, agent_project_id
                )
                if is_member:
                    continue
        
        # Apply default access based on type
        success = await self.db.apply_default_channel_access(
            agent_name, agent_project_id, channel_id, channel['access_type']
        )
        
        if success:
            applied_channels.append(channel_id)
            self.logger.info(f"Applied default access to {channel_id} "
                           f"(type={channel['access_type']})")
    
    return applied_channels

def _get_agent_file_path(self, agent_name: str, 
                         agent_project_id: Optional[str]) -> Optional[str]:
    """Get the path to an agent's markdown file"""
    if agent_project_id:
        # Project agent
        project = self.db.get_project(agent_project_id)
        if project:
            project_path = project['path']
            return os.path.join(project_path, '.claude', 'agents', f'{agent_name}.md')
    else:
        # Global agent
        claude_dir = os.environ.get('CLAUDE_CONFIG_DIR', 
                                   os.path.expanduser('~/.claude'))
        return os.path.join(claude_dir, 'agents', f'{agent_name}.md')
    
    return None
```

#### 2.4 Update Frontmatter Parser

Add support for exclusion lists:

```python
# In frontmatter/parser.py
class FrontmatterParser:
    @staticmethod
    def parse_file(file_path: str) -> Dict[str, Any]:
        """Parse frontmatter with support for exclusions"""
        # ... existing parsing logic ...
        
        # Normalize channels section
        if 'channels' in frontmatter:
            channels = frontmatter['channels']
            
            # Support both old and new formats
            if isinstance(channels, dict):
                # New format with exclusions
                frontmatter['channels'] = {
                    'global': channels.get('global', []),
                    'project': channels.get('project', []),
                    'exclude': channels.get('exclude', []),
                    'never_default': channels.get('never_default', False)
                }
            elif isinstance(channels, list):
                # Old format - convert
                frontmatter['channels'] = {
                    'global': channels,
                    'project': [],
                    'exclude': [],
                    'never_default': False
                }
        
        return frontmatter
```

### Phase 3: Configuration Updates

Update the default configuration file:

```yaml
# template/global/config/claude-slack.config.yaml
version: "1.1"  # Bump version for new structure

# Default channels with V3 properties
default_channels:
  global:
    - name: announcements
      description: "Important system updates"
      access_type: open
      is_default: true
      
    - name: general  
      description: "General discussion"
      access_type: open
      is_default: true
      
    - name: security-alerts
      description: "Security notifications"
      access_type: members
      is_default: false  # Invite-only
      
    - name: all-hands
      description: "All team members"
      access_type: members
      is_default: true  # All agents become members
    
  project:
    - name: general
      description: "Project general discussion"
      access_type: open
      is_default: true
      
    - name: team
      description: "Project team coordination"
      access_type: members
      is_default: true  # All project agents become members
      
    - name: dev
      description: "Development discussion"
      access_type: open
      is_default: true
      
    - name: leads
      description: "Project leads only"
      access_type: members
      is_default: false  # Selective membership

# Remove old default_agent_subscriptions section
# (replaced by is_default on channels)
```

### Phase 4: Handle Edge Cases

#### 4.1 Unsubscribe/Leave Tracking

When an agent explicitly unsubscribes or leaves:

```python
async def unsubscribe_from_channel(self, agent_name: str, 
                                  agent_project_id: Optional[str],
                                  channel_id: str,
                                  mark_opted_out: bool = True) -> bool:
    """
    Unsubscribe with opt-out tracking to prevent re-adding.
    
    Args:
        mark_opted_out: If True and this was a default, mark as opted out
    """
    # Get channel info
    channel = await self.db.get_channel(channel_id)
    
    # Remove subscription
    success = await self.db.unsubscribe_from_channel(
        agent_name, agent_project_id, channel_id
    )
    
    # If this was a default channel, mark as opted out
    if success and mark_opted_out and channel and channel['is_default']:
        await self.db.mark_access_opted_out(
            agent_name, agent_project_id, channel_id
        )
    
    return success
```

#### 4.2 Project Migration

When an agent moves projects:

```python
async def migrate_agent_project(self,
                               agent_name: str,
                               old_project_id: Optional[str],
                               new_project_id: Optional[str]):
    """
    Handle agent moving between projects.
    
    - Remove old project default memberships
    - Apply new project defaults
    """
    # Remove memberships from old project defaults
    if old_project_id:
        old_defaults = await self.db.get_default_channels(old_project_id)
        for channel in old_defaults:
            if channel['scope'] == 'project' and channel['access_type'] == 'members':
                await self.db.remove_channel_member(
                    channel['id'], agent_name, old_project_id
                )
    
    # Apply new project defaults
    if new_project_id:
        await self.apply_default_subscriptions(
            agent_name, new_project_id, force=False
        )
```

## Testing Plan

### Unit Tests

```python
# tests/test_default_provisioning.py
import pytest

@pytest.mark.asyncio
async def test_is_default_open_channel(db_manager):
    """Test that is_default on open channels triggers subscription"""
    # Create default open channel
    await db_manager.create_channel(
        channel_id='global:test',
        channel_type='channel',
        access_type='open',
        scope='global',
        name='test',
        is_default=True
    )
    
    # Register agent
    await db_manager.register_agent('alice', None)
    
    # Apply defaults
    channels = await db_manager.get_default_channels(None)
    assert len(channels) == 1
    
    # Verify subscription created
    is_subscribed = await db_manager.is_subscribed('alice', None, 'global:test')
    assert is_subscribed

@pytest.mark.asyncio
async def test_is_default_members_channel(db_manager):
    """Test that is_default on members channels triggers membership"""
    # Create default members channel
    await db_manager.create_channel(
        channel_id='global:team',
        channel_type='channel',
        access_type='members',
        scope='global',
        name='team',
        is_default=True
    )
    
    # Register agent and apply defaults
    await db_manager.register_agent('bob', None)
    await db_manager.apply_default_channel_access(
        'bob', None, 'global:team', 'members'
    )
    
    # Verify membership created
    members = await db_manager.get_channel_members('global:team')
    assert any(m['agent_name'] == 'bob' for m in members)

@pytest.mark.asyncio
async def test_exclusion_list(subscription_manager):
    """Test that frontmatter exclusions are respected"""
    # Create agent with exclusions
    agent_data = {
        'name': 'charlie',
        'channels': {
            'exclude': ['announcements', 'general']
        }
    }
    
    # Apply defaults with exclusions
    applied = await subscription_manager.apply_default_subscriptions(
        'charlie', None, respect_exclusions=True
    )
    
    # Verify excluded channels not applied
    assert 'global:announcements' not in applied
    assert 'global:general' not in applied

@pytest.mark.asyncio  
async def test_opt_out_persistence(db_manager):
    """Test that opt-outs persist across syncs"""
    # Subscribe then unsubscribe (with opt-out)
    await db_manager.subscribe_to_channel('alice', None, 'global:test')
    await db_manager.mark_access_opted_out('alice', None, 'global:test')
    
    # Try to reapply defaults
    success = await db_manager.apply_default_channel_access(
        'alice', None, 'global:test', 'open'
    )
    
    # Verify not re-subscribed
    is_subscribed = await db_manager.is_subscribed('alice', None, 'global:test')
    assert not is_subscribed
```

### Integration Tests

```python
# tests/test_default_provisioning_integration.py

@pytest.mark.asyncio
async def test_full_agent_provisioning_flow():
    """Test complete agent setup with defaults"""
    # Setup project with defaults
    await setup_manager.setup_project(
        project_id='test_proj',
        project_path='/test/path'
    )
    
    # Register agent
    await agent_manager.register_agent(
        name='alice',
        project_id='test_proj'
    )
    
    # Apply defaults
    applied = await subscription_manager.apply_default_subscriptions(
        'alice', 'test_proj'
    )
    
    # Verify correct channels applied
    assert 'global:announcements' in applied  # Global default
    assert 'proj_test_pro:general' in applied  # Project default
    assert 'proj_test_pro:team' in applied  # Members default
```

## Rollout Strategy

### Stage 1: Database Updates
1. Add new columns with defaults
2. Backfill `is_from_default` for existing subscriptions
3. Deploy schema changes

### Stage 2: Core Logic
1. Deploy DatabaseManager changes
2. Deploy ChannelManager changes
3. Test with new agents only

### Stage 3: Migration
1. Update existing agents to use new system
2. Run migration script to apply defaults
3. Monitor for issues

### Stage 4: Cleanup
1. Remove hardcoded defaults
2. Update documentation
3. Deprecate old methods

## Monitoring and Metrics

Track success of default provisioning:

```sql
-- Monitor default adoption
SELECT 
    c.name,
    c.access_type,
    COUNT(CASE WHEN s.is_from_default THEN 1 END) as default_access,
    COUNT(CASE WHEN NOT s.is_from_default THEN 1 END) as explicit_access,
    COUNT(CASE WHEN s.opted_out THEN 1 END) as opted_out
FROM channels c
LEFT JOIN subscriptions s ON c.id = s.channel_id
WHERE c.is_default = TRUE
GROUP BY c.id;

-- Track opt-out patterns
SELECT 
    channel_id,
    COUNT(*) as opt_out_count,
    AVG(julianday(opted_out_at) - julianday(subscribed_at)) as avg_days_before_optout
FROM subscriptions
WHERE opted_out = TRUE
GROUP BY channel_id
ORDER BY opt_out_count DESC;
```

## Summary

This implementation unifies the `is_default` behavior across channel types, providing:
1. Automatic provisioning appropriate to channel access type
2. Config-driven defaults with frontmatter overrides
3. Proper tracking and respect for user choices
4. Clean migration path from the old system

The key insight is treating "default access" as a concept that manifests differently based on the channel's permission model, while maintaining a consistent user experience.