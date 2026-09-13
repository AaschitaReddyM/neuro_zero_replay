"""Human-in-the-loop escalation and handoff mechanism."""
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ControlState(str, Enum):
    """States for control transfer."""
    AUTOMATION = "automation"
    HUMAN_CONTROL = "human_control"
    PAUSED = "paused"


@dataclass
class InterventionRequest:
    """Request for human intervention."""
    capability_name: str
    current_step: int
    reason: str
    context: Dict[str, Any]
    screenshot_path: Optional[str] = None
    page_content: Optional[str] = None


class EscalationManager:
    """Manage human escalation and control transfer."""
    
    def __init__(self):
        """Initialize escalation manager."""
        self.control_state = ControlState.AUTOMATION
        self.pending_intervention: Optional[InterventionRequest] = None
        self.human_actions: list = []
        
    def detect_stuck_state(self, steps_completed: int, max_steps: int, 
                          consecutive_failures: int = 0) -> bool:
        """Detect if the automation is stuck."""
        # Stuck if we've hit max steps
        if steps_completed >= max_steps:
            logger.warning("Max steps reached, automation may be stuck", 
                         steps=steps_completed, max=max_steps)
            return True
            
        # Stuck if we have consecutive failures
        if consecutive_failures >= 3:
            logger.warning("Consecutive failures detected, automation may be stuck",
                         failures=consecutive_failures)
            return True
            
        return False
        
    def request_intervention(self, request: InterventionRequest) -> None:
        """Request human intervention."""
        logger.info("Requesting human intervention", 
                    capability=request.capability_name,
                    step=request.current_step,
                    reason=request.reason)
        self.pending_intervention = request
        self.control_state = ControlState.PAUSED
        
    def transfer_control_to_human(self) -> bool:
        """Transfer control to human operator."""
        if not self.pending_intervention:
            logger.warning("No pending intervention to transfer")
            return False
            
        logger.info("Transferring control to human operator")
        self.control_state = ControlState.HUMAN_CONTROL
        return True
        
    def record_human_action(self, action: Dict[str, Any]) -> None:
        """Record an action taken by the human operator."""
        logger.info("Recording human action", action_type=action.get("type"))
        self.human_actions.append(action)
        
    def return_control_to_automation(self) -> bool:
        """Return control to automation after human intervention."""
        if self.control_state != ControlState.HUMAN_CONTROL:
            logger.warning("Cannot return control - not in human control state")
            return False
            
        logger.info("Returning control to automation")
        self.control_state = ControlState.AUTOMATION
        self.pending_intervention = None
        return True
        
    def get_control_state(self) -> ControlState:
        """Get the current control state."""
        return self.control_state
        
    def get_pending_intervention(self) -> Optional[InterventionRequest]:
        """Get the pending intervention request."""
        return self.pending_intervention
        
    def get_human_actions(self) -> list:
        """Get the list of human actions taken."""
        return self.human_actions.copy()