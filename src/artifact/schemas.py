"""Data models and schemas for automation artifacts."""
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from datetime import datetime, timezone
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


class ExecutionStatus(str, Enum):
    """Disjoint terminal execution states for replay."""
    SUCCESS = "success"
    BUSINESS_OUTCOME = "business_outcome"
    FAILURE = "failure"
    NEEDS_CONFIRMATION = "needs_confirmation"


class BusinessOutcomeRule(BaseModel):
    """Rule to detect a domain business outcome from page-visible state."""
    outcome: str
    selector: str
    text_contains: str
    description: Optional[str] = None


class TargetLocation(BaseModel):
    """How to locate a target element."""
    strategy: LocationStrategy
    value: str
    role: Optional[str] = None
    name: Optional[str] = None
    fallback_strategies: List[LocationStrategy] = Field(default_factory=list)
    resolved_strategy: Optional[str] = None


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
    extract: Optional[Dict[str, Any]] = None


class CheckpointCondition(BaseModel):
    """Condition for verifying successful completion."""
    type: str = "element_visible"
    target: TargetLocation
    text_contains: Optional[str] = None


class ActionStep(BaseModel):
    """A single action step in the automation flow."""
    step_id: int
    action_type: ActionType
    target: TargetLocation
    value: Optional[str] = None
    output_key: Optional[str] = None
    regex: Optional[str] = None
    description: str
    wait_after: Optional[int] = None  # milliseconds to wait after action
    risk_level: RiskLevel = RiskLevel.SAFE
    postcondition: Optional[CheckpointCondition] = None


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
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None
    target_app: str
    capability_name: str
    description: str
    tenant_id: Optional[str] = None
    app_version: Optional[str] = None
    author: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    confidence_score: Optional[float] = None  # 0.0 to 1.0


class RunOptions(BaseModel):
    """Runtime execution and safety control options separated from parameters."""
    approve_risky: bool = False
    escalate: bool = False
    approved_by: Optional[str] = None
    approval_token: Optional[str] = None


class AutomationArtifact(BaseModel):
    """Complete automation artifact for a capability."""
    metadata: ArtifactMetadata
    parameters: Dict[str, ParameterDefinition]
    outputs: Dict[str, OutputDefinition]
    steps: List[ActionStep]
    checkpoint: Checkpoint
    error_handlers: List[ErrorHandler] = Field(default_factory=list)
    business_outcome_rules: List[BusinessOutcomeRule] = Field(default_factory=list)
    
    def get_parameter_values(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and prepare parameter values. Unknown keys are strictly rejected."""
        unknown_keys = set(params.keys()) - set(self.parameters.keys())
        if unknown_keys:
            raise ValueError(f"Parameter validation failed: unknown parameter(s): {', '.join(sorted(unknown_keys))}")

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
    """Result of executing an automation artifact with disjoint terminal states."""
    status: ExecutionStatus
    success: bool
    outputs: Dict[str, Any] = Field(default_factory=dict)
    business_outcome: Optional[str] = None
    evidence_text: Optional[str] = None
    error: Optional[str] = None
    error_step: Optional[int] = None
    expected: Optional[str] = None
    observed: Optional[str] = None
    screenshot_path: Optional[str] = None
    execution_time_seconds: float
    steps_completed: int

    @classmethod
    def create_success(cls, outputs: Dict[str, Any], execution_time: float, steps_completed: int) -> "ExecutionResult":
        return cls(
            status=ExecutionStatus.SUCCESS,
            success=True,
            outputs=outputs,
            execution_time_seconds=execution_time,
            steps_completed=steps_completed
        )

    @classmethod
    def create_business_outcome(cls, outcome: str, evidence_text: Optional[str], execution_time: float, steps_completed: int) -> "ExecutionResult":
        return cls(
            status=ExecutionStatus.BUSINESS_OUTCOME,
            success=False,
            business_outcome=outcome,
            evidence_text=evidence_text,
            execution_time_seconds=execution_time,
            steps_completed=steps_completed
        )

    @classmethod
    def create_failure(cls, error: str, error_step: Optional[int], expected: Optional[str], observed: Optional[str], execution_time: float, steps_completed: int, screenshot_path: Optional[str] = None) -> "ExecutionResult":
        return cls(
            status=ExecutionStatus.FAILURE,
            success=False,
            error=error,
            error_step=error_step,
            expected=expected,
            observed=observed,
            screenshot_path=screenshot_path,
            execution_time_seconds=execution_time,
            steps_completed=steps_completed
        )

    @classmethod
    def create_needs_confirmation(cls, step_id: int, reason: str, execution_time: float, steps_completed: int, screenshot_path: Optional[str] = None) -> "ExecutionResult":
        return cls(
            status=ExecutionStatus.NEEDS_CONFIRMATION,
            success=False,
            error_step=step_id,
            error=f"Confirmation required: {reason}",
            expected="Human authorization for risky/irreversible action",
            observed=reason,
            screenshot_path=screenshot_path,
            execution_time_seconds=execution_time,
            steps_completed=steps_completed
        )