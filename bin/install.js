#!/usr/bin/env node
/**
 * Claude-Slack NPX Installer
 * Installs channel-based messaging system for Claude Code agents
 * Installs globally to Claude configuration directory (respects CLAUDE_CONFIG_DIR)
 */

const fs = require('fs-extra');
const path = require('path');
const { execSync } = require('child_process');
const prompts = require('prompts');
const chalk = require('chalk');
const ora = require('ora');
const os = require('os');

/**
 * Get the Claude configuration directory, respecting CLAUDE_CONFIG_DIR environment variable
 * @returns {string} Path to Claude configuration directory
 */
function getClaudeConfigDir() {
    // Check for CLAUDE_CONFIG_DIR environment variable
    const customDir = process.env.CLAUDE_CONFIG_DIR;
    if (customDir) {
        // Expand ~ to home directory if present
        const expandedDir = customDir.replace(/^~/, os.homedir());
        return path.resolve(expandedDir);
    }
    // Default to ~/.claude
    return path.join(os.homedir(), '.claude');
}

// Configuration
const GLOBAL_CLAUDE_DIR = getClaudeConfigDir();
const CLAUDE_SLACK_DIR = 'claude-slack';  // Main container directory
const MCP_SERVER_DIR = path.join(CLAUDE_SLACK_DIR, 'mcp');  // Now inside claude-slack
const PYTHON_MIN_VERSION = '3.8';
const DB_NAME = 'claude-slack.db';

class ClaudeSlackInstaller {
    constructor(testMode = false) {
        this.testMode = testMode;
        this.globalClaudeDir = testMode ? '/tmp/test-claude' : GLOBAL_CLAUDE_DIR;
        this.projectDir = null;
        this.projectClaudeDir = null;
        this.hasProject = false;
        this.spinner = null;
    }

    async run() {
        if (this.testMode) {
            console.log(chalk.gray('[TEST MODE] Running in test mode - using temp directory\n'));
        }
        console.log(chalk.cyan.bold('\n🚀 Claude-Slack v4 Installer\n'));
        console.log('Semantic knowledge infrastructure for Claude Code agents');
        console.log(chalk.yellow('Installing GLOBALLY with semantic search capabilities\n'));

        try {
            // 1. Check prerequisites
            await this.checkPrerequisites();

            // 2. Detect project context (optional)
            await this.detectProjectContext();

            // 3. Confirm installation
            const confirmed = await this.confirmInstallation();
            if (!confirmed) {
                console.log(chalk.yellow('\n⚠️  Installation cancelled'));
                process.exit(0);
            }

            // 4. Install global components
            await this.installGlobalComponents();

            // 5. Setup Python environment
            await this.setupPythonEnvironment();

            // 6. Initialize database
            await this.initializeDatabase();

            // 7. Configure MCP in global settings
            await this.configureMCP();

            // 8. Install hooks (SessionStart and PreToolUse)
            await this.installHooks();

            // 9. Setup project agents (if in project)
            if (this.hasProject) {
                await this.setupProjectAgents();
            }

            // 10. Update existing agents for scoped subscriptions
            await this.migrateExistingAgents();

            // 11. Display success message
            this.displaySuccess();

        } catch (error) {
            if (this.spinner) this.spinner.fail();
            console.error(chalk.red(`\n❌ Installation failed: ${error.message}`));
            console.error(chalk.gray(error.stack));
            process.exit(1);
        }
    }

    async checkPrerequisites() {
        this.spinner = ora('Checking prerequisites...').start();

        const issues = [];

        // Check for global .claude directory
        if (!fs.existsSync(this.globalClaudeDir)) {
            // Create it if it doesn't exist
            fs.ensureDirSync(this.globalClaudeDir);
            this.spinner.info(`Created global Claude directory at ${this.globalClaudeDir}`);
        }

        // Check Python version
        try {
            const pythonVersion = execSync('python3 --version', { encoding: 'utf8' });
            const versionMatch = pythonVersion.match(/Python (\d+)\.(\d+)/);
            if (versionMatch) {
                const major = parseInt(versionMatch[1]);
                const minor = parseInt(versionMatch[2]);
                const minMajor = parseInt(PYTHON_MIN_VERSION.split('.')[0]);
                const minMinor = parseInt(PYTHON_MIN_VERSION.split('.')[1]);

                if (major < minMajor || (major === minMajor && minor < minMinor)) {
                    issues.push(`Python ${PYTHON_MIN_VERSION}+ required (found ${versionMatch[1]}.${versionMatch[2]})`);
                }
            }
        } catch (error) {
            issues.push('Python 3 not found (required for MCP server)');
        }

        // Check for existing claude-memory-system
        const memorySystemPath = path.join(this.globalClaudeDir, 'agents', 'memory-manager.md');
        const hasMemorySystem = fs.existsSync(memorySystemPath);

        if (hasMemorySystem) {
            this.spinner.succeed('Prerequisites checked (claude-memory-system detected)');
            console.log(chalk.blue('ℹ️  Existing claude-memory-system will be integrated'));
        } else if (issues.length > 0) {
            this.spinner.fail('Prerequisites check failed');
            issues.forEach(issue => console.log(chalk.red(`  • ${issue}`)));
            throw new Error('Prerequisites not met');
        } else {
            this.spinner.succeed('All prerequisites met');
        }
    }

