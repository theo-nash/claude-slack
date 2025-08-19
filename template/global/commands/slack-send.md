---
name: slack-send
description: Send a message to a channel with scope awareness
---

# Send Message to Channel

Send a message to a specified channel, with automatic scope detection based on context.

## Usage:
```
/slack-send #channel Your message here
/slack-send #global:announcements Global announcement here
/slack-send #project:dev Project-specific message here
```

## What this command does:

1. **Parses the command arguments**
   - First argument: channel name (with or without #)
   - Remaining arguments: message content
   - Supports scope prefixes (global: or project:)

2. **Determines channel scope**
   - If prefix provided (global: or project:), uses that scope explicitly
   - Otherwise, auto-detects based on current context
   - Checks if channel exists in project scope first, then global

3. **Sends the message**
   - Uses `send_channel_message` MCP tool
   - Includes your agent name as sender
   - Adds appropriate scope parameter

## Scope resolution:
- `#general` → Checks project first (if in project), then global
- `#global:general` → Always sends to global channel
- `#project:dev` → Always sends to current project's channel

## Examples:
```
/slack-send #general Hello everyone!
  → Sends to project #general if in project and channel exists, else global

/slack-send #global:announcements System maintenance at 3pm
  → Always sends to global #announcements

/slack-send #project:dev Code review needed for PR #123
  → Sends to current project's #dev channel
```

## Error handling:
- If channel doesn't exist, offer to create it
- If not subscribed, offer to subscribe first
- Show clear error if in global context but trying to send to project channel

## Implementation notes:
- Parse channel name and scope prefix
- Use `send_channel_message` with detected scope
- Confirm with: "✅ Message sent to [scope] #channel"