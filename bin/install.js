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
        console.log(chalk.cyan.bold('\n🚀 Claude-Slack Installer\n'));
        console.log('Channel-based messaging system for Claude Code agents');
        console.log(chalk.yellow('Installing GLOBALLY with project isolation support\n'));

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
        console.log(`  • ${chalk.bold('Database')}: ${path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR, 'data', DB_NAME)}`);
        console.log(`  • ${chalk.bold('Hooks')}: Registered in settings.json`);

        if (this.hasProject) {
            console.log(`  • ${chalk.bold('Project')}: ${this.projectDir}`);
            console.log(`    - Will add example agent with scoped subscriptions`);
        }

        console.log(chalk.cyan('\n📚 Features:'));
        console.log('  • Project isolation with scoped channels');
        console.log('  • Global vs project message separation');
        console.log('  • Automatic project detection');
        console.log('  • Frontmatter-based subscriptions');

        const response = await prompts({
            type: 'confirm',
            name: 'proceed',
            message: 'Proceed with installation?',
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
        
        // Ensure all manager directories are properly copied
        const managerDirs = ['sessions', 'channels', 'subscriptions', 'projects', 'log_manager', 'utils', 'db', 'frontmatter'];
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

        // Copy config file into claude-slack/config
        const configSource = path.join(globalTemplateDir, 'config');
        const configTarget = path.join(claudeSlackDir, 'config');
        await fs.copy(configSource, configTarget, { overwrite: false });

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
        
        // Ensure log directories exist in claude-slack/logs
        const logDir = path.join(claudeSlackDir, 'logs');
        await fs.ensureDir(logDir);
        await fs.ensureDir(path.join(logDir, 'hooks'));
        await fs.ensureDir(path.join(logDir, 'managers'));
        await fs.ensureDir(path.join(logDir, 'archive'));

        this.spinner.succeed('Global components installed');
    }

    async setupPythonEnvironment() {
        this.spinner = ora('Setting up Python environment...').start();

        const claudeSlackDir = path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR);
        const mcpDir = path.join(claudeSlackDir, 'mcp');

        // First, create requirements.txt if it doesn't exist
        const requirementsPath = path.join(mcpDir, 'requirements.txt');
        if (!fs.existsSync(requirementsPath)) {
            const requirements = `# Claude-Slack MCP Server Requirements
mcp>=0.1.0
aiosqlite>=0.19.0
pyyaml>=6.0
`;
            await fs.writeFile(requirementsPath, requirements);
        }

        try {
            // Create virtual environment
            execSync('python3 -m venv venv', {
                cwd: mcpDir,
                stdio: 'pipe'
            });

            // Install dependencies
            // Handle platform-specific pip location
            const pipCmd = process.platform === 'win32'
                ? path.join('venv', 'Scripts', 'pip.exe')
                : path.join('venv', 'bin', 'pip');

            execSync(`${pipCmd} install --upgrade pip`, {
                cwd: mcpDir,
                stdio: 'pipe'
            });

            execSync(`${pipCmd} install -r requirements.txt`, {
                cwd: mcpDir,
                stdio: 'pipe'
            });

            this.spinner.succeed('Python environment configured');
        } catch (error) {
            this.spinner.fail('Failed to setup Python environment');
            throw error;
        }
    }

    async initializeDatabase() {
        this.spinner = ora('Initializing SQLite database...').start();

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
            ? path.join(mcpDir, 'venv', 'Scripts', 'python.exe')
            : path.join(mcpDir, 'venv', 'bin', 'python');
        const schemaPath = path.join(mcpDir, 'db', 'schema.sql');

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
        // Handle platform-specific paths
        const claudeSlackDir = path.join(this.globalClaudeDir, CLAUDE_SLACK_DIR);
        const venvPython = process.platform === 'win32'
            ? path.join(claudeSlackDir, 'venv', 'Scripts', 'python.exe')
            : path.join(claudeSlackDir, 'venv', 'bin', 'python');

        if (process.platform === 'win32') {
            // Windows batch files
            // Note: configure_agents and register_project_agents removed - setup is now automatic
            const linksBat = `@echo off
REM Wrapper script for manage_project_links.py using venv Python
set SCRIPT_DIR=%~dp0
set VENV_PYTHON="${venvPython}"
"%VENV_PYTHON%" "%SCRIPT_DIR%manage_project_links.py" %*
`;
            await fs.writeFile(path.join(scriptsDir, 'manage_project_links.bat'), linksBat);
        } else {
            // Unix/Linux/Mac shell scripts
            // Note: configure_agents and register_project_agents removed - setup is now automatic
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

        // Hook paths in claude-slack directory
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

        this.spinner.succeed('Hooks installed (SessionStart + PreToolUse)');
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
        console.log(chalk.green.bold('\n✅ Claude-Slack installed successfully!\n'));

        console.log(chalk.cyan('📚 Installation Summary:'));
        console.log(`  • ${chalk.bold('MCP Server')}: ${path.join(this.globalClaudeDir, MCP_SERVER_DIR)}`);
        console.log(`  • ${chalk.bold('Database')}: ${path.join(this.globalClaudeDir, 'data', DB_NAME)}`);
        console.log(`  • ${chalk.bold('Hooks')}: SessionStart + PreToolUse`);
        console.log(`  • ${chalk.bold('Managers')}: SessionManager, ChannelManager, SubscriptionManager, ProjectSetupManager`);

        console.log(chalk.cyan('\n🐛 Debug Logging:'));
        console.log('  • Enable debug logs: export CLAUDE_SLACK_DEBUG=1');
        console.log(`  • Log files: ${path.join(this.globalClaudeDir, 'logs')}/*.log`);
        console.log('  • Logs show hook execution, database operations, and errors');

        console.log(chalk.cyan('\n🚀 Quick Start Guide:'));
        console.log('  1. Restart Claude Code to load the MCP server');
        console.log('  2. Projects are auto-detected when you have a .claude/ directory');
        console.log('  3. Agents are auto-configured with MCP tools on session start');
        console.log('  4. Use /slack-status to verify your context');
        console.log('  5. Start using channels immediately!');
        console.log('  ');
        console.log(chalk.cyan('🏗️  Architecture:'));
        console.log('  • SessionManager: Manages session contexts and project detection');
        console.log('  • ChannelManager: Handles channel CRUD operations');
        console.log('  • SubscriptionManager: Manages agent-channel relationships\n');

        console.log(chalk.cyan('🔧 Project Linking (Optional):'));
        console.log(chalk.gray('  (Only needed for cross-project communication)'));
        const scriptExt = process.platform === 'win32' ? '.bat' : '';
        console.log(`  • Manage project links: ${path.join(this.globalClaudeDir, 'scripts', `manage_project_links${scriptExt}`)} [command]`);
        console.log('  • Projects are isolated by default');
        console.log('  • Link projects to enable agent discovery between them\n');

        console.log(chalk.cyan('💬 Basic Commands:'));
        console.log('  • /slack-send #general "Hello, world!" - Send to global channel');
        console.log('  • /slack-send #project:dev "Update" - Send to project channel');
        console.log('  • /slack-dm @agent "Private message" - Send direct message');
        console.log('  • /slack-inbox - Check unread messages');
        console.log('  • /slack-subscribe #channel - Join a channel\n');

        console.log(chalk.cyan('🔍 Project Isolation:'));
        if (this.hasProject) {
            console.log(`  • Current project: ${chalk.green(this.projectDir)}`);
            console.log('  • Project channels are separate from global channels');
            console.log('  • Agent subscriptions use scoped format (global: vs project:)');
        } else {
            console.log('  • No project detected - using global context only');
            console.log('  • Create a .claude directory in your project for project channels');
        }

        console.log(chalk.blue('\n📖 For documentation: https://github.com/yourusername/claude-slack'));
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