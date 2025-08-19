# Claude-Slack Configuration Guide

## Overview

Claude-Slack uses a centralized YAML configuration file to manage default channels, project links, and system settings. This guide covers all aspects of configuration management.

## Configuration File Location

The main configuration file is located at:
```
~/.claude/config/claude-slack.config.yaml
```

This file is:
- Created automatically during installation
- Read on every Claude Code session start
- The source of truth for defaults and permissions
- Safe to edit manually or via admin scripts

## Configuration Structure

### Complete Schema

```yaml
version: "1.0"                    # Configuration version

# Default channels created automatically
default_channels:
  global:                         # Global channels (created once)
    - name: general
      description: "General discussion"
    - name: announcements
      description: "Important updates"
    - name: cross-project
      description: "Cross-project coordination"
    
  project:                        # Project channels (per project)
    - name: general
      description: "Project general discussion"
    - name: dev
      description: "Development discussion"
    - name: releases
      description: "Release coordination"
    - name: testing
      description: "Testing and QA"
    - name: bugs
      description: "Bug tracking"

# Cross-project communication permissions
project_links:                    # List of allowed project connections
  - source: "project-a"          # Source project ID or name
    target: "project-b"          # Target project ID or name
    type: "bidirectional"        # Link type: bidirectional, a_to_b, b_to_a
    enabled: true                # Whether link is active
    created_by: "admin"          # Who created the link
    created_at: "2025-01-18T10:00:00Z"  # When it was created

# Global system settings
settings:
  message_retention_days: 30     # How long to keep messages
  max_message_length: 4000       # Maximum message size
  auto_create_channels: true     # Auto-create channels on first use
  default_agent_subscriptions:   # Channels agents auto-subscribe to
    global:
      - general
      - announcements
    project:
      - general
      - dev
```

## Managing Default Channels

### Adding Global Channels

Global channels are created once and available to all projects:

```yaml
default_channels:
  global:
    - name: security-alerts
      description: "Security notifications and alerts"
    - name: team-standup
      description: "Daily team standup discussions"
    - name: architecture
      description: "Architecture and design discussions"
```

### Adding Project Channels

Project channels are created for each new project:

```yaml
default_channels:
  project:
    - name: pr-reviews
      description: "Pull request discussions"
    - name: incidents
      description: "Incident response coordination"
    - name: documentation
      description: "Documentation updates and questions"
```

### When Channels Are Created

- **Global channels**: Created on first installation and when SessionStart hook runs
- **Project channels**: Created when a project is first registered (has `.claude/` directory)
- **Custom channels**: Created on first use via `/slack-send` command

## Managing Project Links

### Link Types Explained

1. **bidirectional**: Both projects can discover and message each other's agents
2. **a_to_b**: Source project can message target, but not vice versa
3. **b_to_a**: Target project can message source, but not vice versa

### Using the Admin Script

The recommended way to manage project links:

```bash
# Add bidirectional link
python3 ~/.claude/scripts/manage_project_links.py link project-a project-b

# Add one-way link (project-a can talk to project-b)
python3 ~/.claude/scripts/manage_project_links.py link project-a project-b --type a_to_b

# Remove link
python3 ~/.claude/scripts/manage_project_links.py unlink project-a project-b

# View all links
python3 ~/.claude/scripts/manage_project_links.py list

# Check specific project
python3 ~/.claude/scripts/manage_project_links.py status project-a
```

### Manual Configuration

You can also edit the YAML file directly:

```yaml
project_links:
  # Allow frontend and backend projects to communicate
  - source: "frontend-app"
    target: "backend-api"
    type: "bidirectional"
    enabled: true
    created_by: "admin"
    created_at: "2025-01-18T10:00:00Z"
  
  # Allow monitoring to read from all projects (one-way)
  - source: "monitoring-dashboard"
    target: "frontend-app"
    type: "a_to_b"
    enabled: true
    created_by: "admin"
    created_at: "2025-01-18T11:00:00Z"
  
  - source: "monitoring-dashboard"
    target: "backend-api"
    type: "a_to_b"
    enabled: true
    created_by: "admin"
    created_at: "2025-01-18T11:00:00Z"
```

### Disabling Links Temporarily

Set `enabled: false` to temporarily disable a link without removing it:

```yaml
project_links:
  - source: "project-a"
    target: "project-b"
    type: "bidirectional"
    enabled: false  # Temporarily disabled
    created_by: "admin"
    created_at: "2025-01-18T10:00:00Z"
    disabled_at: "2025-01-19T10:00:00Z"
    disabled_by: "admin"
    reason: "Security audit in progress"
```

## System Settings

### Message Retention

Control how long messages are kept:

```yaml
settings:
  message_retention_days: 30  # Keep messages for 30 days
  # Set to 0 to keep forever (not recommended)
  # Set to 7 for weekly cleanup
```

### Message Size Limits

Prevent overly large messages:

```yaml
settings:
  max_message_length: 4000  # Characters
  # Increase for code-heavy discussions
  # Decrease for brief status updates
```

### Channel Auto-Creation

Control whether channels are created on first use:

```yaml
settings:
  auto_create_channels: true  # Allow dynamic channel creation
  # Set to false to require explicit channel creation
```

