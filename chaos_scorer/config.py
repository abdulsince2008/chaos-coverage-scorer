from dataclasses import dataclass, field
from typing import Optional
import yaml


@dataclass
class FaultConfig:
    type: str
    target: str
    duration: str = "30s"
    params: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "FaultConfig":
        return cls(
            type=data["type"],
            target=data["target"],
            duration=data.get("duration", "30s"),
            params=data.get("params", {}),
        )


@dataclass
class AlertExpectation:
    alertname: str
    labels: dict = field(default_factory=dict)
    annotations: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "AlertExpectation":
        return cls(
            alertname=data["alertname"],
            labels=data.get("labels", {}),
            annotations=data.get("annotations", {}),
        )

    def matches(self, alert: dict) -> bool:
        if alert.get("labels", {}).get("alertname") != self.alertname:
            return False
        for k, v in self.labels.items():
            if alert.get("labels", {}).get(k) != v:
                return False
        return True


@dataclass
class ExperimentConfig:
    name: str
    description: str
    fault: FaultConfig
    expected_alerts: list[AlertExpectation]
    alertmanager_url: str = "http://localhost:9093"
    wait_after_fault: int = 10
    timeout: int = 60

    @classmethod
    def from_dict(cls, data: dict) -> "ExperimentConfig":
        return cls(
            name=data["name"],
            description=data["description"],
            fault=FaultConfig.from_dict(data["fault"]),
            expected_alerts=[AlertExpectation.from_dict(a) for a in data["expected_alerts"]],
            alertmanager_url=data.get("alertmanager_url", "http://localhost:9093"),
            wait_after_fault=data.get("wait_after_fault", 10),
            timeout=data.get("timeout", 60),
        )


@dataclass
class Config:
    experiments: list[ExperimentConfig]
    alertmanager_url: str = "http://localhost:9093"
    pumba_image: str = "ghcr.io/alexei-led/pumba:latest"

    @classmethod
    def from_file(cls, path: str) -> "Config":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(
            experiments=[ExperimentConfig.from_dict(e) for e in data["experiments"]],
            alertmanager_url=data.get("alertmanager_url", "http://localhost:9093"),
            pumba_image=data.get("pumba_image", "ghcr.io/alexei-led/pumba:latest"),
        )

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        return cls(
            experiments=[ExperimentConfig.from_dict(e) for e in data["experiments"]],
            alertmanager_url=data.get("alertmanager_url", "http://localhost:9093"),
            pumba_image=data.get("pumba_image", "ghcr.io/alexei-led/pumba:latest"),
        )