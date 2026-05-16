"""Unit tests for ResponseValidator."""

import pytest

from src.response_validator import ResponseValidator


@pytest.fixture
def validator():
    return ResponseValidator()


def _make_recipe(overrides=None):
    """Helper to create a valid recipe dict."""
    recipe = {
        "id": "recipe-001",
        "name": "Tofu Scramble",
        "protein_source_category": "tofu_and_tempeh",
        "servings": 2,
        "ingredients": [
            {"name": "firm tofu", "quantity": 400, "unit": "g"},
            {"name": "spinach", "quantity": 100, "unit": "g"},
        ],
        "macros_per_serving": {
            "protein_g": 25.0,
            "carbs_g": 10.0,
            "fat_g": 12.0,
        },
        "instructions": "Crumble tofu and cook with spinach.",
    }
    if overrides:
        recipe.update(overrides)
    return recipe


def _make_day(day_name="Monday", recipe_overrides=None):
    """Helper to create a valid day dict."""
    recipe = _make_recipe(recipe_overrides)
    return {
        "day": day_name,
        "meals": {
            "breakfast": recipe,
            "lunch": _make_recipe({"id": "recipe-002", "name": "Lentil Soup"}),
            "dinner": _make_recipe({"id": "recipe-003", "name": "Seitan Stir Fry"}),
            "snacks": [_make_recipe({"id": "recipe-004", "name": "Protein Balls"})],
        },
    }


def _make_valid_meal_plan():
    """Helper to create a valid 7-day meal plan."""
    days_of_week = [
        "Monday", "Tuesday", "Wednesday", "Thursday",
        "Friday", "Saturday", "Sunday",
    ]
    return {"days": [_make_day(day) for day in days_of_week]}


class TestValidateMealPlan:
    """Tests for validate_meal_plan method."""

    def test_valid_meal_plan_passes(self, validator):
        plan = _make_valid_meal_plan()
        result = validator.validate_meal_plan(plan)
        assert result.is_valid is True
        assert result.errors == []

    def test_missing_days_key(self, validator):
        result = validator.validate_meal_plan({})
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_fewer_than_7_days(self, validator):
        plan = {"days": [_make_day("Monday")] * 6}
        result = validator.validate_meal_plan(plan)
        assert result.is_valid is False

    def test_more_than_7_days(self, validator):
        plan = {"days": [_make_day("Monday")] * 8}
        result = validator.validate_meal_plan(plan)
        assert result.is_valid is False

    def test_missing_meals_key_in_day(self, validator):
        plan = _make_valid_meal_plan()
        plan["days"][0] = {"day": "Monday"}
        result = validator.validate_meal_plan(plan)
        assert result.is_valid is False

    def test_missing_breakfast_in_meals(self, validator):
        plan = _make_valid_meal_plan()
        del plan["days"][0]["meals"]["breakfast"]
        result = validator.validate_meal_plan(plan)
        assert result.is_valid is False

    def test_snacks_empty_array(self, validator):
        plan = _make_valid_meal_plan()
        plan["days"][0]["meals"]["snacks"] = []
        result = validator.validate_meal_plan(plan)
        assert result.is_valid is False

    def test_snacks_more_than_3(self, validator):
        plan = _make_valid_meal_plan()
        plan["days"][0]["meals"]["snacks"] = [_make_recipe()] * 4
        result = validator.validate_meal_plan(plan)
        assert result.is_valid is False

    def test_recipe_missing_required_field(self, validator):
        plan = _make_valid_meal_plan()
        del plan["days"][0]["meals"]["breakfast"]["id"]
        result = validator.validate_meal_plan(plan)
        assert result.is_valid is False


