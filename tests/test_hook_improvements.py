#!/usr/bin/env python3
"""
Test the improved PreToolUse hook with direct cwd access
"""

import json
import subprocess
import tempfile
import os
from pathlib import Path

def test_hook_with_json_input():
    """Test that the hook correctly processes JSON input with cwd"""
    
    # Create a temp project directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create .claude directory to mark it as a project
        project_dir = Path(tmpdir) / "test-project"
        project_dir.mkdir()
        (project_dir / ".claude").mkdir()
        
        # Prepare hook input
        hook_input = {
            "session_id": "test-session-123",
            "cwd": str(project_dir),
            "tool_name": "claude-slack.send_message",
            "hook_event_name": "PreToolUse",
            "tool_input": {
                "channel": "general",
                "message": "Test message"
            }
        }
        
        # Run the hook
        hook_path = Path(__file__).parent.parent / "template" / "global" / "hooks" / "slack_pre_tool_use.py"
        
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True
        )
        
        # Check it succeeded
        assert result.returncode == 0, f"Hook failed: {result.stderr}"
        
        # Check session file was created
        session_file = Path.home() / ".claude" / "data" / "claude-slack-sessions" / "test-session-123.json"
        if session_file.exists():
            with open(session_file) as f:
                context = json.load(f)
                
            print("✅ Session context file created")
            print(f"   Project ID: {context['project_id']}")
            print(f"   Project Path: {context['project_path']}")
            print(f"   Project Name: {context['project_name']}")
            print(f"   Scope: {context['scope']}")
            
            assert context['scope'] == 'project'
            assert context['project_path'] == str(project_dir)
            assert context['project_name'] == 'test-project'
            
            # Clean up
            session_file.unlink()
        else:
            print("❌ Session file not created")
            return False
    
    print("\n✅ All hook improvement tests passed!")
    return True

def test_hook_without_project():
    """Test that the hook correctly handles non-project directories"""
    
    # Use temp directory without .claude
    with tempfile.TemporaryDirectory() as tmpdir:
        # Prepare hook input
        hook_input = {
            "session_id": "test-global-456",
            "cwd": tmpdir,
            "tool_name": "claude-slack.send_message",
            "hook_event_name": "PreToolUse",
            "tool_input": {}
        }
        
        # Run the hook
        hook_path = Path(__file__).parent.parent / "template" / "global" / "hooks" / "slack_pre_tool_use.py"
        
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        
        # Check session file for global context
        session_file = Path.home() / ".claude" / "data" / "claude-slack-sessions" / "test-global-456.json"
        if session_file.exists():
            with open(session_file) as f:
                context = json.load(f)
                
            print("✅ Global context file created")
            print(f"   Scope: {context['scope']}")
            
            assert context['scope'] == 'global'
            assert context['project_id'] is None
            
            # Clean up
            session_file.unlink()
    
    print("✅ Global context test passed!")
    return True

if __name__ == "__main__":
    print("Testing improved PreToolUse hook...")
    print("=" * 50)
    
    # Enable debug mode
    os.environ['CLAUDE_SLACK_DEBUG'] = '1'
    
    test_hook_with_json_input()
    print()
    test_hook_without_project()
    
    print("\n" + "=" * 50)
    print("All tests completed successfully!")