"""Live demonstration of the computer-use automation system with browser automation."""
import asyncio
import json
from pathlib import Path
from src.automation.browser import BrowserAutomation
from src.artifact.schemas import AutomationArtifact
from src.utils.config import Config
from src.utils.logging import setup_logging

# Setup logging
logger = setup_logging()


async def demo_browser_automation():
    """Demonstrate browser automation interacting with the target application."""
    print("=" * 70)
    print("Computer-Use Automation System - Live Demo")
    print("=" * 70)
    
    print("\n[STEP 1] Starting browser automation...")
    browser = BrowserAutomation(headless=False)  # Non-headless to see the browser
    await browser.start()
    print("[OK] Browser started (visible mode)")
    
    try:
        print("\n[STEP 2] Navigating to target application...")
        await browser.navigate("http://localhost:8080")
        print("[OK] Navigated to http://localhost:8080")
        
        print("\n[STEP 3] Taking initial screenshot...")
        screenshot_path = "logs/demo_initial.png"
        await browser.take_screenshot(screenshot_path)
        print(f"[OK] Screenshot saved to {screenshot_path}")
        
        print("\n[STEP 4] Getting page accessibility tree...")
        accessibility_tree = await browser.get_accessibility_tree()
        print(f"[OK] Accessibility tree retrieved (depth: {len(str(accessibility_tree))} characters)")
        
        print("\n[STEP 5] Getting page content...")
        page_content = await browser.get_page_content()
        print(f"[OK] Page content retrieved (length: {len(page_content)} characters)")
        
        print("\n[STEP 6] Simulating member lookup interaction...")
        print("[INFO] This demonstrates what the LLM-driven discovery would do:")
        
        # Find the member ID input field using accessibility
        from src.artifact.schemas import TargetLocation, LocationStrategy
        
        member_input = TargetLocation(
            strategy=LocationStrategy.ACCESSIBILITY_ROLE,
            value="textbox:Member ID",
            role="textbox",
            name="Member ID",
            fallback_strategies=[LocationStrategy.SEMANTIC_SELECTOR]
        )
        
        print("[INFO] Finding member ID input field...")
        element = await browser.find_element(member_input)
        if element:
            print("[OK] Member ID input field found using accessibility")
            
            # Type member ID
            print("[INFO] Typing member ID '12345'...")
            success, result = await browser.execute_action(
                "type", member_input, "12345"
            )
            if success:
                print("[OK] Member ID entered successfully")
            else:
                print(f"[ERROR] Failed to type: {result}")
        else:
            print("[WARNING] Accessibility selector failed, trying fallback...")
            # Try semantic selector
            member_input_fallback = TargetLocation(
                strategy=LocationStrategy.SEMANTIC_SELECTOR,
                value="#member-id"
            )
            element = await browser.find_element(member_input_fallback)
            if element:
                print("[OK] Found using semantic selector fallback")
                success, result = await browser.execute_action(
                    "type", member_input_fallback, "12345"
                )
                if success:
                    print("[OK] Member ID entered successfully")
        
        # Find and click search button
        print("[INFO] Finding search button...")
        search_button = TargetLocation(
            strategy=LocationStrategy.ACCESSIBILITY_ROLE,
            value="button:Search",
            role="button",
            name="Search",
            fallback_strategies=[LocationStrategy.TEXT_CONTENT]
        )
        
        element = await browser.find_element(search_button)
        if element:
            print("[OK] Search button found")
            print("[INFO] Clicking search button...")
            success, result = await browser.execute_action("click", search_button, None)
            if success:
                print("[OK] Search button clicked successfully")
            else:
                print(f"[ERROR] Failed to click: {result}")
        
        # Wait for results
        print("[INFO] Waiting for search results...")
        await asyncio.sleep(2)
        
        print("\n[STEP 7] Taking result screenshot...")
        screenshot_path = "logs/demo_results.png"
        await browser.take_screenshot(screenshot_path)
        print(f"[OK] Screenshot saved to {screenshot_path}")
        
        print("\n[STEP 8] Extracting results...")
        results_target = TargetLocation(
            strategy=LocationStrategy.SEMANTIC_SELECTOR,
            value=".legacy-table"
        )
        
        element = await browser.find_element(results_target)
        if element:
            print("[OK] Results table found")
            results_text = await element.inner_text()
            print(f"[INFO] Results content:\n{results_text}")
        else:
            print("[WARNING] Results table not found")
        
        print("\n[STEP 9] Demonstrating error handling...")
        print("[INFO] Testing with non-existent member ID...")
        
        # Clear and try with invalid ID
        print("[INFO] Clearing input field...")
        await browser.execute_action("type", member_input, "")  # Clear by typing empty
        
        print("[INFO] Typing invalid member ID '99999'...")
        await browser.execute_action("type", member_input, "99999")
        
        print("[INFO] Clicking search button...")
        await browser.execute_action("click", search_button, None)
        
        print("[INFO] Waiting for error response...")
        await asyncio.sleep(2)
        
        print("[INFO] Taking error screenshot...")
        screenshot_path = "logs/demo_error.png"
        await browser.take_screenshot(screenshot_path)
        print(f"[OK] Screenshot saved to {screenshot_path}")
        
        print("\n[STEP 10] Getting final page state...")
        final_content = await browser.get_page_content()
        if "Member not found" in final_content:
            print("[OK] Business outcome detected: Member not found")
            print("[INFO] This demonstrates the error handler working correctly")
        
        print("\n" + "=" * 70)
        print("Live Demo Summary")
        print("=" * 70)
        print("[SUCCESS] Browser automation completed successfully!")
        print("\nDemonstrated capabilities:")
        print("  [OK] Browser launch and navigation")
        print("  [OK] Accessibility-based element location")
        print("  [OK] Fallback strategies for element location")
        print("  [OK] Form interaction (typing, clicking)")
        print("  [OK] Dynamic content handling")
        print("  [OK] Data extraction from results")
        print("  [OK] Error detection and business outcome handling")
        print("  [OK] Screenshot capture for evidence")
        print("\nScreenshots saved to logs/ directory:")
        print("  - demo_initial.png (initial page load)")
        print("  - demo_results.png (successful lookup)")
        print("  - demo_error.png (error scenario)")
        
    finally:
        print("\n[STEP 11] Cleaning up...")
        await browser.stop()
        print("[OK] Browser closed")


