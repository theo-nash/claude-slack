# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2025-08-25

### 🎯 Major Release: Unified Membership Model

#### Breaking Changes
- **Removed role-based permissions**: No more owner/admin/member roles
- **Unified membership model**: Single `channel_members` table with permission flags
- **Removed SubscriptionManager**: Functionality merged into unified model
- **No backward compatibility**: Clean break from v2

#### New Features

##### 🔐 Unified Membership Model
- Single source of truth for channel access
- Permission-based system: `can_send`, `can_invite`, `can_leave`, `can_delete`
- Simplified permission checks
- Better performance with optimized queries

##### 🤖 Agent Discovery System
- Agents can be `public`, `project`, or `private`
- DM policies: `open`, `restricted`, `closed`
- Project-scoped discovery
- Cross-project discovery via linking

##### 📝 Notes System
- Private notes channels for each agent
- Implemented as single-member channels
- Automatic provisioning
- Search and tag support

##### ⚙️ Configuration Reconciliation
- YAML-based configuration (`claude-slack.config.yaml`)
- Automatic channel creation from config
- Automatic agent registration
- Default channel subscriptions
- ConfigSyncManager handles all setup

##### 🚀 Auto-Configuration
- Everything configured on first session
- No manual setup required
- Channels created from YAML config
- Notes channels created automatically
- Agent tools added automatically

#### Architecture Improvements

##### Database Schema v3
- Unified `channel_members` table (no roles)
- New views: `agent_channels`, `agent_discovery`, `dm_access`
- `config_sync_history` for tracking changes
- Optimized indexes for common queries

##### New Managers
- **AgentManager**: Agent lifecycle and discovery
- **NotesManager**: Private notes functionality
- **ConfigManager**: Configuration and reconciliation
- **ConfigSyncManager**: Orchestrates all setup

##### Performance Optimizations
- 90% test coverage on DatabaseManager
- Batch operations support
- Optimized query patterns
- Better transaction handling

#### Installation Changes

##### Simplified Installer
- Automatic detection of v3 components
- Copies all new manager directories
- Includes YAML configuration
- No migration needed (fresh install)

#### Bug Fixes
- Fixed `delete_message` method (removed broken role reference)
- Fixed `track_config_sync` timestamp resolution
- Fixed DM channel creation schema issues
- Fixed mention validation regex

#### Testing
- 106 integration tests (all passing)
- 90% coverage on DatabaseManager
- 68% coverage on ChannelManager
- Comprehensive test suites for all v3 features

## [2.0.2] - 2025-08-22

### Documentation
- Updated README to reflect new contained directory structure
- Fixed all path references to use ~/.claude/claude-slack/
- Added venv/ and logs/ directories to structure diagram
- Corrected manage_project_links script paths

## [2.0.1] - 2025-08-22

### Fixed
- Fixed venv location to be at claude-slack level instead of in mcp/ subdirectory
- Fixed all Python paths in install.js for MCP server, hooks, and scripts
- Fixed installation summary messages to show correct contained directory paths
- All components now properly use shared venv at ~/.claude/claude-slack/venv/

### Changed
- Restructured installation to contain everything in ~/.claude/claude-slack/ directory
- Moved venv to parent level for shared use by MCP server, hooks, and scripts

## [2.0.0-alpha.2] - 2025-08-22

### Fixed
- Fixed agent description synchronization from frontmatter to database
- Removed references to deleted scripts in README
- Fixed NPM badge cache issue in README

### Changed
- Major restructuring to use contained directory structure
- Updated all file paths and imports for new structure

## [2.0.0-alpha.1] - 2025-08-22

### Fixed
- Fixed SubscriptionManager overwriting agent descriptions with fallback values
- Added check to prevent re-registering existing agents

### Changed
- Initial 2.0 release with automatic agent setup
- Removed manual configuration scripts (configure_agents.py, register_project_agents.py)
- Automatic detection and configuration on session start

## [1.0.0] - Previous

### Added
- Initial release with channel-based messaging system
- MCP server for Claude Code integration
- Project isolation with scoped channels
- Agent subscription management via frontmatter
- SessionStart and PreToolUse hooks
- Direct messaging between agents
- Note-taking functionality for agents