#!/usr/bin/env python3
import sys
import logging
import click
from pathlib import Path

from chaos_scorer import (
    Config,
    PumbaClient,
    AlertmanagerClient,
    ExperimentRunner,
    CoverageScorer,
)


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )


@click.command()
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
@click.option("--alertmanager-url", "-a", default="http://localhost:9093", help="Alertmanager base URL")
@click.option("--pumba-image", "-p", default="ghcr.io/alexei-led/pumba:latest", help="Pumba Docker image")
@click.option("--docker-socket", "-d", default="unix:///var/run/docker.sock", help="Docker socket path")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--dry-run", is_flag=True, help="Print config and exit without running")
def main(config_file: Path, alertmanager_url: str, pumba_image: str, docker_socket: str, verbose: bool, dry_run: bool):
    """Chaos Coverage Scorer - Measure observability coverage by injecting faults and checking alerts."""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    try:
        config = Config.from_file(config_file)
        config.alertmanager_url = alertmanager_url
        config.pumba_image = pumba_image

        if dry_run:
            print("DRY RUN - Configuration:")
            print(f"  Alertmanager: {config.alertmanager_url}")
            print(f"  Pumba image: {config.pumba_image}")
            print(f"  Experiments: {len(config.experiments)}")
            for exp in config.experiments:
                print(f"    - {exp.name}: {exp.fault.type} on {exp.fault.target} (expects {len(exp.expected_alerts)} alerts)")
            return

        if not config.experiments:
            logger.error("No experiments defined in config")
            sys.exit(1)

        logger.info(f"Connecting to Alertmanager at {config.alertmanager_url}")
        alertmanager = AlertmanagerClient(config.alertmanager_url)

        if not alertmanager.health_check():
            logger.error(f"Alertmanager not reachable at {config.alertmanager_url}")
            sys.exit(1)

        logger.info("Alertmanager is healthy")

        logger.info(f"Using Pumba image: {config.pumba_image}")
        pumba = PumbaClient(config.pumba_image, docker_socket)

        runner = ExperimentRunner(pumba, alertmanager)
        scorer = CoverageScorer()

        for experiment in config.experiments:
            result = runner.run(experiment)
            scorer.add_result(result)

        scorer.print_summary()

        overall = scorer.get_overall_score()
        if overall < 100:
            logger.warning(f"Overall coverage is {overall}% - some alerts did not fire!")
            sys.exit(1)
        else:
            logger.info("All expected alerts fired - full coverage!")
            sys.exit(0)

    except FileNotFoundError:
        logger.error(f"Config file not found: {config_file}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()