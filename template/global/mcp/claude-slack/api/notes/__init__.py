"""
Notes management for claude-slack

Provides functionality for agents to write and search private notes.
Notes are implemented as private single-member channels in the unified system.
"""

from .manager import NotesManager

__all__ = ['NotesManager']