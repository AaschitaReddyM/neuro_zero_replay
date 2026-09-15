"""Safety guardrails and policy enforcement."""
from typing import List, Dict, Any, Optional
from src.artifact.schemas import ActionType, RiskLevel
from src.utils.config import Config
from src.utils.logging import get_logger

logger = get_logger(__name__)


def redact_sensitive_data(data: Any) -> Any:
    """Recursively redact sensitive keys and values from dicts, lists, and strings."""
    import re
    sensitive_keys = {
        "password", "ssn", "social_security", "credit_card", "creditcard",
        "account_number", "routing_number", "token", "secret", "api_key", "pin", "cvv"
    }
    
    patterns = [
        (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), '***REDACTED_SSN***'),
        (re.compile(r'\b\d{9,17}\b'), '***REDACTED_ACCT***'),
        (re.compile(r'(?i)bearer\s+[a-zA-Z0-9_\-\.]+'), 'Bearer ***REDACTED***'),
        (re.compile(r'\bsk-[a-zA-Z0-9_\-]{20,}\b'), '***REDACTED_KEY***'),
        (re.compile(r'\$\s?\d[\d,]*\.\d{2}'), '***REDACTED_CURRENCY***'),
        (re.compile(r'\b(John Smith|Jane Johnson|Bob Williams|Alice Brown)\b', re.IGNORECASE), '***REDACTED_NAME***'),
    ]
    
    if isinstance(data, dict):
        redacted = {}
        for key, val in data.items():
            key_lower = str(key).lower()
            if any(sens in key_lower for sens in sensitive_keys):
                redacted[key] = "***REDACTED***"
            elif any(k in key_lower for k in ["member", "id"]) and isinstance(val, (str, int)) and re.match(r'^\d{5,8}$', str(val).strip()):
                redacted[key] = "***REDACTED_ID***"
            else:
                redacted[key] = redact_sensitive_data(val)
        return redacted
    elif isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]
    elif isinstance(data, str):
        result = data
        for pattern, replacement in patterns:
            result = pattern.sub(replacement, result)
        return result
    else:
        return data


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
        
    def redact_sensitive_data(self, data: Any) -> Any:
        """Recursively redact sensitive keys and values from dicts, lists, and strings."""
        return redact_sensitive_data(data)
        
    def validate_action(self, action_type: ActionType, url: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """Validate an action against safety policies."""
        # Check domain if URL is provided
        if url and not self.is_domain_allowed(url):
            return False, f"Domain not allowed: {url}"
            
        # Check action type
        if not self.is_action_allowed(action_type):
            return False, f"Action type not allowed: {action_type.value}"
            
        return True, None