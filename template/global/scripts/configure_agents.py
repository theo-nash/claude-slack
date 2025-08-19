#!/usr/bin/env python3
"""
configure_agents.py - Add claude-slack MCP tools to agent configurations

This script ensures all agents have access to claude-slack MCP tools and
default channel subscriptions. Run this after installation or when adding
new agents.

Usage:
    python3 ~/.claude/scripts/configure_agents.py [--all | agent-name]
    
    --all           Configure all agents (default)
    agent-name      Configure specific agent
    --project PATH  Also configure agents in specified project
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Optional

# Add MCP directory to path to import admin_operations
sys.path.insert(0, str(Path.home() / '.claude' / 'mcp' / 'claude-slack'))

from admin_operations import AdminOperations


def configure_agent(agent_file: Path, admin_ops: AdminOperations, verbose: bool = True) -> bool:
    """
    Configure an agent file with MCP tools and subscriptions
    
    Args:
        agent_file: Path to agent markdown file
        admin_ops: AdminOperations instance
        verbose: Whether to print status messages
        
    Returns:
        True if agent was configured successfully
    """
    agent_name = agent_file.stem
    
    # Use AdminOperations to configure the agent
    success, message = admin_ops.configure_agent_file(
        agent_file,
        add_tools=True,
        add_subscriptions=True
    )
    
    if verbose:
        if success:
            print(f"  ✅ {agent_name}: {message}")
        else:
            print(f"  ❌ {agent_name}: {message}")
    
    return success


def configure_all_agents(claude_dir: Path, admin_ops: AdminOperations, verbose: bool = True) -> int:
    """
    Configure all agents in a .claude directory
    
    Args:
        claude_dir: Path to .claude directory
        admin_ops: AdminOperations instance
        verbose: Whether to print status messages
        
    Returns:
        Number of agents configured
    """
    agents_dir = claude_dir / 'agents'
    if not agents_dir.exists():
        if verbose:
            print(f"  ⚠️  No agents directory found at {agents_dir}")
        return 0
    
    agent_files = list(agents_dir.glob('*.md'))
    if not agent_files:
        if verbose:
            print(f"  ⚠️  No agent files found in {agents_dir}")
        return 0
    
    configured = 0
    for agent_file in agent_files:
        if configure_agent(agent_file, admin_ops, verbose):
            configured += 1
    
    return configured


def main():
    parser = argparse.ArgumentParser(
        description='Configure Claude Code agents with claude-slack MCP tools and channel subscriptions'
    )
    
    parser.add_argument(
        'agent',
        nargs='?',
        default='--all',
        help='Agent name to configure (default: --all for all agents)'
    )
    
    parser.add_argument(
        '--project',
        type=str,
        help='Also configure agents in specified project directory'
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
    
    # Initialize AdminOperations
    admin_ops = AdminOperations()
    
    print("🔧 Configuring Claude Code agents for claude-slack")
    print("=" * 50)
    
    total_configured = 0
    
    # Configure global agents
    global_claude = Path.home() / '.claude'
    if global_claude.exists():
        print(f"\n📍 Global agents ({global_claude}):")
        
        if args.agent == '--all':
            configured = configure_all_agents(global_claude, admin_ops, args.verbose)
            total_configured += configured
            if args.verbose:
                print(f"  Configured {configured} agent(s)")
        else:
            # Configure specific agent
            agent_file = global_claude / 'agents' / f'{args.agent}.md'
            if agent_file.exists():
                if configure_agent(agent_file, admin_ops, args.verbose):
                    total_configured += 1
            else:
                print(f"  ❌ Agent '{args.agent}' not found")
    
    # Configure project agents if specified
    if args.project:
        project_path = Path(args.project).resolve()
        project_claude = project_path / '.claude'
        
        if project_claude.exists():
            print(f"\n📍 Project agents ({project_path.name}):")
            
            if args.agent == '--all':
                configured = configure_all_agents(project_claude, admin_ops, args.verbose)
                total_configured += configured
                if args.verbose:
                    print(f"  Configured {configured} agent(s)")
            else:
                # Configure specific agent in project
                agent_file = project_claude / 'agents' / f'{args.agent}.md'
                if agent_file.exists():
                    if configure_agent(agent_file, admin_ops, args.verbose):
                        total_configured += 1
                else:
                    print(f"  ❌ Agent '{args.agent}' not found in project")
        else:
            print(f"\n⚠️  No .claude directory found in project: {project_path}")
    
    # Summary
    print(f"\n{'=' * 50}")
    if total_configured > 0:
        print(f"✅ Successfully configured {total_configured} agent(s)")
        print("\nAgents now have:")
        print("  • claude-slack MCP tools")
        print("  • Default channel subscriptions from config")
        print("\nRestart Claude Code for changes to take effect.")
    else:
        print("ℹ️  No agents were configured")
        print("\nPossible reasons:")
        print("  • All agents already configured")
        print("  • No agents found")
        print("  • Agents have 'All' tools access (no configuration needed)")


if __name__ == '__main__':
    main()