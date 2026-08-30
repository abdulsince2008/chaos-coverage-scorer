import requests
import time
import logging
from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    labels: dict
    annotations: dict
    starts_at: str
    ends_at: str
    generator_url: str
    status: str = "firing"

    @classmethod
    def from_api(cls, data: dict) -> "Alert":
        # Alertmanager API v2 returns "state" field with values: "active", "suppressed", "unprocessed"
        state = data.get("state", "active")
        # Map Alertmanager states to our status
        status = "firing" if state == "active" else state
        return cls(
            labels=data.get("labels", {}),
            annotations=data.get("annotations", {}),
            starts_at=data.get("startsAt", ""),
            ends_at=data.get("endsAt", ""),
            generator_url=data.get("generatorURL", ""),
            status=status,
        )

    def is_firing(self) -> bool:
        return self.status == "firing"


@dataclass
class AlertQueryResult:
    alerts: list[Alert]
    matched: list[Alert]
    unmatched_expectations: list[dict]
    success: bool


class AlertmanagerClient:
    def __init__(self, base_url: str = "http://localhost:9093", timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def get_alerts(self, filter_silenced: bool = True) -> list[Alert]:
        url = f"{self.base_url}/api/v2/alerts"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            alerts = [Alert.from_api(a) for a in data]
            if filter_silenced:
                alerts = [a for a in alerts if a.is_firing()]
            return alerts
        except requests.exceptions.ConnectionError:
            logger.error(f"Cannot connect to Alertmanager at {self.base_url}")
            return []
        except requests.exceptions.Timeout:
            logger.error(f"Timeout connecting to Alertmanager at {self.base_url}")
            return []
        except Exception as e:
            logger.error(f"Error querying Alertmanager: {e}")
            return []

    def wait_for_alerts(
        self,
        expected_alerts: list[dict],
        wait_time: int = 10,
        poll_interval: int = 2,
        timeout: int = 60,
    ) -> AlertQueryResult:
        time.sleep(wait_time)

        start = time.time()
        while time.time() - start < timeout:
            current_alerts = self.get_alerts()
            matched, unmatched = self._match_alerts(current_alerts, expected_alerts)

            if len(matched) == len(expected_alerts):
                return AlertQueryResult(
                    alerts=current_alerts,
                    matched=matched,
                    unmatched_expectations=unmatched,
                    success=True,
                )

            time.sleep(poll_interval)

        current_alerts = self.get_alerts()
        matched, unmatched = self._match_alerts(current_alerts, expected_alerts)
        return AlertQueryResult(
            alerts=current_alerts,
            matched=matched,
            unmatched_expectations=unmatched,
            success=False,
        )

    def _match_alerts(
        self, current_alerts: list[Alert], expected: list[dict]
    ) -> tuple[list[Alert], list[dict]]:
        matched = []
        unmatched = []

        for exp in expected:
            found = False
            for alert in current_alerts:
                if alert.labels.get("alertname") == exp["alertname"]:
                    label_match = True
                    for k, v in exp.get("labels", {}).items():
                        if alert.labels.get(k) != v:
                            label_match = False
                            break
                    if label_match:
                        matched.append(alert)
                        found = True
                        break
            if not found:
                unmatched.append(exp)

        return matched, unmatched

    def health_check(self) -> bool:
        try:
            resp = self.session.get(f"{self.base_url}/api/v2/status", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def close(self):
        self.session.close()