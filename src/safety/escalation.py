"""Human-in-the-loop escalation and handoff mechanism."""
import asyncio
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List

from src.utils.logging import get_logger
from src.safety.guardrails import redact_sensitive_data

logger = get_logger(__name__)


class ControlState(str, Enum):
    """States for control transfer."""
    AUTOMATION = "automation"
    PAUSED = "paused"
    HUMAN_CONTROL = "human_control"
    RESUMING = "resuming"


@dataclass
class InterventionRequest:
    """Request for human intervention."""
    capability_name: str
    current_step: int
    reason: str
    context: Dict[str, Any]
    screenshot_path: Optional[str] = None
    page_content: Optional[str] = None
    run_id: Optional[str] = None
    created_at: Optional[str] = None


class EscalationManager:
    """Manage human escalation and control transfer with live session retention."""
    
    def __init__(self, interventions_dir: str = "evidence/interventions"):
        """Initialize escalation manager."""
        self.control_state = ControlState.AUTOMATION
        self.pending_intervention: Optional[InterventionRequest] = None
        self.human_actions: List[Dict[str, Any]] = []
        self.interventions_dir = Path(interventions_dir)
        self.interventions_dir.mkdir(parents=True, exist_ok=True)
        self.active_run_id: Optional[str] = None
        
    def detect_stuck_state(self, steps_completed: int, max_steps: int, 
                          consecutive_failures: int = 0) -> bool:
        """Detect if the automation is stuck."""
        if steps_completed >= max_steps:
            logger.warning("Max steps reached, automation may be stuck", 
                         steps=steps_completed, max=max_steps)
            return True
            
        if consecutive_failures >= 3:
            logger.warning("Consecutive failures detected, automation may be stuck",
                         failures=consecutive_failures)
            return True
            
        return False
        
    def request_intervention(self, request: InterventionRequest) -> str:
        """
        Request human intervention and transition state from AUTOMATION -> PAUSED -> HUMAN_CONTROL.
        Persists intervention record to evidence/interventions/<run_id>.json.
        """
        if not request.run_id:
            request.run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if not request.created_at:
            request.created_at = datetime.now().isoformat()
            
        self.active_run_id = request.run_id
        self.pending_intervention = request
        
        # Transition AUTOMATION -> PAUSED
        self.control_state = ControlState.PAUSED
        logger.info("Automation paused for intervention", 
                    capability=request.capability_name,
                    step=request.current_step,
                    reason=request.reason,
                    run_id=request.run_id)
                    
        # Persist structured intervention request (with active recursive redaction)
        intervention_file = self.interventions_dir / f"{request.run_id}.json"
        raw_record = {
            "run_id": request.run_id,
            "capability_name": request.capability_name,
            "step_id": request.current_step,
            "reason": request.reason,
            "control_state": ControlState.HUMAN_CONTROL.value,
            "screenshot_path": request.screenshot_path,
            "page_content": request.page_content[:1000] if request.page_content else None,
            "context": request.context,
            "created_at": request.created_at,
            "status": "pending_human_action",
            "resume_file": str(self.interventions_dir / f"{request.run_id}.resume"),
            "human_actions": []
        }
        redacted_record = redact_sensitive_data(raw_record)
        with open(intervention_file, "w", encoding="utf-8") as f:
            json.dump(redacted_record, f, indent=2)
            
        # Transition PAUSED -> HUMAN_CONTROL
        self.transfer_control_to_human()
        
        # Display instructions for human operator
        print("\n" + "=" * 76)
        print("  [HUMAN ESCALATION REQUIRED] Session Control Transferred")
        print("=" * 76)
        print(f"  Capability : {request.capability_name}")
        print(f"  Failed Step: {request.current_step}")
        print(f"  Reason     : {request.reason}")
        print(f"  Run ID     : {request.run_id}")
        print(f"  Record     : {intervention_file}")
        print(f"  Resume File: {self.interventions_dir / f'{request.run_id}.resume'}")
        print("-" * 76)
        print("  The browser session remains LIVE. Operator actions will be recorded.")
        print(f"  To resume automation:")
        print(f"    Create signal file: {self.interventions_dir / f'{request.run_id}.resume'}")
        print("=" * 76 + "\n")
        
        return request.run_id
        
    def transfer_control_to_human(self) -> bool:
        """Transfer control to human operator."""
        if not self.pending_intervention:
            logger.warning("No pending intervention to transfer")
            return False
            
        logger.info("Control transferred to human operator", run_id=self.active_run_id)
        self.control_state = ControlState.HUMAN_CONTROL
        return True
        
    def record_human_action(self, action: Dict[str, Any]) -> None:
        """Record an action taken by the human operator."""
        redacted_action = redact_sensitive_data(action)
        logger.info("Recording human action", action_type=redacted_action.get("type"))
        self.human_actions.append(redacted_action)
        
        # Update on-disk intervention record if active
        if self.active_run_id:
            intervention_file = self.interventions_dir / f"{self.active_run_id}.json"
            if intervention_file.exists():
                try:
                    with open(intervention_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    data["human_actions"] = self.human_actions
                    with open(intervention_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                except Exception as e:
                    logger.warning("Failed to update intervention file with action", error=str(e))
        
    async def wait_for_resume(self, browser=None, poll_interval: float = 0.5, timeout: float = 60.0) -> Dict[str, Any]:
        """
        Block and wait for human resume signal while observing browser state.
        Signals:
        1. File: evidence/interventions/<run_id>.resume
        """
        if self.control_state != ControlState.HUMAN_CONTROL:
            logger.warning("Cannot wait for resume - not in HUMAN_CONTROL state")
            return {"resumed": False, "reason": "Not in HUMAN_CONTROL"}
            
        run_id = self.active_run_id
        resume_file = self.interventions_dir / f"{run_id}.resume"
        
        # Capture initial browser state
        initial_url = None
        initial_text = None
        if browser and getattr(browser, "page", None):
            try:
                initial_url = browser.page.url
                initial_text = await browser.get_page_content()
            except Exception:
                pass
                
        logger.info("Waiting for human resume signal", run_id=run_id, resume_file=str(resume_file))
        start_wait = time.time()
        
        while time.time() - start_wait < timeout:
            if resume_file.exists():
                logger.info("Resume signal file detected", run_id=run_id)
                resume_data = {}
                try:
                    content = resume_file.read_text(encoding="utf-8").strip()
                    if content:
                        try:
                            resume_data = json.loads(content)
                        except Exception:
                            resume_data = {"notes": content}
                    resume_file.unlink(missing_ok=True)
                except Exception:
                    pass
                
                # Transition to RESUMING
                self.control_state = ControlState.RESUMING
                
                # Capture final browser state & calculate delta
                final_url = None
                final_text = None
                if browser and getattr(browser, "page", None):
                    try:
                        final_url = browser.page.url
                        final_text = await browser.get_page_content()
                    except Exception:
                        pass
                        
                action_record = {
                    "type": "human_operator_intervention",
                    "timestamp": datetime.now().isoformat(),
                    "duration_seconds": round(time.time() - start_wait, 2),
                    "url_before": initial_url,
                    "url_after": final_url,
                    "url_changed": initial_url != final_url,
                    "dom_changed": initial_text != final_text,
                    "operator_notes": resume_data.get("notes", "Operator resolved issue and signaled resume")
                }
                self.record_human_action(action_record)
                
                # Return control to automation
                self.return_control_to_automation()
                return {"resumed": True, "action": action_record}
                
            await asyncio.sleep(poll_interval)
            
        logger.error("Intervention wait timed out", run_id=run_id, timeout=timeout)
        self.control_state = ControlState.AUTOMATION
        return {"resumed": False, "reason": f"Timeout of {timeout}s exceeded"}
        
    def return_control_to_automation(self) -> bool:
        """Return control to automation after human intervention."""
        logger.info("Returning control to automation", run_id=self.active_run_id)
        self.control_state = ControlState.AUTOMATION
        
        # Mark intervention record as resolved
        if self.active_run_id:
            intervention_file = self.interventions_dir / f"{self.active_run_id}.json"
            if intervention_file.exists():
                try:
                    with open(intervention_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    data["status"] = "resolved"
                    data["resumed_at"] = datetime.now().isoformat()
                    data["human_actions"] = self.human_actions
                    with open(intervention_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                except Exception:
                    pass
                    
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