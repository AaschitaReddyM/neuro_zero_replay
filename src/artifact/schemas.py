"""Data models and schemas for automation artifacts."""
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class ActionType(str, Enum):
    """Types of actions that can be performed."""
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    EXTRACT = "extract"
    WAIT = "wait"
    SELECT = "select"
    SUBMIT = "submit"
    CONFIRM = "confirm"


class LocationStrategy(str, Enum):
    """Strategies for locating UI elements."""
    ACCESSIBILITY_ROLE = "accessibility_role"
    SEMANTIC_SELECTOR = "semantic_selector"
    TEXT_CONTENT = "text_content"
    TEST_ID = "test_id"
    XPATH = "xpath"
    CSS_SELECTOR = "css_selector"


class ParameterType(str, Enum):
    """Types of parameters for capabilities."""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class ErrorType(str, Enum):
    """Types of errors that can occur during replay."""
    ELEMENT_NOT_FOUND = "element_not_found"
    TIMEOUT = "timeout"
    VALIDATION_ERROR = "validation_error"
    PERMISSION_DENIED = "permission_denied"
    UNEXPECTED_DIALOG = "unexpected_dialog"
    SESSION_EXPIRED = "session_expired"
    BUSINESS_OUTCOME = "business_outcome"


class RiskLevel(str, Enum):
    """Risk levels for actions."""
    SAFE = "safe"
    REVERSIBLE = "reversible"
    RISKY = "risky"
    IRREVERSIBLE = "irreversible"


class TargetLocation(BaseModel):
    """How to locate a target element."""
    strategy: LocationStrategy
    value: str
    role: Optional[str] = None
    name: Optional[str] = None
    fallback_strategies: List[LocationStrategy] = Field(default_factory=list)


class ParameterDefinition(BaseModel):
    """Definition of a capability parameter."""
    type: ParameterType
    description: str
    required: bool = True
    default: Optional[Any] = None


class OutputDefinition(BaseModel):
    """Definition of a capability output."""
    type: ParameterType
    description: str


class ActionStep(BaseModel):
    """A single action step in the automation flow."""
    step_id: int
    action_type: ActionType
    target: TargetLocation
    value: Optional[str] = None
    output_key: Optional[str] = None
    description: str
    wait_after: Optional[int] = None  # milliseconds to wait after action
    risk_level: RiskLevel = RiskLevel.SAFE


class CheckpointCondition(BaseModel):
    """Condition for verifying successful completion."""
    type: str = "element_visible"
    target: TargetLocation
    text_contains: Optional[str] = None


class Checkpoint(BaseModel):
    """Checkpoint for verifying goal completion."""
    step_id: int
    condition: CheckpointCondition
    description: str


class ErrorHandler(BaseModel):
    """Handler for specific error types."""
    error_type: ErrorType
    fallback_strategy: Optional[str] = None
    outcome: Optional[str] = None
    condition: Optional[Dict[str, Any]] = None
    description: str


class ArtifactMetadata(BaseModel):
    """Metadata for the automation artifact."""
    version: str = "1.0"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: Optional[str] = None
    target_app: str
    capability_name: str
    description: str
    tenant_id: Optional[str] = None
    app_version: Optional[str] = None
    author: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    confidence_score: Optional[float] = None  # 0.0 to 1.0


class AutomationArtifact(BaseModel):
    """Complete automation artifact for a capability."""
    metadata: ArtifactMetadata
    parameters: Dict[str, ParameterDefinition]
    outputs: Dict[str, OutputDefinition]
    steps: List[ActionStep]
    checkpoint: Checkpoint
    error_handlers: List[ErrorHandler] = Field(default_factory=list)
    
    def get_parameter_values(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and prepare parameter values."""
        result = {}
        for param_name, param_def in self.parameters.items():
            if param_name not in params:
                if param_def.required:
                    raise ValueError(f"Required parameter '{param_name}' not provided")
                elif param_def.default is not None:
                    result[param_name] = param_def.default
            else:
                result[param_name] = params[param_name]
        return result
    
    def substitute_parameters(self, template: str, params: Dict[str, Any]) -> str:
        """Substitute parameter placeholders in a template string."""
        validated_params = self.get_parameter_values(params)
        result = template
        for key, value in validated_params.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result


class ExecutionResult(BaseModel):
    """Result of executing an automation artifact."""
    success: bool
    outputs: Dict[str, Any] = Field(default_factory=dict)
    business_outcome: Optional[str] = None
    error: Optional[str] = None
    error_step: Optional[int] = None
    execution_time_seconds: float
    steps_completed: int