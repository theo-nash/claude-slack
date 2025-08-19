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
const MCP_SERVER_DIR = 'mcp/claude-slack';
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
        
        console.log(`  • ${chalk.bold('Global Installation')}: ${this.globalClaudeDir}`);
        console.log(`  • ${chalk.bold('MCP Server')}: Always global`);
        console.log(`  • ${chalk.bold('Database')}: ${path.join(this.globalClaudeDir, 'data', DB_NAME)}`);
        console.log(`  • ${chalk.bold('Commands')}: Global slash commands`);
        console.log(`  • ${chalk.bold('Hook')}: Global PreToolUse hook for project detection`);
        
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
        
        // Copy MCP server
        const mcpSource = path.join(globalTemplateDir, 'mcp');
        const mcpTarget = path.join(this.globalClaudeDir, 'mcp');
        await fs.copy(mcpSource, mcpTarget, { overwrite: false });
        
        // Copy commands
        const commandsSource = path.join(globalTemplateDir, 'commands');
        const commandsTarget = path.join(this.globalClaudeDir, 'commands');
        await fs.copy(commandsSource, commandsTarget, { overwrite: false });
        
        // Copy config file
        const configSource = path.join(globalTemplateDir, 'config');
        const configTarget = path.join(this.globalClaudeDir, 'config');
        await fs.copy(configSource, configTarget, { overwrite: false });
        
        // Copy scripts (including manage_project_links.py)
        const scriptsSource = path.join(globalTemplateDir, 'scripts');
        const scriptsTarget = path.join(this.globalClaudeDir, 'scripts');
        await fs.copy(scriptsSource, scriptsTarget, { overwrite: false });
        
        // Ensure data directory exists
        const dataDir = path.join(this.globalClaudeDir, 'data');
        await fs.ensureDir(dataDir);
        await fs.ensureDir(path.join(dataDir, 'backups'));
        
        this.spinner.succeed('Global components installed');
    }

    async setupPythonEnvironment() {
        this.spinner = ora('Setting up Python environment...').start();
        
        const mcpDir = path.join(this.globalClaudeDir, MCP_SERVER_DIR);
        
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
        
        const dataDir = path.join(this.globalClaudeDir, 'data');
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
        this.spinner = ora('Configuring MCP server in global settings...').start();
        
        const settingsPath = path.join(this.globalClaudeDir, 'settings.json');
        let settings = {};
        
        // Read existing settings if present
        if (fs.existsSync(settingsPath)) {
            settings = await fs.readJson(settingsPath);
        }
        
        // Ensure mcpServers object exists
        if (!settings.mcpServers) {
            settings.mcpServers = {};
        }
        
        // Add claude-slack MCP server configuration
        // Use the venv Python to ensure dependencies are available
        // Handle platform-specific Python executable location
        const venvPython = process.platform === 'win32'
            ? path.join(this.globalClaudeDir, MCP_SERVER_DIR, 'venv', 'Scripts', 'python.exe')
            : path.join(this.globalClaudeDir, MCP_SERVER_DIR, 'venv', 'bin', 'python');
        
        settings.mcpServers['claude-slack'] = {
            "command": venvPython,
            "args": ["server.py"],
            "cwd": path.join(this.globalClaudeDir, MCP_SERVER_DIR),
            "env": {
                "PYTHONPATH": path.join(this.globalClaudeDir, MCP_SERVER_DIR),
                "DB_PATH": path.join(this.globalClaudeDir, 'data', DB_NAME),
                "CLAUDE_CONFIG_DIR": this.globalClaudeDir  // Pass config dir to Python
            }
        };
        
        // Save updated settings
        await fs.writeJson(settingsPath, settings, { spaces: 2 });
        this.spinner.succeed('MCP server configured in global settings.json');
    }

    async createWrapperScripts(scriptsDir) {
        // Create wrapper scripts that use the venv Python
        // Handle platform-specific paths
        const venvPython = process.platform === 'win32'
            ? path.join(this.globalClaudeDir, MCP_SERVER_DIR, 'venv', 'Scripts', 'python.exe')
            : path.join(this.globalClaudeDir, MCP_SERVER_DIR, 'venv', 'bin', 'python');
        
        if (process.platform === 'win32') {
            // Windows batch files
            const configureBat = `@echo off
REM Wrapper script for configure_agents.py using venv Python
set SCRIPT_DIR=%~dp0
set VENV_PYTHON="${venvPython}"
"%VENV_PYTHON%" "%SCRIPT_DIR%configure_agents.py" %*
`;
            await fs.writeFile(path.join(scriptsDir, 'configure_agents.bat'), configureBat);
            
            const registerBat = `@echo off
REM Wrapper script for register_project_agents.py using venv Python
set SCRIPT_DIR=%~dp0
set VENV_PYTHON="${venvPython}"
"%VENV_PYTHON%" "%SCRIPT_DIR%register_project_agents.py" %*
`;
            await fs.writeFile(path.join(scriptsDir, 'register_project_agents.bat'), registerBat);
            
            const linksBat = `@echo off
REM Wrapper script for manage_project_links.py using venv Python
set SCRIPT_DIR=%~dp0
set VENV_PYTHON="${venvPython}"
"%VENV_PYTHON%" "%SCRIPT_DIR%manage_project_links.py" %*
`;
            await fs.writeFile(path.join(scriptsDir, 'manage_project_links.bat'), linksBat);
        } else {
            // Unix/Linux/Mac shell scripts
            const configureWrapper = `#!/bin/bash
# Wrapper script for configure_agents.py using venv Python
SCRIPT_DIR="$( cd "$( dirname "\${BASH_SOURCE[0]}" )" && pwd )"
VENV_PYTHON="${venvPython}"
exec "$VENV_PYTHON" "$SCRIPT_DIR/configure_agents.py" "$@"
`;
            await fs.writeFile(path.join(scriptsDir, 'configure_agents'), configureWrapper);
            await fs.chmod(path.join(scriptsDir, 'configure_agents'), '755');
            
            const registerWrapper = `#!/bin/bash
# Wrapper script for register_project_agents.py using venv Python
SCRIPT_DIR="$( cd "$( dirname "\${BASH_SOURCE[0]}" )" && pwd )"
VENV_PYTHON="${venvPython}"
exec "$VENV_PYTHON" "$SCRIPT_DIR/register_project_agents.py" "$@"
`;
            await fs.writeFile(path.join(scriptsDir, 'register_project_agents'), registerWrapper);
            await fs.chmod(path.join(scriptsDir, 'register_project_agents'), '755');
            
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
        this.spinner = ora('Installing hooks...').start();
        
        const hooksDir = path.join(this.globalClaudeDir, 'hooks');
        await fs.ensureDir(hooksDir);
        
        // Copy SessionStart hook
        const sessionHookSource = path.join(__dirname, '..', 'template', 'global', 'hooks', 'slack_session_start.py');
        const sessionHookTarget = path.join(hooksDir, 'slack_session_start.py');
        await fs.copy(sessionHookSource, sessionHookTarget, { overwrite: true });
        
        // Copy PreToolUse hook
        const preToolHookSource = path.join(__dirname, '..', 'template', 'global', 'hooks', 'slack_pre_tool_use.py');
        const preToolHookTarget = path.join(hooksDir, 'slack_pre_tool_use.py');
        await fs.copy(preToolHookSource, preToolHookTarget, { overwrite: true });
        
        // Copy scripts
        const scriptsDir = path.join(this.globalClaudeDir, 'scripts');
        await fs.ensureDir(scriptsDir);
        
        // Copy configure_agents script
        const configureSource = path.join(__dirname, '..', 'template', 'global', 'scripts', 'configure_agents.py');
        const configureTarget = path.join(scriptsDir, 'configure_agents.py');
        await fs.copy(configureSource, configureTarget, { overwrite: true });
        
        // Copy register_project_agents script
        const registerSource = path.join(__dirname, '..', 'template', 'global', 'scripts', 'register_project_agents.py');
        const registerTarget = path.join(scriptsDir, 'register_project_agents.py');
        await fs.copy(registerSource, registerTarget, { overwrite: true });
        
        // Copy manage_project_links script
        const linksSource = path.join(__dirname, '..', 'template', 'global', 'scripts', 'manage_project_links.py');
        const linksTarget = path.join(scriptsDir, 'manage_project_links.py');
        await fs.copy(linksSource, linksTarget, { overwrite: true });
        
        // Create wrapper scripts that use venv Python
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
        const sessionHookCommand = `python3 ${sessionHookTarget}`;
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
        const preToolHookCommand = `python3 ${preToolHookTarget}`;
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
        console.log(`  • ${chalk.bold('Commands')}: ${path.join(this.globalClaudeDir, 'commands', 'slack-*.md')}`);
        console.log(`  • ${chalk.bold('Hooks')}: SessionStart + PreToolUse`);
        
        console.log(chalk.cyan('\n🚀 Quick Start Guide:'));
        console.log('  1. Restart Claude Code to load the MCP server');
        console.log('  2. Projects are auto-detected when you have a .claude/ directory');
        console.log('  3. Agents are auto-configured with MCP tools on session start');
        console.log('  4. Use /slack-status to verify your context');
        console.log('  5. Start using channels immediately!\n');
        
        console.log(chalk.cyan('🔧 Configuration Scripts:'));
        console.log(chalk.gray('  (Scripts automatically use the virtual environment)'));
        const scriptExt = process.platform === 'win32' ? '.bat' : '';
        console.log(`  • Configure agents: ${path.join(this.globalClaudeDir, 'scripts', `configure_agents${scriptExt}`)}`);
        console.log(`  • Register project agents: ${path.join(this.globalClaudeDir, 'scripts', `register_project_agents${scriptExt}`)} [path]`);
        console.log(`  • Manage project links: ${path.join(this.globalClaudeDir, 'scripts', `manage_project_links${scriptExt}`)} [command]`);
        console.log('  • Project links control cross-project agent discovery and communication');
        console.log('  • Agents auto-configured on SessionStart hook\n');
        
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