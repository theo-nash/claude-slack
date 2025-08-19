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

# Add MCP directory to path to import admin_operations
sys.path.insert(0, str(Path.home() / '.claude' / 'mcp' / 'claude-slack'))

from admin_operations import AdminOperations

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def get_admin_ops() -> AdminOperations:
    """Get AdminOperations instance"""
    return AdminOperations()

async def list_all_projects(ops: AdminOperations) -> List[dict]:
    """List all registered projects"""
    return await ops.list_all_projects()

async def get_project_links_with_names(ops: AdminOperations, project_id: str) -> List[Tuple[str, str]]:
    """Get links for a project with names"""
    linked_ids = await ops.get_project_links(project_id)
    all_projects = await ops.list_all_projects()
    
    # Map IDs to names
    id_to_name = {p['id']: p['name'] for p in all_projects}
    
    result = []
    for linked_id in linked_ids:
        if linked_id in id_to_name:
            result.append((linked_id, id_to_name[linked_id]))
    
    return result

def cmd_list(args):
    """List all projects and their links"""
    ops = get_admin_ops()
    
    print(f"{Colors.HEADER}{Colors.BOLD}📊 Project Communication Links{Colors.ENDC}")
    print("=" * 60)
    
    projects = asyncio.run(ops.list_all_projects())
    
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
        
        links = asyncio.run(get_project_links_with_names(ops, proj_id))
        
        if links:
            print(f"   {Colors.GREEN}Links:{Colors.ENDC}")
            for linked_id, linked_name in links:
                # For now, assume bidirectional (can be enhanced later)
                symbol = "↔️"
                desc = "bidirectional"
                print(f"     {symbol} {linked_name} ({desc})")
        else:
            print(f"   {Colors.YELLOW}No links configured{Colors.ENDC}")

def cmd_link(args):
    """Create a link between two projects"""
    ops = get_admin_ops()
    
    # Create link using AdminOperations
    success, message = ops.sync_link_projects(
        args.project_a,
        args.project_b,
        args.type
    )
    
    if success:
        print(f"{Colors.GREEN}✅ {message}{Colors.ENDC}")
        print(f"\n{Colors.BLUE}ℹ️ Agents in these projects can now discover each other{Colors.ENDC}")
    else:
        print(f"{Colors.RED}❌ {message}{Colors.ENDC}")

def cmd_unlink(args):
    """Remove a link between two projects"""
    ops = get_admin_ops()
    
    # Remove link using AdminOperations
    success, message = ops.sync_unlink_projects(
        args.project_a,
        args.project_b
    )
    
    if success:
        print(f"{Colors.GREEN}✅ {message}{Colors.ENDC}")
        print(f"\n{Colors.YELLOW}⚠️ Agents in these projects can no longer discover each other{Colors.ENDC}")
    else:
        print(f"{Colors.YELLOW}⚠️ {message}{Colors.ENDC}")

def cmd_status(args):
    """Show link status for a specific project"""
    ops = get_admin_ops()
    
    # Get all projects to find the target
    projects = asyncio.run(ops.list_all_projects())
    
    # Find project by name or ID
    project = None
    for p in projects:
        if p['name'] == args.project or p['id'] == args.project or p['path'] == args.project:
            project = p
            break
    
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
    
    links = asyncio.run(get_project_links_with_names(ops, proj_id))
    
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