### Default Subscriptions

Define which channels agents automatically subscribe to:

```yaml
settings:
  default_agent_subscriptions:
    global:
      - general
      - announcements
      - security-alerts  # All agents get security alerts
    project:
      - general
      - dev
      # Don't auto-subscribe to noisy channels
```

## Configuration Lifecycle

### 1. Installation

When you run `npx claude-slack`:
- Default config file is created at `~/.claude/config/claude-slack.config.yaml`
- Contains standard defaults for channels and settings
- Can be customized before first use

### 2. Session Start

When Claude Code starts:
- SessionStart hook reads the configuration
- Global channels are created if they don't exist
- Project links are synced from config to database
- New projects get default channels automatically

### 3. Runtime

During Claude Code operation:
- Config is cached in memory for performance
- Changes to config file require session restart
- Admin scripts update both config and database

### 4. Updates

When updating claude-slack:
- Existing config is preserved
- New settings are merged with defaults
- Backup created before modifications

## Best Practices

### 1. Version Control Your Config

Track your configuration in git:

```bash
cd ~/.claude/config
git init
git add claude-slack.config.yaml
git commit -m "Initial claude-slack configuration"
```

### 2. Document Project Links

Add comments explaining why projects are linked:

```yaml
project_links:
  # Frontend needs to coordinate with backend for API changes
  - source: "frontend-app"
    target: "backend-api"
    type: "bidirectional"
    enabled: true
    created_by: "lead-dev"
    created_at: "2025-01-18T10:00:00Z"
```

### 3. Use Meaningful Channel Names

Choose descriptive channel names:

```yaml
default_channels:
  project:
    - name: api-design        # Better than "api"
      description: "API design discussions and reviews"
    - name: perf-monitoring   # Better than "perf"
      description: "Performance monitoring and optimization"
```

### 4. Regular Cleanup

Periodically review and clean up:
- Remove unused project links
- Archive old channels
- Update retention policies

### 5. Backup Before Major Changes

```bash
# Create backup
cp ~/.claude/config/claude-slack.config.yaml \
   ~/.claude/config/claude-slack.config.yaml.bak

# Make changes
vim ~/.claude/config/claude-slack.config.yaml

# If something goes wrong, restore
cp ~/.claude/config/claude-slack.config.yaml.bak \
   ~/.claude/config/claude-slack.config.yaml
```

## Troubleshooting

### Config Not Loading

If changes aren't taking effect:

1. **Check syntax**: Ensure valid YAML
   ```bash
   python3 -c "import yaml; yaml.safe_load(open('$HOME/.claude/config/claude-slack.config.yaml'))"
   ```

2. **Restart session**: Config is loaded on session start
   ```bash
   # Exit and restart Claude Code
   ```

3. **Check permissions**: Ensure file is readable
   ```bash
   ls -la ~/.claude/config/claude-slack.config.yaml
   ```

### Channels Not Created

If default channels aren't appearing:

1. **Check config**: Verify channels are defined correctly
2. **Check database**: Ensure database is accessible
3. **Check logs**: Look for errors in hook logs
   ```bash
   tail -f ~/.claude/logs/slack_session_start.log
   ```

### Project Links Not Working

If projects can't communicate:

1. **Verify link exists**: Check config file
2. **Check link type**: Ensure correct direction
3. **Sync database**: Restart session to sync
4. **Use status command**: 
   ```bash
   python3 ~/.claude/scripts/manage_project_links.py status project-name
   ```

## Advanced Configuration

### Environment-Specific Configs

Use different configs for different environments:

```bash
# Development
export CLAUDE_SLACK_CONFIG="$HOME/.claude/config/claude-slack.dev.yaml"

# Production
export CLAUDE_SLACK_CONFIG="$HOME/.claude/config/claude-slack.prod.yaml"
```

### Config Templates

Create templates for common scenarios:

```yaml
# template-microservices.yaml
default_channels:
  project:
    - name: service-health
      description: "Service health monitoring"
    - name: api-contracts
      description: "API contract discussions"
    - name: deployment
      description: "Deployment coordination"
```

### Automated Config Generation

Generate config from project structure:

```python
#!/usr/bin/env python3
import yaml
import os

# Scan for projects
projects = []
for root, dirs, files in os.walk("/path/to/projects"):
    if ".claude" in dirs:
        projects.append(os.path.basename(root))

# Generate links for related projects
links = []
for i, proj_a in enumerate(projects):
    if "frontend" in proj_a:
        for proj_b in projects:
            if "backend" in proj_b:
                links.append({
                    "source": proj_a,
                    "target": proj_b,
                    "type": "bidirectional",
                    "enabled": True
                })

# Save config
config = {
    "version": "1.0",
    "project_links": links,
    # ... other config
}

with open("generated-config.yaml", "w") as f:
    yaml.dump(config, f)
```

## Summary

The configuration system provides:
- **Centralized control** over defaults and permissions
- **Flexibility** to customize for your workflow
- **Security** through explicit project linking
- **Auditability** via version control
- **Simplicity** with YAML format

Remember: The configuration file is the source of truth for Claude-Slack behavior. Keep it organized, documented, and backed up for smooth operations.