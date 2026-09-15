"""Tests for RunOptions separation from business parameters (Phase R1)."""
import pytest
import json
from pathlib import Path
from src.artifact.replay_engine import ReplayEngine
from src.artifact.schemas import AutomationArtifact, ExecutionStatus, RunOptions


@pytest.mark.asyncio
async def test_self_approval_via_params_rejected():
    """Verify that passing approve_risky in params fails validation and does not approve risky steps."""
    artifact_path = Path("evidence/artifacts/transfer_funds.json")
    assert artifact_path.exists(), "transfer_funds.json artifact missing"
    
    with open(artifact_path, "r", encoding="utf-8") as f:
        artifact = AutomationArtifact(**json.load(f))
    
    engine = ReplayEngine()
    
    # Passing approve_risky in params must fail parameter validation
    params = {
        "from_account": "1001",
        "to_account": "1002",
        "amount": "50",
        "approve_risky": True
    }
    result = await engine.execute_artifact(artifact, params)
    
    assert result.status == ExecutionStatus.FAILURE, f"Expected FAILURE, got {result.status}"
    assert "Parameter validation failed" in result.error
    assert "unknown parameter(s): approve_risky" in result.error
    assert result.steps_completed == 0


@pytest.mark.asyncio
async def test_approval_via_run_options_allowed():
    """Verify that passing approve_risky via RunOptions authorizes risky actions without polluting params."""
    artifact_path = Path("evidence/artifacts/transfer_funds.json")
    assert artifact_path.exists(), "transfer_funds.json artifact missing"
    
    with open(artifact_path, "r", encoding="utf-8") as f:
        artifact = AutomationArtifact(**json.load(f))
    
    engine = ReplayEngine()
    
    # Clean business params only
    params = {
        "from_account": "1001",
        "to_account": "1002",
        "amount": "50"
    }
    
    # Without options: must trigger confirmation gate
    result_unapproved = await engine.execute_artifact(artifact, params)
    assert result_unapproved.status == ExecutionStatus.NEEDS_CONFIRMATION
    assert result_unapproved.error_step == 6  # Transfer click step is marked risky
    
    # With explicit RunOptions: permits risky action
    options = RunOptions(approve_risky=True, approved_by="automated_test")
    result_approved = await engine.execute_artifact(artifact, params, options=options)
    assert result_approved.status == ExecutionStatus.SUCCESS
    assert result_approved.steps_completed == 8