class TestValidateRecipe:
    """Tests for validate_recipe method."""

    def test_valid_recipe(self, validator):
        recipe = _make_recipe()
        result = validator.validate_recipe(recipe)
        assert result.is_valid is True

    def test_missing_id_field(self, validator):
        recipe = _make_recipe()
        del recipe["id"]
        result = validator.validate_recipe(recipe)
        assert result.is_valid is False
        assert "id" in result.invalid_fields

    def test_missing_multiple_fields(self, validator):
        recipe = _make_recipe()
        del recipe["id"]
        del recipe["name"]
        result = validator.validate_recipe(recipe)
        assert result.is_valid is False
        assert "id" in result.invalid_fields
        assert "name" in result.invalid_fields

    def test_missing_macros_per_serving(self, validator):
        recipe = _make_recipe()
        del recipe["macros_per_serving"]
        result = validator.validate_recipe(recipe)
        assert result.is_valid is False
        assert "macros_per_serving" in result.invalid_fields

    def test_non_numeric_protein(self, validator):
        recipe = _make_recipe()
        recipe["macros_per_serving"]["protein_g"] = "twenty"
        result = validator.validate_recipe(recipe)
        assert result.is_valid is False
        assert "protein_g" in result.invalid_fields

    def test_non_numeric_carbs(self, validator):
        recipe = _make_recipe()
        recipe["macros_per_serving"]["carbs_g"] = "ten"
        result = validator.validate_recipe(recipe)
        assert result.is_valid is False
        assert "carbs_g" in result.invalid_fields

    def test_non_numeric_fat(self, validator):
        recipe = _make_recipe()
        recipe["macros_per_serving"]["fat_g"] = None
        result = validator.validate_recipe(recipe)
        assert result.is_valid is False
        assert "fat_g" in result.invalid_fields

    def test_macros_not_a_dict(self, validator):
        recipe = _make_recipe()
        recipe["macros_per_serving"] = "invalid"
        result = validator.validate_recipe(recipe)
        assert result.is_valid is False
        assert "macros_per_serving" in result.invalid_fields

    def test_integer_macros_are_valid(self, validator):
        recipe = _make_recipe()
        recipe["macros_per_serving"] = {
            "protein_g": 25,
            "carbs_g": 10,
            "fat_g": 12,
        }
        result = validator.validate_recipe(recipe)
        assert result.is_valid is True


class TestValidateMacronutrients:
    """Tests for validate_macronutrients method."""

    def test_protein_above_minimum(self, validator):
        recipe = _make_recipe({"macros_per_serving": {
            "protein_g": 25.0, "carbs_g": 10.0, "fat_g": 12.0
        }})
        result = validator.validate_macronutrients(recipe, protein_target=144)
        assert result.is_valid is True

    def test_protein_exactly_20(self, validator):
        recipe = _make_recipe({"macros_per_serving": {
            "protein_g": 20.0, "carbs_g": 10.0, "fat_g": 12.0
        }})
        result = validator.validate_macronutrients(recipe, protein_target=144)
        assert result.is_valid is True

    def test_protein_below_20_flagged(self, validator):
        recipe = _make_recipe({"macros_per_serving": {
            "protein_g": 15.0, "carbs_g": 10.0, "fat_g": 12.0
        }})
        result = validator.validate_macronutrients(recipe, protein_target=144)
        assert result.is_valid is False
        assert "below minimum 20g threshold" in result.errors[0]

    def test_missing_macros_per_serving(self, validator):
        recipe = {"id": "r1", "name": "Test"}
        result = validator.validate_macronutrients(recipe, protein_target=144)
        assert result.is_valid is False

    def test_missing_protein_g(self, validator):
        recipe = _make_recipe({"macros_per_serving": {
            "carbs_g": 10.0, "fat_g": 12.0
        }})
        result = validator.validate_macronutrients(recipe, protein_target=144)
        assert result.is_valid is False

    def test_non_numeric_protein_g(self, validator):
        recipe = _make_recipe({"macros_per_serving": {
            "protein_g": "high", "carbs_g": 10.0, "fat_g": 12.0
        }})
        result = validator.validate_macronutrients(recipe, protein_target=144)
        assert result.is_valid is False

    def test_zero_protein_flagged(self, validator):
        recipe = _make_recipe({"macros_per_serving": {
            "protein_g": 0.0, "carbs_g": 10.0, "fat_g": 12.0
        }})
        result = validator.validate_macronutrients(recipe, protein_target=144)
        assert result.is_valid is False
