#!/usr/bin/env python3
"""
Database connection helpers for claude-slack
Provides decorators for automatic connection management
"""

import functools
import sqlite3
import aiosqlite
from contextlib import asynccontextmanager, contextmanager


@asynccontextmanager
async def aconnect(db_path: str, writer: bool = False):
    """
    Asynchronous database connection context manager.
    
    Args:
        db_path: Path to SQLite database
        writer: If True, commits changes on exit
    """
    conn = await aiosqlite.connect(db_path)
    try:
        # Enable WAL mode for better concurrency
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA foreign_keys=ON")
        
        yield conn
        
        if writer:
            await conn.commit()
    except Exception:
        if writer:
            await conn.rollback()
        raise
    finally:
        await conn.close()


@contextmanager
def connect(db_path: str, writer: bool = False):
    """
    Synchronous database connection context manager.
    
    Args:
        db_path: Path to SQLite database
        writer: If True, commits changes on exit
    """
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    try:
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        
        yield conn
        
        if writer:
            conn.commit()
    except Exception:
        if writer:
            conn.rollback()
        raise
    finally:
        conn.close()


def with_connection(writer: bool = False):
    """
    Decorator that provides a database connection to the decorated method.
    
    Args:
        writer: If True, commits changes after successful execution
    """
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(self, *args, **kwargs):
            async with aconnect(self.db_path, writer=writer) as conn:
                return await fn(self, conn, *args, **kwargs)
        return wrapper
    return decorator