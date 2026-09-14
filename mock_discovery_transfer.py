"""Mock discovery for transfer funds capability."""
import json
from datetime import datetime
from pathlib import Path
from src.artifact.schemas import (
    AutomationArtifact, ArtifactMetadata, ActionStep, ActionType, 
    LocationStrategy, TargetLocation, ParameterDefinition, OutputDefinition,
    Checkpoint, CheckpointCondition, ErrorHandler, ErrorType, ParameterType,
    RiskLevel
)
from src.utils.config import Config
from src.utils.logging import setup_logging

logger = setup_logging()


def create_transfer_artifact() -> AutomationArtifact:
    """Create a transfer funds automation artifact."""
    
    metadata = ArtifactMetadata(
        target_app="http://localhost:8080",
        capability_name="transfer_funds",
        description="Transfer funds between accounts with validation and confirmation"
    )
    
    parameters = {
        "from_account": ParameterDefinition(
            type=ParameterType.STRING,
            description="Source account number",
            required=True
        ),
        "to_account": ParameterDefinition(
            type=ParameterType.STRING,
            description="Destination account number",
            required=True
        ),
        "amount": ParameterDefinition(
            type=ParameterType.NUMBER,
            description="Transfer amount",
            required=True
        )
    }
    
    outputs = {
        "confirmation_number": OutputDefinition(
            type=ParameterType.STRING,
            description="Transaction confirmation number"
        ),
        "status": OutputDefinition(
            type=ParameterType.STRING,
            description="Transfer status (completed, failed, pending)"
        )
    }
    
    steps = [
        ActionStep(
            step_id=1,
            action_type=ActionType.NAVIGATE,
            target=TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value="http://localhost:8080"
            ),
            description="Navigate to banking system homepage",
            risk_level=RiskLevel.SAFE
        ),
        ActionStep(
            step_id=2,
            action_type=ActionType.CLICK,
            target=TargetLocation(
                strategy=LocationStrategy.TEXT_CONTENT,
                value="Transfer Funds"
            ),
            description="Click Transfer Funds navigation button",
            risk_level=RiskLevel.SAFE
        ),
        ActionStep(
            step_id=3,
            action_type=ActionType.TYPE,
            target=TargetLocation(
                strategy=LocationStrategy.ACCESSIBILITY_ROLE,
                value="textbox:From Account",
                role="textbox",
                name="From Account",
                fallback_strategies=[LocationStrategy.SEMANTIC_SELECTOR]
            ),
            value="{{from_account}}",
            description="Enter source account number",
            risk_level=RiskLevel.REVERSIBLE
        ),
        ActionStep(
            step_id=4,
            action_type=ActionType.TYPE,
            target=TargetLocation(
                strategy=LocationStrategy.ACCESSIBILITY_ROLE,
                value="textbox:To Account",
                role="textbox",
                name="To Account",
                fallback_strategies=[LocationStrategy.SEMANTIC_SELECTOR]
            ),
            value="{{to_account}}",
            description="Enter destination account number",
            risk_level=RiskLevel.REVERSIBLE
        ),
        ActionStep(
            step_id=5,
            action_type=ActionType.TYPE,
            target=TargetLocation(
                strategy=LocationStrategy.ACCESSIBILITY_ROLE,
                value="textbox:Amount",
                role="textbox",
                name="Amount",
                fallback_strategies=[LocationStrategy.SEMANTIC_SELECTOR]
            ),
            value="{{amount}}",
            description="Enter transfer amount",
            risk_level=RiskLevel.REVERSIBLE
        ),
        ActionStep(
            step_id=6,
            action_type=ActionType.CLICK,
            target=TargetLocation(
                strategy=LocationStrategy.ACCESSIBILITY_ROLE,
                value="button:Transfer",
                role="button",
                name="Transfer",
                fallback_strategies=[LocationStrategy.TEXT_CONTENT]
            ),
            description="Click Transfer button to initiate transfer",
            risk_level=RiskLevel.RISKY
        ),
        ActionStep(
            step_id=7,
            action_type=ActionType.WAIT,
            target=TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value="#transfer-result"
            ),
            value="2000",
            description="Wait for transfer processing to complete",
            risk_level=RiskLevel.SAFE
        ),
        ActionStep(
            step_id=8,
            action_type=ActionType.EXTRACT,
            target=TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value="#transfer-result",
                fallback_strategies=[LocationStrategy.TEXT_CONTENT]
            ),
            output_key="confirmation_number",
            description="Extract confirmation number from results",
            risk_level=RiskLevel.SAFE
        )
    ]
    
    checkpoint = Checkpoint(
        step_id=8,
        condition=CheckpointCondition(
            type="element_visible",
            target=TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value="#transfer-result"
            ),
            text_contains="Transfer Completed"
        ),
        description="Verify transfer completion and confirmation"
    )
    
    error_handlers = [
        ErrorHandler(
            error_type=ErrorType.BUSINESS_OUTCOME,
            condition={"text_contains": "Please fill in all fields"},
            outcome="validation_error",
            description="Handle missing required fields"
        ),
        ErrorHandler(
            error_type=ErrorType.BUSINESS_OUTCOME,
            condition={"text_contains": "Amount must be greater than 0"},
            outcome="invalid_amount",
            description="Handle invalid transfer amount"
        ),
        ErrorHandler(
            error_type=ErrorType.BUSINESS_OUTCOME,
            condition={"text_contains": "is Frozen"},
            outcome="account_frozen",
            description="Handle transfer attempted from frozen account"
        ),
        ErrorHandler(
            error_type=ErrorType.BUSINESS_OUTCOME,
            condition={"text_contains": "Insufficient funds"},
            outcome="insufficient_funds",
            description="Handle transfer exceeding available account balance"
        ),
        ErrorHandler(
            error_type=ErrorType.ELEMENT_NOT_FOUND,
            fallback_strategy="text_content_match",
            description="Fallback to text content matching"
        ),
        ErrorHandler(
            error_type=ErrorType.TIMEOUT,
            fallback_strategy="increase_wait_time",
            description="Handle slow transfer processing"
        )
    ]
    
    return AutomationArtifact(
        metadata=metadata,
        parameters=parameters,
        outputs=outputs,
        steps=steps,
        checkpoint=checkpoint,
        error_handlers=error_handlers
    )


def save_transfer_artifact():
    """Save the transfer funds artifact."""
    evidence_dir = Path(Config.EVIDENCE_DIR)
    artifact_dir = evidence_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    artifact = create_transfer_artifact()
    artifact_path = artifact_dir / "transfer_funds.json"
    
    with open(artifact_path, 'w') as f:
        json.dump(artifact.model_dump(), f, indent=2)
    
    logger.info("Transfer artifact saved", path=str(artifact_path))
    print(f"\n[SUCCESS] Transfer artifact saved to: {artifact_path}")
    print(f"[SUCCESS] Capability: {artifact.metadata.capability_name}")
    print(f"[SUCCESS] Steps recorded: {len(artifact.steps)}")
    print(f"[SUCCESS] Parameters: {list(artifact.parameters.keys())}")
    print(f"[SUCCESS] Outputs: {list(artifact.outputs.keys())}")
    print(f"[SUCCESS] Error handlers: {len(artifact.error_handlers)}")
    
    return artifact_path


if __name__ == "__main__":
    try:
        Config.validate()
        save_transfer_artifact()
        print("\nTransfer funds discovery completed successfully!")
    except Exception as e:
        logger.error("Transfer discovery failed", error=str(e))
        print(f"[ERROR] Transfer discovery failed: {str(e)}")