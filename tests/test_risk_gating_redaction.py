import pytest
from src.artifact.schemas import (
    AutomationArtifact, ActionStep, ActionType, TargetLocation, LocationStrategy,
    RiskLevel, Checkpoint, CheckpointCondition, ArtifactMetadata, ExecutionStatus
)
from src.safety.guardrails import redact_sensitive_data, SafetyGuardrails
from src.artifact.replay_engine import ReplayEngine

def test_recursive_pii_redaction():
    payload = {
        'user': {
            'name': 'Alice',
            'ssn': '123-45-6789',
            'accounts': [
                {'account_number': '987654321012', 'type': 'checking'},
                {'note': 'Account 1234567890123 has active hold'}
            ]
        },
        'auth': {
            'header': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9',
            'api_key': 'sk-ant-api03-abcdef1234567890abcdef123456'
        }
    }
    
    redacted = redact_sensitive_data(payload)
    
    assert redacted['user']['ssn'] == '***REDACTED***'
    assert redacted['user']['accounts'][0]['account_number'] == '***REDACTED***'
    assert '1234567890123' not in redacted['user']['accounts'][1]['note']
    assert '***REDACTED_ACCT***' in redacted['user']['accounts'][1]['note']
    assert redacted['auth']['header'] == 'Bearer ***REDACTED***'
    assert redacted['auth']['api_key'] == '***REDACTED***'

@pytest.mark.asyncio
async def test_replay_halts_on_unapproved_risky_step():
    engine = ReplayEngine()
    artifact = AutomationArtifact(
        metadata=ArtifactMetadata(
            target_app='http://localhost:8080',
            capability_name='test_risky_gate',
            description='Test risky gating'
        ),
        parameters={},
        outputs={},
        steps=[
            ActionStep(
                step_id=1,
                action_type=ActionType.CLICK,
                target=TargetLocation(
                    strategy=LocationStrategy.SEMANTIC_SELECTOR,
                    value='#risky-btn'
                ),
                risk_level=RiskLevel.RISKY,
                description='High stakes button'
            )
        ],
        checkpoint=Checkpoint(
            step_id=1,
            condition=CheckpointCondition(type='element_visible', target=TargetLocation(strategy=LocationStrategy.SEMANTIC_SELECTOR, value='#done')),
            description='Done'
        )
    )
    
    result = await engine.execute_artifact(artifact, {})
    assert result.status == ExecutionStatus.NEEDS_CONFIRMATION
    assert result.success is False
    assert result.error_step == 1
    assert 'risky' in result.error
