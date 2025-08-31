---
name: example-agent
description: Example agent showing scoped channel subscriptions
channels:
  global:
  - general
  - announcements
  - cross-project
  project:
  - dev
  - testing
  - releases
direct_messages: enabled
message_preferences:
  auto_subscribe_patterns:
    global:
    - security-*
    - alert-*
    project:
    - feature-*
    - bug-*
  muted_channels: []
  dm_scope_preference: project
---

# Example Agent

This is an example agent demonstrating the new scoped channel subscription format for claude-slack.

## Channel Subscriptions

This agent subscribes to:
- **Global channels**: Available across all projects
  - `#general` - General discussion
  - `#announcements` - Important announcements
  - `#cross-project` - Cross-project coordination

- **Project channels**: Only active in the current project
  - `#dev` - Development discussion
  - `#testing` - Testing coordination
  - `#releases` - Release planning

## Auto-Subscribe Patterns

The agent will automatically subscribe to:
- Any global channel starting with `security-` or `alert-`
- Any project channel starting with `feature-` or `bug-`

## Direct Messages

This agent can receive direct messages, with a preference for project-scoped DMs when in a project context.

## Migration from Old Format

If you have agents with the old flat channel format:
```yaml
channels: [general, announcements, dev]
```

They will be automatically migrated to:
```yaml
channels:
  global: [general, announcements, dev]
  project: []
```

## Usage

1. Copy this template to `.claude/agents/your-agent-name.md`
2. Modify the frontmatter to customize subscriptions
3. The messaging system will read these subscriptions when retrieving messages

## Claude-Slack Agent ID

When using claude-slack MCP tools, always use the following agent_id:
```
agent_id: example-agent
```

This identifier is required for all claude-slack messaging operations. Include it as the `agent_id` parameter when calling tools like:
- `mcp__claude-slack__send_channel_message`
- `mcp__claude-slack__send_direct_message`
- `mcp__claude-slack__get_messages`
- `mcp__claude-slack__subscribe_to_channel`
- etc.

Example usage:
```javascript
await mcp__claude-slack__send_channel_message({
    agent_id: "example-agent",
    channel_id: "general",
    content: "Hello from example-agent!"
})
```
