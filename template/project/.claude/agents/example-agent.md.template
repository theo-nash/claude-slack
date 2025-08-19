---
name: example-agent
description: Example agent showing scoped channel subscriptions
tools: All
channels:                           # Scoped channel subscriptions
  global:                          # Global channels (available everywhere)
    - general
    - announcements
    - cross-project
  project:                         # Project-specific channels (only in current project)
    - dev
    - testing
    - releases
direct_messages: enabled            # Can receive DMs (default: enabled)
message_preferences:                # Optional preferences
  auto_subscribe_patterns:          # Auto-subscribe to channels matching patterns
    global:
      - security-*                 # Auto-subscribe to any global security channels
      - alert-*                     # Auto-subscribe to any global alert channels
    project:
      - feature-*                   # Auto-subscribe to project feature channels
      - bug-*                       # Auto-subscribe to project bug channels
  muted_channels: []               # Channels to mute notifications from
  dm_scope_preference: project     # Prefer project or global for DMs (default: project)
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