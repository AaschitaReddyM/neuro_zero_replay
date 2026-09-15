"""Deterministic replay engine for executing automation artifacts."""
from typing import Dict, Any, Optional, Tuple
import time
import json
import asyncio
from pathlib import Path
from src.automation.browser import BrowserAutomation
from src.artifact.schemas import (
    AutomationArtifact, ExecutionResult, ExecutionStatus, ErrorType, 
    ActionType, CheckpointCondition, BusinessOutcomeRule, RiskLevel,
    RunOptions
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
        
    async def execute_artifact_with_options(self, artifact: AutomationArtifact,
                                           parameters: Dict[str, Any],
                                           options: Any) -> ExecutionResult:
        """Execute an automation artifact with explicit run options."""
        if isinstance(options, dict):
            options = RunOptions(**options)
        elif not isinstance(options, RunOptions):
            options = RunOptions()
        return await self.execute_artifact(artifact, parameters, options=options)

    async def execute_artifact(self, artifact: AutomationArtifact, 
                              parameters: Dict[str, Any],
                              options: Optional[RunOptions] = None) -> ExecutionResult:
        """Execute an automation artifact with given parameters."""
        if options is None:
            options = RunOptions()
        logger.info("Starting artifact execution", 
                   capability=artifact.metadata.capability_name,
                   version=artifact.metadata.version)
        
        start_time = time.time()
        steps_completed = 0
        outputs = {}
        error = None
        error_step = None
        error_expected = None
        error_observed = None
        screenshot_path = None
        business_outcome = None
        evidence_text = None
        
        try:
            # Start browser
            await self.browser.start()
            
            # Validate parameters
            try:
                validated_params = artifact.get_parameter_values(parameters)
            except ValueError as e:
                return ExecutionResult.create_failure(
                    error=f"Parameter validation failed: {str(e)}",
                    error_step=None,
                    expected="Valid input parameters matching schema",
                    observed=str(e),
                    execution_time=time.time() - start_time,
                    steps_completed=0
                )
            
            # Execute each step (use deep copy to prevent mutating the artifact in-memory)
            for raw_step in artifact.steps:
                step = raw_step.model_copy(deep=True)
                step_start = time.time()
                
                # Substitute parameters in value
                if step.value:
                    step.value = artifact.substitute_parameters(step.value, validated_params)
                
                # Determine resolved URL for navigation actions
                resolved_url = None
                if step.action_type == ActionType.NAVIGATE:
                    resolved_url = step.value if step.value else step.target.value
                
                # Safety check on resolved target
                is_allowed, safety_error = self.safety.validate_action(
                    step.action_type, 
                    resolved_url
                )
                
                if not is_allowed:
                    error = f"Safety policy violation: {safety_error}"
                    error_step = step.step_id
                    error_expected = "Action within safety allowlist"
                    error_observed = safety_error
                    logger.error("Safety violation", step=step.step_id, error=error)
                    break
                
                # Risk gating policy check
                if step.risk_level == RiskLevel.RISKY and not options.approve_risky:
                    error_step = step.step_id
                    reason = f"Step {step.step_id} ({step.action_type.value}) is marked as 'risky' and requires explicit confirmation (--approve-risky)"
                    screenshot_path = f"logs/confirmation_required_{step.step_id}.png"
                    if self.browser:
                        try:
                            await self.browser.take_screenshot(screenshot_path)
                        except Exception:
                            pass
                    logger.warning("Risk gate triggered: confirmation required", step=step.step_id, action=step.action_type.value)
                    return ExecutionResult.create_needs_confirmation(
                        step_id=step.step_id,
                        reason=reason,
                        execution_time=time.time() - start_time,
                        steps_completed=steps_completed,
                        screenshot_path=screenshot_path
                    )
                elif step.risk_level == RiskLevel.IRREVERSIBLE:
                    error_step = step.step_id
                    reason = f"Step {step.step_id} ({step.action_type.value}) is marked as 'irreversible' and requires human escalation"
                    screenshot_path = f"logs/irreversible_escalation_{step.step_id}.png"
                    if self.browser:
                        try:
                            await self.browser.take_screenshot(screenshot_path)
                        except Exception:
                            pass
                    logger.warning("Risk gate triggered: irreversible action requires escalation", step=step.step_id)
                    return ExecutionResult.create_needs_confirmation(
                        step_id=step.step_id,
                        reason=reason,
                        execution_time=time.time() - start_time,
                        steps_completed=steps_completed,
                        screenshot_path=screenshot_path
                    )
                
                # Execute the step
                success, result = await self._execute_step(step, validated_params)
                
                if success:
                    # Post-action URL boundary check (detect any unexpected redirect or navigation off-domain)
                    if self.browser and getattr(self.browser, "page", None):
                        current_page_url = self.browser.page.url
                        if current_page_url and current_page_url != "about:blank":
                            if not self.safety.is_domain_allowed(current_page_url):
                                error = f"Navigation boundary violation: navigated off-domain to '{current_page_url}'"
                                error_step = step.step_id
                                error_expected = f"URL within allowed domains {self.safety.allowed_domains}"
                                error_observed = f"Current URL '{current_page_url}' is not in allowlist"
                                screenshot_path = f"logs/boundary_violation_{step.step_id}.png"
                                try:
                                    await self.browser.take_screenshot(screenshot_path)
                                except Exception:
                                    pass
                                logger.error("Off-domain boundary violation", url=current_page_url, step=step.step_id)
                                break

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

                    # Check for business outcome immediately if page state changed
                    page_outcome = await self._detect_page_business_outcome(artifact)
                    if page_outcome:
                        business_outcome = page_outcome["outcome"]
                        evidence_text = page_outcome.get("evidence_text")
                        logger.info("Page-visible business outcome detected", 
                                   outcome=business_outcome, evidence=evidence_text)
                        break
                else:
                    # Handle error
                    error_info = await self._handle_step_error(step, result, artifact)
                    
                    if error_info.get("is_business_outcome"):
                        business_outcome = error_info["outcome"]
                        evidence_text = error_info.get("evidence_text")
                        logger.info("Business outcome encountered", 
                                   outcome=business_outcome, evidence=evidence_text)
                        break
                    elif error_info.get("is_recoverable"):
                        logger.info("Error recovered", step=step.step_id)
                        steps_completed += 1
                        continue
                    else:
                        error = error_info["error"]
                        error_step = step.step_id
                        error_expected = error_info.get("expected", f"Step {step.step_id} to succeed")
                        error_observed = error_info.get("observed", error)
                        logger.error("Step failed irrecoverably", 
                                   step=step.step_id, error=error)
                        
                        # Human Escalation Seam
                        if options.escalate:
                            logger.info("Escalation triggered for irrecoverable step error", step=step.step_id)
                            screenshot_path = f"logs/escalation_step_{step.step_id}.png"
                            if self.browser:
                                try:
                                    await self.browser.take_screenshot(screenshot_path)
                                except Exception:
                                    pass
                            
                            page_content = None
                            if self.browser:
                                try:
                                    page_content = await self.browser.get_page_content()
                                except Exception:
                                    pass
                                
                            run_id = f"escalation_{int(time.time())}"
                            request = InterventionRequest(
                                capability_name=artifact.metadata.capability_name,
                                current_step=step.step_id,
                                reason=f"Step {step.step_id} failed: {error}",
                                context={"step_description": step.description, "error": error},
                                screenshot_path=screenshot_path,
                                page_content=page_content,
                                run_id=run_id
                            )
                            self.escalation.request_intervention(request)
                            
                            # Block and wait for human operator resume signal
                            resume_res = await self.escalation.wait_for_resume(
                                browser=self.browser,
                                timeout=Config.AGENT_TIMEOUT_SECONDS
                            )
                            
                            if resume_res.get("resumed"):
                                logger.info("Session resumed by human operator. Re-evaluating step...", step=step.step_id)
                                step_satisfied = False
                                verification_path = None
                                
                                # 1. If step has a postcondition, evaluate it
                                if getattr(step, "postcondition", None):
                                    verification_path = "postcondition"
                                    step_satisfied = await self._verify_checkpoint_condition(step.postcondition)
                                
                                # 2. Otherwise re-execute the step once
                                if not step_satisfied:
                                    verification_path = "re_execute"
                                    retry_success, retry_result = await self._execute_step(step, validated_params)
                                    step_satisfied = retry_success
                                
                                if step_satisfied:
                                    logger.info("Step completed successfully after operator intervention", 
                                                step=step.step_id, verification_path=verification_path)
                                    steps_completed += 1
                                    error = None
                                    error_step = None
                                    error_expected = None
                                    error_observed = None
                                    continue
                                else:
                                    logger.error("Step still failing after operator intervention", 
                                                 step=step.step_id, verification_path=verification_path)
                                    error = "Step still failing after operator intervention"
                                    error_step = step.step_id
                                    error_expected = f"Step {step.step_id} satisfied by operator or re-execution"
                                    error_observed = "step re-executed after operator intervention and still failed"
                                    break
                        break
            
            # Verify checkpoint if no errors and no business outcome
            if not error and not business_outcome:
                try:
                    checkpoint_passed = await self._verify_checkpoint(artifact.checkpoint)
                    if not checkpoint_passed:
                        error = "Checkpoint verification failed"
                        error_step = artifact.checkpoint.step_id
                        error_expected = f"Checkpoint {artifact.checkpoint.description} to pass"
                        error_observed = "Condition not met on page"
                        logger.error("Checkpoint verification failed")
                except Exception as e:
                    error = f"Checkpoint verification exception: {str(e)}"
                    error_step = artifact.checkpoint.step_id
                    error_expected = "Checkpoint verification to execute without exception"
                    error_observed = str(e)
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
            
            # Redact sensitive data from outputs and error observations
            outputs = self.safety.redact_sensitive_data(outputs)
            if error_observed:
                error_observed = self.safety.redact_sensitive_data(error_observed)
                
            if business_outcome:
                return ExecutionResult.create_business_outcome(
                    outcome=business_outcome,
                    evidence_text=evidence_text,
                    execution_time=execution_time,
                    steps_completed=steps_completed
                )
            elif error:
                return ExecutionResult.create_failure(
                    error=error,
                    error_step=error_step,
                    expected=error_expected,
                    observed=error_observed,
                    execution_time=execution_time,
                    steps_completed=steps_completed,
                    screenshot_path=screenshot_path
                )
            else:
                return ExecutionResult.create_success(
                    outputs=outputs,
                    execution_time=execution_time,
                    steps_completed=steps_completed
                )
            
        except Exception as e:
            logger.error("Artifact execution failed with exception", error=str(e))
            return ExecutionResult.create_failure(
                error=f"Execution exception: {str(e)}",
                error_step=error_step or (steps_completed + 1),
                expected="Artifact execution to proceed without unexpected exceptions",
                observed=str(e),
                execution_time=time.time() - start_time,
                steps_completed=steps_completed
            )
        finally:
            await self.browser.stop()
            
    async def _execute_step(self, step, parameters: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Execute a single step."""
        try:
            # Special handling for navigate action
            if step.action_type == ActionType.NAVIGATE:
                url = step.value if step.value else step.target.value
                if not self.safety.is_domain_allowed(url):
                    return False, f"Safety violation: domain not allowed '{url}'"
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
        
        # 1. First, check if page-visible state indicates a business outcome (requires active page)
        if self.browser and getattr(self.browser, "page", None):
            business_outcome = await self._detect_page_business_outcome(artifact)
            if business_outcome:
                return {
                    "is_business_outcome": True,
                    "outcome": business_outcome["outcome"],
                    "evidence_text": business_outcome.get("evidence_text"),
                    "is_recoverable": False
                }
        
        # 2. Check error handlers for recoverable technical errors (skip business outcomes)
        for handler in artifact.error_handlers:
            if handler.error_type == ErrorType.BUSINESS_OUTCOME:
                continue
                
            if self._matches_error_type(error, handler.error_type):
                logger.info("Found matching error handler", error_type=handler.error_type.value)
                
                # Try fallback strategy
                if handler.fallback_strategy:
                    success, result = await self._try_fallback_strategy(
                        step, handler.fallback_strategy
                    )
                    if success:
                        return {"is_recoverable": True, "error": None, "is_business_outcome": False}
        
        # 3. Default: unrecoverable hard failure
        return {
            "is_recoverable": False,
            "is_business_outcome": False,
            "error": error,
            "expected": f"Step {step.step_id} ({step.action_type.value}) target '{step.target.value}' to succeed",
            "observed": error
        }
        
    def _matches_error_type(self, error: str, error_type: ErrorType) -> bool:
        """Check if an error matches a specific technical error type."""
        error_lower = error.lower()
        
        if error_type == ErrorType.BUSINESS_OUTCOME:
            # Business outcomes are NEVER matched from error strings; only from page state.
            return False
        elif error_type == ErrorType.ELEMENT_NOT_FOUND:
            return any(p in error_lower for p in ["element not found", "no element found", "waiting for selector", "waiting for locator", "could not find element"])
        elif error_type == ErrorType.TIMEOUT:
            return any(p in error_lower for p in ["timeout", "timed out", "timeouterror", "timeout exceeded"])
        elif error_type == ErrorType.VALIDATION_ERROR:
            return any(p in error_lower for p in ["validation error", "invalid selector", "invalid parameter"])
        elif error_type == ErrorType.PERMISSION_DENIED:
            return any(p in error_lower for p in ["permission denied", "access denied", "forbidden", "unauthorized"])
        elif error_type == ErrorType.UNEXPECTED_DIALOG:
            return any(p in error_lower for p in ["unexpected dialog", "modal dialog", "alert present"])
        elif error_type == ErrorType.SESSION_EXPIRED:
            return any(p in error_lower for p in ["session expired", "session timeout", "session invalid"])
        else:
            return False

    async def _detect_page_business_outcome(self, artifact: AutomationArtifact) -> Optional[Dict[str, str]]:
        """Detect if current page-visible state matches a declared business outcome."""
        try:
            if not self.browser or not getattr(self.browser, "page", None):
                return None
            page = self.browser.page
            
            # Check BusinessOutcomeRules if defined on artifact
            rules = getattr(artifact, "business_outcome_rules", [])
            for rule in rules:
                if rule.text_contains:
                    candidates = [rule.selector] if rule.selector else ["#lookup-result", "#transfer-result", "#account-result", ".result", "body"]
                    for selector in candidates:
                        try:
                            loc = page.locator(selector)
                            if await loc.count() > 0 and await loc.first.is_visible():
                                txt = await loc.first.inner_text()
                                if rule.text_contains.lower() in txt.lower():
                                    return {"outcome": rule.outcome, "evidence_text": txt.strip()}
                        except Exception:
                            pass

            # Check legacy error_handlers with error_type == BUSINESS_OUTCOME
            for handler in artifact.error_handlers:
                if handler.error_type == ErrorType.BUSINESS_OUTCOME and handler.outcome:
                    expected_text = None
                    if handler.condition and "text_contains" in handler.condition:
                        expected_text = handler.condition["text_contains"]
                    
                    if expected_text:
                        for selector in ["#lookup-result", "#transfer-result", "#account-result", ".result", "body"]:
                            try:
                                loc = page.locator(selector)
                                if await loc.count() > 0:
                                    is_vis = await loc.first.is_visible()
                                    if is_vis or selector == "body":
                                        content = await loc.first.inner_text()
                                        if expected_text.lower() in content.lower():
                                            return {
                                                "outcome": handler.outcome,
                                                "evidence_text": content.strip()
                                            }
                            except Exception:
                                continue
        except Exception as e:
            logger.warning("Error detecting page business outcome", error=str(e))
        return None
        
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

    async def _verify_checkpoint_condition(self, condition: CheckpointCondition) -> bool:
        """Verify that a specific checkpoint condition is met."""
        try:
            return await self.browser.check_checkpoint(
                condition.target,
                condition.text_contains
            )
        except Exception as e:
            logger.warning("Checkpoint condition check failed", error=str(e))
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