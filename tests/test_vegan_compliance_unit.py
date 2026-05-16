"""Unit tests for VeganComplianceChecker."""

import pytest

from src.models import ComplianceResult, IngredientEntry, Recipe
from src.vegan_compliance import VeganComplianceChecker


@pytest.fixture
def checker() -> VeganComplianceChecker:
    return VeganComplianceChecker()


class TestIsIngredientVegan:
    """Tests for is_ingredient_vegan method."""

    def test_vegan_ingredients_pass(self, checker: VeganComplianceChecker) -> None:
        vegan_items = ["tofu", "lentils", "quinoa", "broccoli", "soy sauce", "tempeh"]
        for item in vegan_items:
            assert checker.is_ingredient_vegan(item) is True

    def test_exact_match_non_vegan(self, checker: VeganComplianceChecker) -> None:
        assert checker.is_ingredient_vegan("chicken") is False
        assert checker.is_ingredient_vegan("beef") is False
        assert checker.is_ingredient_vegan("milk") is False
        assert checker.is_ingredient_vegan("egg") is False
        assert checker.is_ingredient_vegan("honey") is False
        assert checker.is_ingredient_vegan("gelatin") is False

    def test_case_insensitive(self, checker: VeganComplianceChecker) -> None:
        assert checker.is_ingredient_vegan("Chicken") is False
        assert checker.is_ingredient_vegan("BEEF") is False
        assert checker.is_ingredient_vegan("Milk") is False
        assert checker.is_ingredient_vegan("EGG") is False

    def test_substring_match(self, checker: VeganComplianceChecker) -> None:
        assert checker.is_ingredient_vegan("milk chocolate") is False
        assert checker.is_ingredient_vegan("egg noodles") is False
        assert checker.is_ingredient_vegan("honey mustard") is False
        assert checker.is_ingredient_vegan("chicken broth") is False

    def test_animal_derived_additives(self, checker: VeganComplianceChecker) -> None:
        assert checker.is_ingredient_vegan("casein") is False
        assert checker.is_ingredient_vegan("whey protein") is False
        assert checker.is_ingredient_vegan("carmine dye") is False
        assert checker.is_ingredient_vegan("lanolin") is False
        assert checker.is_ingredient_vegan("shellac") is False


class TestCheckRecipe:
    """Tests for check_recipe method."""

    def test_compliant_recipe(self, checker: VeganComplianceChecker) -> None:
        recipe = Recipe(
            id="1",
            name="Tofu Stir Fry",
            protein_source_category="tofu_and_tempeh",
            servings=2,
            ingredients=[
                IngredientEntry(name="tofu", quantity=200, unit="g"),
                IngredientEntry(name="broccoli", quantity=100, unit="g"),
                IngredientEntry(name="soy sauce", quantity=2, unit="tbsp"),
            ],
            macros_per_serving={"protein_g": 25, "carbs_g": 10, "fat_g": 8},
            instructions="Cook it",
        )
        result = checker.check_recipe(recipe)
        assert result.is_compliant is True
        assert result.rejected_ingredient is None
        assert result.non_vegan_category is None

    def test_non_compliant_recipe(self, checker: VeganComplianceChecker) -> None:
        recipe = Recipe(
            id="2",
            name="Bad Recipe",
            protein_source_category="legumes",
            servings=1,
            ingredients=[
                IngredientEntry(name="lentils", quantity=200, unit="g"),
                IngredientEntry(name="butter", quantity=20, unit="g"),
            ],
            macros_per_serving={"protein_g": 20, "carbs_g": 30, "fat_g": 15},
            instructions="Mix it",
        )
        result = checker.check_recipe(recipe)
        assert result.is_compliant is False
        assert result.rejected_ingredient == "butter"
        assert result.non_vegan_category == "dairy"

    def test_dict_recipe_input(self, checker: VeganComplianceChecker) -> None:
        recipe_dict = {
            "ingredients": [
                {"name": "rice"},
                {"name": "egg noodles"},
            ]
        }
        result = checker.check_recipe(recipe_dict)
        assert result.is_compliant is False
        assert result.rejected_ingredient == "egg noodles"
        assert result.non_vegan_category == "eggs"

    def test_dict_recipe_all_vegan(self, checker: VeganComplianceChecker) -> None:
        recipe_dict = {
            "ingredients": [
                {"name": "rice"},
                {"name": "black beans"},
                {"name": "avocado"},
            ]
        }
        result = checker.check_recipe(recipe_dict)
        assert result.is_compliant is True

    def test_empty_ingredients(self, checker: VeganComplianceChecker) -> None:
        recipe_dict = {"ingredients": []}
        result = checker.check_recipe(recipe_dict)
        assert result.is_compliant is True

    def test_stops_at_first_non_vegan(self, checker: VeganComplianceChecker) -> None:
        recipe_dict = {
            "ingredients": [
                {"name": "chicken"},
                {"name": "milk"},
                {"name": "egg"},
            ]
        }
        result = checker.check_recipe(recipe_dict)
        assert result.is_compliant is False
        assert result.rejected_ingredient == "chicken"
        assert result.non_vegan_category == "poultry"


class TestNonVeganCategories:
    """Tests for NON_VEGAN_CATEGORIES coverage."""

    def test_all_categories_present(self, checker: VeganComplianceChecker) -> None:
        expected = {
            "meat", "poultry", "fish", "shellfish",
            "dairy", "eggs", "honey", "gelatin",
            "animal-derived additives",
        }
        assert set(checker.NON_VEGAN_CATEGORIES.keys()) == expected

    def test_categories_have_keywords(self, checker: VeganComplianceChecker) -> None:
        for category, keywords in checker.NON_VEGAN_CATEGORIES.items():
            assert len(keywords) > 0, f"Category '{category}' has no keywords"
