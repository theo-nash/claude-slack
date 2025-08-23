#!/usr/bin/env python3
"""
Tests for Agent Discovery functionality
Tests the agent_discovery view and related methods
"""

import asyncio
import os
import sys
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'template', 'global', 'mcp', 'claude-slack'))

from db.manager_v3 import DatabaseManagerV3

class TestAgentDiscovery:
    """Test agent discovery functionality"""
    
    def __init__(self):
        self.test_dir = None
        self.db_path = None
        self.db = None
    
    async def setup(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp(prefix='agent_discovery_test_')
        self.db_path = os.path.join(self.test_dir, 'test.db')
        
        # Initialize database
        self.db = DatabaseManagerV3(self.db_path)
        await self.db.initialize()
        
        # Create test projects
        await self.db.register_project('proj_web', '/projects/web', 'Web Project')
        await self.db.register_project('proj_api', '/projects/api', 'API Project')
        await self.db.register_project('proj_ml', '/projects/ml', 'ML Project')
        await self.db.register_project('proj_isolated', '/projects/isolated', 'Isolated Project')
        
        # Link web and api projects
        await self._create_project_link('proj_web', 'proj_api')
        
        # Create test agents with various configurations
        # Global agents
        await self.db.register_agent('alice', None, 'Alice Global', 
                                    dm_policy='open', discoverable='public')
        await self.db.register_agent('bob', None, 'Bob Global', 
                                    dm_policy='restricted', discoverable='public')
        
        # Project agents with different discoverability
        await self.db.register_agent('charlie', 'proj_web', 'Charlie Web Dev',
                                    dm_policy='open', discoverable='project')
        await self.db.register_agent('diana', 'proj_api', 'Diana API Dev',
                                    dm_policy='open', discoverable='project')
        await self.db.register_agent('eve', 'proj_ml', 'Eve ML Engineer',
                                    dm_policy='closed', discoverable='public')
        await self.db.register_agent('frank', 'proj_isolated', 'Frank Isolated',
                                    dm_policy='open', discoverable='private')
        
        print(f"✅ Test environment created with 6 agents across 4 projects")
    
    async def _create_project_link(self, proj1: str, proj2: str):
        """Helper to create project link"""
        # Ensure consistent ordering for the link
        if proj1 > proj2:
            proj1, proj2 = proj2, proj1
        
        # Use aconnect directly
        from db.db_helpers import aconnect
        async with aconnect(self.db_path, writer=True) as conn:
            await conn.execute("""
                INSERT OR REPLACE INTO project_links 
                (project_a_id, project_b_id, link_type, enabled)
                VALUES (?, ?, 'bidirectional', TRUE)
            """, (proj1, proj2))
    
    async def teardown(self):
        """Clean up test environment"""
        if self.db:
            await self.db.close()
        
        if self.test_dir and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        
        print("✅ Test environment cleaned up")
    
    async def test_global_agent_discovery(self):
        """Test discovery from a global agent's perspective"""
        print("\n🧪 Testing global agent discovery...")
        
        # Alice (global, public, open) should see most agents
        # Include unavailable to see Eve (who has closed policy)
        alice_discoverable = await self.db.get_discoverable_agents('alice', None, include_unavailable=True)
        alice_names = {a['name'] for a in alice_discoverable}
        
        # Should see all public agents
        assert 'bob' in alice_names, "Should see other global public agent"
        assert 'eve' in alice_names, "Should see public project agent (even with closed DM)"
        
        # Should see project-scoped agents (global can discover project agents)
        assert 'charlie' in alice_names, "Global should see project-scoped agent"
        assert 'diana' in alice_names, "Global should see project-scoped agent"
        
        # Should NOT see private agents
        assert 'frank' not in alice_names, "Should not see private agent"
        
        print(f"  ✅ Alice (global) can discover {len(alice_discoverable)} agents")
        
        # Check DM availability
        for agent in alice_discoverable:
            if agent['name'] == 'bob':
                assert agent['dm_availability'] == 'requires_permission', "Bob has restricted policy"
            elif agent['name'] == 'eve':
                assert agent['dm_availability'] == 'unavailable', "Eve has closed policy"
            elif agent['name'] in ['charlie', 'diana']:
                assert agent['dm_availability'] == 'available', "Open policy agents available"
        
        print("  ✅ DM availability correctly determined")
        
        return True
    
    async def test_project_agent_discovery(self):
        """Test discovery from a project agent's perspective"""
        print("\n🧪 Testing project agent discovery...")
        
        # Charlie (proj_web, project-scoped, open) perspective
        # Include unavailable to see Eve (who has closed policy)
        charlie_discoverable = await self.db.get_discoverable_agents('charlie', 'proj_web', include_unavailable=True)
        charlie_names = {a['name'] for a in charlie_discoverable}
        
        # Should see public agents
        assert 'alice' in charlie_names, "Should see public global agent"
        assert 'bob' in charlie_names, "Should see public global agent"
        assert 'eve' in charlie_names, "Should see public project agent"
        
        # Should see linked project agent (web linked to api)
        assert 'diana' in charlie_names, "Should see agent from linked project"
        
        # Should NOT see unlinked project agents or private agents
        assert 'frank' not in charlie_names, "Should not see private agent"
        
        print(f"  ✅ Charlie (proj_web) can discover {len(charlie_discoverable)} agents")
        
        # Diana (proj_api) should also see Charlie (bidirectional link)
        diana_discoverable = await self.db.get_discoverable_agents('diana', 'proj_api')
        diana_names = {a['name'] for a in diana_discoverable}
        assert 'charlie' in diana_names, "Linked projects work bidirectionally"
        
        print("  ✅ Linked project discovery works bidirectionally")
        
        return True
    
    async def test_isolated_project_discovery(self):
        """Test discovery from an isolated project"""
        print("\n🧪 Testing isolated project discovery...")
        
        # Frank is private, but let's create another agent in isolated project
        await self.db.register_agent('greg', 'proj_isolated', 'Greg Isolated',
                                    dm_policy='open', discoverable='project')
        
        greg_discoverable = await self.db.get_discoverable_agents('greg', 'proj_isolated', include_unavailable=True)
        greg_names = {a['name'] for a in greg_discoverable}
        
        # Should only see public agents
        assert 'alice' in greg_names, "Should see public global agent"
        assert 'bob' in greg_names, "Should see public global agent"
        assert 'eve' in greg_names, "Should see public agent"
        
        # Should NOT see project-scoped agents from other projects
        assert 'charlie' not in greg_names, "Should not see unlinked project agent"
        assert 'diana' not in greg_names, "Should not see unlinked project agent"
        
        # Should not see frank (private)
        assert 'frank' not in greg_names, "Should not see private agent in same project"
        
        print(f"  ✅ Greg (isolated project) can only discover {len(greg_discoverable)} public agents")
        
        return True
    
    async def test_dm_permissions_affect_availability(self):
        """Test that DM permissions affect availability but not discovery"""
        print("\n🧪 Testing DM permissions and availability...")
        
        # Set up some DM permissions
        # Bob (restricted) allows Alice
        await self.db.set_dm_permission('bob', None, 'alice', None, 'allow')
        
        # Charlie blocks Alice
        await self.db.set_dm_permission('charlie', 'proj_web', 'alice', None, 'block')
        
        # Get Alice's discoverable agents again
        alice_discoverable = await self.db.get_discoverable_agents('alice', None)
        
        for agent in alice_discoverable:
            if agent['name'] == 'bob':
                assert agent['dm_availability'] == 'available', "Bob now allows Alice"
                print("  ✅ Restricted agent with allow permission shows as available")
            elif agent['name'] == 'charlie':
                assert agent['dm_availability'] == 'blocked', "Charlie blocked Alice"
                print("  ✅ Open agent with block shows as blocked")
        
        return True
    
    async def test_existing_dm_detection(self):
        """Test that existing DM channels are detected"""
        print("\n🧪 Testing existing DM detection...")
        
        # Create a DM channel between Alice and Diana (not blocked)
        dm_channel = await self.db.create_or_get_dm_channel(
            'alice', None, 'diana', 'proj_api'
        )
        assert dm_channel is not None
        
        # Get Alice's discoverable agents
        alice_discoverable = await self.db.get_discoverable_agents('alice', None)
        
        for agent in alice_discoverable:
            if agent['name'] == 'diana':
                assert agent['has_existing_dm'], "Should detect existing DM"
                print("  ✅ Existing DM channel detected")
                break
        else:
            assert False, "Diana should be in Alice's discoverable list"
        
        # Verify ordering - existing DMs should come first
        if len(alice_discoverable) > 1:
            first_agent = alice_discoverable[0]
            if first_agent['name'] == 'diana':
                print("  ✅ Existing DMs sorted first")
        
        return True
    
    async def test_check_specific_discovery(self):
        """Test checking if specific agent pairs can discover each other"""
        print("\n🧪 Testing specific agent discovery checks...")
        
        # Alice (global, public) can discover Charlie (project, project-scoped)
        can_discover = await self.db.check_can_discover_agent(
            'alice', None, 'charlie', 'proj_web'
        )
        assert can_discover, "Global agent should discover project agent"
        print("  ✅ Global → Project discovery works")
        
        # Charlie can discover Alice (public)
        can_discover = await self.db.check_can_discover_agent(
            'charlie', 'proj_web', 'alice', None
        )
        assert can_discover, "Project agent should discover public global agent"
        print("  ✅ Project → Global (public) discovery works")
        
        # Charlie cannot discover Frank (private)
        can_discover = await self.db.check_can_discover_agent(
            'charlie', 'proj_web', 'frank', 'proj_isolated'
        )
        assert not can_discover, "Should not discover private agent"
        print("  ✅ Private agents not discoverable")
        
        # Charlie can discover Diana (linked project)
        can_discover = await self.db.check_can_discover_agent(
            'charlie', 'proj_web', 'diana', 'proj_api'
        )
        assert can_discover, "Should discover agent from linked project"
        print("  ✅ Linked project discovery works")
        
        return True
    
    async def test_include_unavailable_filter(self):
        """Test the include_unavailable parameter"""
        print("\n🧪 Testing unavailable agent filtering...")
        
        # Without including unavailable (default)
        alice_available = await self.db.get_discoverable_agents(
            'alice', None, include_unavailable=False
        )
        alice_available_names = {a['name'] for a in alice_available}
        
        # Eve has closed policy, should not be included
        assert 'eve' not in alice_available_names, "Closed policy agent excluded by default"
        
        # With including unavailable
        alice_all = await self.db.get_discoverable_agents(
            'alice', None, include_unavailable=True
        )
        alice_all_names = {a['name'] for a in alice_all}
        
        # Eve should now be included
        assert 'eve' in alice_all_names, "Closed policy agent included when requested"
        
        print(f"  ✅ Filter works: {len(alice_available)} available, {len(alice_all)} total")
        
        return True
    
    async def run_all_tests(self):
        """Run all tests"""
        print("=" * 60)
        print("Agent Discovery Tests")
        print("=" * 60)
        
        try:
            await self.setup()
            
            # Run tests
            results = []
            results.append(await self.test_global_agent_discovery())
            results.append(await self.test_project_agent_discovery())
            results.append(await self.test_isolated_project_discovery())
            results.append(await self.test_dm_permissions_affect_availability())
            results.append(await self.test_existing_dm_detection())
            results.append(await self.test_check_specific_discovery())
            results.append(await self.test_include_unavailable_filter())
            
            # Summary
            print("\n" + "=" * 60)
            print("Test Summary")
            print("=" * 60)
            
            total = len(results)
            passed = sum(1 for r in results if r)
            
            if passed == total:
                print(f"✅ All {total} tests passed!")
                return True
            else:
                print(f"❌ {passed}/{total} tests passed")
                return False
            
        finally:
            await self.teardown()

async def main():
    """Main test runner"""
    tester = TestAgentDiscovery()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    asyncio.run(main())