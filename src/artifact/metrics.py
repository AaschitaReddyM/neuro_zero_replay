"""Performance metrics and confidence scoring for artifacts."""
import time
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ConfidenceLevel(str, Enum):
    """Confidence levels for artifact reliability."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ExecutionMetrics:
    """Metrics from a single artifact execution."""
    artifact_name: str
    execution_id: str
    timestamp: str
    success: bool
    execution_time_seconds: float
    steps_completed: int
    total_steps: int
    error_type: Optional[str] = None
    business_outcome: Optional[str] = None
    fallback_strategies_used: List[str] = None
    
    def __post_init__(self):
        if self.fallback_strategies_used is None:
            self.fallback_strategies_used = []


@dataclass
class ArtifactConfidence:
    """Confidence score and reliability metrics for an artifact."""
    artifact_name: str
    confidence_level: ConfidenceLevel
    success_rate: float
    average_execution_time: float
    total_executions: int
    recent_failures: int
    last_execution_time: str
    reliability_factors: Dict[str, float]
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "artifact_name": self.artifact_name,
            "confidence_level": self.confidence_level.value,
            "success_rate": self.success_rate,
            "average_execution_time": self.average_execution_time,
            "total_executions": self.total_executions,
            "recent_failures": self.recent_failures,
            "last_execution_time": self.last_execution_time,
            "reliability_factors": self.reliability_factors
        }


class MetricsCollector:
    """Collect and analyze performance metrics for artifact executions."""
    
    def __init__(self):
        """Initialize the metrics collector."""
        self.execution_history: Dict[str, List[ExecutionMetrics]] = {}
        self.confidence_scores: Dict[str, ArtifactConfidence] = {}
    
    def record_execution(self, metrics: ExecutionMetrics) -> None:
        """Record metrics from an artifact execution."""
        artifact_name = metrics.artifact_name
        
        if artifact_name not in self.execution_history:
            self.execution_history[artifact_name] = []
        
        self.execution_history[artifact_name].append(metrics)
        
        # Update confidence score
        self._update_confidence_score(artifact_name)
        
        logger.info("Execution recorded", artifact=artifact_name, success=metrics.success, 
                   time_seconds=metrics.execution_time_seconds)
    
    def _update_confidence_score(self, artifact_name: str) -> None:
        """Calculate and update confidence score for an artifact."""
        if artifact_name not in self.execution_history:
            return
        
        history = self.execution_history[artifact_name]
        
        if not history:
            return
        
        # Calculate success rate
        successful = sum(1 for m in history if m.success)
        success_rate = successful / len(history)
        
        # Calculate average execution time
        total_time = sum(m.execution_time_seconds for m in history)
        avg_time = total_time / len(history)
        
        # Count recent failures (last 10 executions)
        recent_history = history[-10:]
        recent_failures = sum(1 for m in recent_history if not m.success)
        
        # Determine confidence level
        if success_rate >= 0.95 and recent_failures == 0:
            confidence = ConfidenceLevel.HIGH
        elif success_rate >= 0.80 and recent_failures <= 2:
            confidence = ConfidenceLevel.MEDIUM
        else:
            confidence = ConfidenceLevel.LOW
        
        # Calculate reliability factors
        reliability_factors = {
            "success_rate": success_rate,
            "execution_consistency": self._calculate_consistency(history),
            "error_recovery_rate": self._calculate_error_recovery(history),
            "fallback_efficiency": self._calculate_fallback_efficiency(history)
        }
        
        self.confidence_scores[artifact_name] = ArtifactConfidence(
            artifact_name=artifact_name,
            confidence_level=confidence,
            success_rate=success_rate,
            average_execution_time=avg_time,
            total_executions=len(history),
            recent_failures=recent_failures,
            last_execution_time=history[-1].timestamp,
            reliability_factors=reliability_factors
        )
    
    def _calculate_consistency(self, history: List[ExecutionMetrics]) -> float:
        """Calculate execution time consistency (lower variance = higher consistency)."""
        if len(history) < 2:
            return 1.0
        
        times = [m.execution_time_seconds for m in history]
        avg_time = sum(times) / len(times)
        
        if avg_time == 0:
            return 1.0
        
        variance = sum((t - avg_time) ** 2 for t in times) / len(times)
        std_dev = variance ** 0.5
        
        # Consistency score: 1 - (std_dev / avg_time), bounded between 0 and 1
        consistency = max(0, min(1, 1 - (std_dev / avg_time)))
        return consistency
    
    def _calculate_error_recovery_rate(self, history: List[ExecutionMetrics]) -> float:
        """Calculate how often errors are successfully recovered."""
        failed_executions = [m for m in history if not m.success]
        
        if not failed_executions:
            return 1.0
        
        # Count executions that used fallback strategies
        recovered = sum(1 for m in failed_executions if m.fallback_strategies_used)
        
        return recovered / len(failed_executions)
    
    def _calculate_fallback_efficiency(self, history: List[ExecutionMetrics]) -> float:
        """Calculate efficiency of fallback strategies."""
        executions_with_fallbacks = [m for m in history if m.fallback_strategies_used]
        
        if not executions_with_fallbacks:
            return 1.0
        
        # Count executions that succeeded after using fallbacks
        successful_after_fallback = sum(1 for m in executions_with_fallbacks if m.success)
        
        return successful_after_fallback / len(executions_with_fallbacks)
    
    def get_confidence_score(self, artifact_name: str) -> Optional[ArtifactConfidence]:
        """Get the current confidence score for an artifact."""
        return self.confidence_scores.get(artifact_name)
    
    def get_execution_history(self, artifact_name: str) -> List[ExecutionMetrics]:
        """Get execution history for an artifact."""
        return self.execution_history.get(artifact_name, [])
    
    def get_system_overview(self) -> Dict:
        """Get overview of all artifacts and their confidence scores."""
        overview = {
            "total_artifacts": len(self.confidence_scores),
            "high_confidence": 0,
            "medium_confidence": 0,
            "low_confidence": 0,
            "total_executions": sum(len(h) for h in self.execution_history.values()),
            "artifacts": {}
        }
        
        for artifact_name, confidence in self.confidence_scores.items():
            overview["artifacts"][artifact_name] = confidence.to_dict()
            
            if confidence.confidence_level == ConfidenceLevel.HIGH:
                overview["high_confidence"] += 1
            elif confidence.confidence_level == ConfidenceLevel.MEDIUM:
                overview["medium_confidence"] += 1
            else:
                overview["low_confidence"] += 1
        
        return overview
    
    def generate_performance_report(self) -> str:
        """Generate a comprehensive performance report."""
        overview = self.get_system_overview()
        
        report = []
        report.append("=" * 70)
        report.append("ARTIFACT PERFORMANCE REPORT")
        report.append("=" * 70)
        report.append(f"\nGenerated: {datetime.utcnow().isoformat()}")
        
        report.append("\nSYSTEM OVERVIEW")
        report.append("-" * 70)
        report.append(f"Total Artifacts Tracked: {overview['total_artifacts']}")
        report.append(f"Total Executions: {overview['total_executions']}")
        report.append(f"High Confidence: {overview['high_confidence']}")
        report.append(f"Medium Confidence: {overview['medium_confidence']}")
        report.append(f"Low Confidence: {overview['low_confidence']}")
        
        report.append("\nARTIFACT PERFORMANCE DETAILS")
        report.append("-" * 70)
        
        for artifact_name, confidence_data in overview["artifacts"].items():
            report.append(f"\n{artifact_name}")
            report.append(f"  Confidence Level: {confidence_data['confidence_level'].upper()}")
            report.append(f"  Success Rate: {confidence_data['success_rate']:.1%}")
            report.append(f"  Avg Execution Time: {confidence_data['average_execution_time']:.2f}s")
            report.append(f"  Total Executions: {confidence_data['total_executions']}")
            report.append(f"  Recent Failures: {confidence_data['recent_failures']}")
            
            report.append(f"  Reliability Factors:")
            for factor, value in confidence_data['reliability_factors'].items():
                report.append(f"    - {factor}: {value:.2f}")
        
        return "\n".join(report)


# Global metrics collector instance
metrics_collector = MetricsCollector()


def record_artifact_execution(artifact_name: str, success: bool, execution_time: float,
                            steps_completed: int, total_steps: int,
                            error_type: Optional[str] = None,
                            business_outcome: Optional[str] = None,
                            fallback_strategies_used: Optional[List[str]] = None) -> None:
    """Convenience function to record artifact execution metrics."""
    execution_id = f"{artifact_name}_{int(time.time() * 1000)}"
    
    metrics = ExecutionMetrics(
        artifact_name=artifact_name,
        execution_id=execution_id,
        timestamp=datetime.utcnow().isoformat(),
        success=success,
        execution_time_seconds=execution_time,
        steps_completed=steps_completed,
        total_steps=total_steps,
        error_type=error_type,
        business_outcome=business_outcome,
        fallback_strategies_used=fallback_strategies_used or []
    )
    
    metrics_collector.record_execution(metrics)


def get_artifact_confidence(artifact_name: str) -> Optional[ArtifactConfidence]:
    """Get confidence score for an artifact."""
    return metrics_collector.get_confidence_score(artifact_name)