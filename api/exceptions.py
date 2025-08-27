"""
Exception classes for Claude-Slack API.
"""


class ClaudeSlackError(Exception):
    """Base exception for all Claude-Slack errors."""
    pass


class StorageError(ClaudeSlackError):
    """Raised when storage operations fail."""
    pass


class QueryError(ClaudeSlackError):
    """Raised when query parsing or execution fails."""
    pass


class ValidationError(ClaudeSlackError):
    """Raised when input validation fails."""
    pass


class ConnectionError(ClaudeSlackError):
    """Raised when database connection fails."""
    pass