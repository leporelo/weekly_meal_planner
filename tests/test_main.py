"""Unit tests for src/main.py CLI entry point."""

from unittest.mock import MagicMock, patch
from pathlib import Path

from src.main import main, parse_args, setup_logging
from src.models import GenerationResult


class TestParseArgs:
    """Tests for command-line argument parsing."""

    def test_default_config(self):
        """Default config path is config.yaml."""
        args = parse_args([])
        assert args.config == "config.yaml"

    def test_custom_config(self):
        """--config flag sets the config path."""
        args = parse_args(["--config", "/path/to/custom.yaml"])
        assert args.config == "/path/to/custom.yaml"

    def test_custom_config_relative(self):
        """Relative paths are preserved as-is."""
        args = parse_args(["--config", "my_config.yaml"])
        assert args.config == "my_config.yaml"


class TestMain:
    """Tests for the main entry point function."""

    def test_missing_config_returns_1(self, tmp_path):
        """Returns exit code 1 when config file does not exist."""
        exit_code = main(["--config", str(tmp_path / "nonexistent.yaml")])
        assert exit_code == 1

    @patch("src.main.MealPlanOrchestrator")
    def test_successful_generation_returns_0(self, mock_orchestrator_cls, tmp_path):
        """Returns exit code 0 when generation succeeds."""
        # Create a config file so the path check passes
        config_file = tmp_path / "config.yaml"
        config_file.write_text("users: []")

        mock_orchestrator = MagicMock()
        mock_orchestrator.run_weekly_generation.return_value = GenerationResult(
            success=True, errors=[]
        )
        mock_orchestrator_cls.return_value = mock_orchestrator

        exit_code = main(["--config", str(config_file)])
        assert exit_code == 0
        mock_orchestrator_cls.assert_called_once_with(config_path=config_file)

    @patch("src.main.MealPlanOrchestrator")
    def test_failed_generation_returns_1(self, mock_orchestrator_cls, tmp_path):
        """Returns exit code 1 when generation fails."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("users: []")

        mock_orchestrator = MagicMock()
        mock_orchestrator.run_weekly_generation.return_value = GenerationResult(
            success=False, errors=["No valid profiles"]
        )
        mock_orchestrator_cls.return_value = mock_orchestrator

        exit_code = main(["--config", str(config_file)])
        assert exit_code == 1

    @patch("src.main.MealPlanOrchestrator")
    def test_exception_during_generation_returns_1(
        self, mock_orchestrator_cls, tmp_path
    ):
        """Returns exit code 1 when orchestrator raises an exception."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("users: []")

        mock_orchestrator_cls.side_effect = RuntimeError("Config parse error")

        exit_code = main(["--config", str(config_file)])
        assert exit_code == 1

    @patch("src.main.MealPlanOrchestrator")
    def test_success_with_non_critical_errors(self, mock_orchestrator_cls, tmp_path):
        """Returns exit code 0 even when there are non-critical errors."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("users: []")

        mock_orchestrator = MagicMock()
        mock_orchestrator.run_weekly_generation.return_value = GenerationResult(
            success=True, errors=["Email failed for one user"]
        )
        mock_orchestrator_cls.return_value = mock_orchestrator

        exit_code = main(["--config", str(config_file)])
        assert exit_code == 0


class TestSetupLogging:
    """Tests for logging configuration."""

    def test_setup_logging_does_not_raise(self):
        """setup_logging should configure logging without errors."""
        setup_logging()
