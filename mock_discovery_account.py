"""Mock discovery for account management capability."""
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


def create_account_management_artifact() -> AutomationArtifact:
    """Create an account management automation artifact."""
    
    metadata = ArtifactMetadata(
        target_app="http://localhost:8080",
        capability_name="account_management",
        description="Manage account information and view account details"
    )
    
    parameters = {
        "member_id": ParameterDefinition(
            type=ParameterType.STRING,
            description="Member ID for account management",
            required=True
        )
    }
    
    outputs = {
        "account_status": OutputDefinition(
            type=ParameterType.STRING,
            description="Current account status"
        ),
        "available_actions": OutputDefinition(
            type=ParameterType.ARRAY,
            description="List of available management actions"
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
                value="Account Management"
            ),
            description="Click Account Management navigation button",
            risk_level=RiskLevel.SAFE
        ),
        ActionStep(
            step_id=3,
            action_type=ActionType.TYPE,
            target=TargetLocation(
                strategy=LocationStrategy.ACCESSIBILITY_ROLE,
                value="textbox:Member ID",
                role="textbox",
                name="Member ID",
                fallback_strategies=[LocationStrategy.SEMANTIC_SELECTOR]
            ),
            value="{{member_id}}",
            description="Enter member ID for account management",
            risk_level=RiskLevel.REVERSIBLE
        ),
        ActionStep(
            step_id=4,
            action_type=ActionType.CLICK,
            target=TargetLocation(
                strategy=LocationStrategy.ACCESSIBILITY_ROLE,
                value="button:Manage Account",
                role="button",
                name="Manage Account",
                fallback_strategies=[LocationStrategy.TEXT_CONTENT]
            ),
            description="Click Manage Account button",
            risk_level=RiskLevel.RISKY
        ),
        ActionStep(
            step_id=5,
            action_type=ActionType.WAIT,
            target=TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value="#account-result"
            ),
            value="1500",
            description="Wait for account management results",
            risk_level=RiskLevel.SAFE
        ),
        ActionStep(
            step_id=6,
            action_type=ActionType.EXTRACT,
            target=TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value="#account-result",
                fallback_strategies=[LocationStrategy.TEXT_CONTENT]
            ),
            output_key="account_status",
            description="Extract account status information",
            risk_level=RiskLevel.SAFE
        )
    ]
    
    checkpoint = Checkpoint(
        step_id=6,
        condition=CheckpointCondition(
            type="element_visible",
            target=TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value="#account-result"
            ),
            text_contains="Account Management"
        ),
        description="Verify account management interface loaded"
    )
    
    error_handlers = [
        ErrorHandler(
            error_type=ErrorType.BUSINESS_OUTCOME,
            condition={"text_contains": "Member not found"},
            outcome="member_not_found",
            description="Handle non-existent member"
        ),
        ErrorHandler(
            error_type=ErrorType.ELEMENT_NOT_FOUND,
            fallback_strategy="text_content_match",
            description="Fallback to text content matching"
        ),
        ErrorHandler(
            error_type=ErrorType.PERMISSION_DENIED,
            fallback_strategy="request_permission_refresh",
            condition={"text_contains": "permission"},
            outcome="access_denied",
            description="Handle insufficient permissions for account management"
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


def save_account_management_artifact():
    """Save the account management artifact."""
    evidence_dir = Path(Config.EVIDENCE_DIR)
    artifact_dir = evidence_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    artifact = create_account_management_artifact()
    artifact_path = artifact_dir / "account_management.json"
    
    with open(artifact_path, 'w') as f:
        json.dump(artifact.model_dump(), f, indent=2)
    
    logger.info("Account management artifact saved", path=str(artifact_path))
    print(f"\n[SUCCESS] Account management artifact saved to: {artifact_path}")
    print(f"[SUCCESS] Capability: {artifact.metadata.capability_name}")
    print(f"[SUCCESS] Steps recorded: {len(artifact.steps)}")
    print(f"[SUCCESS] Parameters: {list(artifact.parameters.keys())}")
    print(f"[SUCCESS] Outputs: {list(artifact.outputs.keys())}")
    print(f"[SUCCESS] Error handlers: {len(artifact.error_handlers)}")
    
    return artifact_path


if __name__ == "__main__":
    try:
        Config.validate()
        save_account_management_artifact()
        print("\nAccount management discovery completed successfully!")
    except Exception as e:
        logger.error("Account management discovery failed", error=str(e))
        print(f"[ERROR] Account management discovery failed: {str(e)}")