#!/usr/bin/env python3
"""
Database initialization helpers for claude-slack
Provides decorators and context managers for ensuring database is initialized
"""

import functools
from typing import Optional, Any, Callable
from contextlib import asynccontextmanager

class DatabaseInitializer:
    """Mixin class for managers that need database initialization"""
    
    def __init__(self):
        self._db_initialized = False
        self.db_manager = None  # Should be set by the inheriting class
    
    async def _ensure_db_initialized(self):
        """Ensure DatabaseManager is initialized (idempotent)"""
        if not self._db_initialized and self.db_manager:
            await self.db_manager.initialize()
            self._db_initialized = True


def ensure_db_initialized(func: Callable) -> Callable:
    """
    Decorator that ensures database is initialized before running the method.
    Use on async methods of classes that have a db_manager attribute and 
    inherit from DatabaseInitializer.
    """
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        # Ensure the class has the required method
        if hasattr(self, '_ensure_db_initialized'):
            await self._ensure_db_initialized()
        elif hasattr(self, 'db_manager') and hasattr(self.db_manager, 'initialize'):
            # Fallback for classes that don't inherit from DatabaseInitializer
            if not hasattr(self, '_db_initialized'):
                self._db_initialized = False
            if not self._db_initialized:
                await self.db_manager.initialize()
                self._db_initialized = True
        
        # Call the original function
        return await func(self, *args, **kwargs)
    
    return wrapper


@asynccontextmanager
async def initialized_db_manager(db_manager):
    """
    Context manager that ensures a DatabaseManager is initialized.
    
    Usage:
        async with initialized_db_manager(db_manager) as dm:
            await dm.register_agent(...)
    """
    if db_manager:
        await db_manager.initialize()
    try:
        yield db_manager
    finally:
        # Could add cleanup here if needed
        pass


class LazyDatabaseManager:
    """
    Wrapper for DatabaseManager that initializes on first use.
    
    Usage:
        lazy_db = LazyDatabaseManager(db_path)
        # No initialization happens yet
        
        await lazy_db.register_agent(...)  # Initializes here on first call
    """
    
    def __init__(self, db_path: str):
        from db.manager import DatabaseManager
        self._db_manager = DatabaseManager(db_path)
        self._initialized = False
    
    async def _ensure_initialized(self):
        """Initialize if not already done"""
        if not self._initialized:
            await self._db_manager.initialize()
            self._initialized = True
    
    def __getattr__(self, name):
        """Proxy all attribute access to the wrapped DatabaseManager"""
        attr = getattr(self._db_manager, name)
        
        # If it's an async method, wrap it with initialization
        if asyncio.iscoroutinefunction(attr):
            @functools.wraps(attr)
            async def wrapper(*args, **kwargs):
                await self._ensure_initialized()
                return await attr(*args, **kwargs)
            return wrapper
        
        return attr


# Import asyncio only when needed to avoid circular imports
import asyncio