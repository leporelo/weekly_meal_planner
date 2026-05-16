"""Integration tests for MealPlanOrchestrator.

Tests the full pipeline with mocked Gemini API and SMTP server.
Validates: Requirements 2.1, 2.4, 5.1, 8.1
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.gemini_client import DAYS_OF_WEEK
from src.orchestrator import MealPlanOrchestrator


# --- Helpers ---


def _make_recipe(recipe_id: str, name: str, category: str) -> dict:
    """Create a valid recipe dict matching SINGLE_DAY_JSON_SCHEMA."""
    return {
        "id": recipe_id,
        "name": name,
        "protein_source_category": category,
        "servings": 2,
        "ingredients": [
            {"name": "tofu", "quantity": 200, "unit": "g"},
            {"name": "spinach", "quantity": 100, "unit": "g"},
        ],
        "macros_per_serving": {"protein_g": 30.0, "carbs_g": 20.0, "fat_g": 10.0},
        "instructions": "Press tofu for 15 minutes to remove excess water. Heat oil in a pan over medium-high heat. Cube the tofu and cook for 8 minutes until golden. Add spinach and cook until wilted, season with soy sauce.",
        "prep_time_min": 15,
        "cook_time_min": 10,
    }


def _build_valid_single_day_response(day_name: str, day_index: int) -> dict:
    """Build a valid single day response matching SINGLE_DAY_JSON_SCHEMA.

    Uses rotating protein source categories to pass variety checks.
    """
    categories = [
        "legumes",
        "tofu_and_tempeh",
        "seitan",
        "nuts_and_seeds",
        "protein_rich_grains",
    ]
    cat = categories[day_index % len(categories)]

    return {
        "day": day_name,
        "meals": {
            "breakfast": _make_recipe(f"b-{day_index}", f"Breakfast {day_name}", cat),
            "lunch": _make_recipe(f"l-{day_index}", f"Lunch {day_name}", categories[(day_index + 1) % 5]),
            "dinner": _make_recipe(f"d-{day_index}", f"Dinner {day_name}", categories[(day_index + 2) % 5]),
            "snacks": [
                _make_recipe(f"s-{day_index}", f"Snack {day_name}", categories[(day_index + 3) % 5]),
            ],
        },
    }


def _build_valid_meal_plan_response() -> dict:
    """Build a full 7-day meal plan response matching MEAL_PLAN_JSON_SCHEMA."""
    days = []
    for i, day_name in enumerate(DAYS_OF_WEEK):
        days.append(_build_valid_single_day_response(day_name, i))
    return {"days": days}


def _write_test_config(tmp_path: Path, history_file: str = "history.yaml") -> Path:
    """Write a temporary config.yaml and return its path."""
    config = {
        "users": [
            {
                "name": "David",
                "email": "david@example.com",
                "weight_kg": 90.0,
                "height_cm": 180,
                "gender": "male",
                "preferences": {
                    "dislike": ["smoothies"],
                    "like": ["high-protein meals"],
                    "supplements": [],
                },
            },
            {
                "name": "Sarah",
                "email": "sarah@example.com",
                "weight_kg": 70.0,
                "height_cm": 165,
                "gender": "female",
                "preferences": {
                    "dislike": ["onion"],
                    "like": ["simple recipes"],
                    "supplements": [],
                },
            },
        ],
        "gemini": {
            "api_key_env": "GEMINI_API_KEY",
            "model": "gemini-2.0-flash",
            "max_retries": 2,
        },
        "email": {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "sender_email_env": "SENDER_EMAIL",
            "sender_password_env": "SENDER_PASSWORD",
        },
        "history": {
            "file_path": str(tmp_path / history_file),
            "retention_weeks": 4,
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config), encoding="utf-8")
    return config_path


# --- Fixtures ---


@pytest.fixture
def test_config(tmp_path, monkeypatch):
    """Set up a temporary config and required environment variables."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    monkeypatch.setenv("SENDER_EMAIL", "sender@example.com")
    monkeypatch.setenv("SENDER_PASSWORD", "password123")
    config_path = _write_test_config(tmp_path)
    return config_path


@pytest.fixture
def mock_gemini_response():
    """Return a valid meal plan response for mocking."""
    return _build_valid_meal_plan_response()


