"""CLI entry point for the Vegan Meal Planner.

Loads configuration and runs the MealPlanOrchestrator to generate
weekly meal plans, validate them, build grocery lists, and send emails.

Scheduling
----------
This application is designed to be run via cron (or equivalent scheduler).
The config.yaml file contains scheduling preferences under the 'email' section:

    email:
      schedule_day: "Sunday"
      schedule_time: "08:00"
      schedule_timezone: "Europe/London"

These values document when the user intends the job to run. Set up your
system cron job to match. For example:

    # Cron example for weekly execution (Sunday 8:00 AM):
    # 0 8 * * 0 cd /path/to/vegan-meal-planner && python -m src.main

    # To use a specific timezone, set TZ in cron or use systemd timers:
    # TZ=Europe/London
    # 0 8 * * 0 cd /path/to/vegan-meal-planner && python -m src.main

    # Alternatively with systemd timer (recommended for timezone support):
    # [Timer]
    # OnCalendar=Sun *-*-* 08:00:00
    # Persistent=true

Exit codes:
    0 - Success (at least one meal plan generated and delivered)
    1 - Failure (no plans generated or critical error)
"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.orchestrator import MealPlanOrchestrator


def setup_logging() -> None:
    """Configure logging with timestamp, level, and message."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:] if None).

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        prog="vegan-meal-planner",
        description="Generate weekly vegan meal plans and send via email.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to the configuration file (default: config.yaml)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the vegan meal planner CLI.

    Args:
        argv: Argument list (defaults to sys.argv[1:] if None).

    Returns:
        Exit code: 0 for success, 1 for failure.
    """
    load_dotenv()  # Load .env file into environment
    setup_logging()
    logger = logging.getLogger(__name__)

    args = parse_args(argv)
    config_path = Path(args.config)

    if not config_path.exists():
        logger.error("Configuration file not found: %s", config_path)
        return 1

    logger.info("Starting vegan meal planner with config: %s", config_path)

    try:
        orchestrator = MealPlanOrchestrator(config_path=config_path)
        result = orchestrator.run_weekly_generation()
    except Exception as e:
        logger.error("Fatal error during meal plan generation: %s", e)
        return 1

    if result.success:
        logger.info("Meal plan generation completed successfully.")
        if result.errors:
            logger.warning(
                "Completed with %d non-critical error(s):", len(result.errors)
            )
            for error in result.errors:
                logger.warning("  - %s", error)
        return 0
    else:
        logger.error("Meal plan generation failed.")
        for error in result.errors:
            logger.error("  - %s", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
