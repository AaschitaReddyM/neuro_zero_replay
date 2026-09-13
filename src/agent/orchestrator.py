"""Agent orchestrator for LLM-driven automation."""
from typing import Dict, Any, List, Optional
import asyncio
import time
from datetime import datetime
from src.agent.llm_client import LLMClient
from src.automation.browser import BrowserAutomation
from src.artifact.schemas import (
    ActionStep, ActionType, LocationStrategy, TargetLocation, 
    AutomationArtifact, ArtifactMetadata, ParameterDefinition, 
    OutputDefinition, Checkpoint, CheckpointCondition
)
from src.safety.guardrails import SafetyGuardrails
from src.safety.escalation import EscalationManager, InterventionRequest, ControlState
from src.utils.config import Config
from src.utils.logging import get_logger

logger = get_logger(__name__)


class AgentOrchestrator:
    """Orchestrate LLM-driven automation with artifact recording."""
    
    def __init__(self):
        """Initialize the agent orchestrator."""
        self.llm_client = LLMClient()
        self.browser = BrowserAutomation(headless=False)  # Non-headless for visibility
        self.safety = SafetyGuardrails()
        self.escalation = EscalationManager()
        self.action_history: List[Dict[str, Any]] = []
        self.recorded_steps: List[ActionStep] = []
        self.start_time: Optional[float] = None
        
    async def execute_goal(self, goal: str, target_url: str, 
                          capability_name: str, description: str) -> AutomationArtifact:
        """Execute a goal using LLM and record the artifact."""
        logger.info("Starting goal execution", goal=goal, target_url=target_url)
        self.start_time = time.time()
        
        # Start browser
        await self.browser.start()
        
        # Navigate to target
        await self.browser.navigate(target_url)
        
        # Initialize action history
        self.action_history = []
        self.recorded_steps = []
        
        # Main agent loop
        step_count = 0
        consecutive_failures = 0
        
        while step_count < Config.MAX_AGENT_STEPS:
            # Check for escalation
            if self.escalation.get_control_state() == ControlState.HUMAN_CONTROL:
                logger.info("Waiting for human intervention to complete")
                await self._handle_human_intervention()
                continue
                
            # Check if stuck
            if self.escalation.detect_stuck_state(step_count, Config.MAX_AGENT_STEPS, consecutive_failures):
                logger.warning("Agent appears stuck, requesting intervention")
                await self._request_intervention(goal, step_count, "Agent appears stuck")
                continue
                
            # Get current state
            current_state = await self._get_current_state()
            
            # Get LLM decision
            try:
                decision = await self.llm_client.decide_next_action(
                    goal, current_state, self.action_history
                )
            except Exception as e:
                logger.error("LLM decision failed, retrying", error=str(e))
                consecutive_failures += 1
                await asyncio.sleep(2)
                continue
                
            # Execute action
            success, result = await self._execute_llm_decision(decision, step_count)
            
            if success:
                consecutive_failures = 0
                step_count += 1
                
                # Check if goal is complete
                if await self._check_goal_completion(goal):
                    logger.info("Goal completed successfully")
                    break
            else:
                consecutive_failures += 1
                logger.warning("Action failed", error=result)
                
                if consecutive_failures >= 3:
                    logger.error("Too many consecutive failures, requesting intervention")
                    await self._request_intervention(goal, step_count, f"Action failures: {result}")
                    
        # Build artifact
        artifact = await self._build_artifact(goal, capability_name, description, target_url)
        
        # Cleanup
        await self.browser.stop()
        
        execution_time = time.time() - self.start_time
        logger.info("Goal execution completed", 
                   steps=step_count, 
                   time_seconds=execution_time)
        
        return artifact
        
    async def _get_current_state(self) -> Dict[str, Any]:
        """Get the current state of the application."""
        url = self.browser.page.url
        title = await self.browser.page.title()
        accessibility_tree = await self.browser.get_accessibility_tree()
        text_content = await self.browser.get_page_content()
        
        return {
            "url": url,
            "page_title": title,
            "accessibility_tree": accessibility_tree,
            "text_content": text_content
        }
        
    async def _execute_llm_decision(self, decision: Dict[str, Any], step_id: int) -> tuple[bool, Optional[str]]:
        """Execute a decision made by the LLM."""
        action_type_str = decision.get("action_type", "wait")
        action_type = ActionType(action_type_str)
        
        # Safety check
        is_allowed, error = self.safety.validate_action(action_type)
        if not is_allowed:
            logger.error("Action not allowed by safety policy", action_type=action_type_str, error=error)
            return False, error
            
        # Build target location
        target = self._build_target_from_decision(decision)
        
        # Execute action
        success, result = await self.browser.execute_action(
            action_type, target, decision.get("value")
        )
        
        # Record the action
        action_step = ActionStep(
            step_id=step_id + 1,
            action_type=action_type,
            target=target,
            value=decision.get("value"),
            description=decision.get("reasoning", ""),
            risk_level=self.safety.assess_risk(action_type)
        )
        self.recorded_steps.append(action_step)
        
        # Add to history
        self.action_history.append({
            "action_type": action_type_str,
            "description": decision.get("reasoning", ""),
            "success": success
        })
        
        return success, result
        
    def _build_target_from_decision(self, decision: Dict[str, Any]) -> TargetLocation:
        """Build a target location from LLM decision."""
        role = decision.get("target_role", "")
        name = decision.get("target_name", "")
        
        # Use accessibility as primary strategy
        return TargetLocation(
            strategy=LocationStrategy.ACCESSIBILITY_ROLE,
            value=f"{role}:{name}",
            role=role,
            name=name,
            fallback_strategies=[
                LocationStrategy.TEXT_CONTENT,
                LocationStrategy.SEMANTIC_SELECTOR
            ]
        )
        
    async def _check_goal_completion(self, goal: str) -> bool:
        """Check if the goal has been completed."""
        # Simple heuristic: if the LLM says it's done or we see success indicators
        # In a real system, this would be more sophisticated
        current_state = await self._get_current_state()
        text = current_state.get("text_content", "").lower()
        
        # Look for success indicators
        success_indicators = ["success", "completed", "done", "confirmed", "saved"]
        return any(indicator in text for indicator in success_indicators)
        
    async def _request_intervention(self, goal: str, step: int, reason: str) -> None:
        """Request human intervention."""
        # Take screenshot for context
        screenshot_path = f"logs/intervention_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        await self.browser.take_screenshot(screenshot_path)
        
        # Get current state
        current_state = await self._get_current_state()
        
        request = InterventionRequest(
            capability_name=goal,
            current_step=step,
            reason=reason,
            context=current_state,
            screenshot_path=screenshot_path,
            page_content=current_state.get("text_content")
        )
        
        self.escalation.request_intervention(request)
        
    async def _handle_human_intervention(self) -> None:
        """Handle human intervention (mock implementation)."""
        logger.info("Human intervention handler called")
        # In a real system, this would wait for human input via an operator console
        # For this demo, we'll simulate human action and return control
        await asyncio.sleep(2)
        self.escalation.record_human_action({"type": "manual_fix", "description": "Simulated human fix"})
        self.escalation.return_control_to_automation()
        
    async def _build_artifact(self, goal: str, capability_name: str, 
                            description: str, target_url: str) -> AutomationArtifact:
        """Build the automation artifact from recorded steps."""
        # Create metadata
        metadata = ArtifactMetadata(
            target_app=target_url,
            capability_name=capability_name,
            description=description
        )
        
        # Define parameters (simple heuristic-based extraction)
        parameters = self._extract_parameters(goal, description)
        
        # Define outputs
        outputs = self._extract_outputs(goal, description)
        
        # Create checkpoint (use last step as checkpoint)
        if self.recorded_steps:
            last_step = self.recorded_steps[-1]
            checkpoint = Checkpoint(
                step_id=last_step.step_id,
                condition=CheckpointCondition(
                    target=last_step.target
                ),
                description="Goal completion checkpoint"
            )
        else:
            # Fallback checkpoint
            checkpoint = Checkpoint(
                step_id=1,
                condition=CheckpointCondition(
                    target=TargetLocation(
                        strategy=LocationStrategy.TEXT_CONTENT,
                        value="body"
                    )
                ),
                description="Default checkpoint"
            )
        
        return AutomationArtifact(
            metadata=metadata,
            parameters=parameters,
            outputs=outputs,
            steps=self.recorded_steps,
            checkpoint=checkpoint
        )
        
    def _extract_parameters(self, goal: str, description: str) -> Dict[str, ParameterDefinition]:
        """Extract parameters from goal and description (heuristic)."""
        from src.artifact.schemas import ParameterType
        
        parameters = {}
        
        # Simple heuristic: look for common parameter patterns
        if "member" in goal.lower() or "customer" in goal.lower():
            parameters["member_id"] = ParameterDefinition(
                type=ParameterType.STRING,
                description="Member or customer ID"
            )
            
        if "account" in goal.lower():
            parameters["account_number"] = ParameterDefinition(
                type=ParameterType.STRING,
                description="Account number"
            )
            
        return parameters
        
    def _extract_outputs(self, goal: str, description: str) -> Dict[str, OutputDefinition]:
        """Extract outputs from goal and description (heuristic)."""
        from src.artifact.schemas import ParameterType
        
        outputs = {}
        
        # Simple heuristic: look for common output patterns
        if "balance" in goal.lower():
            outputs["balance"] = OutputDefinition(
                type=ParameterType.NUMBER,
                description="Account balance"
            )
            
        if "status" in goal.lower():
            outputs["status"] = OutputDefinition(
                type=ParameterType.STRING,
                description="Account or transaction status"
            )
            
        return outputs