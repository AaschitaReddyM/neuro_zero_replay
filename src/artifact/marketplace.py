"""Artifact marketplace and directory management system."""
import json
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime
from src.artifact.schemas import AutomationArtifact
from src.utils.config import Config
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ArtifactMarketplace:
    """Manage a collection of automation artifacts with discovery and versioning."""
    
    def __init__(self, artifact_dir: Optional[str] = None):
        """Initialize the artifact marketplace."""
        self.artifact_dir = Path(artifact_dir or Config.ARTIFACT_DIR)
        self.artifacts: Dict[str, Dict] = {}
        self._load_artifacts()
    
    def _load_artifacts(self) -> None:
        """Load all artifacts from the artifact directory."""
        if not self.artifact_dir.exists():
            logger.warning("Artifact directory does not exist", dir=str(self.artifact_dir))
            return
        
        for artifact_file in self.artifact_dir.glob("*.json"):
            try:
                with open(artifact_file, 'r') as f:
                    data = json.load(f)
                
                artifact = AutomationArtifact(**data)
                capability_name = artifact.metadata.capability_name
                
                self.artifacts[capability_name] = {
                    "artifact": artifact,
                    "file_path": str(artifact_file),
                    "loaded_at": datetime.utcnow().isoformat(),
                    "version": artifact.metadata.version,
                    "target_app": artifact.metadata.target_app
                }
                
                logger.info("Artifact loaded", capability=capability_name, version=artifact.metadata.version)
                
            except Exception as e:
                logger.error("Failed to load artifact", file=str(artifact_file), error=str(e))
    
    def list_artifacts(self) -> List[Dict]:
        """List all available artifacts with metadata."""
        artifact_list = []
        
        for capability_name, artifact_data in self.artifacts.items():
            artifact = artifact_data["artifact"]
            
            artifact_list.append({
                "capability_name": capability_name,
                "version": artifact.metadata.version,
                "target_app": artifact.metadata.target_app,
                "description": artifact.metadata.description,
                "parameters": list(artifact.parameters.keys()),
                "outputs": list(artifact.outputs.keys()),
                "steps": len(artifact.steps),
                "error_handlers": len(artifact.error_handlers),
                "created_at": artifact.metadata.created_at,
                "file_path": artifact_data["file_path"]
            })
        
        return sorted(artifact_list, key=lambda x: x["capability_name"])
    
    def get_artifact(self, capability_name: str) -> Optional[AutomationArtifact]:
        """Get a specific artifact by capability name."""
        if capability_name in self.artifacts:
            return self.artifacts[capability_name]["artifact"]
        return None
    
    def search_artifacts(self, query: str) -> List[Dict]:
        """Search artifacts by name, description, or target app."""
        query = query.lower()
        results = []
        
        for artifact_info in self.list_artifacts():
            if (query in artifact_info["capability_name"].lower() or
                query in artifact_info["description"].lower() or
                query in artifact_info["target_app"].lower()):
                results.append(artifact_info)
        
        return results
    
    def get_artifact_stats(self) -> Dict:
        """Get statistics about the artifact collection."""
        total_artifacts = len(self.artifacts)
        total_steps = sum(len(data["artifact"].steps) for data in self.artifacts.values())
        total_error_handlers = sum(len(data["artifact"].error_handlers) for data in self.artifacts.values())
        
        target_apps = set(data["artifact"].metadata.target_app for data in self.artifacts.values())
        
        return {
            "total_artifacts": total_artifacts,
            "total_steps": total_steps,
            "total_error_handlers": total_error_handlers,
            "unique_target_apps": len(target_apps),
            "target_apps": list(target_apps),
            "capabilities": list(self.artifacts.keys())
        }
    
    def validate_artifact_consistency(self) -> Dict[str, List]:
        """Validate consistency across all artifacts."""
        issues = {
            "warnings": [],
            "errors": []
        }
        
        for capability_name, artifact_data in self.artifacts.items():
            artifact = artifact_data["artifact"]
            
            # Check for missing required fields
            if not artifact.metadata.capability_name:
                issues["errors"].append(f"{capability_name}: Missing capability name")
            
            if not artifact.metadata.target_app:
                issues["errors"].append(f"{capability_name}: Missing target app")
            
            # Check for empty steps
            if not artifact.steps:
                issues["errors"].append(f"{capability_name}: No steps defined")
            
            # Check for parameters without required field
            for param_name, param_def in artifact.parameters.items():
                if not param_def.required and param_def.default is None:
                    issues["warnings"].append(f"{capability_name}: Parameter '{param_name}' is optional but has no default")
            
            # Check for error handlers without strategies
            for handler in artifact.error_handlers:
                if handler.error_type.value not in ["business_outcome"] and not handler.fallback_strategy:
                    issues["warnings"].append(f"{capability_name}: Error handler for '{handler.error_type.value}' has no fallback strategy")
        
        return issues
    
    def generate_marketplace_report(self) -> str:
        """Generate a comprehensive marketplace report."""
        stats = self.get_artifact_stats()
        validation = self.validate_artifact_consistency()
        
        report = []
        report.append("=" * 70)
        report.append("ARTIFACT MARKETPLACE REPORT")
        report.append("=" * 70)
        report.append(f"\nGenerated: {datetime.utcnow().isoformat()}")
        
        report.append("\nSTATISTICS")
        report.append("-" * 70)
        report.append(f"Total Artifacts: {stats['total_artifacts']}")
        report.append(f"Total Automation Steps: {stats['total_steps']}")
        report.append(f"Total Error Handlers: {stats['total_error_handlers']}")
        report.append(f"Unique Target Applications: {stats['unique_target_apps']}")
        
        report.append("\nTARGET APPLICATIONS")
        report.append("-" * 70)
        for app in stats['target_apps']:
            report.append(f"  - {app}")
        
        report.append("\nAVAILABLE CAPABILITIES")
        report.append("-" * 70)
        for capability in stats['capabilities']:
            report.append(f"  - {capability}")
        
        report.append("\nARTIFACT DETAILS")
        report.append("-" * 70)
        
        for artifact_info in self.list_artifacts():
            report.append(f"\n{artifact_info['capability_name']} (v{artifact_info['version']})")
            report.append(f"  Target: {artifact_info['target_app']}")
            report.append(f"  Description: {artifact_info['description']}")
            report.append(f"  Parameters: {', '.join(artifact_info['parameters'])}")
            report.append(f"  Outputs: {', '.join(artifact_info['outputs'])}")
            report.append(f"  Steps: {artifact_info['steps']}")
            report.append(f"  Error Handlers: {artifact_info['error_handlers']}")
        
        if validation['errors'] or validation['warnings']:
            report.append("\nVALIDATION ISSUES")
            report.append("-" * 70)
            
            if validation['errors']:
                report.append("\nERRORS:")
                for error in validation['errors']:
                    report.append(f"  [ERROR] {error}")
            
            if validation['warnings']:
                report.append("\nWARNINGS:")
                for warning in validation['warnings']:
                    report.append(f"  [WARNING] {warning}")
        else:
            report.append("\nVALIDATION")
            report.append("-" * 70)
            report.append("[OK] All artifacts passed validation")
        
        return "\n".join(report)


def main():
    """Demonstrate the artifact marketplace functionality."""
    marketplace = ArtifactMarketplace()
    
    print(marketplace.generate_marketplace_report())
    
    # Demonstrate search functionality
    print("\n\nSEARCH DEMONSTRATION")
    print("=" * 70)
    
    search_results = marketplace.search_artifacts("transfer")
    print(f"\nSearch for 'transfer': {len(search_results)} results")
    for result in search_results:
        print(f"  - {result['capability_name']}: {result['description']}")
    
    # Demonstrate artifact retrieval
    print("\n\nARTIFACT RETRIEVAL")
    print("=" * 70)
    
    lookup_artifact = marketplace.get_artifact("lookup_member_balance")
    if lookup_artifact:
        print(f"\nRetrieved: {lookup_artifact.metadata.capability_name}")
        print(f"Version: {lookup_artifact.metadata.version}")
        print(f"Steps: {len(lookup_artifact.steps)}")


if __name__ == "__main__":
    main()