#!/usr/bin/env python3
"""
register_project_agents.py - Register project agents with claude-slack system

This script registers all agents in a project's .claude/agents directory with the
claude-slack messaging system. It:

1. Parses agent names and descriptions from frontmatter
2. Registers agents in the database
3. Adds MCP tools if needed
4. Sets up default channel subscriptions

Usage:
    python3 ~/.claude/scripts/register_project_agents.py [project_path]
    
    project_path    Path to project directory (default: current directory)

Examples:
    # Register agents in current project
    python3 ~/.claude/scripts/register_project_agents.py
    
    # Register agents in specific project
    python3 ~/.claude/scripts/register_project_agents.py /path/to/my-project
"""

import os
import sys
import argparse
import hashlib
from pathlib import Path
from typing import Dict, Optional

# Add MCP directory to path to import admin_operations
sys.path.insert(0, str(Path.home() / '.claude' / 'mcp' / 'claude-slack'))

from admin_operations import AdminOperations


def get_project_id(project_path: str) -> str:
    """Generate consistent project ID from path"""
    return hashlib.sha256(project_path.encode()).hexdigest()[:32]


def parse_agent_description(agent_file: Path) -> Optional[str]:
    """
    Parse agent file to extract description from frontmatter or first paragraph
    
    Args:
        agent_file: Path to agent markdown file
        
    Returns:
        Description string or None
    """
    try:
        with open(agent_file, 'r') as f:
            content = f.read()
        
        if not content.startswith('---'):
            # No frontmatter, use first paragraph as description
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    return line[:200]  # Limit description length
            return None
        
        # Parse frontmatter
        lines = content.split('\n')
        in_frontmatter = False
        
        for i, line in enumerate(lines):
            if i == 0 and line == '---':
                in_frontmatter = True
                continue
            
            if in_frontmatter:
                if line == '---':
                    # End of frontmatter, look for description after
                    for j in range(i + 1, len(lines)):
                        line = lines[j].strip()
                        if line and not line.startswith('#'):
                            return line[:200]
                    break
                
                if line.startswith('description:'):
                    desc = line.split(':', 1)[1].strip().strip('"\'')
                    if desc:
                        return desc
        
        return None
        
    except Exception:
        return None


def register_agent(
    agent_file: Path,
    project_id: str,
    admin_ops: AdminOperations,
    verbose: bool = True,
    dry_run: bool = False
) -> bool:
    """
    Register a single agent with the system
    
    Args:
        agent_file: Path to agent markdown file
        project_id: Project ID
        admin_ops: AdminOperations instance
        verbose: Whether to print status messages
        dry_run: If True, don't actually make changes
        
    Returns:
        True if agent was registered successfully
    """
    agent_name = agent_file.stem
    description = parse_agent_description(agent_file)
    
    if not description:
        description = f"Agent: {agent_name}"
    
    if dry_run:
        if verbose:
            print(f"  Would register: {agent_name}")
            print(f"    Description: {description}")
        return True
    
    # Register agent in database
    success, message = admin_ops.sync_register_agent(
        agent_name,
        description,
        project_id
    )
    
    if not success:
        if verbose:
            print(f"  ❌ {agent_name}: Failed to register - {message}")
        return False
    
    # Configure agent file with tools and subscriptions
    success, message = admin_ops.configure_agent_file(
        agent_file,
        add_tools=True,
        add_subscriptions=True
    )
    
    if verbose:
        if success:
            print(f"  ✅ {agent_name}: Registered and configured")
        else:
            print(f"  ⚠️  {agent_name}: Registered but configuration failed - {message}")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Register project agents with claude-slack messaging system'
    )
    
    parser.add_argument(
        'project_path',
        nargs='?',
        default='.',
        help='Path to project directory (default: current directory)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what would be done without making changes'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        default=True,
        help='Show detailed output (default: True)'
    )
    
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress output'
    )
    
    args = parser.parse_args()
    
    if args.quiet:
        args.verbose = False
    
    # Resolve project path
    project_path = Path(args.project_path).resolve()
    
    # Check for .claude directory
    claude_dir = project_path / '.claude'
    if not claude_dir.exists():
        print(f"❌ No .claude directory found in {project_path}")
        print("\nTo create a project:")
        print("  1. cd to your project directory")
        print("  2. mkdir .claude")
        print("  3. mkdir .claude/agents")
        print("  4. Add agent markdown files to .claude/agents/")
        sys.exit(1)
    
    # Check for agents directory
    agents_dir = claude_dir / 'agents'
    if not agents_dir.exists():
        print(f"❌ No agents directory found at {agents_dir}")
        print("\nCreate it with: mkdir .claude/agents")
        sys.exit(1)
    
    # Find all agent files
    agent_files = list(agents_dir.glob('*.md'))
    if not agent_files:
        print(f"⚠️  No agent files found in {agents_dir}")
        sys.exit(0)
    
    # Initialize AdminOperations
    admin_ops = AdminOperations()
    
    # Get project info
    project_name = project_path.name
    project_id = get_project_id(str(project_path))
    
    print(f"📦 Registering agents for project: {project_name}")
    print(f"📍 Location: {project_path}")
    print(f"🔑 Project ID: {project_id[:8]}...")
    print("=" * 50)
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print()
    
    # Register the project itself
    if not args.dry_run:
        success, message = admin_ops.sync_register_project(str(project_path), project_name)
        if success:
            print(f"✅ Project registered: {message}")
        else:
            print(f"⚠️  Project registration: {message}")
        print()
    
    # Register each agent
    print(f"Found {len(agent_files)} agent(s) to register:")
    registered = 0
    
    for agent_file in sorted(agent_files):
        if register_agent(agent_file, project_id, admin_ops, args.verbose, args.dry_run):
            registered += 1
    
    # Summary
    print(f"\n{'=' * 50}")
    if args.dry_run:
        print(f"Would register {registered}/{len(agent_files)} agent(s)")
        print("\nRun without --dry-run to apply changes")
    else:
        print(f"✅ Successfully registered {registered}/{len(agent_files)} agent(s)")
        
        if registered > 0:
            print("\nAgents now have:")
            print("  • Registration in claude-slack database")
            print("  • MCP tools for messaging")
            print("  • Default channel subscriptions from config")
            print("\nProject channels created:")
            print("  • From ~/.claude/config/claude-slack.config.yaml")
            print("\nRestart Claude Code for changes to take effect.")


if __name__ == '__main__':
    main()