    async detectProjectContext() {
        this.spinner = ora('Detecting project context...').start();

        // Check for local .claude directory
        const localClaude = path.join(process.cwd(), '.claude');

        if (fs.existsSync(localClaude)) {
            this.projectDir = process.cwd();
            this.projectClaudeDir = localClaude;
            this.hasProject = true;
            this.spinner.succeed(`Found project at ${chalk.green(this.projectDir)}`);
        } else {
            this.spinner.info('No project context detected (global installation only)');
        }
    }

    async confirmInstallation() {
        console.log(chalk.yellow('\n📋 Installation Summary:'));

        // Show if using custom config directory
        if (process.env.CLAUDE_CONFIG_DIR) {
            console.log(chalk.blue(`  ℹ️  Using custom config directory from CLAUDE_CONFIG_DIR`));
        }

        console.log(`  • ${chalk.bold('Installation Directory')}: ${path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR)}`);
        console.log(`  • ${chalk.bold('MCP Server')}: ${path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR, 'mcp')}`);
        console.log(`  • ${chalk.bold('SQLite Database')}: ${path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR, 'data', DB_NAME)}`);
        console.log(`  • ${chalk.bold('Qdrant Vectors')}: In-memory or Qdrant Cloud`);
        console.log(`  • ${chalk.bold('Configuration')}: ${path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR, 'config', 'claude-slack.config.yaml')}`);

        if (this.hasProject) {
            console.log(`  • ${chalk.bold('Project')}: ${this.projectDir}`);
            console.log(`    - Will add example agent`);
        }

        console.log(chalk.cyan('\n🎯 Claude-Slack v4 Features:'));
        console.log('  • 🔍 Semantic search with vector embeddings (Qdrant)');
        console.log('  • 📊 Intelligent ranking (similarity + confidence + time decay)');
        console.log('  • 💡 Agent reflections with breadcrumbs');
        console.log('  • ⚙️ Auto-configuration from YAML config');
        console.log('  • 🤖 Agent discovery with DM policies');
        console.log('  • 📝 Private notes channels for agent memory');
        console.log('  • ✨ Automatic reconciliation on session start');
        
        console.log(chalk.green('\n💡 Semantic Search Info:'));
        console.log('  • Qdrant client will be installed automatically');
        console.log('  • Embedding model will be pre-downloaded (~80MB)');
        console.log('  • No first-run delays - ready immediately');
        console.log('  • Falls back to keyword search if unavailable');
        console.log('  • No heavy ML frameworks required!');

        const response = await prompts({
            type: 'confirm',
            name: 'proceed',
            message: 'Proceed with v4 installation?',
            initial: true
        });

        return response.proceed;
    }

    async installGlobalComponents() {
        this.spinner = ora('Installing global components...').start();

        const templateDir = path.join(__dirname, '..', 'template');
        const globalTemplateDir = path.join(templateDir, 'global');
        
        // Main claude-slack container directory
        const claudeSlackDir = path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR);
        await fs.ensureDir(claudeSlackDir);

        // Copy MCP server into claude-slack/mcp
        const mcpSource = path.join(globalTemplateDir, 'mcp', 'claude-slack');
        const mcpTarget = path.join(claudeSlackDir, 'mcp');
        await fs.copy(mcpSource, mcpTarget, { overwrite: false });
        
        // Ensure all v4 manager directories are properly copied
        const managerDirs = ['sessions', 'channels', 'agents', 'notes', 'projects', 'config', 'log_manager', 'utils', 'db', 'frontmatter'];
        for (const dir of managerDirs) {
            const dirSource = path.join(globalTemplateDir, 'mcp', 'claude-slack', dir);
            const dirTarget = path.join(mcpTarget, dir);
            if (fs.existsSync(dirSource)) {
                await fs.copy(dirSource, dirTarget, { overwrite: false });
            }
        }

        // Make server.py executable on Unix-like systems
        if (process.platform !== 'win32') {
            const serverPath = path.join(mcpTarget, 'server.py');
            if (fs.existsSync(serverPath)) {
                await fs.chmod(serverPath, '755');
            }
        }

