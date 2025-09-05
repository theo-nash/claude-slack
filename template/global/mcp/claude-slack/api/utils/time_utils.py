#!/usr/bin/env python3
"""
Shared timestamp utilities for consistent time handling across the application.

All timestamps are stored as Unix timestamps (float, seconds since epoch) in UTC.
This ensures consistency across SQLite, Qdrant, and all other storage systems.
"""

import time
from datetime import datetime, timezone
from typing import Union, Optional


def now_timestamp() -> float:
    """
    Get current Unix timestamp in UTC.
    
    Returns:
        Float Unix timestamp (seconds since epoch)
    """
    return time.time()


def to_timestamp(dt: Optional[Union[datetime, str, float, int]]) -> Optional[float]:
    """
    Convert various time formats to Unix timestamp.
    
    Args:
        dt: Can be:
            - datetime object (assumed local if naive)
            - ISO string format ("2025-09-04T14:30:00" or "2025-09-04T14:30:00.123456")
            - Unix timestamp (float or int)
            - None
    
    Returns:
        Unix timestamp as float, or None if input is None
    """
    if dt is None:
        return None
    
    # Already a timestamp
    if isinstance(dt, (int, float)):
        return float(dt)
    
    # Parse ISO string
    if isinstance(dt, str):
        # Handle various ISO formats
        try:
            # Try parsing as ISO format
            if 'T' in dt:
                parsed = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            else:
                # SQLite format "YYYY-MM-DD HH:MM:SS"
                parsed = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                # Assume UTC for SQLite timestamps
                parsed = parsed.replace(tzinfo=timezone.utc)
            
            # Convert to timestamp
            return parsed.timestamp()
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Cannot parse timestamp string: {dt}") from e
    
    # datetime object
    if isinstance(dt, datetime):
        # If naive, assume local time
        if dt.tzinfo is None:
            # Get local timezone offset and apply it
            return dt.timestamp()
        else:
            # Timezone-aware, use directly
            return dt.timestamp()
    
    raise TypeError(f"Cannot convert {type(dt)} to timestamp")


def from_timestamp(ts: Optional[float], as_utc: bool = False) -> Optional[datetime]:
    """
    Convert Unix timestamp back to datetime object.
    
    Args:
        ts: Unix timestamp (float)
        as_utc: If True, return as UTC datetime; if False, return as local time
    
    Returns:
        datetime object or None if timestamp is None
    """
    if ts is None:
        return None
    
    if as_utc:
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    else:
        return datetime.fromtimestamp(ts)


def format_timestamp(ts: Optional[float], fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format Unix timestamp as human-readable string.
    
    Args:
        ts: Unix timestamp
        fmt: strftime format string
    
    Returns:
        Formatted string or empty string if timestamp is None
    """
    if ts is None:
        return ""
    
    dt = from_timestamp(ts)
    return dt.strftime(fmt) if dt else ""


def iso_string(ts: Optional[float]) -> Optional[str]:
    """
    Convert Unix timestamp to ISO format string.
    
    Args:
        ts: Unix timestamp
    
    Returns:
        ISO format string or None
    """
    if ts is None:
        return None
    
    dt = from_timestamp(ts, as_utc=True)
    return dt.isoformat() if dt else None


# Convenience functions for filtering
def parse_filter_time(time_value: Optional[Union[datetime, str, float, int]]) -> Optional[float]:
    """
    Parse a time filter value to Unix timestamp.
    Convenience wrapper around to_timestamp for filter operations.
    
    Args:
        time_value: Time value in various formats
    
    Returns:
        Unix timestamp or None
    """
    return to_timestamp(time_value)