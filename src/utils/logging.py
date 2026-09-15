"""Logging utilities for the computer-use automation system."""
import logging
import structlog
from pathlib import Path
from typing import Any
from src.utils.config import Config


def redaction_processor(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Structlog processor that recursively redacts sensitive PII from all log events."""
    try:
        from src.safety.guardrails import redact_sensitive_data
        return redact_sensitive_data(event_dict)
    except Exception:
        return event_dict


def setup_logging() -> structlog.stdlib.BoundLogger:
    """Configure structured logging for the application."""
    # Ensure log directory exists
    log_dir = Path(Config.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, Config.LOG_LEVEL.upper()),
    )
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            redaction_processor,
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    return structlog.get_logger()


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a logger instance with the specified name."""
    return structlog.get_logger(name)