        // Copy config directory and YAML configuration
        const configSource = path.join(globalTemplateDir, 'config');
        const configTarget = path.join(claudeSlackDir, 'config');
        await fs.copy(configSource, configTarget, { overwrite: false });
        
        // Ensure YAML config is copied (critical for v4 auto-configuration)
        const configYamlSource = path.join(globalTemplateDir, 'config', 'claude-slack.config.yaml');
        const configYamlTarget = path.join(claudeSlackDir, 'config', 'claude-slack.config.yaml');
        if (!fs.existsSync(configYamlTarget)) {
            await fs.copy(configYamlSource, configYamlTarget);
        }

        // Copy scripts into claude-slack/scripts
        const scriptsSource = path.join(globalTemplateDir, 'scripts');
        const scriptsTarget = path.join(claudeSlackDir, 'scripts');
        await fs.copy(scriptsSource, scriptsTarget, { overwrite: false });

        // Copy hooks into claude-slack/hooks
        const hooksSource = path.join(globalTemplateDir, 'hooks');
        const hooksTarget = path.join(claudeSlackDir, 'hooks');
        await fs.copy(hooksSource, hooksTarget, { overwrite: false });

        // Ensure data directory exists in claude-slack/data
        const dataDir = path.join(claudeSlackDir, 'data');
        await fs.ensureDir(dataDir);
        await fs.ensureDir(path.join(dataDir, 'backups'));
        // Qdrant uses in-memory storage by default, no directory needed
        
        // Ensure log directories exist in claude-slack/logs
        const logDir = path.join(claudeSlackDir, 'logs');
        await fs.ensureDir(logDir);
        await fs.ensureDir(path.join(logDir, 'hooks'));
        await fs.ensureDir(path.join(logDir, 'managers'));
        await fs.ensureDir(path.join(logDir, 'archive'));

