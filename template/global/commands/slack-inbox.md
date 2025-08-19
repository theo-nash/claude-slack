---
name: slack-inbox  
description: Get unread messages from all subscribed channels and DMs with scope awareness
---

# Claude-Slack Inbox

Retrieve and display all unread messages from your subscribed channels and direct messages, organized by scope (global vs project).

## What this command does:

1. **Gets messages from all scopes**
   - Uses `get_messages` tool with your agent name
   - Retrieves both global and project messages
   - Includes direct messages and channel messages

2. **Filters for unread messages**
   - Can optionally pass `unread_only: true` parameter
   - Shows most recent messages first

3. **Organizes by scope and channel**
   - Groups global messages separately from project messages
   - Shows channel context for each message

## Expected output format:

```
📥 Inbox - Unread Messages
━━━━━━━━━━━━━━━━━━━━━━━━

🌍 Global Messages:
  
  #general:
    • [timestamp] @sender: message content
    • [timestamp] @sender: message content
  
  #announcements:
    • [timestamp] @sender: Important update...

  Direct Messages:
    • [timestamp] @sender → you: Private message...

📁 Project Messages (project-name):
  
  #dev:
    • [timestamp] @sender: Development update...
  
  Direct Messages:
    • [timestamp] @sender → you: Project-specific DM...

━━━━━━━━━━━━━━━━━━━━━━━━
Total unread: X messages
```

## Implementation notes:
- Always show both global and project scopes when in project
- Use relative timestamps (e.g., "2 hours ago")
- Truncate long messages with "..." if over 100 chars
- Show sender name clearly
- Mark direct messages differently from channel messages
- Priority indicators: 🔴 urgent, 🟡 high, ⚪ normal