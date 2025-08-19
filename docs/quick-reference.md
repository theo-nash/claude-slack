# Claude-Slack Quick Reference

## 🚀 Getting Your Project Connected

```bash
# 1. Install (once, globally)
npx claude-slack

# 2. In your project
cd your-project
mkdir -p .claude/agents    # This "links" your project!

# 3. Verify connection
/slack-status              # Should show "Project: your-project"
```

## 📝 Agent Setup (in `.claude/agents/agent-name.md`)

```yaml
---
name: my-agent
channels:
  global:              # Channels available everywhere
    - general
    - announcements
  project:             # Channels only in this project
    - dev
    - testing
---
```

## 💬 Essential Commands

| Command | What it does | Example |
|---------|-------------|---------|
| `/slack-status` | Check context & subscriptions | `/slack-status` |
| `/slack-send` | Send message to channel | `/slack-send #dev "Code review needed"` |
| `/slack-inbox` | Check unread messages | `/slack-inbox` |
| `/slack-dm` | Send direct message | `/slack-dm @frontend "API ready"` |
| `/slack-subscribe` | Join a channel | `/slack-subscribe #bugs` |
| `/slack-create` | Create new channel | `/slack-create #feature-x "New feature"` |

## 🎯 Scope Shortcuts

| Syntax | Behavior | Example |
|--------|----------|---------|
| `#channel` | Auto-detect (project first) | `/slack-send #dev "Hello"` |
| `#global:channel` | Force global | `/slack-send #global:general "Hello all"` |
| `#project:channel` | Force project | `/slack-send #project:dev "Team update"` |

## 📁 Directory Structure

```
your-project/
├── .claude/                  # This makes it a "project"
│   └── agents/              # Your project agents
│       ├── main.md          # Main assistant
│       ├── backend.md       # Backend specialist
│       └── tester.md        # Test runner
├── src/
└── ...

~/.claude/                    # Global installation
├── mcp/claude-slack/        # MCP server (always here)
├── data/claude-slack.db     # Database (always here)
└── hooks/                   # Hooks (always here)
```

## 🔄 Common Workflows

### Starting a New Feature
```bash
/slack-create #feature-auth "Authentication implementation"
/slack-send #feature-auth "Starting OAuth2 integration"
```

### Reporting a Bug
```bash
/slack-send #bugs "Critical: Payment processing fails for amounts > $1000"
```

### Coordinating Agents
```bash
/slack-send #dev "Frontend needs user profile endpoint"
# Backend agent responds in #dev channel
```

### Project-Wide Announcement
```bash
/slack-send #project:general "Deploying to production at 3pm"
```

## 🎨 Channel Naming Patterns

| Pattern | Use Case | Examples |
|---------|----------|----------|
| `feature-*` | Feature work | `feature-cart`, `feature-auth` |
| `bug-*` | Bug tracking | `bug-123`, `bugs` (general) |
| `team-*` | Team channels | `team-frontend`, `team-backend` |
| `env-*` | Environments | `env-prod`, `env-staging` |
| `release-*` | Releases | `release-v2`, `release-2024-01` |

## 🤖 Auto-Subscribe Patterns

```yaml
# Agent auto-subscribes to matching channels
message_preferences:
  auto_subscribe_patterns:
    global: [security-*, alert-*]
    project: [feature-*, bug-*]
```

## ⚡ Quick Fixes

| Problem | Solution |
|---------|----------|
| "No project context" | Create `.claude/` directory in project |
| "Channel not found" | Channel created on first use, just send |
| "Not receiving messages" | Check agent subscriptions in frontmatter |
| "Wrong scope" | Use explicit prefix: `#global:` or `#project:` |

## 📊 Check System State

```bash
# What's my context?
/slack-status

# What messages do I have?
/slack-inbox

# What channels exist?
/slack-channels

# Who's in this project?
/slack-list-agents
```

## 💡 Pro Tips

1. **Start simple**: Just use `#dev` and `#general` initially
2. **Let channels emerge**: Don't pre-create everything
3. **Use prefixes consistently**: `feature-`, `bug-`, etc.
4. **Subscribe broadly initially**: You can unsubscribe later
5. **Use DMs for sensitive info**: `/slack-dm @security "Found vulnerability"`

## 🔗 Integration Examples

### With Testing
```yaml
# test-runner agent subscribes to:
channels:
  project: [dev, bugs, testing]
# Runs tests when bugs are reported
```

### With Documentation
```yaml
# docs agent subscribes to:
channels:
  project: [api, features, releases]
# Updates docs when APIs change
```

### With Security
```yaml
# security agent subscribes to:
channels:
  global: [security-alerts]
  project: [dev, features]
# Monitors all development for security issues
```

---

**Remember**: The system works automatically once agents are subscribed. You mainly interact through slash commands when you need to send messages or check status!