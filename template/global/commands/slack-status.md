---
name: slack-status
description: Show Claude-Slack messaging system status with project context
---

# Claude-Slack Status

Check the status of the Claude-Slack messaging system, including project context and scoped channels.

## What this command does:

1. **Checks current project context**
   - Uses `get_current_project` tool to identify if you're in a project or global context
   - Shows project name and ID if applicable

2. **Lists your channel subscriptions**
   - Uses `get_my_subscriptions` tool to show subscriptions by scope
   - Separates global channels from project channels

3. **Shows available channels**
   - Uses `list_channels` to display all accessible channels
   - Marks which ones you're subscribed to

4. **Displays message statistics**
   - Shows unread message count
   - Lists recent activity

## Expected output format:

```
📊 Claude-Slack Status
━━━━━━━━━━━━━━━━━━━━━

🌍 Context: [Global | Project: project-name]

📺 Your Subscriptions:
  Global Channels:
    ✓ #general
    ✓ #announcements
  
  Project Channels:
    ✓ #dev
    ✓ #testing

📬 Messages:
  • Unread: X messages
  • Last activity: timestamp

🔍 Available Channels:
  [List of all channels with subscription status]
```

## Implementation notes:
- Always check project context first
- Show scoped channels clearly separated
- Use checkmarks (✓) for subscribed channels
- Include both global and project channels when in project context