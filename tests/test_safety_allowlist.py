"""Test safety allowlist validation on resolved URLs and post-action boundaries."""
import pytest
import copy
from unittest.mock import AsyncMock, MagicMock
from src.artifact.replay_engine import ReplayEngine
from src.artifact.schemas import (
    AutomationArtifact, ArtifactMetadata, ActionStep, ActionType,
    TargetLocation, LocationStrategy, ParameterDefinition, ParameterType,
    Checkpoint, CheckpointCondition, ExecutionStatus
)
from src.safety.guardrails import SafetyGuardrails


def create_parameterized_navigation_artifact():
    return AutomationArtifact(
        metadata=ArtifactMetadata(
            target_app="http://localhost:8080",
            capability_name="test_navigation_security",
            description="Test that parameterized navigation validates resolved URLs"
        ),
        parameters={
            "target_url": ParameterDefinition(
                type=ParameterType.STRING,
                description="Target URL to navigate to"
            )
        },
        outputs={},
        steps=[
            ActionStep(
                step_id=1,
                action_type=ActionType.NAVIGATE,
                target=TargetLocation(
                    strategy=LocationStrategy.SEMANTIC_SELECTOR,
                    value="http://localhost:8080"
                ),
                value="{{target_url}}",
                description="Navigate to parameterized URL"
            )
        ],
        checkpoint=Checkpoint(
            step_id=1,
            condition=CheckpointCondition(
                target=TargetLocation(
                    strategy=LocationStrategy.SEMANTIC_SELECTOR,
                    value="body"
                )
            ),
            description="Checkpoint for navigation"
        ),
        error_handlers=[]
    )


@pytest.mark.asyncio
async def test_replay_refuses_disallowed_resolved_url():
    """Replay must refuse before navigating when parameterized URL is outside allowlist."""
    engine = ReplayEngine()
    artifact = create_parameterized_navigation_artifact()
    
    # Store original value to verify immutability
    original_step_value = artifact.steps[0].value
    
    result = await engine.execute_artifact(
        artifact=artifact,
        parameters={"target_url": "http://attacker.example/exfil"}
    )
    
    # Replay must fail with safety policy violation
    assert result.status == ExecutionStatus.FAILURE
    assert result.success is False
    assert "Safety policy violation" in result.error
    assert "attacker.example" in result.error or "attacker.example" in str(result.observed)
    
    # Artifact must NOT be mutated in-memory
    assert artifact.steps[0].value == original_step_value, "Artifact was mutated in-memory during replay!"


@pytest.mark.asyncio
async def test_post_action_boundary_check():
    """If browser leaves the allowlist after an action, replay must immediately abort."""
    engine = ReplayEngine()
    artifact = create_parameterized_navigation_artifact()
    
    # Mock browser so step execution succeeds but current_page_url is attacker site
    mock_browser = MagicMock()
    mock_browser.start = AsyncMock()
    mock_browser.stop = AsyncMock()
    mock_browser.navigate = AsyncMock()
    mock_browser.take_screenshot = AsyncMock()
    
    mock_page = MagicMock()
    mock_page.url = "http://untrusted-external-site.com/login"
    mock_browser.page = mock_page
    
    async def mock_execute_step(step, params):
        return True, None
        
    engine.browser = mock_browser
    engine._execute_step = mock_execute_step
    
    # Run with allowed parameter so pre-check passes
    result = await engine.execute_artifact(
        artifact=artifact,
        parameters={"target_url": "http://localhost:8080/safe-page"}
    )
    
    assert result.status == ExecutionStatus.FAILURE
    assert "boundary violation" in result.error.lower()
    assert "untrusted-external-site.com" in result.error
