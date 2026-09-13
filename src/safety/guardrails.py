"""Safety guardrails and policy enforcement."""
from typing import List, Dict, Any, Optional
from src.artifact.schemas import ActionType, RiskLevel
from src.utils.config import Config
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SafetyGuardrails:
    """Enforce safety policies and guardrails."""
    
    def __init__(self):
        """Initialize safety guardrails with configuration."""
        self.allowed_domains = Config.ALLOWED_DOMAINS
        self.allowed_action_types = [ActionType(t) for t in Config.ALLOWED_ACTION_TYPES]
        self.risky_action_types = [ActionType(t) for t in Config.RISKY_ACTION_TYPES]
        
    def is_domain_allowed(self, url: str) -> bool:
        """Check if a domain is in the allowlist."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc
        
        # Remove port if present
        if ":" in domain:
            domain = domain.split(":")[0]
            
        is_allowed = any(domain == allowed or domain.endswith(f".{allowed}") 
                       for allowed in self.allowed_domains)
        
        logger.info("Domain check", domain=domain, allowed=is_allowed)
        return is_allowed
        
    def is_action_allowed(self, action_type: ActionType) -> bool:
        """Check if an action type is allowed."""
        is_allowed = action_type in self.allowed_action_types
        logger.info("Action type check", action_type=action_type.value, allowed=is_allowed)
        return is_allowed
        
    def assess_risk(self, action_type: ActionType) -> RiskLevel:
        """Assess the risk level of an action."""
        if action_type in self.risky_action_types:
            return RiskLevel.RISKY
        return RiskLevel.SAFE
        
    def should_require_confirmation(self, action_type: ActionType) -> bool:
        """Determine if an action requires human confirmation."""
        risk = self.assess_risk(action_type)
        return risk in [RiskLevel.RISKY, RiskLevel.IRREVERSIBLE]
        
    def redact_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Redact sensitive data from logs and artifacts."""
        sensitive_keys = [
            "password", "ssn", "social_security", "credit_card", "creditcard",
            "account_number", "routing_number", "token", "secret", "api_key"
        ]
        
        redacted = data.copy()
        for key in sensitive_keys:
            if key in redacted:
                redacted[key] = "***REDACTED***"
                
        return redacted
        
    def validate_action(self, action_type: ActionType, url: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """Validate an action against safety policies."""
        # Check domain if URL is provided
        if url and not self.is_domain_allowed(url):
            return False, f"Domain not allowed: {url}"
            
        # Check action type
        if not self.is_action_allowed(action_type):
            return False, f"Action type not allowed: {action_type.value}"
            
        return True, None