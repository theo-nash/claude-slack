"""
Ranking profiles for search result scoring.
"""

from dataclasses import dataclass


@dataclass
class RankingProfile:
    """
    Ranking parameters for search result scoring.
    
    Attributes:
        decay_half_life_hours: Time for recency score to drop by half
        decay_weight: Weight for time decay in final score
        similarity_weight: Weight for semantic similarity in final score
        confidence_weight: Weight for confidence score in final score
    """
    decay_half_life_hours: float = 168  # 1 week default
    decay_weight: float = 0.33
    similarity_weight: float = 0.34
    confidence_weight: float = 0.33


class RankingProfiles:
    """Pre-defined ranking profiles for common use cases."""
    
    RECENT_PRIORITY = RankingProfile(
        decay_half_life_hours=24,  # 1 day half-life
        decay_weight=0.6,
        similarity_weight=0.3,
        confidence_weight=0.1
    )
    """Prioritize recent messages (good for debugging, current status)"""
    
    QUALITY_PRIORITY = RankingProfile(
        decay_half_life_hours=720,  # 30 days half-life
        decay_weight=0.1,
        similarity_weight=0.4,
        confidence_weight=0.5
    )
    """Prioritize high-confidence messages (good for proven solutions)"""
    
    BALANCED = RankingProfile(
        decay_half_life_hours=168,  # 1 week half-life
        decay_weight=0.33,
        similarity_weight=0.34,
        confidence_weight=0.33
    )
    """Balanced weighting of all factors (default)"""
    
    SIMILARITY_ONLY = RankingProfile(
        decay_half_life_hours=8760,  # 1 year (minimal decay)
        decay_weight=0.0,
        similarity_weight=1.0,
        confidence_weight=0.0
    )
    """Pure semantic similarity (good for exact topic match)"""
    
    @classmethod
    def get_profile(cls, name: str) -> RankingProfile:
        """
        Get a named ranking profile.
        
        Args:
            name: Profile name ('recent', 'quality', 'balanced', 'similarity')
            
        Returns:
            RankingProfile instance
        """
        profiles = {
            'recent': cls.RECENT_PRIORITY,
            'quality': cls.QUALITY_PRIORITY,
            'balanced': cls.BALANCED,
            'similarity': cls.SIMILARITY_ONLY
        }
        return profiles.get(name.lower(), cls.BALANCED)