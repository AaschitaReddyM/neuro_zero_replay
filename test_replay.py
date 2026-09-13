"""Test script to demonstrate replay functionality without full browser automation."""
import json
import sys
from pathlib import Path
from src.artifact.schemas import AutomationArtifact
from src.utils.config import Config
from src.utils.logging import setup_logging

# Setup logging
logger = setup_logging()


def test_artifact_loading():
    """Test that we can load and validate the artifact."""
    try:
        artifact_path = Path("evidence/artifacts/lookup_member_balance.json")
        
        if not artifact_path.exists():
            print(f"[ERROR] Artifact not found at {artifact_path}")
            return False
            
        with open(artifact_path, 'r') as f:
            data = json.load(f)
            
        # Validate with Pydantic
        artifact = AutomationArtifact(**data)
        
        print(f"[SUCCESS] Artifact loaded and validated successfully")
        print(f"[INFO] Capability: {artifact.metadata.capability_name}")
        print(f"[INFO] Version: {artifact.metadata.version}")
        print(f"[INFO] Target app: {artifact.metadata.target_app}")
        print(f"[INFO] Steps: {len(artifact.steps)}")
        print(f"[INFO] Parameters: {list(artifact.parameters.keys())}")
        print(f"[INFO] Outputs: {list(artifact.outputs.keys())}")
        print(f"[INFO] Error handlers: {len(artifact.error_handlers)}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to load artifact: {str(e)}")
        logger.error("Artifact loading failed", error=str(e))
        return False


def test_parameter_substitution():
    """Test parameter substitution in artifact steps."""
    try:
        artifact_path = Path("evidence/artifacts/lookup_member_balance.json")
        
        with open(artifact_path, 'r') as f:
            data = json.load(f)
            
        artifact = AutomationArtifact(**data)
        
        # Test parameter substitution
        test_params = {"member_id": "12345"}
        validated_params = artifact.get_parameter_values(test_params)
        
        print(f"[SUCCESS] Parameter validation passed")
        print(f"[INFO] Validated parameters: {validated_params}")
        
        # Test substitution in a step with parameters
        for step in artifact.steps:
            if step.value and "{{member_id}}" in step.value:
                substituted = artifact.substitute_parameters(step.value, test_params)
                print(f"[INFO] Step {step.step_id}: Original value: {step.value}")
                print(f"[INFO] Step {step.step_id}: Substituted value: {substituted}")
                
                if substituted == "12345":
                    print(f"[SUCCESS] Parameter substitution works correctly")
                else:
                    print(f"[ERROR] Parameter substitution failed")
                    return False
                    
        return True
        
    except Exception as e:
        print(f"[ERROR] Parameter substitution test failed: {str(e)}")
        logger.error("Parameter substitution test failed", error=str(e))
        return False


def test_error_handler_structure():
    """Test that error handlers are properly structured."""
    try:
        artifact_path = Path("evidence/artifacts/lookup_member_balance.json")
        
        with open(artifact_path, 'r') as f:
            data = json.load(f)
            
        artifact = AutomationArtifact(**data)
        
        print(f"[INFO] Error handlers in artifact:")
        for handler in artifact.error_handlers:
            print(f"[INFO] - Type: {handler.error_type}")
            print(f"[INFO]   Description: {handler.description}")
            if handler.fallback_strategy:
                print(f"[INFO]   Fallback: {handler.fallback_strategy}")
            if handler.outcome:
                print(f"[INFO]   Outcome: {handler.outcome}")
                
        # Check for business outcome handler
        business_outcome_handlers = [h for h in artifact.error_handlers if str(h.error_type) == "business_outcome" or h.error_type.value == "business_outcome"]
        if business_outcome_handlers:
            print(f"[SUCCESS] Business outcome handler found (member_not_found case)")
        else:
            print(f"[WARNING] No business outcome handler found")
            
        return True
        
    except Exception as e:
        print(f"[ERROR] Error handler structure test failed: {str(e)}")
        logger.error("Error handler test failed", error=str(e))
        return False


def test_checkpoint_structure():
    """Test that checkpoint is properly structured."""
    try:
        artifact_path = Path("evidence/artifacts/lookup_member_balance.json")
        
        with open(artifact_path, 'r') as f:
            data = json.load(f)
            
        artifact = AutomationArtifact(**data)
        
        print(f"[INFO] Checkpoint structure:")
        print(f"[INFO] - Step ID: {artifact.checkpoint.step_id}")
        print(f"[INFO] - Condition type: {artifact.checkpoint.condition.type}")
        print(f"[INFO] - Target strategy: {artifact.checkpoint.condition.target.strategy}")
        print(f"[INFO] - Text contains: {artifact.checkpoint.condition.text_contains}")
        print(f"[INFO] - Description: {artifact.checkpoint.description}")
        
        # Verify checkpoint refers to a valid step
        step_ids = [step.step_id for step in artifact.steps]
        if artifact.checkpoint.step_id in step_ids:
            print(f"[SUCCESS] Checkpoint refers to valid step {artifact.checkpoint.step_id}")
        else:
            print(f"[ERROR] Checkpoint refers to invalid step {artifact.checkpoint.step_id}")
            return False
            
        return True
        
    except Exception as e:
        print(f"[ERROR] Checkpoint structure test failed: {str(e)}")
        logger.error("Checkpoint test failed", error=str(e))
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Computer-Use Automation System - Replay Tests")
    print("=" * 60)
    
    try:
        Config.validate()
    except ValueError as e:
        print(f"[ERROR] Configuration validation failed: {str(e)}")
        sys.exit(1)
    
    tests = [
        ("Artifact Loading", test_artifact_loading),
        ("Parameter Substitution", test_parameter_substitution),
        ("Error Handler Structure", test_error_handler_structure),
        ("Checkpoint Structure", test_checkpoint_structure)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'=' * 60}")
        print(f"Running: {test_name}")
        print(f"{'=' * 60}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"[ERROR] Test crashed: {str(e)}")
            results.append((test_name, False))
    
    # Summary
    print(f"\n{'=' * 60}")
    print("Test Summary")
    print(f"{'=' * 60}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n[SUCCESS] All tests passed!")
        return 0
    else:
        print(f"\n[ERROR] {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())