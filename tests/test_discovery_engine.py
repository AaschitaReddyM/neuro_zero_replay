"""Tests for live capability discovery engine and dynamic parameterization."""
import pytest
import json
from pathlib import Path
from src.agent.orchestrator import AgentOrchestrator
from src.artifact.schemas import (
    AutomationArtifact, ActionStep, ActionType, TargetLocation,
    LocationStrategy, Checkpoint, CheckpointCondition, RiskLevel,
    ParameterType
)
from src.artifact.replay_engine import ReplayEngine


def test_discovery_artifact_contract_structure():
    """Verify that an artifact produced by discovery fulfills the complete schema contract."""
    orchestrator = AgentOrchestrator(headless=True)
    orchestrator.active_parameters = {"member_id": "12345"}
    orchestrator.extracted_outputs = {
        "member_name": "John Smith",
        "savings_balance": "$5432.50",
        "account_details": "Member Found\nName: John Smith"
    }
    
    orchestrator.recorded_steps = [
        ActionStep(
            step_id=1,
            action_type=ActionType.NAVIGATE,
            target=TargetLocation(strategy=LocationStrategy.SEMANTIC_SELECTOR, value="http://localhost:8080"),
            value="http://localhost:8080",
            description="Navigate to target application"
        ),
        ActionStep(
            step_id=2,
            action_type=ActionType.TYPE,
            target=TargetLocation(strategy=LocationStrategy.ACCESSIBILITY_ROLE, value="textbox:Member ID:", role="textbox", name="Member ID:"),
            value="{{member_id}}",
            description="Enter member ID"
        ),
        ActionStep(
            step_id=3,
            action_type=ActionType.CLICK,
            target=TargetLocation(strategy=LocationStrategy.ACCESSIBILITY_ROLE, value="button:Search", role="button", name="Search"),
            description="Click Search"
        ),
        ActionStep(
            step_id=4,
            action_type=ActionType.EXTRACT,
            target=TargetLocation(strategy=LocationStrategy.SEMANTIC_SELECTOR, value="#lookup-result"),
            output_key="account_details",
            description="Extract account details"
        )
    ]
    
    artifact = orchestrator._build_artifact(
        goal="Look up member 12345",
        capability_name="test_lookup",
        description="Test lookup capability",
        target_url="http://localhost:8080"
    )
    
    assert isinstance(artifact, AutomationArtifact)
    assert "member_id" in artifact.parameters
    assert artifact.parameters["member_id"].type == ParameterType.STRING
    assert "savings_balance" in artifact.outputs
    assert len(artifact.steps) == 4
    assert artifact.steps[1].value == "{{member_id}}"
    assert artifact.checkpoint is not None
    assert artifact.checkpoint.condition.target.value == "#lookup-result"
    assert len(artifact.error_handlers) >= 2
    assert len(artifact.business_outcome_rules) >= 1
    assert artifact.business_outcome_rules[0].outcome == "member_not_found"


def test_discovered_artifact_json_roundtrip():
    """Verify that an artifact can be loaded and validated from disk."""
    artifact_file = Path("evidence/artifacts/lookup_member_balance.json")
    assert artifact_file.exists(), "Discovered artifact lookup_member_balance.json must exist"
    
    replay_engine = ReplayEngine()
    loaded = replay_engine.load_artifact(str(artifact_file))
    
    assert loaded.metadata.capability_name == "lookup_member_balance"
    assert "member_id" in loaded.parameters
    assert any(s.value == "{{member_id}}" for s in loaded.steps)
    assert loaded.checkpoint.condition.text_contains == "Member Found"
    assert any(r.outcome == "member_not_found" for r in loaded.business_outcome_rules)
