"""Main entry point for the computer-use automation system."""
import asyncio
import sys
import argparse
from pathlib import Path
from src.agent.orchestrator import AgentOrchestrator
from src.artifact.replay_engine import ReplayEngine
from src.utils.config import Config
from src.utils.logging import setup_logging

# Setup logging
logger = setup_logging()

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


async def run_discovery(goal: str, target_url: str, capability_name: str, description: str):
    """Run LLM-driven discovery to create an automation artifact."""
    logger.info("Starting discovery mode", goal=goal, target_url=target_url)
    
    try:
        orchestrator = AgentOrchestrator()
        artifact = await orchestrator.execute_goal(goal, target_url, capability_name, description)
        
        # Save artifact
        from src.utils.config import Config
        artifact_path = Path(Config.ARTIFACT_DIR) / f"{capability_name}.json"
        
        replay_engine = ReplayEngine()
        replay_engine.save_artifact(artifact, str(artifact_path))
        
        logger.info("Discovery completed successfully", artifact_path=str(artifact_path))
        print(f"\n✓ Artifact saved to: {artifact_path}")
        print(f"✓ Steps recorded: {len(artifact.steps)}")
        print(f"✓ Parameters defined: {len(artifact.parameters)}")
        print(f"✓ Outputs defined: {len(artifact.outputs)}")
        
        return artifact
        
    except Exception as e:
        logger.error("Discovery failed", error=str(e))
        print(f"\n✗ Discovery failed: {str(e)}")
        sys.exit(1)


async def run_replay(artifact_path: str, parameters: dict):
    """Run deterministic replay of an automation artifact."""
    logger.info("Starting replay mode", artifact_path=artifact_path)
    
    try:
        replay_engine = ReplayEngine()
        artifact = replay_engine.load_artifact(artifact_path)
        
        logger.info("Artifact loaded", capability=artifact.metadata.capability_name)
        
        result = await replay_engine.execute_artifact(artifact, parameters)
        
        logger.info("Replay completed", success=result.success, steps=result.steps_completed)
        
        print(f"\n{'[SUCCESS]' if result.success else '[COMPLETED]'} Replay {'succeeded' if result.success else 'finished'}")
        print(f"Status: {result.status.value}")
        print(f"Steps completed: {result.steps_completed}/{len(artifact.steps)}")
        print(f"Execution time: {result.execution_time_seconds:.2f}s")
        
        if result.outputs:
            print("\nOutputs:")
            for key, value in result.outputs.items():
                print(f"  {key}: {value}")
        
        if result.business_outcome:
            print(f"\nBusiness outcome: {result.business_outcome}")
            if result.evidence_text:
                print(f"Evidence: {result.evidence_text}")
        
        if result.error:
            print(f"\nError: {result.error}")
            if result.error_step:
                print(f"Failed at step: {result.error_step}")
            if result.expected:
                print(f"Expected: {result.expected}")
            if result.observed:
                print(f"Observed: {result.observed}")
        
        return result
        
    except Exception as e:
        logger.error("Replay failed", error=str(e))
        print(f"\n[FAILED] Replay failed: {str(e)}")
        sys.exit(1)


BANNER = """
  _   _                      _____                 ____            _             
 | \\ | | ___ _   _ _ __ ___ |__  /___ _ __ ___    |  _ \\ ___ _ __ | | __ _ _   _ 
 |  \\| |/ _ \\ | | | '__/ _ \\  / // _ \\ '__/ _ \\   | |_) / _ \\ '_ \\| |/ _` | | | |
 | |\\  |  __/ |_| | | | (_) |/ /|  __/ | | (_) |  |  _ <  __/ |_) | | (_| | |_| |
 |_| \\_|\\___|\\__,_|_|  \\___//____\\___|_|  \\___/   |_| \\_\\___| .__/|_|\\__,_|\\__, |
                                                             |_|            |___/ 
  Agentic Computer-Use & Zero-LLM Deterministic Replay Engine
  v1.0.0 | Enterprise FinTech Edition
"""


async def main():
    """Main entry point."""
    print(BANNER)
    parser = argparse.ArgumentParser(description="NeuroZero Replay: Agentic Computer-Use & Deterministic Replay Engine")
    subparsers = parser.add_subparsers(dest="mode", help="Operation mode")
    
    # Discovery mode
    discovery_parser = subparsers.add_parser("discovery", help="Run LLM-driven discovery")
    discovery_parser.add_argument("--goal", required=True, help="Natural language goal")
    discovery_parser.add_argument("--target-url", required=True, help="Target application URL")
    discovery_parser.add_argument("--capability-name", required=True, help="Name for the capability")
    discovery_parser.add_argument("--description", required=True, help="Description of the capability")
    
    # Replay mode
    replay_parser = subparsers.add_parser("replay", help="Run deterministic replay")
    replay_parser.add_argument("--artifact", required=True, help="Path to artifact JSON file")
    replay_parser.add_argument("--params", help="Parameters as JSON string")
    replay_parser.add_argument("--approve-risky", action="store_true", help="Authorize execution of actions marked with risk_level='risky'")
    replay_parser.add_argument("--escalate", action="store_true", help="Enable human escalation on step failures or risk gating")
    
    args = parser.parse_args()
    
    # Validate configuration
    try:
        Config.validate()
    except ValueError as e:
        logger.error("Configuration error", error=str(e))
        print(f"Configuration error: {str(e)}")
        sys.exit(1)
    
    if args.mode == "discovery":
        await run_discovery(args.goal, args.target_url, args.capability_name, args.description)
    elif args.mode == "replay":
        import json
        params = json.loads(args.params) if args.params else {}
        if getattr(args, "approve_risky", False):
            params["approve_risky"] = True
        if getattr(args, "escalate", False):
            params["escalate"] = True
        await run_replay(args.artifact, params)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())