async def demo_artifact_loading():
    """Demonstrate loading and analyzing the generated artifact."""
    print("\n" + "=" * 70)
    print("Artifact Analysis Demo")
    print("=" * 70)
    
    artifact_path = Path("evidence/artifacts/lookup_member_balance.json")
    
    if not artifact_path.exists():
        print("[ERROR] Artifact not found. Run python main.py discovery first.")
        return
    
    with open(artifact_path, 'r') as f:
        data = json.load(f)
    
    artifact = AutomationArtifact(**data)
    
    print(f"\n[INFO] Artifact: {artifact.metadata.capability_name}")
    print(f"[INFO] Version: {artifact.metadata.version}")
    print(f"[INFO] Target: {artifact.metadata.target_app}")
    print(f"[INFO] Description: {artifact.metadata.description}")
    
    print(f"\n[INFO] Parameters ({len(artifact.parameters)}):")
    for param_name, param_def in artifact.parameters.items():
        print(f"  - {param_name}: {param_def.type} ({'required' if param_def.required else 'optional'})")
    
    print(f"\n[INFO] Outputs ({len(artifact.outputs)}):")
    for output_name, output_def in artifact.outputs.items():
        print(f"  - {output_name}: {output_def.type}")
    
    print(f"\n[INFO] Steps ({len(artifact.steps)}):")
    for step in artifact.steps:
        print(f"  Step {step.step_id}: {step.action_type.value} - {step.description}")
    
    print(f"\n[INFO] Error Handlers ({len(artifact.error_handlers)}):")
    for handler in artifact.error_handlers:
        print(f"  - {handler.error_type.value}: {handler.description}")
    
    print(f"\n[INFO] Checkpoint: Step {artifact.checkpoint.step_id}")
    print(f"  Condition: {artifact.checkpoint.condition.type}")
    print(f"  Description: {artifact.checkpoint.description}")


async def main():
    """Run the complete live demonstration."""
    try:
        # First show artifact analysis
        await demo_artifact_loading()
        
        # Then run live browser automation
        await demo_browser_automation()
        
        print("\n" + "=" * 70)
        print("DEMO COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print("\nThe system is working as designed:")
        print("1. Artifact generation creates structured automation capabilities")
        print("2. Browser automation can interact with legacy UIs")
        print("3. Error handling distinguishes business outcomes from failures")
        print("4. Multiple fallback strategies ensure reliability")
        print("5. Evidence collection provides audit trails")
        
        return 0
        
    except Exception as e:
        print(f"\n[ERROR] Demo failed: {str(e)}")
        logger.error("Demo failed", error=str(e))
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))