import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

from .config import ExperimentConfig, AlertExpectation
from .pumba import PumbaClient, FaultResult
from .alertmanager import AlertmanagerClient, AlertQueryResult

logger = logging.getLogger(__name__)


@dataclass
class ExperimentResult:
    experiment_name: str
    fault_result: FaultResult
    alert_result: AlertQueryResult
    coverage_score: float
    started_at: str
    completed_at: str
    duration_seconds: float
    error: Optional[str] = None


class ExperimentRunner:
    def __init__(
        self,
        pumba_client: PumbaClient,
        alertmanager_client: AlertmanagerClient,
    ):
        self.pumba = pumba_client
        self.alertmanager = alertmanager_client

    def run(self, experiment: ExperimentConfig) -> ExperimentResult:
        started_at = datetime.now(timezone.utc).isoformat()
        start_time = time.time()

        logger.info(f"Starting experiment: {experiment.name}")
        logger.info(f"  Fault: {experiment.fault.type} on {experiment.fault.target}")
        logger.info(f"  Expected alerts: {[e.alertname for e in experiment.expected_alerts]}")

        fault_result = self.pumba.inject_fault(
            fault_type=experiment.fault.type,
            target=experiment.fault.target,
            duration=experiment.fault.duration,
            params=experiment.fault.params,
        )

        if not fault_result.success:
            completed_at = datetime.now(timezone.utc).isoformat()
            return ExperimentResult(
                experiment_name=experiment.name,
                fault_result=fault_result,
                alert_result=AlertQueryResult(alerts=[], matched=[], unmatched_expectations=[], success=False),
                coverage_score=0.0,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=time.time() - start_time,
                error=f"Fault injection failed: {fault_result.error}",
            )

        logger.info(f"Fault injected successfully, waiting {experiment.wait_after_fault}s for alerts...")

        expected_dicts = [
            {
                "alertname": e.alertname,
                "labels": e.labels,
                "annotations": e.annotations,
            }
            for e in experiment.expected_alerts
        ]

        alert_result = self.alertmanager.wait_for_alerts(
            expected_alerts=expected_dicts,
            wait_time=experiment.wait_after_fault,
            timeout=experiment.timeout,
        )

        coverage_score = self._calculate_coverage(
            len(experiment.expected_alerts),
            len(alert_result.matched),
        )

        completed_at = datetime.now(timezone.utc).isoformat()
        duration = time.time() - start_time

        result = ExperimentResult(
            experiment_name=experiment.name,
            fault_result=fault_result,
            alert_result=alert_result,
            coverage_score=coverage_score,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
        )

        self._log_result(result)
        return result

    def _calculate_coverage(self, expected: int, matched: int) -> float:
        if expected == 0:
            return 100.0
        return round((matched / expected) * 100, 2)

    def _log_result(self, result: ExperimentResult):
        logger.info(f"Experiment '{result.experiment_name}' completed:")
        logger.info(f"  Fault: {'SUCCESS' if result.fault_result.success else 'FAILED'}")
        logger.info(f"  Alerts matched: {len(result.alert_result.matched)}/{len(result.alert_result.matched) + len(result.alert_result.unmatched_expectations)}")
        logger.info(f"  Coverage score: {result.coverage_score}%")

        if result.alert_result.unmatched_expectations:
            for exp in result.alert_result.unmatched_expectations:
                logger.warning(f"  MISSING ALERT: {exp['alertname']} (labels: {exp.get('labels', {})})")

        if result.alert_result.matched:
            for alert in result.alert_result.matched:
                logger.info(f"  MATCHED: {alert.labels.get('alertname')} (labels: {alert.labels})")


class CoverageScorer:
    def __init__(self):
        self.results: list[ExperimentResult] = []

    def add_result(self, result: ExperimentResult):
        self.results.append(result)

    def get_overall_score(self) -> float:
        if not self.results:
            return 0.0
        total = sum(r.coverage_score for r in self.results)
        return round(total / len(self.results), 2)

    def get_summary(self) -> dict:
        total_experiments = len(self.results)
        successful_faults = sum(1 for r in self.results if r.fault_result.success)
        total_expected = sum(len(r.alert_result.matched) + len(r.alert_result.unmatched_expectations) for r in self.results)
        total_matched = sum(len(r.alert_result.matched) for r in self.results)

        return {
            "total_experiments": total_experiments,
            "successful_fault_injections": successful_faults,
            "total_expected_alerts": total_expected,
            "total_matched_alerts": total_matched,
            "overall_coverage_score": self.get_overall_score(),
            "per_experiment": [
                {
                    "name": r.experiment_name,
                    "fault_success": r.fault_result.success,
                    "coverage_score": r.coverage_score,
                    "expected_alerts": len(r.alert_result.matched) + len(r.alert_result.unmatched_expectations),
                    "matched_alerts": len(r.alert_result.matched),
                    "duration_seconds": round(r.duration_seconds, 2),
                }
                for r in self.results
            ],
        }

    def print_summary(self):
        summary = self.get_summary()
        print("\n" + "=" * 60)
        print("CHAOS COVERAGE SCORE REPORT")
        print("=" * 60)
        print(f"Overall Coverage Score: {summary['overall_coverage_score']}%")
        print(f"Experiments Run: {summary['total_experiments']}")
        print(f"Successful Fault Injections: {summary['successful_fault_injections']}/{summary['total_experiments']}")
        print(f"Expected Alerts: {summary['total_expected_alerts']}")
        print(f"Matched Alerts: {summary['total_matched_alerts']}")
        print("-" * 60)
        for exp in summary["per_experiment"]:
            status = "✓" if exp["fault_success"] else "✗"
            print(f"{status} {exp['name']}: {exp['coverage_score']}% ({exp['matched_alerts']}/{exp['expected_alerts']} alerts)")
        print("=" * 60)