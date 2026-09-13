"""Deterministic replay engine for executing automation artifacts."""
from typing import Dict, Any, Optional, Tuple
import time
import json
import asyncio
from pathlib import Path
from src.automation.browser import BrowserAutomation
from src.artifact.schemas import (
    AutomationArtifact, ExecutionResult, ErrorType, 
    ActionType, CheckpointCondition
)
from src.safety.guardrails import SafetyGuardrails
from src.safety.escalation import EscalationManager, InterventionRequest
from src.utils.config import Config
from src.utils.logging import get_logger
from src.artifact.metrics import record_artifact_execution

logger = get_logger(__name__)


class ReplayEngine:
    """Execute automation artifacts deterministically without LLM involvement."""
    
    def __init__(self):
        """Initialize the replay engine."""
        self.browser = BrowserAutomation(headless=True)
        self.safety = SafetyGuardrails()
        self.escalation = EscalationManager()
        
    async def execute_artifact(self, artifact: AutomationArtifact, 
                              parameters: Dict[str, Any]) -> ExecutionResult:
        """Execute an automation artifact with given parameters."""
        logger.info("Starting artifact execution", 
                   capability=artifact.metadata.capability_name,
                   version=artifact.metadata.version)
        
        start_time = time.time()
        steps_completed = 0
        outputs = {}
        error = None
        error_step = None
        business_outcome = None
        
        try:
            # Start browser
            await self.browser.start()
            
            # Validate parameters
            try:
                validated_params = artifact.get_parameter_values(parameters)
            except ValueError as e:
                return ExecutionResult(
                    success=False,
                    error=f"Parameter validation failed: {str(e)}",
                    execution_time_seconds=time.time() - start_time,
                    steps_completed=0
                )
            
            # Execute each step
            for step in artifact.steps:
                step_start = time.time()
                
                # Substitute parameters in value
                if step.value:
                    step.value = artifact.substitute_parameters(step.value, parameters)
                
                # Safety check
                is_allowed, safety_error = self.safety.validate_action(
                    step.action_type, 
                    step.target.value if step.action_type == ActionType.NAVIGATE else None
                )
                
                if not is_allowed:
                    error = f"Safety policy violation: {safety_error}"
                    error_step = step.step_id
                    logger.error("Safety violation", step=step.step_id, error=error)
                    break
                
                # Execute the step
                success, result = await self._execute_step(step, validated_params)
                
                if success:
                    steps_completed += 1
                    
                    # Store output if this is an extract action
                    if step.action_type == ActionType.EXTRACT and step.output_key:
                        outputs[step.output_key] = result
                        
                    # Wait if specified
                    if step.wait_after:
                        await asyncio.sleep(step.wait_after / 1000)  # Convert ms to seconds
                        
                    logger.info("Step completed", step=step.step_id, 
                               action_type=step.action_type.value,
                               duration_seconds=time.time() - step_start)
                else:
                    # Handle error
                    error_info = await self._handle_step_error(step, result, artifact)
                    
                    if error_info["is_business_outcome"]:
                        business_outcome = error_info["outcome"]
                        logger.info("Business outcome encountered", 
                                   outcome=business_outcome)
                        break
                    elif error_info["is_recoverable"]:
                        logger.info("Error recovered", step=step.step_id)
                        steps_completed += 1
                        continue
                    else:
                        error = error_info["error"]
                        error_step = step.step_id
                        logger.error("Step failed irrecoverably", 
                                   step=step.step_id, error=error)
                        break
            
            # Verify checkpoint if no errors
            if not error and not business_outcome:
                try:
                    checkpoint_passed = await self._verify_checkpoint(artifact.checkpoint)
                    if not checkpoint_passed:
                        error = "Checkpoint verification failed"
                        error_step = artifact.checkpoint.step_id
                        logger.error("Checkpoint verification failed")
                except Exception as e:
                    error = f"Checkpoint verification exception: {str(e)}"
                    error_step = artifact.checkpoint.step_id
                    logger.error("Checkpoint verification exception", error=str(e))
            
            # Determine success
            success = (error is None and business_outcome is None)
            
            execution_time = time.time() - start_time
            
            # Record execution metrics
            record_artifact_execution(
                artifact_name=artifact.metadata.capability_name,
                success=success,
                execution_time=execution_time,
                steps_completed=steps_completed,
                total_steps=len(artifact.steps),
                error_type=error,
                business_outcome=business_outcome,
                fallback_strategies_used=[]
            )
            
            return ExecutionResult(
                success=success,
                outputs=outputs,
                business_outcome=business_outcome,
                error=error,
                error_step=error_step,
                execution_time_seconds=execution_time,
                steps_completed=steps_completed
            )
            
        except Exception as e:
            logger.error("Artifact execution failed with exception", error=str(e))
            return ExecutionResult(
                success=False,
                error=f"Execution exception: {str(e)}",
                execution_time_seconds=time.time() - start_time,
                steps_completed=steps_completed
            )
        finally:
            await self.browser.stop()
            
    async def _execute_step(self, step, parameters: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Execute a single step."""
        try:
            # Special handling for navigate action
            if step.action_type == ActionType.NAVIGATE:
                url = step.target.value
                if step.value:  # If value is provided, it might be a parameterized URL
                    url = step.value
                await self.browser.navigate(url)
                return True, None
                
            # Standard action execution
            success, result = await self.browser.execute_action(
                step.action_type, step.target, step.value
            )
            return success, result
            
        except Exception as e:
            logger.error("Step execution exception", step=step.step_id, error=str(e))
            return False, str(e)
            
    async def _handle_step_error(self, step, error: str, 
                                 artifact: AutomationArtifact) -> Dict[str, Any]:
        """Handle errors during step execution with fallback strategies."""
        logger.info("Handling step error", step=step.step_id, error=error)
        
        # Check error handlers
        for handler in artifact.error_handlers:
            if self._matches_error_type(error, handler.error_type):
                logger.info("Found matching error handler", error_type=handler.error_type.value)
                
                # Try fallback strategy
                if handler.fallback_strategy:
                    success, result = await self._try_fallback_strategy(
                        step, handler.fallback_strategy
                    )
                    if success:
                        return {"is_recoverable": True, "error": None}
                
                # Check if it's a business outcome
                if handler.error_type == ErrorType.BUSINESS_OUTCOME:
                    if handler.condition and self._matches_condition(error, handler.condition):
                        return {
                            "is_business_outcome": True,
                            "outcome": handler.outcome,
                            "is_recoverable": False
                        }
                
                # If it's explicitly marked as a business outcome
                if handler.outcome:
                    return {
                        "is_business_outcome": True,
                        "outcome": handler.outcome,
                        "is_recoverable": False
                    }
        
        # Default: unrecoverable error
        return {
            "is_recoverable": False,
            "is_business_outcome": False,
            "error": error
        }
        
    def _matches_error_type(self, error: str, error_type: ErrorType) -> bool:
        """Check if an error matches a specific error type."""
        error_lower = error.lower()
        
        if error_type == ErrorType.ELEMENT_NOT_FOUND:
            return "not found" in error_lower or "element" in error_lower
        elif error_type == ErrorType.TIMEOUT:
            return "timeout" in error_lower
        elif error_type == ErrorType.VALIDATION_ERROR:
            return "validation" in error_lower or "invalid" in error_lower
        elif error_type == ErrorType.PERMISSION_DENIED:
            return "permission" in error_lower or "denied" in error_lower
        elif error_type == ErrorType.UNEXPECTED_DIALOG:
            return "dialog" in error_lower or "popup" in error_lower
        elif error_type == ErrorType.SESSION_EXPIRED:
            return "session" in error_lower or "expired" in error_lower
        elif error_type == ErrorType.BUSINESS_OUTCOME:
            return True  # Business outcomes are handled explicitly
        else:
            return False
            
    def _matches_condition(self, error: str, condition: Dict[str, Any]) -> bool:
        """Check if error matches a specific condition."""
        if "text_contains" in condition:
            return condition["text_contains"].lower() in error.lower()
        return False
        
    async def _try_fallback_strategy(self, step, strategy: str) -> tuple[bool, Optional[str]]:
        """Try a fallback element location strategy."""
        logger.info("Trying fallback strategy", strategy=strategy)
        
        # Add fallback strategy to target
        from src.artifact.schemas import LocationStrategy
        
        if strategy == "text_content_match":
            original_strategy = step.target.strategy
            step.target.strategy = LocationStrategy.TEXT_CONTENT
            success, result = await self.browser.execute_action(
                step.action_type, step.target, step.value
            )
            step.target.strategy = original_strategy  # Restore original
            return success, result
        
        elif strategy == "increase_wait_time":
            # Increase wait time and retry
            original_wait = step.wait_after or 1000
            await asyncio.sleep((original_wait * 2) / 1000)  # Double the wait time
            success, result = await self.browser.execute_action(
                step.action_type, step.target, step.value
            )
            return success, result
        
        elif strategy == "retry_with_refresh":
            # Retry the action (in real implementation would refresh page)
            await asyncio.sleep(1)  # Brief pause before retry
            success, result = await self.browser.execute_action(
                step.action_type, step.target, step.value
            )
            return success, result
        
        return False, "Fallback strategy not implemented"
        
    async def _verify_checkpoint(self, checkpoint) -> bool:
        """Verify that the checkpoint condition is met."""
        logger.info("Verifying checkpoint", step=checkpoint.step_id)
        
        try:
            passed = await self.browser.check_checkpoint(
                checkpoint.condition.target,
                checkpoint.condition.text_contains
            )
            
            if passed:
                logger.info("Checkpoint passed")
            else:
                logger.warning("Checkpoint failed")
                
            return passed
            
        except Exception as e:
            logger.error("Checkpoint verification failed", error=str(e))
            return False
            
    def load_artifact(self, artifact_path: str) -> AutomationArtifact:
        """Load an artifact from a JSON file."""
        logger.info("Loading artifact", path=artifact_path)
        
        with open(artifact_path, 'r') as f:
            data = json.load(f)
            
        return AutomationArtifact(**data)
        
    def save_artifact(self, artifact: AutomationArtifact, artifact_path: str) -> None:
        """Save an artifact to a JSON file."""
        logger.info("Saving artifact", path=artifact_path)
        
        # Ensure directory exists
        Path(artifact_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(artifact_path, 'w') as f:
            json.dump(artifact.model_dump(), f, indent=2)
            
        logger.info("Artifact saved successfully")