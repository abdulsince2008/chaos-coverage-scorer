import docker
import time
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FaultResult:
    success: bool
    fault_type: str
    target: str
    duration: str
    error: Optional[str] = None
    container_id: Optional[str] = None


class PumbaClient:
    def __init__(self, pumba_image: str = "ghcr.io/alexei-led/pumba:latest", docker_socket: str = "unix:///var/run/docker.sock"):
        self.pumba_image = pumba_image
        self.docker_socket = docker_socket
        self._client = None

    def _get_client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.DockerClient(base_url=self.docker_socket)
        return self._client

    def inject_fault(self, fault_type: str, target: str, duration: str = "30s", params: dict = None) -> FaultResult:
        params = params or {}
        client = self._get_client()

        try:
            cmd = self._build_command(fault_type, target, duration, params)
            logger.info(f"Running Pumba command: {' '.join(cmd)}")

            container = client.containers.run(
                self.pumba_image,
                command=cmd,
                detach=True,
                remove=False,
                volumes={"/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}},
                network_mode="host",
                privileged=True,
            )

            try:
                exit_code = container.wait(timeout=int(duration.rstrip('s')) + 30)["StatusCode"]
                logs = container.logs().decode("utf-8")
                container.remove(force=True)

                if exit_code == 0:
                    return FaultResult(
                        success=True,
                        fault_type=fault_type,
                        target=target,
                        duration=duration,
                        container_id=container.id[:12],
                    )
                else:
                    return FaultResult(
                        success=False,
                        fault_type=fault_type,
                        target=target,
                        duration=duration,
                        error=f"Pumba exited with code {exit_code}: {logs}",
                        container_id=container.id[:12],
                    )
            except Exception as e:
                try:
                    container.kill()
                    container.remove(force=True)
                except Exception:
                    pass
                return FaultResult(
                    success=False,
                    fault_type=fault_type,
                    target=target,
                    duration=duration,
                    error=f"Pumba execution failed: {e}",
                )

        except docker.errors.ImageNotFound:
            return FaultResult(
                success=False,
                fault_type=fault_type,
                target=target,
                duration=duration,
                error=f"Pumba image not found: {self.pumba_image}. Run 'docker pull {self.pumba_image}' first.",
            )
        except docker.errors.APIError as e:
            return FaultResult(
                success=False,
                fault_type=fault_type,
                target=target,
                duration=duration,
                error=f"Docker API error: {e}",
            )
        except Exception as e:
            return FaultResult(
                success=False,
                fault_type=fault_type,
                target=target,
                duration=duration,
                error=f"Unexpected error: {e}",
            )

    def _build_command(self, fault_type: str, target: str, duration: str, params: dict) -> list[str]:
        base = ["--log-level", "info"]

        if fault_type == "kill":
            signal = params.get("signal", "SIGKILL")
            return base + ["kill", "--signal", signal, target]
        elif fault_type == "stop":
            return base + ["stop", "--duration", duration, target]
        elif fault_type == "pause":
            return base + ["pause", "--duration", duration, target]
        elif fault_type == "rm":
            return base + ["rm", target]
        elif fault_type == "netem":
            return base + ["netem", "--duration", duration, self._build_netem_params(params), target]
        elif fault_type == "stress":
            return base + ["stress", "--duration", duration, self._build_stress_params(params), target]
        else:
            raise ValueError(f"Unknown fault type: {fault_type}")

    def _build_netem_params(self, params: dict) -> str:
        parts = []
        if "delay" in params:
            parts.append(f"--delay {params['delay']}")
        if "jitter" in params:
            parts.append(f"--jitter {params['jitter']}")
        if "loss" in params:
            parts.append(f"--loss {params['loss']}")
        if "rate" in params:
            parts.append(f"--rate {params['rate']}")
        if "corrupt" in params:
            parts.append(f"--corrupt {params['corrupt']}")
        if "duplicate" in params:
            parts.append(f"--duplicate {params['duplicate']}")
        return " ".join(parts)

    def _build_stress_params(self, params: dict) -> str:
        parts = []
        if "cpu" in params:
            parts.append(f"--cpu {params['cpu']}")
        if "memory" in params:
            parts.append(f"--vm {params['memory']}")
        if "io" in params:
            parts.append(f"--io {params['io']}")
        if "stressors" in params:
            parts.append(f"--stressors {params['stressors']}")
        return " ".join(parts)

    def close(self):
        if self._client:
            self._client.close()
            self._client = None