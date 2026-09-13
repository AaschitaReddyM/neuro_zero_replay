"""Test error scenarios and business outcome handling."""
import json
from pathlib import Path
from src.artifact.schemas import AutomationArtifact, ErrorType
from src.utils.logging import setup_logging

# Setup logging
logger = setup_logging()


def test_business_outcome_detection():
    """Test detection of business outcomes vs system failures."""
    print("Testing Business Outcome Detection")
    print("=" * 60)
    
    artifact_path = Path("evidence/artifacts/lookup_member_balance.json")
    
    with open(artifact_path, 'r') as f:
        data = json.load(f)
        
    artifact = AutomationArtifact(**data)
    
    # Simulate different error scenarios
    test_scenarios = [
        {
            "error_message": "Member not found. Please check the member ID and try again.",
            "expected_type": "business_outcome",
            "description": "Member doesn't exist (legitimate business outcome)"
        },
        {
            "error_message": "Element not found: button with role 'button' and name 'Search'",
            "expected_type": "element_not_found",
            "description": "UI element missing (system failure)"
        },
        {
            "error_message": "Timeout waiting for element #lookup-result to be visible",
            "expected_type": "timeout",
            "description": "Element didn't appear in time (system failure)"
        },
        {
            "error_message": "Permission denied: User does not have access to this resource",
            "expected_type": "permission_denied",
            "description": "Access denied (system failure)"
        }
    ]
    
    for scenario in test_scenarios:
        error_msg = scenario["error_message"]
        expected = scenario["expected_type"]
        description = scenario["description"]
        
        print(f"\nScenario: {description}")
        print(f"Error message: {error_msg}")
        
        # Find matching error handler
        matched_handler = None
        for handler in artifact.error_handlers:
            # Handle both enum and string cases
            handler_type = handler.error_type if isinstance(handler.error_type, str) else handler.error_type.value
            if handler_type == expected:
                matched_handler = handler
                break
        
        if matched_handler:
            print(f"[MATCH] Found handler for {expected}")
            print(f"[INFO] Handler description: {matched_handler.description}")
            
            if matched_handler.condition and "text_contains" in matched_handler.condition:
                condition_text = matched_handler.condition["text_contains"]
                if condition_text.lower() in error_msg.lower():
                    print(f"[SUCCESS] Condition matches: '{condition_text}' found in error message")
                    if matched_handler.outcome:
                        print(f"[INFO] Business outcome: {matched_handler.outcome}")
                else:
                    print(f"[INFO] Condition doesn't match: '{condition_text}' not in error message")
        else:
            print(f"[NO MATCH] No handler found for {expected}")
            print(f"[INFO] This would be treated as a hard failure")
    
    print("\n" + "=" * 60)
    print("Business outcome detection test completed")


def test_parameter_validation():
    """Test parameter validation scenarios."""
    print("\nTesting Parameter Validation")
    print("=" * 60)
    
    artifact_path = Path("evidence/artifacts/lookup_member_balance.json")
    
    with open(artifact_path, 'r') as f:
        data = json.load(f)
        
    artifact = AutomationArtifact(**data)
    
    test_cases = [
        {
            "params": {"member_id": "12345"},
            "should_pass": True,
            "description": "Valid parameters"
        },
        {
            "params": {"member_id": "67890"},
            "should_pass": True,
            "description": "Different valid member ID"
        },
        {
            "params": {},
            "should_pass": False,
            "description": "Missing required parameter"
        },
        {
            "params": {"member_id": ""},
            "should_pass": True,  # Empty string is technically valid
            "description": "Empty member ID"
        },
        {
            "params": {"member_id": "99999", "extra_param": "value"},
            "should_pass": True,  # Extra params are ignored
            "description": "Extra parameter (should be ignored)"
        }
    ]
    
    for test_case in test_cases:
        params = test_case["params"]
        should_pass = test_case["should_pass"]
        description = test_case["description"]
        
        print(f"\nTest: {description}")
        print(f"Parameters: {params}")
        
        try:
            validated = artifact.get_parameter_values(params)
            if should_pass:
                print(f"[SUCCESS] Validation passed as expected")
                print(f"[INFO] Validated parameters: {validated}")
            else:
                print(f"[ERROR] Validation passed but should have failed")
        except ValueError as e:
            if not should_pass:
                print(f"[SUCCESS] Validation failed as expected")
                print(f"[INFO] Error: {str(e)}")
            else:
                print(f"[ERROR] Validation failed but should have passed")
                print(f"[INFO] Error: {str(e)}")
    
    print("\n" + "=" * 60)
    print("Parameter validation test completed")


def test_step_risk_assessment():
    """Test risk level assessment for steps."""
    print("\nTesting Step Risk Assessment")
    print("=" * 60)
    
    artifact_path = Path("evidence/artifacts/lookup_member_balance.json")
    
    with open(artifact_path, 'r') as f:
        data = json.load(f)
        
    artifact = AutomationArtifact(**data)
    
    print(f"\nStep risk levels:")
    for step in artifact.steps:
        risk_level = step.risk_level
        action_type = step.action_type.value
        description = step.description
        
        print(f"Step {step.step_id}: {action_type} - Risk: {risk_level}")
        print(f"  Description: {description}")
        
        # Assess if risk level is appropriate
        if action_type in ["navigate", "extract", "wait"]:
            if risk_level == "safe":
                print(f"  [APPROPRIATE] {action_type} is correctly marked as safe")
            else:
                print(f"  [WARNING] {action_type} should be safe but is marked as {risk_level}")
        elif action_type in ["click", "type"]:
            if risk_level in ["safe", "reversible"]:
                print(f"  [APPROPRIATE] {action_type} is appropriately marked")
            else:
                print(f"  [INFO] {action_type} marked as {risk_level} (may need review)")
    
    print("\n" + "=" * 60)
    print("Risk assessment test completed")


def main():
    """Run all error scenario tests."""
    print("=" * 60)
    print("Computer-Use Automation System - Error Scenario Tests")
    print("=" * 60)
    
    try:
        test_business_outcome_detection()
        test_parameter_validation()
        test_step_risk_assessment()
        
        print("\n" + "=" * 60)
        print("[SUCCESS] All error scenario tests completed")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n[ERROR] Test execution failed: {str(e)}")
        logger.error("Error scenario tests failed", error=str(e))
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())