def _setup_mock_model_for_single_day(mock_genai):
    """Set up the mock model to return valid single-day responses.

    Returns the mock model for further assertion.
    """
    mock_model = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model

    def make_response(prompt):
        """Return a valid single-day response based on the day mentioned in the prompt."""
        for i, day_name in enumerate(DAYS_OF_WEEK):
            if f"**{day_name}**" in prompt:
                day_resp = _build_valid_single_day_response(day_name, i)
                mock_resp = MagicMock()
                mock_resp.text = json.dumps(day_resp)
                return mock_resp
        # Fallback: return Monday
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(_build_valid_single_day_response("Monday", 0))
        return mock_resp

    mock_model.generate_content.side_effect = make_response
    return mock_model


# --- Tests ---


@patch("src.gemini_client.genai")
@patch("src.email_dispatcher.EmailDispatcher._send_smtp")
class TestFullPipelineSuccess:
    """Test full pipeline with mocked Gemini API and SMTP server.

    Validates: Requirements 2.1, 2.4, 5.1
    """

    def test_full_pipeline_generates_shared_plan_for_all_users(
        self, mock_send_smtp, mock_genai, test_config
    ):
        """Full pipeline generates ONE shared plan stored under each user's name."""
        mock_model = _setup_mock_model_for_single_day(mock_genai)
        mock_send_smtp.return_value = None

        orchestrator = MealPlanOrchestrator(test_config)
        result = orchestrator.run_weekly_generation()

        # Verify generation succeeded
        assert result.success is True

        # Verify the same plan is stored under both user names
        assert "David" in result.plans
        assert "Sarah" in result.plans

        # Both entries should be the exact same MealPlan object
        assert result.plans["David"] is result.plans["Sarah"]

        # Verify the plan has recipes
        recipes = result.plans["David"].all_recipes()
        assert len(recipes) > 0

    def test_full_pipeline_sends_emails_to_all_users(
        self, mock_send_smtp, mock_genai, test_config
    ):
        """Full pipeline sends emails to both users."""
        _setup_mock_model_for_single_day(mock_genai)
        mock_send_smtp.return_value = None

        orchestrator = MealPlanOrchestrator(test_config)
        orchestrator.run_weekly_generation()

        # Verify SMTP was called for both users
        assert mock_send_smtp.call_count == 2

    def test_generate_content_called_7_times_total(
        self, mock_send_smtp, mock_genai, test_config
    ):
        """Shared plan means only 7 generate_content calls (one per day)."""
        mock_model = _setup_mock_model_for_single_day(mock_genai)
        mock_send_smtp.return_value = None

        orchestrator = MealPlanOrchestrator(test_config)
        orchestrator.run_weekly_generation()

        # 1 shared plan × 7 days = 7 calls total
        assert mock_model.generate_content.call_count == 7


@patch("src.gemini_client.genai")
@patch("src.email_dispatcher.EmailDispatcher._send_smtp")
class TestPromptUsesMaxProteinTarget:
    """Test that the prompt uses the HIGHEST protein target across all users.

    Validates: Requirement 2.4
    """

    def test_prompt_contains_max_protein_target(
        self, mock_send_smtp, mock_genai, test_config
    ):
        """Prompt passed to generate_content uses the max protein target (144g)."""
        mock_model = _setup_mock_model_for_single_day(mock_genai)
        mock_send_smtp.return_value = None

        orchestrator = MealPlanOrchestrator(test_config)
        orchestrator.run_weekly_generation()

        # David: round(90 * 1.6) = 144g (the max)
        # Sarah: round(70 * 1.6) = 112g
        # The shared plan should use 144g
        calls = mock_model.generate_content.call_args_list
        all_prompts_text = " ".join(call[0][0] for call in calls)
        assert "144" in all_prompts_text

    def test_prompt_merges_preferences(
        self, mock_send_smtp, mock_genai, test_config
    ):
        """Prompt includes merged preferences from all users."""
        mock_model = _setup_mock_model_for_single_day(mock_genai)
        mock_send_smtp.return_value = None

        orchestrator = MealPlanOrchestrator(test_config)
        orchestrator.run_weekly_generation()

        calls = mock_model.generate_content.call_args_list
        all_prompts_text = " ".join(call[0][0] for call in calls)

        # Both users' dislikes should be in the prompt
        assert "smoothies" in all_prompts_text
        assert "onion" in all_prompts_text

        # Both users' likes should be in the prompt
        assert "high-protein meals" in all_prompts_text
        assert "simple recipes" in all_prompts_text


