"""Configuration management for the computer-use automation system."""
import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Centralized configuration for the automation system."""
    
    # LLM Configuration
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    
    # Application Configuration
    TARGET_APP_URL: str = os.getenv("TARGET_APP_URL", "http://localhost:8080")
    MAX_AGENT_STEPS: int = int(os.getenv("MAX_AGENT_STEPS", "20"))
    AGENT_TIMEOUT_SECONDS: int = int(os.getenv("AGENT_TIMEOUT_SECONDS", "300"))
    
    # Safety Configuration
    ALLOWED_DOMAINS: List[str] = os.getenv("ALLOWED_DOMAINS", "localhost,127.0.0.1").split(",")
    ALLOWED_ACTION_TYPES: List[str] = os.getenv("ALLOWED_ACTION_TYPES", "navigate,click,type,extract,wait").split(",")
    RISKY_ACTION_TYPES: List[str] = os.getenv("RISKY_ACTION_TYPES", "submit,confirm").split(",")
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")
    
    # Paths
    EVIDENCE_DIR: str = "evidence"
    ARTIFACT_DIR: str = "evidence/artifacts"
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        # Skip API key validation for demo/testing mode
        # if not cls.OPENAI_API_KEY or cls.OPENAI_API_KEY == "demo_key_placeholder":
        #     raise ValueError("OPENAI_API_KEY is required")
        
        if cls.MAX_AGENT_STEPS <= 0:
            raise ValueError("MAX_AGENT_STEPS must be positive")
        
        if cls.AGENT_TIMEOUT_SECONDS <= 0:
            raise ValueError("AGENT_TIMEOUT_SECONDS must be positive")
        
        # Validate action types against ActionType enum
        from src.artifact.schemas import ActionType
        valid_action_types = [action.value for action in ActionType]
        for action_type in cls.ALLOWED_ACTION_TYPES:
            if action_type not in valid_action_types:
                raise ValueError(f"Invalid action type in ALLOWED_ACTION_TYPES: {action_type}")
        
        for action_type in cls.RISKY_ACTION_TYPES:
            if action_type not in valid_action_types:
                raise ValueError(f"Invalid action type in RISKY_ACTION_TYPES: {action_type}")