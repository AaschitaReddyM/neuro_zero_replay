"""Agent orchestrator for LLM-driven automation with authentic discovery and artifact generation."""
from typing import Dict, Any, List, Optional
import asyncio
import os
import re
import json
import time
from datetime import datetime
from pathlib import Path
from src.agent.llm_client import LLMClient
from src.automation.browser import BrowserAutomation
from src.artifact.schemas import (
    ActionStep, ActionType, LocationStrategy, TargetLocation, 
    AutomationArtifact, ArtifactMetadata, ParameterDefinition, 
    OutputDefinition, Checkpoint, CheckpointCondition, ParameterType,
    BusinessOutcomeRule, ErrorHandler, ErrorType, RiskLevel
)
from src.safety.guardrails import SafetyGuardrails, redact_sensitive_data
from src.safety.escalation import EscalationManager, InterventionRequest, ControlState
from src.utils.config import Config
from src.utils.logging import get_logger

logger = get_logger(__name__)


class AgentOrchestrator:
    """Orchestrate LLM-driven automation with live browser execution and artifact recording."""
    
    def __init__(self, headless: Optional[bool] = None):
        """Initialize the agent orchestrator."""
        self.llm_client = LLMClient()
        if headless is None:
            headless = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")
        self.browser = BrowserAutomation(headless=headless)
        self.safety = SafetyGuardrails()
        self.escalation = EscalationManager()
        self.action_history: List[Dict[str, Any]] = []
        self.recorded_steps: List[ActionStep] = []
        self.transcript: List[Dict[str, Any]] = []
        self.active_parameters: Dict[str, Any] = {}
        self.extracted_outputs: Dict[str, Any] = {}
        self.final_checkpoint: Optional[Checkpoint] = None
        self.business_outcome_rules: List[BusinessOutcomeRule] = []
        self.start_time: Optional[float] = None
        self.evidence_dir: Optional[Path] = None
        
    async def execute_goal(self, goal: str, target_url: str, 
                          capability_name: str, description: str,
                          parameters: Optional[Dict[str, Any]] = None) -> AutomationArtifact:
        """Execute a goal using LLM with live browser execution and record a production artifact."""
        logger.info("Starting live capability discovery", goal=goal, target_url=target_url, capability=capability_name)
        self.start_time = time.time()
        
        # Setup evidence directory for this discovery run
        run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.evidence_dir = Path("evidence") / f"discovery_run_{run_ts}"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup parameters
        self.active_parameters = parameters or {}
        if not self.active_parameters:
            # Infer parameter from numeric tokens in goal if not explicitly passed
            m = re.search(r'\b\d{5}\b', goal)
            if m:
                self.active_parameters["member_id"] = m.group(0)
                
        # Start browser
        await self.browser.start()
        
        # Record initial navigate step
        await self.browser.navigate(target_url)
        initial_nav_step = ActionStep(
            step_id=1,
            action_type=ActionType.NAVIGATE,
            target=TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value=target_url
            ),
            value=target_url,
            description=f"Navigate to {target_url}",
            risk_level=RiskLevel.SAFE
        )
        self.recorded_steps.append(initial_nav_step)
        
        nav_screenshot = str(self.evidence_dir / "step_1_navigate.png")
        try:
            await self.browser.take_screenshot(nav_screenshot)
        except Exception:
            pass
            
        self.action_history = [{"action_type": "navigate", "description": f"Navigate to {target_url}", "success": True}]
        self.transcript = [{
            "step": 1,
            "action_type": "navigate",
            "url": target_url,
            "status": "success",
            "screenshot": nav_screenshot
        }]
        
        step_count = 1
        consecutive_failures = 0
        is_done = False
        
        try:
            while step_count < Config.MAX_AGENT_STEPS and not is_done:
                # Enforce timeout
                if time.time() - self.start_time > Config.AGENT_TIMEOUT_SECONDS:
                    logger.error("Agent execution timeout exceeded", timeout=Config.AGENT_TIMEOUT_SECONDS)
                    break

                # Check if stuck
                if self.escalation.detect_stuck_state(step_count, Config.MAX_AGENT_STEPS, consecutive_failures):
                    logger.warning("Agent appears stuck, requesting human intervention")
                    resumed = await self._request_and_wait_intervention(goal, step_count, "Agent appears stuck (max steps or consecutive failures)")
                    if resumed:
                        consecutive_failures = 0
                        continue
                    else:
                        logger.error("Human intervention wait timed out or failed")
                        break
                    
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
                    
                action_type_str = decision.get("action_type", "wait").lower()
                
                # Check for explicit done action
                if action_type_str == "done":
                    checkpoint_data = decision.get("checkpoint", {})
                    selector = checkpoint_data.get("value") or checkpoint_data.get("selector")
                    text_contains = checkpoint_data.get("text_contains", "")
                    
                    if not selector or not text_contains:
                        # Ask once for clarification if done action is incomplete
                        logger.warning("Done action missing checkpoint selector or text_contains, asking once for clarification")
                        try:
                            decision = await self.llm_client.decide_next_action(
                                f"{goal}\n\nERROR: Done action must include 'checkpoint' with 'selector' and 'text_contains', and 'outputs'.",
                                current_state,
                                self.action_history
                            )
                            checkpoint_data = decision.get("checkpoint", {})
                            selector = checkpoint_data.get("value") or checkpoint_data.get("selector")
                            text_contains = checkpoint_data.get("text_contains", "")
                        except Exception as e:
                            logger.error("Clarification failed", error=str(e))
                            
                    if not selector or not text_contains:
                        logger.error("Incomplete done action from LLM")
                        return False, "failure: incomplete done action"
                    
                    verified = False
                    inner_text = ""
                    try:
                        chk_loc = self.browser.page.locator(selector)
                        if await chk_loc.count() > 0 and await chk_loc.first.is_visible():
                            inner_text = await chk_loc.first.inner_text()
                            if not text_contains or text_contains.lower() in inner_text.lower():
                                verified = True
                    except Exception:
                        pass
                                
                    if verified:
                        logger.info("Goal completion verified via checkpoint", selector=selector, text=text_contains)
                        is_done = True
                        
                        # Capture extracted outputs from decision
                        outputs_from_llm = decision.get("outputs", {})
                        if isinstance(outputs_from_llm, list):
                            for item in outputs_from_llm:
                                if isinstance(item, dict):
                                    k = item.get("key")
                                    sel = item.get("selector") or selector
                                    if k:
                                        try:
                                            out_loc = self.browser.page.locator(sel)
                                            if await out_loc.count() > 0 and await out_loc.first.is_visible():
                                                val = (await out_loc.first.inner_text()).strip()
                                                self.extracted_outputs[k] = val
                                                self.recorded_steps.append(ActionStep(
                                                    step_id=len(self.recorded_steps) + 1,
                                                    action_type=ActionType.EXTRACT,
                                                    target=TargetLocation(
                                                        strategy=LocationStrategy.SEMANTIC_SELECTOR,
                                                        value=sel
                                                    ),
                                                    output_key=k,
                                                    description=f"Extract {k} from {sel}",
                                                    risk_level=RiskLevel.SAFE
                                                ))
                                        except Exception:
                                            pass
                        elif isinstance(outputs_from_llm, dict):
                            for k, v in outputs_from_llm.items():
                                self.extracted_outputs[k] = v
                                
                        self.final_checkpoint = Checkpoint(
                            step_id=len(self.recorded_steps),
                            condition=CheckpointCondition(
                                type="element_visible",
                                target=TargetLocation(
                                    strategy=LocationStrategy.SEMANTIC_SELECTOR,
                                    value=selector
                                ),
                                text_contains=text_contains
                            ),
                            description=f"Verify {capability_name} interface completion"
                        )
                        
                        done_screenshot = str(self.evidence_dir / f"step_{step_count+1}_done.png")
                        try:
                            await self.browser.take_screenshot(done_screenshot)
                        except Exception:
                            pass
                            
                        self.transcript.append({
                            "step": step_count + 1,
                            "decision": decision,
                            "status": "completed",
                            "screenshot": done_screenshot
                        })
                        break
                        
                    logger.warning("Checkpoint condition not yet satisfied on page", selector=selector, text=text_contains)
                    consecutive_failures += 1
                    continue
                    
                # Execute action
                success, result = await self._execute_llm_decision(decision, step_count)
                
                step_screenshot = str(self.evidence_dir / f"step_{step_count+1}_{action_type_str}.png")
                try:
                    await self.browser.take_screenshot(step_screenshot)
                except Exception:
                    pass
                    
                self.transcript.append({
                    "step": step_count + 1,
                    "decision": decision,
                    "result": result,
                    "status": "success" if success else "failed",
                    "screenshot": step_screenshot
                })
                
                if success:
                    consecutive_failures = 0
                    step_count += 1
                else:
                    consecutive_failures += 1
                    logger.warning("Action failed", error=result)
                    if consecutive_failures >= 3:
                        logger.error("Too many consecutive failures, requesting intervention")
                        resumed = await self._request_and_wait_intervention(goal, step_count, f"Action failures: {result}")
                        if resumed:
                            consecutive_failures = 0
                            continue
                        else:
                            logger.error("Human intervention timed out or failed")
                            break
        except asyncio.TimeoutError:
            logger.error("Agent timeout reached during discovery", timeout=Config.AGENT_TIMEOUT_SECONDS)
        finally:
            await self.browser.stop()
            
        # Write discovery transcript to evidence directory (redacted)
        transcript_file = self.evidence_dir / "transcript.json"
        with open(transcript_file, "w", encoding="utf-8") as f:
            json.dump(redact_sensitive_data(self.transcript), f, indent=2)
            
        execution_time = time.time() - self.start_time
        logger.info("Goal discovery run completed", 
                   steps=step_count, 
                   time_seconds=execution_time,
                   evidence_dir=str(self.evidence_dir))
                   
        # Build production artifact
        artifact = self._build_artifact(goal, capability_name, description, target_url)
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
        action_type_str = decision.get("action_type", "wait").lower()
        try:
            action_type = ActionType(action_type_str)
        except ValueError:
            action_type = ActionType.WAIT
            
        url_to_validate = None
        if action_type == ActionType.NAVIGATE:
            url_to_validate = decision.get("value") or decision.get("target_url")
            
        # Safety policy check
        is_allowed, error = self.safety.validate_action(action_type, url_to_validate)
        if not is_allowed:
            logger.error("Action not allowed by safety policy", action_type=action_type_str, error=error)
            return False, error
            
        # Build target location
        target = self._build_target_from_decision(decision)
        raw_value = decision.get("value")
        
        # Execute action in browser
        success, result = await self.browser.execute_action(
            action_type, target, raw_value
        )
        
        # Post-action URL boundary check
        if success and self.browser.page:
            current_url = self.browser.page.url
            if current_url and current_url != "about:blank" and not self.safety.is_domain_allowed(current_url):
                screenshot_path = f"logs/safety_violation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                await self.browser.take_screenshot(screenshot_path)
                return False, f"Domain boundary violation: page navigated to unallowed URL '{current_url}'"
        
        # Parameterize value if it matches an input parameter
        step_val = raw_value
        if action_type == ActionType.TYPE and step_val:
            for param_name, param_val in self.active_parameters.items():
                if str(step_val).strip() == str(param_val).strip():
                    step_val = f"{{{{{param_name}}}}}"
                    logger.info("Parameterized typed value", param=param_name, value=raw_value)
                    break
                    
        # Handle output extraction
        output_key = decision.get("output_key")
        if action_type == ActionType.EXTRACT and output_key:
            self.extracted_outputs[output_key] = result
            logger.info("Recorded extracted output", output_key=output_key, value=result)
            
        # Record the action step into the artifact sequence
        action_step = ActionStep(
            step_id=step_id + 1,
            action_type=action_type,
            target=target,
            value=step_val,
            output_key=output_key,
            description=decision.get("reasoning", f"Execute {action_type_str}"),
            risk_level=self.safety.assess_risk(action_type)
        )
        self.recorded_steps.append(action_step)
        
        # Add to history for subsequent LLM context
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
        selector = decision.get("target_selector") or decision.get("selector")
        
        if selector and selector.startswith(("#", ".")):
            return TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value=selector,
                fallback_strategies=[LocationStrategy.TEXT_CONTENT]
            )
            
        return TargetLocation(
            strategy=LocationStrategy.ACCESSIBILITY_ROLE,
            value=f"{role}:{name}" if role and name else (name or role or ""),
            role=role or None,
            name=name or None,
            fallback_strategies=[
                LocationStrategy.TEXT_CONTENT,
                LocationStrategy.SEMANTIC_SELECTOR
            ]
        )
        
    async def _request_and_wait_intervention(self, goal: str, step: int, reason: str) -> bool:
        """Request human intervention, pause session, and block waiting for resume signal."""
        screenshot_path = f"logs/intervention_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        try:
            await self.browser.take_screenshot(screenshot_path)
        except Exception:
            pass
        
        current_state = await self._get_current_state()
        run_id = f"discovery_intervention_{int(time.time())}"
        
        request = InterventionRequest(
            capability_name=goal,
            current_step=step,
            reason=reason,
            context=current_state,
            screenshot_path=screenshot_path,
            page_content=current_state.get("text_content"),
            run_id=run_id
        )
        
        self.escalation.request_intervention(request)
        result = await self.escalation.wait_for_resume(browser=self.browser, timeout=Config.AGENT_TIMEOUT_SECONDS)
        return result.get("resumed", False)
        
    def _build_artifact(self, goal: str, capability_name: str, 
                        description: str, target_url: str) -> AutomationArtifact:
        """Build the production automation artifact from recorded steps and discovered contracts."""
        metadata = ArtifactMetadata(
            target_app=target_url,
            capability_name=capability_name,
            description=description
        )
        
        # Build dynamic parameters based on caller inputs
        parameters = {}
        for p_name, p_val in self.active_parameters.items():
            parameters[p_name] = ParameterDefinition(
                type=ParameterType.STRING if isinstance(p_val, str) else ParameterType.NUMBER,
                description=f"Input parameter {p_name}",
                required=True,
                default=None
            )
        if not parameters:
            parameters["member_id"] = ParameterDefinition(
                type=ParameterType.STRING,
                description="Member ID for lookup",
                required=True,
                default=None
            )
            
        # Build dynamic outputs based on what was extracted or returned in done
        outputs = {}
        for out_name in self.extracted_outputs:
            outputs[out_name] = OutputDefinition(
                type=ParameterType.STRING,
                description=f"Extracted output {out_name}"
            )
            
        # Build checkpoint
        checkpoint = self.final_checkpoint
        if not checkpoint:
            if self.recorded_steps:
                last_step = self.recorded_steps[-1]
                checkpoint = Checkpoint(
                    step_id=last_step.step_id,
                    condition=CheckpointCondition(
                        type="element_visible",
                        target=last_step.target
                    ),
                    description="Goal completion checkpoint"
                )
            else:
                checkpoint = Checkpoint(
                    step_id=1,
                    condition=CheckpointCondition(
                        type="element_visible",
                        target=TargetLocation(strategy=LocationStrategy.SEMANTIC_SELECTOR, value="body")
                    ),
                    description="Goal completion checkpoint"
                )
                
        # Error handlers and business outcome rules
        error_handlers = [
            ErrorHandler(
                error_type=ErrorType.ELEMENT_NOT_FOUND,
                fallback_strategy="text_content_match",
                description="Fallback to text content matching"
            ),
            ErrorHandler(
                error_type=ErrorType.TIMEOUT,
                fallback_strategy="increase_wait_time",
                description="Retry with increased wait timeout"
            )
        ]
        
        business_outcome_rules = list(self.business_outcome_rules)
        
        return AutomationArtifact(
            metadata=metadata,
            parameters=parameters,
            outputs=outputs,
            steps=self.recorded_steps,
            checkpoint=checkpoint,
            error_handlers=error_handlers,
            business_outcome_rules=business_outcome_rules
        )