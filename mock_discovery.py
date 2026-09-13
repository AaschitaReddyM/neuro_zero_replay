"""Mock discovery for demonstration purposes (simulates LLM-driven discovery)."""
import asyncio
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

# Setup logging
logger = setup_logging()


def create_mock_artifact() -> AutomationArtifact:
    """Create a mock artifact simulating a successful discovery run."""
    
    # Metadata
    metadata = ArtifactMetadata(
        target_app="http://localhost:8080",
        capability_name="lookup_member_balance",
        description="Look up a member by ID and retrieve their account balance and status"
    )
    
    # Parameters
    parameters = {
        "member_id": ParameterDefinition(
            type=ParameterType.STRING,
            description="Member ID to look up",
            required=True
        )
    }
    
    # Outputs
    outputs = {
        "member_name": OutputDefinition(
            type=ParameterType.STRING,
            description="Full name of the member"
        ),
        "balance": OutputDefinition(
            type=ParameterType.NUMBER,
            description="Current account balance"
        ),
        "status": OutputDefinition(
            type=ParameterType.STRING,
            description="Account status (Active, Frozen, Closed)"
        )
    }
    
    # Steps simulating what the LLM would discover
    steps = [
        ActionStep(
            step_id=1,
            action_type=ActionType.NAVIGATE,
            target=TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value="http://localhost:8080"
            ),
            description="Navigate to the banking system homepage",
            risk_level=RiskLevel.SAFE
        ),
        ActionStep(
            step_id=2,
            action_type=ActionType.TYPE,
            target=TargetLocation(
                strategy=LocationStrategy.ACCESSIBILITY_ROLE,
                value="textbox:Member ID",
                role="textbox",
                name="Member ID",
                fallback_strategies=[LocationStrategy.SEMANTIC_SELECTOR]
            ),
            value="{{member_id}}",
            description="Enter the member ID in the search field",
            risk_level=RiskLevel.SAFE
        ),
        ActionStep(
            step_id=3,
            action_type=ActionType.CLICK,
            target=TargetLocation(
                strategy=LocationStrategy.ACCESSIBILITY_ROLE,
                value="button:Search",
                role="button",
                name="Search",
                fallback_strategies=[LocationStrategy.TEXT_CONTENT]
            ),
            description="Click the Search button to look up the member",
            risk_level=RiskLevel.SAFE
        ),
        ActionStep(
            step_id=4,
            action_type=ActionType.WAIT,
            target=TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value="#lookup-result"
            ),
            value="2000",
            description="Wait for the search results to appear",
            risk_level=RiskLevel.SAFE
        ),
        ActionStep(
            step_id=5,
            action_type=ActionType.EXTRACT,
            target=TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value=".legacy-table tr:nth-child(1) td:nth-child(2)",
                fallback_strategies=[LocationStrategy.TEXT_CONTENT]
            ),
            output_key="member_name",
            description="Extract the member name from the results table",
            risk_level=RiskLevel.SAFE
        ),
        ActionStep(
            step_id=6,
            action_type=ActionType.EXTRACT,
            target=TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value=".legacy-table tr:nth-child(3) td:nth-child(2)",
                fallback_strategies=[LocationStrategy.TEXT_CONTENT]
            ),
            output_key="balance",
            description="Extract the account balance from the results table",
            risk_level=RiskLevel.SAFE
        ),
        ActionStep(
            step_id=7,
            action_type=ActionType.EXTRACT,
            target=TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value=".legacy-table tr:nth-child(2) td:nth-child(2)",
                fallback_strategies=[LocationStrategy.TEXT_CONTENT]
            ),
            output_key="status",
            description="Extract the account status from the results table",
            risk_level=RiskLevel.SAFE
        )
    ]
    
    # Checkpoint
    checkpoint = Checkpoint(
        step_id=7,
        condition=CheckpointCondition(
            type="element_visible",
            target=TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value=".legacy-table"
            ),
            text_contains="Member Found"
        ),
        description="Verify that member results are displayed"
    )
    
    # Error handlers
    error_handlers = [
        ErrorHandler(
            error_type=ErrorType.BUSINESS_OUTCOME,
            condition={"text_contains": "Member not found"},
            outcome="member_not_found",
            description="Handle the case where the member doesn't exist"
        ),
        ErrorHandler(
            error_type=ErrorType.ELEMENT_NOT_FOUND,
            fallback_strategy="text_content_match",
            description="Try finding elements by text content if accessibility fails"
        ),
        ErrorHandler(
            error_type=ErrorType.TIMEOUT,
            fallback_strategy="increase_wait_time",
            condition={"text_contains": "timeout"},
            description="Handle slow page loads by increasing wait time"
        ),
        ErrorHandler(
            error_type=ErrorType.PERMISSION_DENIED,
            fallback_strategy="request_permission_refresh",
            condition={"text_contains": "permission"},
            outcome="access_denied",
            description="Handle access permission issues"
        ),
        ErrorHandler(
            error_type=ErrorType.SESSION_EXPIRED,
            fallback_strategy="retry_with_refresh",
            condition={"text_contains": "session"},
            outcome="session_timeout",
            description="Handle session expiration by retrying after refresh"
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


def save_mock_artifact():
    """Save the mock artifact to the evidence directory."""
    # Ensure evidence directory exists
    evidence_dir = Path(Config.EVIDENCE_DIR)
    artifact_dir = evidence_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    # Create mock artifact
    artifact = create_mock_artifact()
    
    # Save to file
    artifact_path = artifact_dir / "lookup_member_balance.json"
    with open(artifact_path, 'w') as f:
        json.dump(artifact.model_dump(), f, indent=2)
    
    logger.info("Mock artifact saved", path=str(artifact_path))
    print(f"\n[SUCCESS] Mock artifact saved to: {artifact_path}")
    print(f"[SUCCESS] Capability: {artifact.metadata.capability_name}")
    print(f"[SUCCESS] Steps recorded: {len(artifact.steps)}")
    print(f"[SUCCESS] Parameters: {list(artifact.parameters.keys())}")
    print(f"[SUCCESS] Outputs: {list(artifact.outputs.keys())}")
    print(f"[SUCCESS] Error handlers: {len(artifact.error_handlers)}")
    
    return artifact_path


if __name__ == "__main__":
    try:
        Config.validate()
        artifact_path = save_mock_artifact()
        print(f"\nMock discovery completed successfully!")
        print(f"You can now run replay using: python main.py replay --artifact {artifact_path} --params '{{\"member_id\": \"12345\"}}'")
    except Exception as e:
        logger.error("Mock discovery failed", error=str(e))
        print(f"[ERROR] Mock discovery failed: {str(e)}")