@patch("src.gemini_client.genai")
@patch("src.email_dispatcher.EmailDispatcher._send_smtp")
class TestPromptIncludesExcludedRecipes:
    """Test that the prompt includes excluded recipes from history.

    Validates: Requirement 2.4, 8.1
    """

    def test_prompt_contains_excluded_recipe_names(
        self, mock_send_smtp, mock_genai, tmp_path, monkeypatch
    ):
        """When history has recipes, those names appear in the prompt as exclusions."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.setenv("SENDER_EMAIL", "sender@example.com")
        monkeypatch.setenv("SENDER_PASSWORD", "password123")

        # Write config pointing to our history file
        config_path = _write_test_config(tmp_path)

        # Pre-populate history with some recipes (YAML format)
        from datetime import date

        history_data = [
            {
                "generation_date": date.today().isoformat(),
                "users": {
                    "David": ["Tofu Scramble", "Lentil Curry", "Seitan Stir Fry"],
                    "Sarah": ["Protein Smoothie", "Black Bean Bowl"],
                },
                "email_sent": True,
                "email_sent_at": None,
            }
        ]
        history_path = tmp_path / "history.yaml"
        history_path.write_text(
            yaml.dump(history_data, default_flow_style=False),
            encoding="utf-8",
        )

        # Set up mock
        mock_model = _setup_mock_model_for_single_day(mock_genai)
        mock_send_smtp.return_value = None

        orchestrator = MealPlanOrchestrator(config_path)
        orchestrator.run_weekly_generation()

        # Collect all prompts
        calls = mock_model.generate_content.call_args_list
        all_prompts_text = " ".join(call[0][0] for call in calls)

        # Verify excluded recipe names appear in the prompts
        assert "Tofu Scramble" in all_prompts_text
        assert "Lentil Curry" in all_prompts_text
        assert "Seitan Stir Fry" in all_prompts_text
        assert "Protein Smoothie" in all_prompts_text
        assert "Black Bean Bowl" in all_prompts_text


@patch("src.gemini_client.genai")
@patch("src.email_dispatcher.EmailDispatcher._send_smtp")
class TestHistoryUpdatedAfterGeneration:
    """Test that history file is updated after successful generation.

    Validates: Requirement 8.1
    """

    def test_history_file_created_and_contains_record(
        self, mock_send_smtp, mock_genai, tmp_path, monkeypatch
    ):
        """After pipeline runs, history file contains the new generation record."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
        monkeypatch.setenv("SENDER_EMAIL", "sender@example.com")
        monkeypatch.setenv("SENDER_PASSWORD", "password123")

        config_path = _write_test_config(tmp_path)
        history_path = tmp_path / "history.yaml"

        # Ensure history file does not exist before run
        assert not history_path.exists()

        # Set up mock
        _setup_mock_model_for_single_day(mock_genai)
        mock_send_smtp.return_value = None

        orchestrator = MealPlanOrchestrator(config_path)
        result = orchestrator.run_weekly_generation()

        assert result.success is True

        # Verify history file was created
        assert history_path.exists()

        # Load and verify content (YAML)
        history_data = yaml.safe_load(history_path.read_text(encoding="utf-8"))
        assert isinstance(history_data, list)
        assert len(history_data) == 1

        record = history_data[0]
        assert "generation_date" in record
        assert "users" in record
        assert "email_sent" in record
        assert "email_sent_at" in record

        # Verify both users have recipe entries (same recipes since it's a shared plan)
        assert "David" in record["users"]
        assert "Sarah" in record["users"]

        # Both users should have the same recipe list (shared plan)
        david_recipes = record["users"]["David"]
        sarah_recipes = record["users"]["Sarah"]
        assert david_recipes == sarah_recipes
        assert len(david_recipes) > 0

        # Recipe names should match what was generated
        assert any("Breakfast" in r for r in david_recipes)
        assert any("Lunch" in r for r in david_recipes)
        assert any("Dinner" in r for r in david_recipes)

        # Verify email_sent field
        assert record["email_sent"] is True
