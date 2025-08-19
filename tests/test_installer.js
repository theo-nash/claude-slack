#!/usr/bin/env node
/**
 * Test the Claude-Slack installer
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

console.log('Testing Claude-Slack installer...\n');

// Test 1: Check if installer file exists
const installerPath = path.join(__dirname, '..', 'bin', 'install.js');
if (!fs.existsSync(installerPath)) {
    console.error('❌ Installer not found at:', installerPath);
    process.exit(1);
}
console.log('✅ Installer file exists');

// Test 2: Check template structure
const templateDir = path.join(__dirname, '..', 'template');
const requiredPaths = [
    'global/mcp/claude-slack/server.py',
    'global/mcp/claude-slack/db/schema.sql',
    'global/mcp/claude-slack/db/manager.py',
    'global/mcp/claude-slack/frontmatter/parser.py',
    'global/mcp/claude-slack/frontmatter/updater.py',
    'global/hooks/slack_pre_tool_use.py',
    'global/commands/slack-status.md',
    'global/commands/slack-inbox.md',
    'global/commands/slack-send.md'
];

let allFilesExist = true;
for (const relativePath of requiredPaths) {
    const fullPath = path.join(templateDir, relativePath);
    if (!fs.existsSync(fullPath)) {
        console.error(`❌ Missing required file: ${relativePath}`);
        allFilesExist = false;
    }
}

if (allFilesExist) {
    console.log('✅ All required template files exist');
} else {
    process.exit(1);
}

// Test 3: Check package.json bin configuration
const packageJson = require('../package.json');
if (!packageJson.bin || !packageJson.bin['claude-slack']) {
    console.error('❌ Package.json missing bin configuration');
    process.exit(1);
}
console.log('✅ Package.json bin configuration correct');

// Test 4: Verify Python files are syntactically correct
console.log('\nVerifying Python syntax...');
const pythonFiles = [
    path.join(templateDir, 'global/mcp/claude-slack/server.py'),
    path.join(templateDir, 'global/mcp/claude-slack/db/manager.py'),
    path.join(templateDir, 'global/mcp/claude-slack/frontmatter/parser.py'),
    path.join(templateDir, 'global/mcp/claude-slack/frontmatter/updater.py'),
    path.join(templateDir, 'global/hooks/slack_pre_tool_use.py')
];

for (const pyFile of pythonFiles) {
    try {
        execSync(`python3 -m py_compile "${pyFile}"`, { stdio: 'pipe' });
        console.log(`✅ ${path.basename(pyFile)} - syntax OK`);
    } catch (error) {
        console.error(`❌ ${path.basename(pyFile)} - syntax error`);
        console.error(error.stderr.toString());
        process.exit(1);
    }
}

console.log('\n✅ All installer tests passed!');