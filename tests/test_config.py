import pytest
import yaml
from chaos_scorer.config import Config, ExperimentConfig, FaultConfig, AlertExpectation


def test_config_parsing():
    yaml_content = """
alertmanager_url: "http://localhost:9093"
pumba_image: "ghcr.io/alexei-led/pumba:latest"
experiments:
  - name: "test-kill"
    description: "Test kill"
    fault:
      type: "kill"
      target: "my-container"
      duration: "30s"
      params:
        signal: "SIGTERM"
    expected_alerts:
      - alertname: "ContainerDown"
        labels:
          severity: "critical"
    wait_after_fault: 10
    timeout: 60
"""
    config = Config.from_dict(yaml.safe_load(yaml_content))
    assert config.alertmanager_url == "http://localhost:9093"
    assert len(config.experiments) == 1
    exp = config.experiments[0]
    assert exp.name == "test-kill"
    assert exp.fault.type == "kill"
    assert exp.fault.target == "my-container"
    assert exp.fault.params["signal"] == "SIGTERM"
    assert len(exp.expected_alerts) == 1
    assert exp.expected_alerts[0].alertname == "ContainerDown"
    assert exp.expected_alerts[0].labels["severity"] == "critical"


def test_alert_matching():
    exp = AlertExpectation(alertname="TestAlert", labels={"severity": "critical"})
    alert = {
        "labels": {"alertname": "TestAlert", "severity": "critical", "instance": "test"},
        "annotations": {},
        "startsAt": "2024-01-01T00:00:00Z",
        "endsAt": "2024-01-01T00:05:00Z",
        "generatorURL": "http://test",
    }
    assert exp.matches(alert) is True

    alert_wrong_name = {**alert, "labels": {**alert["labels"], "alertname": "OtherAlert"}}
    assert exp.matches(alert_wrong_name) is False

    alert_wrong_label = {**alert, "labels": {**alert["labels"], "severity": "warning"}}
    assert exp.matches(alert_wrong_label) is False


def test_fault_config_defaults():
    fault = FaultConfig.from_dict({"type": "kill", "target": "test"})
    assert fault.duration == "30s"
    assert fault.params == {}