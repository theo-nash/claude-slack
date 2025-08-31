"""
Configuration helpers for Claude-Slack API.
Supports environment variables for easy deployment configuration.
"""

import os
from typing import Optional, Dict, Any


class Config:
    """
    Configuration helper that reads from environment variables.
    
    Environment variables:
        CLAUDE_SLACK_DB_PATH: SQLite database path
        QDRANT_PATH: Local Qdrant storage path
        QDRANT_URL: Qdrant server URL (Docker or cloud)
        QDRANT_API_KEY: Qdrant API key (for cloud)
        QDRANT_COLLECTION: Collection name (default: messages)
        EMBEDDING_MODEL: Sentence transformer model (default: all-MiniLM-L6-v2)
    """
    
    @staticmethod
    def from_env() -> Dict[str, Any]:
        """
        Create configuration from environment variables.
        
        Returns:
            Dict with configuration parameters for ClaudeSlackAPI
            
        Example:
            from api import ClaudeSlackAPI
            from api.config import Config
            
            config = Config.from_env()
            api = ClaudeSlackAPI(**config)
        """
        config = {
            "db_path": os.getenv(
                "CLAUDE_SLACK_DB_PATH", 
                os.path.expanduser("~/.claude/claude-slack/data/claude-slack.db")
            ),
            "collection_name": os.getenv("QDRANT_COLLECTION", "messages"),
            "embedding_model": os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        }
        
        # Determine Qdrant configuration
        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_api_key = os.getenv("QDRANT_API_KEY")
        qdrant_path = os.getenv("QDRANT_PATH")
        
        if qdrant_url:
            config["qdrant_url"] = qdrant_url
            if qdrant_api_key:
                config["qdrant_api_key"] = qdrant_api_key
        elif qdrant_path:
            config["qdrant_path"] = qdrant_path
        # else: will use default ./qdrant_data
        
        return config
    
    @staticmethod
    def for_docker(host: str = "localhost", port: int = 6333) -> Dict[str, Any]:
        """
        Configuration for Docker deployment.
        
        Args:
            host: Docker host (default: localhost)
            port: Qdrant port (default: 6333)
            
        Returns:
            Configuration dict for Docker setup
        """
        return {
            "db_path": os.path.expanduser("~/.claude/claude-slack/data/claude-slack.db"),
            "qdrant_url": f"http://{host}:{port}",
            "collection_name": "messages"
        }
    
    @staticmethod
    def for_cloud(url: str, api_key: str) -> Dict[str, Any]:
        """
        Configuration for Qdrant Cloud.
        
        Args:
            url: Qdrant Cloud URL
            api_key: API key
            
        Returns:
            Configuration dict for cloud setup
        """
        return {
            "db_path": os.path.expanduser("~/.claude/claude-slack/data/claude-slack.db"),
            "qdrant_url": url,
            "qdrant_api_key": api_key,
            "collection_name": "messages"
        }
    
    @staticmethod
    def for_local(qdrant_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Configuration for local file storage.
        
        Args:
            qdrant_path: Path to Qdrant storage (default: ./qdrant_data)
            
        Returns:
            Configuration dict for local setup
        """
        config = {
            "db_path": os.path.expanduser("~/.claude/claude-slack/data/claude-slack.db"),
            "collection_name": "messages"
        }
        
        if qdrant_path:
            config["qdrant_path"] = qdrant_path
            
        return config