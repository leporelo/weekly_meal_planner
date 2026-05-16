"""Unit tests for GeminiClient."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.gemini_client import DAYS_OF_WEEK, GeminiClient
from src.models import SINGLE_DAY_JSON_SCHEMA, UserProfile


@pytest.fixture
def api_key():
    return "test-api-key-12345"


@pytest.fixture
def sample_profile():
    return UserProfile(
        name="David",
        email="david@example.com",
        weight_kg=90.0,
        height_cm=180,
        gender="male",
    )


@pytest.fixture
def valid_single_day_response():
    """A minimal valid single day response matching SINGLE_DAY_JSON_SCHEMA."""
    recipe = {
        "id": "recipe-001",
        "name": "Tofu Scramble",
        "protein_source_category": "tofu_and_tempeh",
        "servings": 2,
        "ingredients": [
            {"name": "firm tofu", "quantity": 400, "unit": "g"},
            {"name": "spinach", "quantity": 100, "unit": "g"},
        ],
        "macros_per_serving": {"protein_g": 25.0, "carbs_g": 8.0, "fat_g": 12.0},
        "instructions": "Press tofu for 15 minutes to remove excess water. Crumble into a heated pan with olive oil. Add turmeric, nutritional yeast, and black salt for egg-like flavor. Cook for 5 minutes, then add spinach and cook until wilted.",
        "prep_time_min": 20,
        "cook_time_min": 10,
    }
    snack = {
        "id": "snack-001",
        "name": "Protein Shake",
        "protein_source_category": "nuts_and_seeds",
        "servings": 1,
        "ingredients": [
            {"name": "hemp seeds", "quantity": 30, "unit": "g"},
            {"name": "banana", "quantity": 1, "unit": "whole"},
        ],
        "macros_per_serving": {"protein_g": 22.0, "carbs_g": 30.0, "fat_g": 9.0},
        "instructions": "Add hemp seeds, banana, and 300ml plant milk to a blender. Blend on high for 60 seconds until smooth and creamy. Pour into a glass and serve immediately.",
        "prep_time_min": 5,
        "cook_time_min": 0,
    }
    return {
        "day": "Monday",
        "meals": {
            "breakfast": recipe,
            "lunch": recipe,
            "dinner": recipe,
            "snacks": [snack],
        },
    }


@pytest.fixture
def valid_meal_plan_response(valid_single_day_response):
    """A full 7-day meal plan built from single day responses."""
    days = []
    for day_name in DAYS_OF_WEEK:
        day = json.loads(json.dumps(valid_single_day_response))
        day["day"] = day_name
        days.append(day)
    return {"days": days}


@patch("src.gemini_client.genai")
class TestGeminiClientInit:
    """Tests for GeminiClient initialization."""

    def test_init_with_explicit_api_key(self, mock_genai):
        client = GeminiClient(api_key="my-key", model="gemini-2.0-flash")
        assert client.api_key == "my-key"
        assert client.model_name == "gemini-2.0-flash"
        mock_genai.configure.assert_called_once_with(api_key="my-key")

    def test_init_with_env_var(self, mock_genai, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "env-key")
        client = GeminiClient()
        assert client.api_key == "env-key"
        mock_genai.configure.assert_called_once_with(api_key="env-key")

    def test_init_raises_without_api_key(self, mock_genai, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(ValueError, match="API key must be provided"):
            GeminiClient()

    def test_init_default_model(self, mock_genai):
        client = GeminiClient(api_key="key")
        assert client.model_name == "gemini-2.0-flash"

    def test_init_custom_model(self, mock_genai):
        client = GeminiClient(api_key="key", model="gemini-1.5-pro")
        assert client.model_name == "gemini-1.5-pro"


@patch("src.gemini_client.genai")
class TestGenerateSingleDay:
    """Tests for the generate_single_day method."""

    def test_successful_single_day_generation(self, mock_genai, sample_profile, valid_single_day_response):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        mock_response = MagicMock()
        mock_response.text = json.dumps(valid_single_day_response)
        mock_model.generate_content.return_value = mock_response

        client = GeminiClient(api_key="test-key")
        result = client.generate_single_day(
            sample_profile, "Monday", excluded_recipes=[], already_used_recipes=[]
        )

        assert result == valid_single_day_response
        mock_model.generate_content.assert_called_once()

    def test_strips_markdown_code_blocks(self, mock_genai, sample_profile, valid_single_day_response):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        mock_response = MagicMock()
        mock_response.text = f"```json\n{json.dumps(valid_single_day_response)}\n```"
        mock_model.generate_content.return_value = mock_response

        client = GeminiClient(api_key="test-key")
        result = client.generate_single_day(
            sample_profile, "Monday", excluded_recipes=[], already_used_recipes=[]
        )

        assert result == valid_single_day_response

    def test_retry_on_schema_validation_failure(self, mock_genai, sample_profile, valid_single_day_response):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        invalid_response = MagicMock()
        invalid_response.text = json.dumps({"day": "Monday"})  # Missing meals

        valid_response = MagicMock()
        valid_response.text = json.dumps(valid_single_day_response)

        mock_model.generate_content.side_effect = [invalid_response, valid_response]

        client = GeminiClient(api_key="test-key")
        result = client.generate_single_day(
            sample_profile, "Monday", excluded_recipes=[], already_used_recipes=[]
        )

        assert result == valid_single_day_response
        assert mock_model.generate_content.call_count == 2

    def test_retry_on_api_error(self, mock_genai, sample_profile, valid_single_day_response):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        valid_response = MagicMock()
        valid_response.text = json.dumps(valid_single_day_response)

        mock_model.generate_content.side_effect = [
            Exception("API timeout"),
            valid_response,
        ]

        client = GeminiClient(api_key="test-key")
        result = client.generate_single_day(
            sample_profile, "Monday", excluded_recipes=[], already_used_recipes=[]
        )

        assert result == valid_single_day_response
        assert mock_model.generate_content.call_count == 2

    def test_raises_after_max_retries_exhausted(self, mock_genai, sample_profile):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        mock_model.generate_content.side_effect = Exception("API error")

        client = GeminiClient(api_key="test-key")

        with pytest.raises(RuntimeError, match="Failed to generate valid meal plan for Monday"):
            client.generate_single_day(
                sample_profile, "Monday", excluded_recipes=[], already_used_recipes=[]
            )

        # 1 initial + 2 retries = 3 total attempts
        assert mock_model.generate_content.call_count == 3

    def test_prompt_includes_already_used_recipes(self, mock_genai, sample_profile, valid_single_day_response):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        mock_response = MagicMock()
        mock_response.text = json.dumps(valid_single_day_response)
        mock_model.generate_content.return_value = mock_response

        client = GeminiClient(api_key="test-key")
        client.generate_single_day(
            sample_profile, "Tuesday",
            excluded_recipes=[],
            already_used_recipes=["Tofu Scramble", "Lentil Curry"],
        )

        call_args = mock_model.generate_content.call_args[0][0]
        assert "Tofu Scramble" in call_args
        assert "Lentil Curry" in call_args
        assert "Already Used This Week" in call_args


@patch("src.gemini_client.genai")
class TestGenerateMealPlan:
    """Tests for the generate_meal_plan method (calls generate_single_day 7 times)."""

    def test_successful_generation_calls_7_times(self, mock_genai, sample_profile, valid_single_day_response):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        # Return a valid single-day response for each call, varying the day name
        def make_response(prompt):
            # Extract day name from prompt and build appropriate response
            for day_name in DAYS_OF_WEEK:
                if f"**{day_name}**" in prompt:
                    day_resp = json.loads(json.dumps(valid_single_day_response))
                    day_resp["day"] = day_name
                    mock_resp = MagicMock()
                    mock_resp.text = json.dumps(day_resp)
                    return mock_resp
            # Fallback
            mock_resp = MagicMock()
            mock_resp.text = json.dumps(valid_single_day_response)
            return mock_resp

        mock_model.generate_content.side_effect = make_response

        client = GeminiClient(api_key="test-key")
        result = client.generate_meal_plan(sample_profile, excluded_recipes=[])

        assert "days" in result
        assert len(result["days"]) == 7
        assert mock_model.generate_content.call_count == 7

    def test_prompt_includes_protein_target(self, mock_genai, sample_profile, valid_single_day_response):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        mock_response = MagicMock()
        mock_response.text = json.dumps(valid_single_day_response)
        mock_model.generate_content.return_value = mock_response

        client = GeminiClient(api_key="test-key")
        client.generate_meal_plan(sample_profile, excluded_recipes=[])

        # Check first call's prompt
        call_args = mock_model.generate_content.call_args_list[0][0][0]
        assert str(sample_profile.protein_target_g) in call_args
        assert "144" in call_args  # 90 * 1.6 = 144

    def test_prompt_includes_excluded_recipes(self, mock_genai, sample_profile, valid_single_day_response):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        mock_response = MagicMock()
        mock_response.text = json.dumps(valid_single_day_response)
        mock_model.generate_content.return_value = mock_response

        client = GeminiClient(api_key="test-key")
        excluded = ["Tofu Scramble", "Lentil Curry"]
        client.generate_meal_plan(sample_profile, excluded_recipes=excluded)

        call_args = mock_model.generate_content.call_args_list[0][0][0]
        assert "Tofu Scramble" in call_args
        assert "Lentil Curry" in call_args

    def test_prompt_includes_vegan_constraint(self, mock_genai, sample_profile, valid_single_day_response):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        mock_response = MagicMock()
        mock_response.text = json.dumps(valid_single_day_response)
        mock_model.generate_content.return_value = mock_response

        client = GeminiClient(api_key="test-key")
        client.generate_meal_plan(sample_profile, excluded_recipes=[])

        call_args = mock_model.generate_content.call_args_list[0][0][0]
        assert "100% vegan" in call_args

    def test_invalid_json_response_triggers_retry(self, mock_genai, sample_profile, valid_single_day_response):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        bad_response = MagicMock()
        bad_response.text = "This is not valid JSON at all"

        good_response = MagicMock()
        good_response.text = json.dumps(valid_single_day_response)

        # First call fails, then all subsequent succeed
        mock_model.generate_content.side_effect = [bad_response, good_response] + [
            good_response
        ] * 6

        client = GeminiClient(api_key="test-key")
        result = client.generate_meal_plan(sample_profile, excluded_recipes=[])

        assert "days" in result
        # First day took 2 attempts, rest took 1 each = 8 total
        assert mock_model.generate_content.call_count == 8
