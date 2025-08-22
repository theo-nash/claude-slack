# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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