        this.spinner.succeed('Global components installed');
    }

    async setupPythonEnvironment() {
        this.spinner = ora('Setting up Python environment with v4 dependencies...').start();

        const claudeSlackDir = path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR);
        const mcpDir = path.join(claudeSlackDir, 'mcp');

        // Use the requirements.txt from the MCP directory (which has v4.1 dependencies)
        const mcpRequirementsPath = path.join(mcpDir, 'requirements.txt');
        const requirementsPath = path.join(claudeSlackDir, 'requirements.txt');
        
        // Copy the MCP requirements to the claude-slack level for pip install
        if (fs.existsSync(mcpRequirementsPath)) {
            fs.copyFileSync(mcpRequirementsPath, requirementsPath);
        } else {
            // Fallback if MCP requirements doesn't exist
            const requirements = `# Claude-Slack v4.1 MCP Server Requirements
# Core API dependencies
aiosqlite>=0.19.0
qdrant-client>=1.7.0
sentence-transformers>=2.2.0
numpy>=1.24.0

# MCP Server dependencies  
mcp>=0.1.0
python-dotenv>=1.0.0
`;
            await fs.writeFile(requirementsPath, requirements);
        }

        try {
            // Create virtual environment at claude-slack level
            execSync('python3 -m venv venv', {
                cwd: claudeSlackDir,
                stdio: 'pipe'
            });

            // Install dependencies
            // Handle platform-specific pip location
            const pipCmd = process.platform === 'win32'
                ? path.join('venv', 'Scripts', 'pip.exe')
                : path.join('venv', 'bin', 'pip');

            execSync(`${pipCmd} install --upgrade pip`, {
                cwd: claudeSlackDir,
                stdio: 'pipe'
            });

            execSync(`${pipCmd} install -r requirements.txt`, {
                cwd: claudeSlackDir,
                stdio: 'pipe'
            });

            this.spinner.succeed('Python environment configured with semantic search capabilities');
            
            // Check if Qdrant was successfully installed
            await this.checkSemanticSearchDependencies();
            
        } catch (error) {
            this.spinner.fail('Failed to setup Python environment');
            throw error;
        }
    }

    async checkSemanticSearchDependencies() {
        this.spinner = ora('Verifying v4 semantic search components...').start();
        
        const claudeSlackDir = path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR);
        const pythonPath = process.platform === 'win32'
            ? path.join(claudeSlackDir, 'venv', 'Scripts', 'python.exe')
            : path.join(claudeSlackDir, 'venv', 'bin', 'python');

        // Check for Qdrant and dependencies installation
        const checkScript = `
import sys
import json
results = {"qdrant": False, "numpy": False, "transformers": False, "qdrant_version": None, "embedding_model": None}
try:
    import qdrant_client
    results["qdrant"] = True
    # Get version using importlib.metadata
    try:
        import importlib.metadata
        results["qdrant_version"] = importlib.metadata.version('qdrant-client')
    except:
        results["qdrant_version"] = "unknown"
except ImportError:
    pass
try:
    import numpy
    results["numpy"] = True
except ImportError:
    pass
try:
    from sentence_transformers import SentenceTransformer
    results["transformers"] = True
    results["embedding_model"] = "all-MiniLM-L6-v2 (will download on first use ~80MB)"
except ImportError:
    pass
print(json.dumps(results))
`;

        try {
            const output = execSync(`${pythonPath} -c "${checkScript}"`, {
                cwd: claudeSlackDir,
                stdio: 'pipe',
                encoding: 'utf8'
            });
            
            const results = JSON.parse(output.trim());
            
            if (results.qdrant && results.numpy && results.transformers) {
                this.spinner.succeed(`✅ v4.1 Semantic Search: ENABLED (Qdrant ${results.qdrant_version})`);
                console.log(chalk.green(`  • Vector embeddings: Automatic for all messages`));
                console.log(chalk.green(`  • Embedding model: ${results.embedding_model}`));
                console.log(chalk.green(`  • Search profiles: recent, quality, balanced, similarity`));
                
                // Pre-download embedding model if needed
                if (results.embedding_model.includes('will download')) {
                    await this.predownloadEmbeddingModel();
                }
                
            } else if (results.qdrant && !results.numpy) {
                this.spinner.warn('⚠️ Qdrant installed but NumPy missing - semantic search may be limited');
                console.log(chalk.yellow('  Run: pip install numpy>=1.24.0'));
            } else if (results.qdrant && !results.transformers) {
                this.spinner.warn('⚠️ Qdrant installed but sentence-transformers missing');
                console.log(chalk.yellow('  Run: pip install sentence-transformers>=2.2.0'));
            } else {
                this.spinner.warn('⚠️ v4.1 Semantic Search: DISABLED (Qdrant not installed)');
                console.log(chalk.yellow('  • System will fall back to keyword search (FTS)'));
                console.log(chalk.yellow('  • To enable: pip install qdrant-client>=1.7.0 sentence-transformers>=2.2.0'));
                console.log(chalk.yellow('  • This is optional - system works without it'));
            }
        } catch (error) {
            this.spinner.info('ℹ️ Could not verify semantic search components');
            console.log(chalk.gray('  System will detect capabilities at runtime'));
        }
    }

    async predownloadEmbeddingModel() {
        this.spinner = ora('Downloading embedding model (all-MiniLM-L6-v2, ~80MB)...').start();
        
        const claudeSlackDir = path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR);
        const pythonPath = process.platform === 'win32'
            ? path.join(claudeSlackDir, 'venv', 'Scripts', 'python.exe')
            : path.join(claudeSlackDir, 'venv', 'bin', 'python');

        // Script to download and initialize the embedding model
        const downloadScript = `
import sys
import os
# Suppress sentence-transformers logging during download
os.environ['SENTENCE_TRANSFORMERS_HOME'] = os.path.expanduser('~/.cache/sentence-transformers')
import logging
logging.getLogger('sentence_transformers').setLevel(logging.WARNING)

try:
    from sentence_transformers import SentenceTransformer
    print("Downloading embedding model...", file=sys.stderr)
    
    # Initialize the model - this triggers the download
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    # Test it with a sample text to ensure it's fully initialized
    test_embedding = model.encode(["test initialization"])
    
    print("SUCCESS")
except Exception as e:
    print(f"ERROR: {e}")
`;

        try {
            // Run with longer timeout for download (5 minutes)
            const result = execSync(`${pythonPath} -c "${downloadScript}"`, {
                cwd: claudeSlackDir,
                encoding: 'utf8',
                timeout: 300000, // 5 minute timeout
                stdio: ['pipe', 'pipe', 'pipe']  // Capture stdout and stderr
            });
            
            if (result.includes('SUCCESS')) {
                this.spinner.succeed('✅ Embedding model downloaded and ready (all-MiniLM-L6-v2)');
                console.log(chalk.green('  • First-run delay eliminated'));
                console.log(chalk.green('  • Model cached in ~/.cache/sentence-transformers'));
            } else {
                this.spinner.warn('⚠️ Could not pre-download embedding model');
                console.log(chalk.yellow('  • Model will download on first use'));
            }
        } catch (error) {
            // Check if it was a timeout
            if (error.code === 'ETIMEDOUT') {
                this.spinner.warn('⚠️ Embedding model download timed out');
                console.log(chalk.yellow('  • Model will download on first use'));
                console.log(chalk.yellow('  • This may be due to slow internet connection'));
            } else {
                this.spinner.warn('⚠️ Could not pre-download embedding model');
                console.log(chalk.yellow('  • Model will download on first use (~80MB)'));
            }
        }
    }

    async initializeDatabase() {
        this.spinner = ora('Initializing database with v4 schema...').start();

        const claudeSlackDir = path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR);
        const dataDir = path.join(claudeSlackDir, 'data');
        const dbPath = path.join(dataDir, DB_NAME);

        // Check if database already exists
        if (fs.existsSync(dbPath)) {
            this.spinner.info('Database already exists, skipping initialization');
            return;
        }

        // Run Python script to create database with schema
        const mcpDir = path.join(this.globalClaudeDir, MCP_SERVER_DIR);
        // Handle platform-specific Python executable location
        const pythonPath = process.platform === 'win32'
            ? path.join(claudeSlackDir, 'venv', 'Scripts', 'python.exe')
            : path.join(claudeSlackDir, 'venv', 'bin', 'python');
        const schemaPath = path.join(mcpDir, 'api', 'schema.sql');

        const initScript = `
import sqlite3
import os

db_path = '${dbPath}'
schema_path = '${schemaPath}'

# Create database
conn = sqlite3.connect(db_path)

# Read and execute schema
with open(schema_path, 'r') as f:
    schema = f.read()
    conn.executescript(schema)

conn.commit()
conn.close()

print('Database initialized successfully')
`;

        try {
            execSync(`${pythonPath} -c "${initScript}"`, {
                cwd: mcpDir,
                stdio: 'pipe'
            });
            this.spinner.succeed('Database initialized successfully');
        } catch (error) {
            this.spinner.fail('Failed to initialize database');
            throw error;
        }
    }

    async configureMCP() {
        this.spinner = ora('Configuring MCP server...').start();

        // MCP servers are configured in ~/.claude.json (not settings.json)
        const claudeJsonPath = path.join(os.homedir(), '.claude.json');
        let claudeConfig = {};

        // Read existing config if present
        if (fs.existsSync(claudeJsonPath)) {
            claudeConfig = await fs.readJson(claudeJsonPath);
        }

        // Ensure mcpServers object exists
        if (!claudeConfig.mcpServers) {
            claudeConfig.mcpServers = {};
        }

        // Add claude-slack MCP server configuration
        // Use the venv Python to ensure dependencies are available
        // Handle platform-specific Python executable location
        const claudeSlackDir = path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR);
        const venvPython = process.platform === 'win32'
            ? path.join(claudeSlackDir, 'venv', 'Scripts', 'python.exe')
            : path.join(claudeSlackDir, 'venv', 'bin', 'python');
        const mcpDir = path.join(claudeSlackDir, 'mcp');
        claudeConfig.mcpServers['claude-slack'] = {
            "command": venvPython,
            "args": [path.join(mcpDir, "server.py")],
            "cwd": mcpDir,
            "env": {
                "PYTHONPATH": mcpDir,
                "DB_PATH": path.join(claudeSlackDir, 'data', DB_NAME),
                "CLAUDE_CONFIG_DIR": this.globalClaudeDir,  // Pass config dir to Python
                "CLAUDE_SLACK_DIR": claudeSlackDir  // Pass claude-slack dir to Python
            }
        };

        // Save updated config
        await fs.writeJson(claudeJsonPath, claudeConfig, { spaces: 2 });
        this.spinner.succeed('MCP server configured in ~/.claude.json');
    }

    async createWrapperScripts(scriptsDir) {
        // Create wrapper scripts that use the venv Python
        // V4: Only manage_project_links is needed - everything else is automatic
        const claudeSlackDir = path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR);
        const venvPython = process.platform === 'win32'
            ? path.join(claudeSlackDir, 'venv', 'Scripts', 'python.exe')
            : path.join(claudeSlackDir, 'venv', 'bin', 'python');

        if (process.platform === 'win32') {
            // Windows batch file for project linking
            const linksBat = `@echo off
REM Wrapper script for manage_project_links.py using venv Python
set SCRIPT_DIR=%~dp0
set VENV_PYTHON="${venvPython}"
"%VENV_PYTHON%" "%SCRIPT_DIR%manage_project_links.py" %*
`;
            await fs.writeFile(path.join(scriptsDir, 'manage_project_links.bat'), linksBat);
        } else {
            // Unix/Linux/Mac shell script for project linking
            const linksWrapper = `#!/bin/bash
# Wrapper script for manage_project_links.py using venv Python
SCRIPT_DIR="$( cd "$( dirname "\${BASH_SOURCE[0]}" )" && pwd )"
VENV_PYTHON="${venvPython}"
exec "$VENV_PYTHON" "$SCRIPT_DIR/manage_project_links.py" "$@"
`;
            await fs.writeFile(path.join(scriptsDir, 'manage_project_links'), linksWrapper);
            await fs.chmod(path.join(scriptsDir, 'manage_project_links'), '755');
        }
    }

    async installHooks() {
        this.spinner = ora('Configuring hooks...').start();

        const claudeSlackDir = path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR);
        
        // Hooks are already copied to claude-slack/hooks in installGlobalComponents
        // Now we just need to register them in settings.json
        
        // Get venv Python path for hooks
        const venvPython = process.platform === 'win32'
            ? path.join(claudeSlackDir, 'venv', 'Scripts', 'python.exe')
            : path.join(claudeSlackDir, 'venv', 'bin', 'python');

        // Hook paths in claude-slack directory (NOT global hooks)
        const sessionHookTarget = path.join(claudeSlackDir, 'hooks', 'slack_session_start.py');
        const preToolHookTarget = path.join(claudeSlackDir, 'hooks', 'slack_pre_tool_use.py');

        // Make hook scripts executable on Unix-like systems
        if (process.platform !== 'win32') {
            await fs.chmod(sessionHookTarget, '755');
            await fs.chmod(preToolHookTarget, '755');
        }

        // Create wrapper scripts for admin tools
        const scriptsDir = path.join(claudeSlackDir, 'scripts');
        await this.createWrapperScripts(scriptsDir);

        // Update settings.json to register the hooks
        const settingsPath = path.join(this.globalClaudeDir, 'settings.json');
        let settings = {};
        if (fs.existsSync(settingsPath)) {
            settings = await fs.readJson(settingsPath);
        }

        // Ensure hooks object exists with correct Claude Code format
        if (!settings.hooks) {
            settings.hooks = {};
        }

        // Configure SessionStart hook (Claude Code format)
        if (!settings.hooks.SessionStart) {
            settings.hooks.SessionStart = [];
        }

        // Check if our SessionStart hook already exists
        const sessionHookCommand = `${venvPython} ${sessionHookTarget}`;
        const oldSessionHookCommand = `python3 ${sessionHookTarget}`;
        
        // Remove old python3 version if it exists
        settings.hooks.SessionStart = settings.hooks.SessionStart.filter(entry => 
            !entry.hooks || !entry.hooks.some(h => h.command === oldSessionHookCommand)
        );
        
        const hasSessionHook = settings.hooks.SessionStart.some(entry =>
            entry.hooks && entry.hooks.some(h => h.command === sessionHookCommand)
        );

        if (!hasSessionHook) {
            settings.hooks.SessionStart.push({
                "hooks": [
                    {
                        "type": "command",
                        "command": sessionHookCommand
                    }
                ]
            });
        }

        // Configure PreToolUse hook for claude-slack MCP tools
        if (!settings.hooks.PreToolUse) {
            settings.hooks.PreToolUse = [];
        }

        // Check if our PreToolUse hook already exists
        const preToolHookCommand = `${venvPython} ${preToolHookTarget}`;
        const oldPreToolHookCommand = `python3 ${preToolHookTarget}`;
        
        // Remove old python3 version if it exists
        settings.hooks.PreToolUse = settings.hooks.PreToolUse.filter(entry => 
            !(entry.matcher === "mcp__claude-slack__.*" && 
              entry.hooks && entry.hooks.some(h => h.command === oldPreToolHookCommand))
        );
        
        const hasPreToolHook = settings.hooks.PreToolUse.some(entry =>
            entry.matcher === "mcp__claude-slack__.*" &&
            entry.hooks && entry.hooks.some(h => h.command === preToolHookCommand)
        );

        if (!hasPreToolHook) {
            settings.hooks.PreToolUse.push({
                "matcher": "mcp__claude-slack__.*",
                "hooks": [
                    {
                        "type": "command",
                        "command": preToolHookCommand
                    }
                ]
            });
        }

        await fs.writeJson(settingsPath, settings, { spaces: 2 });

        this.spinner.succeed('Hooks configured in settings.json (SessionStart + PreToolUse)');
    }

    async setupProjectAgents() {
        this.spinner = ora('Setting up project agents...').start();

        const agentsDir = path.join(this.projectClaudeDir, 'agents');
        await fs.ensureDir(agentsDir);

        // Copy example agent template
        const exampleSource = path.join(__dirname, '..', 'template', 'project', '.claude', 'agents', 'example-agent.md.template');
        const exampleTarget = path.join(agentsDir, 'example-agent.md');

        if (!fs.existsSync(exampleTarget)) {
            await fs.copy(exampleSource, exampleTarget);
            this.spinner.succeed('Added example agent with scoped subscriptions');
        } else {
            this.spinner.info('Example agent already exists in project');
        }
    }

    displaySemanticSearchStatus() {
        // Quick check for Qdrant status
        const claudeSlackDir = path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR);
        const pythonPath = process.platform === 'win32'
            ? path.join(claudeSlackDir, 'venv', 'Scripts', 'python.exe')
            : path.join(claudeSlackDir, 'venv', 'bin', 'python');

        try {
            const checkScript = `
import json
result = {"enabled": False}
try:
    import qdrant_client
    import numpy
    from sentence_transformers import SentenceTransformer
    result["enabled"] = True
    # Get version using importlib.metadata
    try:
        import importlib.metadata
        result["version"] = importlib.metadata.version('qdrant-client')
    except:
        result["version"] = "unknown"
except:
    pass
print(json.dumps(result))
`;
            const output = execSync(`${pythonPath} -c "${checkScript}"`, {
                cwd: claudeSlackDir,
                stdio: 'pipe',
                encoding: 'utf8'
            });
            
            const result = JSON.parse(output.trim());
            
            if (result.enabled) {
                console.log(chalk.green('\n🔍 Semantic Search Status: ENABLED ✓'));
                console.log(chalk.green(`  • Qdrant ${result.version} installed`));
                console.log(chalk.green('  • AI-powered search ready'));
                console.log(chalk.green('  • Ranking profiles available'));
            } else {
                console.log(chalk.yellow('\n🔍 Semantic Search Status: FALLBACK MODE'));
                console.log(chalk.yellow('  • Using keyword search (FTS)'));
                console.log(chalk.yellow('  • Semantic features unavailable'));
            }
        } catch {
            // Silent fail - not critical
        }
    }

    async migrateExistingAgents() {
        this.spinner = ora('Migrating existing agents to scoped format...').start();

        const locations = [
            path.join(this.globalClaudeDir, 'agents'),
            this.projectClaudeDir ? path.join(this.projectClaudeDir, 'agents') : null
        ].filter(Boolean);

        let migrated = 0;

        for (const agentsDir of locations) {
            if (!fs.existsSync(agentsDir)) continue;

            const agentFiles = await fs.readdir(agentsDir);
            const mdFiles = agentFiles.filter(f => f.endsWith('.md'));

            for (const file of mdFiles) {
                const filePath = path.join(agentsDir, file);
                let content = await fs.readFile(filePath, 'utf8');

                // Check if already has scoped channels
                if (content.includes('channels:\n  global:')) {
                    continue; // Already migrated
                }

                // Find and update channels in frontmatter
                const lines = content.split('\n');
                let inFrontmatter = false;
                let foundChannels = false;

                for (let i = 0; i < lines.length; i++) {
                    if (lines[i] === '---') {
                        if (!inFrontmatter) {
                            inFrontmatter = true;
                        } else {
                            break; // End of frontmatter
                        }
                    } else if (inFrontmatter && lines[i].startsWith('channels:')) {
                        foundChannels = true;
                        const channelLine = lines[i];

                        // Extract channel list
                        let channels = [];
                        if (channelLine.includes('[')) {
                            // Format: channels: [general, announcements]
                            const match = channelLine.match(/\[(.*?)\]/);
                            if (match) {
                                channels = match[1].split(',').map(c => c.trim());
                            }
                        }

                        // Replace with scoped format
                        lines[i] = 'channels:';
                        lines.splice(i + 1, 0,
                            '  global:',
                            ...channels.map(c => `    - ${c}`),
                            '  project: []'
                        );

                        migrated++;
                        break;
                    }
                }

                if (foundChannels) {
                    await fs.writeFile(filePath, lines.join('\n'));
                } else if (inFrontmatter) {
                    // Add default channels if none exist
                    for (let i = 0; i < lines.length; i++) {
                        if (lines[i].startsWith('tools:')) {
                            lines.splice(i + 1, 0,
                                'channels:',
                                '  global:',
                                '    - general',
                                '    - announcements',
                                '  project: []'
                            );
                            migrated++;
                            await fs.writeFile(filePath, lines.join('\n'));
                            break;
                        }
                    }
                }
            }
        }

        if (migrated > 0) {
            this.spinner.succeed(`Migrated ${migrated} agent(s) to scoped subscription format`);
        } else {
            this.spinner.succeed('All agents already use scoped subscription format');
        }
    }

    displaySuccess() {
        console.log(chalk.green.bold('\n✅ Claude-Slack v4 installed successfully!\n'));

        console.log(chalk.cyan('📚 Installation Summary:'));
        console.log(`  • ${chalk.bold('MCP Server')}: ${path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR, 'mcp')}`);
        console.log(`  • ${chalk.bold('SQLite Database')}: ${path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR, 'data', DB_NAME)}`);
        console.log(`  • ${chalk.bold('Qdrant Vectors')}: In-memory or Qdrant Cloud`);
        console.log(`  • ${chalk.bold('Configuration')}: ${path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR, 'config', 'claude-slack.config.yaml')}`);
        console.log(`  • ${chalk.bold('Hooks Directory')}: ${path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR, 'hooks')} (SessionStart + PreToolUse)`);
        
        // Check and display semantic search status
        this.displaySemanticSearchStatus();

        console.log(chalk.cyan('\n🐛 Debug Logging:'));
        console.log('  • Enable debug logs: export CLAUDE_SLACK_DEBUG=1');
        console.log(`  • Log files: ${path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR, 'logs')}/*.log`);
        console.log('  • Logs show hook execution, database operations, and errors');
        console.log(`  • Qdrant data: In-memory or Qdrant Cloud`);

        console.log(chalk.cyan('\n🎯 Auto-Configuration:'));
        console.log('  • Channels created automatically from config YAML');
        console.log('  • Notes channels created for each agent');
        console.log('  • Agent subscriptions managed via reconciliation');
        console.log('  • Semantic search indexes built automatically');
        console.log('  • Everything happens on first session start!');
        console.log('');
        console.log(chalk.cyan('🚀 Quick Start:'));
        console.log('  1. Restart Claude Code');
        console.log('  2. Start a new session - everything auto-configures!');
        console.log('  3. Use /slack-status to verify');
        console.log('');
        console.log(chalk.cyan('🏗️  V4 Architecture:'));
        console.log('  • Hybrid storage: SQLite + Qdrant');
        console.log('  • Semantic search with vector embeddings');
        console.log('  • Intelligent ranking with time decay');
        console.log('  • Reflection-based knowledge capture');
        console.log('  • ConfigSyncManager handles all setup');
        console.log('  • Private notes channels for agent memory\n');

        console.log(chalk.cyan('🔧 Project Linking (Optional):'));
        console.log(chalk.gray('  (Only needed for cross-project communication)'));
        const scriptExt = process.platform === 'win32' ? '.bat' : '';
        console.log(`  • Manage project links: ${path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR, 'scripts', `manage_project_links${scriptExt}`)} [command]`);
        console.log('  • Projects are isolated by default');
        console.log('  • Link projects to enable agent discovery between them\n');

        console.log(chalk.cyan('💬 Basic Commands:'));
        console.log('  • /slack-send #general "Hello, world!" - Send to global channel');
        console.log('  • /slack-send #project:dev "Update" - Send to project channel');
        console.log('  • /slack-dm @agent "Private message" - Send direct message');
        console.log('  • /slack-inbox - Check unread messages');
        console.log('  • /slack-subscribe #channel - Join a channel');
        console.log('  • /slack-search "query" - Semantic search across messages\n');

        console.log(chalk.cyan('🔍 Semantic Search (v4 Feature):'));
        console.log('  • Find by meaning, not just keywords');
        console.log('  • Ranking profiles: recent, quality, balanced, similarity');
        console.log('  • Time decay with configurable half-life');
        console.log('  • Confidence-weighted results');
        console.log('  • Agent reflections with breadcrumbs\n');

        console.log(chalk.cyan('🔧 Configuration:'));
        console.log(`  • Edit defaults: ${path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR, 'config', 'claude-slack.config.yaml')}`);
        console.log('  • Changes apply on next session start');
        console.log('');
        if (this.hasProject) {
            console.log(chalk.cyan('📁 Project Context:'));
            console.log(`  • Project detected: ${chalk.green(this.projectDir)}`);
            console.log('  • Project channels will be created automatically');
            console.log('  • Agents use scoped subscriptions (global: vs project:)');
        } else {
            console.log(chalk.gray('📁 No project detected - global context only'));
        }

        console.log(chalk.cyan('\n✨ V4 Semantic Search Tips:'));
        console.log('  • Messages automatically get vector embeddings');
        console.log('  • Use "recent" profile for debugging issues');
        console.log('  • Use "quality" profile for proven solutions');
        console.log('  • Reflections with high confidence persist longer');
        console.log('  • Include breadcrumbs in reflections for better discovery\n');

        console.log(chalk.blue('📖 For documentation: https://github.com/yourusername/claude-slack'));
        console.log(chalk.yellow('⚠️  Remember to restart Claude Code for changes to take effect!'));
    }
}

// Run installer
if (require.main === module) {
    const isTestMode = process.argv.includes('--test');
    const installer = new ClaudeSlackInstaller(isTestMode);
    installer.run().catch(error => {
        console.error(chalk.red('Fatal error:'), error);
        process.exit(1);
    });
}

module.exports = ClaudeSlackInstaller;