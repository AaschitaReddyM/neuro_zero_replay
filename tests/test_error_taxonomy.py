"""Test error taxonomy and disjoint terminal execution states."""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from src.artifact.replay_engine import ReplayEngine
from src.artifact.schemas import (
    AutomationArtifact, ActionStep, ActionType, TargetLocation,
    LocationStrategy, ExecutionResult, ExecutionStatus, ErrorType
)


@pytest.fixture
def replay_engine():
    return ReplayEngine()


@pytest.fixture
def sample_artifact():
    with open("evidence/artifacts/lookup_member_balance.json", "r") as f:
        data = json.load(f)
    return AutomationArtifact(**data)


@pytest.mark.asyncio
async def test_page_crash_reported_as_failure(replay_engine, sample_artifact):
    """Crash must never be classified as business outcome."""
    step = sample_artifact.steps[1]
    res = await replay_engine._handle_step_error(step, "Page crashed", sample_artifact)
    
    assert res.get("is_business_outcome") is False
    assert res.get("is_recoverable") is False
    assert "crashed" in res.get("error").lower()
    assert "expected" in res
    assert "observed" in res


@pytest.mark.asyncio
async def test_timeout_reported_as_failure_or_recoverable(replay_engine, sample_artifact):
    """Timeout error must not be reported as business outcome."""
    step = sample_artifact.steps[1]
    res = await replay_engine._handle_step_error(step, "TimeoutError: 30000ms exceeded", sample_artifact)
    
    assert res.get("is_business_outcome") is False
    # If not recovered, must be a hard failure
    if not res.get("is_recoverable"):
        assert "timeout" in res.get("error").lower()


@pytest.mark.asyncio
async def test_connection_refused_reported_as_failure(replay_engine, sample_artifact):
    """Network connection refused must be a hard failure."""
    step = sample_artifact.steps[0]
    res = await replay_engine._handle_step_error(
        step, "net::ERR_CONNECTION_REFUSED at http://localhost:8080", sample_artifact
    )
    assert res.get("is_business_outcome") is False
    assert res.get("is_recoverable") is False
    assert "ERR_CONNECTION_REFUSED" in res.get("error")


@pytest.mark.asyncio
async def test_arbitrary_exception_reported_as_failure(replay_engine, sample_artifact):
    """Unrecognized technical exceptions must be hard failures."""
    step = sample_artifact.steps[1]
    res = await replay_engine._handle_step_error(
        step, "Unrecognized memory allocation fault in v8 worker", sample_artifact
    )
    assert res.get("is_business_outcome") is False
    assert res.get("is_recoverable") is False
    assert "allocation fault" in res.get("error")


@pytest.mark.asyncio
async def test_page_shows_member_not_found_triggers_business_outcome(replay_engine, sample_artifact):
    """When the live page DOM shows 'Member not found', it must be detected as a business outcome."""
    # Mock active browser page with mock Locator returning "Member not found"
    mock_page = MagicMock()
    mock_loc = MagicMock()
    mock_loc.count = AsyncMock(return_value=1)
    mock_loc.first = MagicMock()
    mock_loc.first.is_visible = AsyncMock(return_value=True)
    mock_loc.first.inner_text = AsyncMock(return_value="Member not found. Please check the member ID and try again.")
    
    def mock_locator(selector):
        if selector == "#lookup-result":
            return mock_loc
        empty = MagicMock()
        empty.count = AsyncMock(return_value=0)
        return empty
        
    mock_page.locator = MagicMock(side_effect=mock_locator)
    replay_engine.browser.page = mock_page
    
    outcome_info = await replay_engine._detect_page_business_outcome(sample_artifact)
    assert outcome_info is not None
    assert outcome_info["outcome"] == "member_not_found"
    assert "Member not found" in outcome_info["evidence_text"]
    
    # Also verify that _handle_step_error consults page state and returns business outcome
    step = sample_artifact.steps[4]  # Step trying to extract data from missing table
    res = await replay_engine._handle_step_error(step, "Element not found", sample_artifact)
    assert res.get("is_business_outcome") is True
    assert res.get("outcome") == "member_not_found"
    assert "Member not found" in res.get("evidence_text")


def test_disjoint_execution_result_states():
    """Verify ExecutionResult disjoint terminal states contract."""
    # 1. Success state
    success_res = ExecutionResult.create_success(
        outputs={"member_name": "John Smith", "balance": 5432.5},
        execution_time=1.2,
        steps_completed=7
    )
    assert success_res.status == ExecutionStatus.SUCCESS
    assert success_res.success is True
    assert success_res.outputs["member_name"] == "John Smith"
    assert success_res.business_outcome is None
    assert success_res.error is None
    
    # 2. Business outcome state
    outcome_res = ExecutionResult.create_business_outcome(
        outcome="member_not_found",
        evidence_text="Member not found in core system",
        execution_time=0.8,
        steps_completed=3
    )
    assert outcome_res.status == ExecutionStatus.BUSINESS_OUTCOME
    assert outcome_res.success is False
    assert outcome_res.business_outcome == "member_not_found"
    assert outcome_res.evidence_text == "Member not found in core system"
    assert outcome_res.error is None
    
    # 3. Failure state
    fail_res = ExecutionResult.create_failure(
        error="TargetClosedError: Browser window closed unexpectedly",
        error_step=3,
        expected="Search button visible and clickable",
        observed="Browser target destroyed",
        execution_time=0.5,
        steps_completed=2
    )
    assert fail_res.status == ExecutionStatus.FAILURE
    assert fail_res.success is False
    assert fail_res.business_outcome is None
    assert fail_res.error_step == 3
    assert fail_res.expected == "Search button visible and clickable"
    assert "TargetClosedError" in fail_res.error
