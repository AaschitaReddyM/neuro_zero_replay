import asyncio
import json
import os
import time
import pytest
from pathlib import Path
from src.artifact.replay_engine import ReplayEngine
from src.artifact.schemas import (
    AutomationArtifact, ExecutionStatus, RunOptions, 
    CheckpointCondition, TargetLocation, LocationStrategy
)
from src.safety.escalation import EscalationManager, ControlState

@pytest.mark.asyncio
async def test_escalation_lifecycle(tmp_path):
    mgr = EscalationManager(interventions_dir=str(tmp_path))
    assert mgr.get_control_state() == ControlState.AUTOMATION
    
    # Load account_management artifact
    with open('evidence/artifacts/account_management.json') as f:
        art_data = json.load(f)
    artifact = AutomationArtifact(**art_data)
    
    # Inject a failure in step 4 to trigger escalation
    artifact.steps[3].target.value = 'button:NonExistentBrokenButton'
    artifact.steps[3].target.name = 'NonExistentBrokenButton'
    artifact.steps[3].postcondition = CheckpointCondition(
        type="element_visible",
        target=TargetLocation(strategy=LocationStrategy.TEXT_CONTENT, value="Account Management Portal"),
        text_contains="Account Management Portal"
    )
    
    engine = ReplayEngine(escalation=mgr)
    
    async def simulate_human_operator():
        # Wait until intervention file is created
        interventions_dir = tmp_path
        found_file = None
        for _ in range(30):
            await asyncio.sleep(0.2)
            files = list(interventions_dir.glob('*.json'))
            if files:
                # Find newest
                files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                newest = files[0]
                with open(newest) as jf:
                    data = json.load(jf)
                if data.get('status') == 'pending_human_action':
                    found_file = newest
                    break
                    
        assert found_file is not None, 'Intervention record was not written to disk'
        run_id = found_file.stem
        
        # Simulate human operator acting on page (clicking real button via browser)
        if engine.browser and getattr(engine.browser, 'page', None):
            btn = engine.browser.page.get_by_role('button', name='Manage Account')
            if await btn.count() > 0:
                await btn.click()
                await engine.browser.page.wait_for_timeout(1000)
                
        # Send resume signal
        resume_file = interventions_dir / f'{run_id}.resume'
        resume_file.write_text(json.dumps({
            'notes': 'Operator located member and clicked Manage Account'
        }), encoding='utf-8')
        
    operator_task = asyncio.create_task(simulate_human_operator())
    
    # Run with RunOptions (separated from params)
    options = RunOptions(escalate=True, approve_risky=True)
    result = await engine.execute_artifact(
        artifact, 
        {'member_id': '12345'},
        options=options
    )
    
    await operator_task
    
    assert result.status == ExecutionStatus.SUCCESS
    assert result.steps_completed == 6
    assert result.outputs.get('account_status') == 'ACTIVE'


@pytest.mark.asyncio
async def test_noop_operator_does_not_pass_step(tmp_path):
    """Verify that a no-op operator resume signal does NOT pass a broken step."""
    with open('evidence/artifacts/account_management.json') as f:
        art_data = json.load(f)
    artifact = AutomationArtifact(**art_data)
    
    # Inject broken step 4 with no postcondition (must re-execute and fail)
    artifact.steps[3].target.value = 'button:NonExistentBrokenButton'
    artifact.steps[3].target.name = 'NonExistentBrokenButton'
    
    mgr = EscalationManager(interventions_dir=str(tmp_path))
    engine = ReplayEngine(escalation=mgr)
    
    async def simulate_noop_operator():
        interventions_dir = tmp_path
        found_file = None
        for _ in range(30):
            await asyncio.sleep(0.2)
            files = list(interventions_dir.glob('*.json'))
            if files:
                files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                newest = files[0]
                with open(newest) as jf:
                    data = json.load(jf)
                if data.get('status') == 'pending_human_action':
                    found_file = newest
                    break
                    
        assert found_file is not None, 'Intervention record was not written to disk'
        run_id = found_file.stem
        
        # Send resume signal WITHOUT fixing the page (no-op)
        resume_file = interventions_dir / f'{run_id}.resume'
        resume_file.write_text(json.dumps({
            'notes': 'Operator sent resume without touching or fixing the page'
        }), encoding='utf-8')
        
    operator_task = asyncio.create_task(simulate_noop_operator())
    
    options = RunOptions(escalate=True, approve_risky=True)
    result = await engine.execute_artifact(
        artifact,
        {'member_id': '12345'},
        options=options
    )
    
    await operator_task
    
    assert result.status == ExecutionStatus.FAILURE
    assert result.error_step == 4
    assert "step re-executed after operator intervention and still failed" in result.observed
