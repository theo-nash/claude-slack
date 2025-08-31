#!/usr/bin/env python3
"""
Tests for HybridStore - v4 semantic search functionality.
Tests dual storage (SQLite + ChromaDB) and intelligent ranking.
"""

import pytest
import pytest_asyncio
import tempfile
import os
import sys
import json
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Add parent directory to path
test_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, test_dir)
sys.path.insert(0, os.path.join(test_dir, 'template/global/mcp/claude-slack'))

# Import with graceful fallback if dependencies missing
try:
    from db.hybrid_store import HybridStore, RankingProfiles, RankingProfile
    from db.manager import DatabaseManager
    HYBRID_AVAILABLE = True
except ImportError as e:
    HYBRID_AVAILABLE = False
    skip_reason = f"HybridStore not available: {e}"


@pytest.mark.skipif(not HYBRID_AVAILABLE, reason="HybridStore dependencies not installed")
class TestHybridStore:
    """Test the HybridStore dual storage system."""
    
    @pytest_asyncio.fixture
    async def hybrid_store(self):
        """Create a HybridStore instance with temp storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            chroma_path = os.path.join(tmpdir, 'chroma')
            
            # Initialize database with schema
            db_manager = DatabaseManager(db_path, enable_hybrid_store=False)
            await db_manager.initialize()
            await db_manager.close()
            
            # Create HybridStore
            store = HybridStore(db_path, chroma_path)
            yield store
            store.close()
    
    @pytest.mark.asyncio
    async def test_store_and_retrieve_message(self, hybrid_store):
        """Test basic message storage and retrieval."""
        # Store a message
        message_id = await hybrid_store.store_message(
            channel_id="test:channel",
            sender_id="test_agent",
            content="This is a test message about Python programming",
            metadata={"type": "message", "topic": "python"},
            confidence=0.8
        )
        
        assert message_id > 0
        
        # Retrieve the message
        message = await hybrid_store.get_message(message_id)
        assert message is not None
        assert message['content'] == "This is a test message about Python programming"
        assert message['confidence'] == 0.8
        assert message['metadata']['type'] == "message"
    
    @pytest.mark.asyncio
    async def test_semantic_search(self, hybrid_store):
        """Test semantic similarity search."""
        # Store several messages
        await hybrid_store.store_message(
            channel_id="test:channel",
            sender_id="agent1",
            content="Python is a great programming language for data science",
            metadata={"type": "message"},
            confidence=0.9
        )
        
        await hybrid_store.store_message(
            channel_id="test:channel",
            sender_id="agent2",
            content="JavaScript is popular for web development",
            metadata={"type": "message"},
            confidence=0.85
        )
        
        await hybrid_store.store_message(
            channel_id="test:channel",
            sender_id="agent3",
            content="Machine learning with Python and scikit-learn",
            metadata={"type": "message"},
            confidence=0.95
        )
        
        # Search for Python-related content
        results = await hybrid_store.search(
            query="Python programming and data analysis",
            limit=2
        )
        
        assert len(results) > 0
        assert len(results) <= 2
        
        # First result should be Python-related
        assert "Python" in results[0]['content']
        assert 'search_scores' in results[0]
        assert 'similarity' in results[0]['search_scores']
        assert results[0]['search_scores']['similarity'] > 0.5
    
    @pytest.mark.asyncio
    async def test_ranking_profiles(self, hybrid_store):
        """Test different ranking profiles."""
        # Store messages with different ages and confidence
        now = datetime.now()
        
        # Old high-confidence message
        await asyncio.sleep(0.1)  # Ensure different timestamps
        msg1 = await hybrid_store.store_message(
            channel_id="test:channel",
            sender_id="agent1",
            content="Important decision about authentication",
            metadata={"type": "decision"},
            confidence=0.95
        )
        
        # Recent low-confidence message
        await asyncio.sleep(0.1)
        msg2 = await hybrid_store.store_message(
            channel_id="test:channel",
            sender_id="agent2",
            content="Maybe we should consider authentication",
            metadata={"type": "message"},
            confidence=0.3
        )
        
        # Test QUALITY_PRIORITY profile (favors confidence)
        results = await hybrid_store.search(
            query="authentication",
            ranking_profile=RankingProfiles.QUALITY_PRIORITY,
            limit=2
        )
        
        assert len(results) >= 1  # Should find at least one result
        if len(results) >= 2:
            # High confidence should rank higher despite being older
            assert results[0]['confidence'] > results[1]['confidence']
        
        # Test RECENT_PRIORITY profile (favors recency)
        results = await hybrid_store.search(
            query="authentication",
            ranking_profile=RankingProfiles.RECENT_PRIORITY,
            limit=2
        )
        
        assert len(results) >= 1  # Should find at least one result
        if len(results) >= 2:
            # Check that recency is prioritized - the most recent message
            # should have higher recency score
            assert results[0]['search_scores']['recency'] >= results[1]['search_scores']['recency']
    
    @pytest.mark.asyncio
    async def test_time_decay(self, hybrid_store):
        """Test time decay in ranking."""
        # Create custom profile with longer half-life to avoid overflow
        profile = RankingProfile(
            decay_half_life_hours=1.0,  # 1 hour half-life
            decay_weight=0.8,  # Heavy weight on recency
            similarity_weight=0.1,
            confidence_weight=0.1
        )
        
        # Store two similar messages
        old_msg = await hybrid_store.store_message(
            channel_id="test:channel",
            sender_id="agent1",
            content="Testing time decay functionality",
            confidence=0.8
        )
        
        # Wait to ensure different timestamp
        await asyncio.sleep(1.0)  # Wait 1 second for clear difference
        
        recent_msg = await hybrid_store.store_message(
            channel_id="test:channel",
            sender_id="agent2",
            content="Testing time decay functionality",
            confidence=0.8
        )
        
        # Search with custom profile
        results = await hybrid_store.search(
            query="time decay",
            ranking_profile=profile,
            limit=2
        )
        
        assert len(results) >= 1  # Should find at least one result
        if len(results) >= 2:
            # With high decay weight, more recent should score higher
            # Check recency scores rather than IDs
            assert results[0]['search_scores']['recency'] >= results[1]['search_scores']['recency']
            # The first result should have lower age
            assert results[0]['search_scores']['age_hours'] <= results[1]['search_scores']['age_hours']
    
    @pytest.mark.asyncio
    async def test_filter_search(self, hybrid_store):
        """Test searching with filters."""
        # Store messages in different channels with different types
        await hybrid_store.store_message(
            channel_id="notes:agent1",
            sender_id="agent1",
            content="Reflection on implementing authentication",
            metadata={"type": "reflection"},
            confidence=0.9
        )
        
        await hybrid_store.store_message(
            channel_id="global:general",
            sender_id="agent2",
            content="Discussion about authentication",
            metadata={"type": "message"},
            confidence=0.7
        )
        
        await hybrid_store.store_message(
            channel_id="notes:agent1",
            sender_id="agent1",
            content="Another reflection on testing",
            metadata={"type": "reflection"},
            confidence=0.85
        )
        
        # Filter by channel
        results = await hybrid_store.search(
            query="authentication",
            channel_ids=["notes:agent1"],
            limit=10
        )
        
        assert all(r['channel_id'] == "notes:agent1" for r in results)
        
        # Filter by message type
        results = await hybrid_store.search(
            query="authentication reflection",
            message_type="reflection",
            limit=10
        )
        
        assert all(r['metadata'].get('type') == "reflection" for r in results)
        
        # Filter by confidence
        results = await hybrid_store.search(
            query="authentication",
            min_confidence=0.8,
            limit=10
        )
        
        assert all(r.get('confidence', 0) >= 0.8 for r in results)
    
    @pytest.mark.asyncio
    async def test_reflection_with_breadcrumbs(self, hybrid_store):
        """Test storing and searching reflections with breadcrumbs."""
        reflection_content = """
        Successfully implemented JWT authentication for the API.
        The solution uses RS256 for signing and includes refresh tokens.
        Key decisions: stateless auth, 15-minute access token expiry.
        """
        
        breadcrumbs = {
            "files": ["src/auth.py:45-120", "tests/test_auth.py:200-250"],
            "commits": ["abc123def", "789ghi012"],
            "decisions": ["use-jwt", "stateless-auth", "short-expiry"],
            "patterns": ["middleware", "decorator", "factory"]
        }
        
        # Store reflection
        msg_id = await hybrid_store.store_message(
            channel_id="notes:backend-engineer",
            sender_id="backend-engineer",
            content=reflection_content,
            metadata={
                "type": "reflection",
                "breadcrumbs": breadcrumbs,
                "session_context": "auth-implementation",
                "outcome": "success"
            },
            confidence=0.9
        )
        
        # Search for related content
        results = await hybrid_store.search(
            query="JWT refresh token implementation",
            message_type="reflection",
            limit=5
        )
        
        assert len(results) > 0
        assert results[0]['id'] == msg_id
        assert results[0]['metadata']['breadcrumbs'] == breadcrumbs
        assert results[0]['metadata']['outcome'] == "success"
    
    @pytest.mark.asyncio
    async def test_pure_filter_search_no_query(self, hybrid_store):
        """Test filter-only search without semantic query."""
        # Store several messages
        for i in range(5):
            await hybrid_store.store_message(
                channel_id="test:channel",
                sender_id=f"agent{i}",
                content=f"Message {i} with different content",
                metadata={"type": "message" if i % 2 == 0 else "reflection"},
                confidence=0.5 + i * 0.1
            )
        
        # Search without query - just filters
        results = await hybrid_store.search(
            query=None,  # No semantic search
            message_type="reflection",
            min_confidence=0.6,
            limit=10
        )
        
        assert all(r['metadata'].get('type') == "reflection" for r in results)
        assert all(r.get('confidence', 0) >= 0.6 for r in results)


@pytest.mark.skipif(not HYBRID_AVAILABLE, reason="HybridStore dependencies not installed")
class TestDatabaseManagerIntegration:
    """Test DatabaseManager integration with HybridStore."""
    
    @pytest_asyncio.fixture
    async def db_with_hybrid(self):
        """Create DatabaseManager with HybridStore enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            manager = DatabaseManager(db_path, enable_hybrid_store=True)
            await manager.initialize()
            
            # Setup just like other tests - register agent first
            await manager.register_agent("test_agent", None, "Test Agent")
            
            # Create channel
            channel_id = await manager.create_channel(
                channel_id="test:semantic",
                channel_type="channel",
                access_type="open",
                scope="global",
                name="test-semantic",
                description="Test semantic search"
            )
            
            # Add agent to channel
            await manager.add_channel_member(channel_id, "test_agent", None)
            
            yield manager
            await manager.close()
    
    @pytest.mark.asyncio
    async def test_semantic_search_through_manager(self, db_with_hybrid):
        """Test semantic search through DatabaseManager."""
        if not db_with_hybrid.has_semantic_search():
            pytest.skip("Semantic search not available")
        
        # Send messages through manager (will dual-write to HybridStore)
        await db_with_hybrid.send_message(
            channel_id="test:semantic",
            sender_id="test_agent",
            sender_project_id=None,
            content="Python is excellent for machine learning",
            metadata={"confidence": 0.9, "type": "statement"}
        )
        
        await db_with_hybrid.send_message(
            channel_id="test:semantic",
            sender_id="test_agent",
            sender_project_id=None,
            content="JavaScript dominates web development",
            metadata={"confidence": 0.85, "type": "statement"}
        )
        
        # Search with semantic query
        results = await db_with_hybrid.search_messages(
            agent_name="test_agent",
            agent_project_id=None,
            query="Python data science and AI",
            semantic_search=True,
            ranking_profile="balanced",
            limit=2
        )
        
        assert len(results) > 0
        assert "Python" in results[0]['content']
        assert 'search_scores' in results[0]
    
    @pytest.mark.asyncio
    async def test_fallback_to_fts(self, db_with_hybrid):
        """Test fallback to FTS when semantic search disabled."""
        # Send a message
        await db_with_hybrid.send_message(
            channel_id="test:semantic",
            sender_id="test_agent",
            sender_project_id=None,
            content="Testing fallback to full text search"
        )
        
        # Search with semantic disabled
        results = await db_with_hybrid.search_messages(
            agent_name="test_agent",
            agent_project_id=None,
            query="fallback",
            semantic_search=False,  # Force FTS
            limit=10
        )
        
        # Should still find results using FTS
        assert len(results) > 0
        assert "fallback" in results[0]['content'].lower()
        # FTS results won't have search_scores with similarity
        if 'search_scores' in results[0]:
            assert 'similarity' not in results[0]['search_scores']
    
    @pytest.mark.asyncio 
    async def test_confidence_extraction(self, db_with_hybrid):
        """Test confidence extraction from metadata."""
        # Send message with confidence in metadata
        msg_id = await db_with_hybrid.send_message(
            channel_id="test:semantic",
            sender_id="test_agent",
            sender_project_id=None,
            content="High confidence statement",
            metadata={"confidence": 0.95, "type": "decision"}
        )
        
        # Verify confidence was extracted and stored
        if db_with_hybrid.has_semantic_search():
            results = await db_with_hybrid.search_messages(
                agent_name="test_agent",
                agent_project_id=None,
                query="confidence",
                min_confidence=0.9,
                limit=10
            )
            
            assert len(results) > 0
            assert results[0]['confidence'] == 0.95


class TestRankingProfiles:
    """Test ranking profile configurations."""
    
    def test_predefined_profiles(self):
        """Test pre-defined ranking profiles."""
        assert RankingProfiles.RECENT_PRIORITY.decay_weight == 0.6
        assert RankingProfiles.QUALITY_PRIORITY.confidence_weight == 0.5
        assert RankingProfiles.BALANCED.decay_weight == 0.33
        assert RankingProfiles.SIMILARITY_ONLY.similarity_weight == 1.0
    
    def test_get_profile_by_name(self):
        """Test getting profiles by name."""
        recent = RankingProfiles.get_profile('recent')
        assert recent.decay_weight == 0.6
        
        quality = RankingProfiles.get_profile('quality')
        assert quality.confidence_weight == 0.5
        
        # Default to balanced for unknown
        unknown = RankingProfiles.get_profile('unknown')
        assert unknown.decay_weight == 0.33


if __name__ == "__main__":
    pytest.main([__file__, "-v"])