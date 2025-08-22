#!/usr/bin/env python3
"""
manage_project_links.py - Manage cross-project communication permissions

This administrative script allows users to explicitly configure which projects
can communicate with each other. Project links must be explicitly created - 
agents cannot inadvertently link projects.

Usage:
    python3 ~/.claude/scripts/manage_project_links.py [command] [options]
    
Commands:
    list                List all projects and their links
    link                Create a link between two projects
    unlink              Remove a link between two projects
    status              Show link status for a specific project

Examples:
    # List all projects and links
    python3 ~/.claude/scripts/manage_project_links.py list
    
    # Link two projects (bidirectional)
    python3 ~/.claude/scripts/manage_project_links.py link project-a project-b
    
    # Link with one-way permission (A can talk to B, but not vice versa)
    python3 ~/.claude/scripts/manage_project_links.py link project-a project-b --type a_to_b
    
    # Remove a link
    python3 ~/.claude/scripts/manage_project_links.py unlink project-a project-b
    
    # Check links for specific project
    python3 ~/.claude/scripts/manage_project_links.py status project-a
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path
from typing import List, Tuple, Optional

# Add MCP directory to path
claude_config_dir = os.environ.get('CLAUDE_CONFIG_DIR', str(Path.home() / '.claude'))
claude_slack_dir = os.path.join(claude_config_dir, 'claude-slack')
mcp_dir = os.path.join(claude_slack_dir, 'mcp')
sys.path.insert(0, mcp_dir)

from db.manager import DatabaseManager
from db.initialization import initialized_db_manager
from environment_config import env_config

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def get_db_path() -> str:
    """Get database path from environment config"""
    try:
        return env_config.db_path
    except:
        claude_config_dir = os.environ.get('CLAUDE_CONFIG_DIR', str(Path.home() / '.claude'))
        claude_slack_dir = os.path.join(claude_config_dir, 'claude-slack')
        return os.path.join(claude_slack_dir, 'data', 'claude-slack.db')

async def list_all_projects(db_manager: DatabaseManager) -> List[dict]:
    """List all registered projects"""
    async with initialized_db_manager(db_manager) as dm:
        async with dm.get_connection() as conn:
            return await dm.list_projects(conn)

async def get_project_by_identifier(db_manager: DatabaseManager, identifier: str) -> Optional[dict]:
    """Find project by name, ID, or path"""
    projects = await list_all_projects(db_manager)
    
    for project in projects:
        if (project['name'] == identifier or 
            project['id'] == identifier or 
            project['path'] == identifier or
            project['id'].startswith(identifier)):  # Allow partial ID match
            return project
    
    return None

async def get_project_links_with_names(db_manager: DatabaseManager, project_id: str) -> List[Tuple[str, str]]:
    """Get links for a project with names"""
    async with initialized_db_manager(db_manager) as dm:
        async with dm.get_connection() as conn:
            linked_ids = await dm.get_linked_projects(conn, project_id)
            all_projects = await dm.list_projects(conn)
    
    # Map IDs to names
    id_to_name = {p['id']: p['name'] for p in all_projects}
    
    result = []
    for linked_id in linked_ids:
        if linked_id in id_to_name:
            result.append((linked_id, id_to_name[linked_id]))
    
    return result

async def cmd_list_async(args):
    """List all projects and their links"""
    db_manager = DatabaseManager(get_db_path())
    
    print(f"{Colors.HEADER}{Colors.BOLD}📊 Project Communication Links{Colors.ENDC}")
    print("=" * 60)
    
    projects = await list_all_projects(db_manager)
    
    if not projects:
        print(f"{Colors.YELLOW}No projects registered yet{Colors.ENDC}")
        return
    
    for project in projects:
        proj_id = project['id']
        proj_name = project['name']
        proj_path = project['path']
        
        print(f"\n{Colors.BLUE}{Colors.BOLD}📁 {proj_name}{Colors.ENDC}")
        print(f"   ID: {proj_id[:8]}...")
        print(f"   Path: {proj_path}")
        
        links = await get_project_links_with_names(db_manager, proj_id)
        
        if links:
            print(f"   {Colors.GREEN}Links:{Colors.ENDC}")
            for linked_id, linked_name in links:
                # For now, assume bidirectional (can be enhanced later)
                symbol = "↔️"
                desc = "bidirectional"
                print(f"     {symbol} {linked_name} ({desc})")
        else:
            print(f"   {Colors.YELLOW}No links configured{Colors.ENDC}")

def cmd_list(args):
    """Sync wrapper for list command"""
    asyncio.run(cmd_list_async(args))

async def cmd_link_async(args):
    """Create a link between two projects"""
    db_manager = DatabaseManager(get_db_path())
    
    # Find projects by identifier
    project_a = await get_project_by_identifier(db_manager, args.project_a)
    project_b = await get_project_by_identifier(db_manager, args.project_b)
    
    if not project_a:
        print(f"{Colors.RED}❌ Project '{args.project_a}' not found{Colors.ENDC}")
        return
    
    if not project_b:
        print(f"{Colors.RED}❌ Project '{args.project_b}' not found{Colors.ENDC}")
        return
    
    # Create link using DatabaseManager
    async with initialized_db_manager(db_manager) as dm:
        async with dm.get_connection() as conn:
            success = await dm.link_projects(
                conn,
                project_a['id'],
                project_b['id'],
                args.type
            )
    
    if success:
        print(f"{Colors.GREEN}✅ Successfully linked {project_a['name']} and {project_b['name']}{Colors.ENDC}")
        if args.type == 'bidirectional':
            print(f"\n{Colors.BLUE}ℹ️ Agents in these projects can now discover each other{Colors.ENDC}")
        elif args.type == 'a_to_b':
            print(f"\n{Colors.BLUE}ℹ️ Agents in {project_a['name']} can now discover agents in {project_b['name']}{Colors.ENDC}")
        else:  # b_to_a
            print(f"\n{Colors.BLUE}ℹ️ Agents in {project_b['name']} can now discover agents in {project_a['name']}{Colors.ENDC}")
    else:
        print(f"{Colors.YELLOW}⚠️ Projects may already be linked or an error occurred{Colors.ENDC}")

def cmd_link(args):
    """Sync wrapper for link command"""
    asyncio.run(cmd_link_async(args))

async def cmd_unlink_async(args):
    """Remove a link between two projects"""
    db_manager = DatabaseManager(get_db_path())
    
    # Find projects by identifier
    project_a = await get_project_by_identifier(db_manager, args.project_a)
    project_b = await get_project_by_identifier(db_manager, args.project_b)
    
    if not project_a:
        print(f"{Colors.RED}❌ Project '{args.project_a}' not found{Colors.ENDC}")
        return
    
    if not project_b:
        print(f"{Colors.RED}❌ Project '{args.project_b}' not found{Colors.ENDC}")
        return
    
    # Remove link using DatabaseManager
    async with initialized_db_manager(db_manager) as dm:
        async with dm.get_connection() as conn:
            success = await dm.unlink_projects(
                conn,
                project_a['id'],
                project_b['id']
            )
    
    if success:
        print(f"{Colors.GREEN}✅ Successfully unlinked {project_a['name']} and {project_b['name']}{Colors.ENDC}")
        print(f"\n{Colors.YELLOW}⚠️ Agents in these projects can no longer discover each other{Colors.ENDC}")
    else:
        print(f"{Colors.YELLOW}⚠️ Projects were not linked or an error occurred{Colors.ENDC}")

def cmd_unlink(args):
    """Sync wrapper for unlink command"""
    asyncio.run(cmd_unlink_async(args))

async def cmd_status_async(args):
    """Show link status for a specific project"""
    db_manager = DatabaseManager(get_db_path())
    
    # Find project by identifier
    project = await get_project_by_identifier(db_manager, args.project)
    
    if not project:
        print(f"{Colors.RED}❌ Project '{args.project}' not found{Colors.ENDC}")
        return
    
    proj_id = project['id']
    proj_name = project['name']
    proj_path = project['path']
    
    print(f"{Colors.HEADER}{Colors.BOLD}📊 Link Status for {proj_name}{Colors.ENDC}")
    print("=" * 60)
    print(f"ID: {proj_id[:8]}...")
    print(f"Path: {proj_path}")
    
    links = await get_project_links_with_names(db_manager, proj_id)
    
    if not links:
        print(f"\n{Colors.YELLOW}No links configured for this project{Colors.ENDC}")
        print(f"{Colors.BLUE}ℹ️ This project can only communicate within itself and with global agents{Colors.ENDC}")
    else:
        print(f"\n{Colors.GREEN}Linked Projects:{Colors.ENDC}")
        print(f"\n  ↔️ {Colors.BOLD}Bidirectional:{Colors.ENDC}")
        for linked_id, linked_name in links:
            print(f"     • {linked_name}")
    
    print(f"\n{Colors.BLUE}📊 Agent Visibility:{Colors.ENDC}")
    print(f"  • Can see global agents: Yes")
    print(f"  • Can see own project agents: Yes")
    
    if links:
        print(f"  • Can see linked project agents: Yes ({len(links)} linked project(s))")
    else:
        print(f"  • Can see linked project agents: None (no links)")

def cmd_status(args):
    """Sync wrapper for status command"""
    asyncio.run(cmd_status_async(args))

def main():
    parser = argparse.ArgumentParser(
        description='Manage cross-project communication permissions for claude-slack'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List all projects and their links')
    
    # Link command
    link_parser = subparsers.add_parser('link', help='Create a link between two projects')
    link_parser.add_argument('project_a', help='First project (name, ID, or path)')
    link_parser.add_argument('project_b', help='Second project (name, ID, or path)')
    link_parser.add_argument('--type', 
                            choices=['bidirectional', 'a_to_b', 'b_to_a'],
                            default='bidirectional',
                            help='Link type (default: bidirectional)')
    
    # Unlink command
    unlink_parser = subparsers.add_parser('unlink', help='Remove a link between two projects')
    unlink_parser.add_argument('project_a', help='First project (name, ID, or path)')
    unlink_parser.add_argument('project_b', help='Second project (name, ID, or path)')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show link status for a project')
    status_parser.add_argument('project', help='Project (name, ID, or path)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Execute command
    if args.command == 'list':
        cmd_list(args)
    elif args.command == 'link':
        cmd_link(args)
    elif args.command == 'unlink':
        cmd_unlink(args)
    elif args.command == 'status':
        cmd_status(args)

if __name__ == '__main__':
    main()