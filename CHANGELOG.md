# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.1.0] - 2025-08-31

### 🚀 Major Release: Enterprise-Ready with MongoDB Filtering & Event Streaming

#### New Features

##### 🔍 MongoDB-Style Query Filtering
- **Rich Query Language**: Full MongoDB operator support ($eq, $gte, $in, $and, $or, etc.)
- **Deep Nesting Support**: Query arbitrarily nested JSON with dot notation
- **Backend Agnostic**: Works with both SQLite and Qdrant
- **Pre-flight Validation**: Catches errors before execution
- **No Schema Required**: Query any JSON structure without registration

##### 📡 Real-Time Event Streaming
- **Server-Sent Events (SSE)**: Live updates for web clients
- **Auto-Event Emission**: AutoEventProxy wraps all operations
- **Topic-Based Routing**: Efficient event distribution
- **Ring Buffer**: Recent events always available
- **Zero Configuration**: Works out of the box

##### 🌐 REST API & Web Integration
- **FastAPI Server**: Production-ready REST API
- **OpenAPI Documentation**: Auto-generated at /docs
- **MCP HTTP Bridge**: Tools can use HTTP instead of direct DB
- **CORS Support**: Ready for browser-based clients
- **Next.js Examples**: Complete React integration samples

##### 🚀 Qdrant Vector Database
- **Enterprise Vector Search**: Replaces ChromaDB with Qdrant
- **Cloud & Local Support**: Works with Qdrant Cloud or local instance
- **CUDA Acceleration**: Automatic GPU detection for embeddings
- **Hybrid Storage**: SQLite for structure, Qdrant for vectors
- **Automatic Fallback**: Works without vector DB if needed

#### Technical Improvements
- **Unified API Layer**: Single orchestrator for all operations
- **Clean Architecture**: Clear separation of concerns
- **Performance**: <50ms for complex MongoDB queries on 100k messages
- **Test Coverage**: Comprehensive test suite for all features

## [4.0.0] - 2025-08-27

### 🚀 Major Release: Semantic Search & Knowledge Infrastructure

#### New Features

##### 🔍 Semantic Search with Vector Embeddings
- **Qdrant Integration**: Dual storage system (SQLite + Qdrant)
- **AI-Powered Discovery**: Find messages by meaning, not just keywords
- **Automatic Embeddings**: Every message automatically gets vector representation
- **Hybrid Search**: Graceful fallback to FTS when vector DB unavailable

##### 📊 Intelligent Ranking System
- **Three-Factor Ranking**: Similarity + Confidence + Time Decay
- **Pre-configured Profiles**:
  - `recent`: Fresh information priority (24-hour half-life)
  - `quality`: High-confidence priority (30-day half-life)
  - `balanced`: Equal weighting (1-week half-life)
  - `similarity`: Pure relevance matching
- **Configurable Time Decay**: Exponential decay with customizable half-life
- **Confidence Scoring**: Quality-weighted search results

##### 💡 Reflection-Based Knowledge Capture
- **Agent Reflections**: Structured knowledge with confidence scores
- **Breadcrumbs System**: File paths, commits, decisions, patterns
- **Temporal Validity**: Time-based relevance with decay
- **Multiple Perspectives**: Preserves different viewpoints on same topic

##### 🏗️ Architecture Improvements
- **MessageStore Class**: Clean abstraction for dual storage
- **Backward Compatible**: Falls back to SQLite FTS when needed
- **No Migration Required**: Clean v4 with optional semantic features
- **Lightweight Dependencies**: Uses sentence-transformers for embeddings

#### Technical Details
- **Embedding Model**: all-MiniLM-L6-v2 (via sentence-transformers)
- **Vector Storage**: Qdrant with HNSW index
- **Time Decay Formula**: `e^(-ln(2) * age_hours / half_life_hours)`
- **Performance**: <100ms semantic search for 10k documents

#### Installation
```bash
# v4 dependencies (optional but recommended)
pip install qdrant-client>=1.7.0 sentence-transformers>=2.2.0
```

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