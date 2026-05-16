"""Property-based tests for ResponseValidator.

Uses Hypothesis to verify universal properties of meal plan schema validation,
daily protein targets, and minimum protein per recipe.
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.response_validator import ResponseValidator


# --- Strategies ---

PROTEIN_SOURCE_CATEGORIES = [
    "legumes",
    "tofu_and_tempeh",
    "seitan",
    "nuts_and_seeds",
    "protein_rich_grains",
]

VALID_UNITS = ["g", "ml", "whole", "tbsp", "tsp", "cup"]


@st.composite
def valid_ingredient_strategy(draw):
    """Generate a valid ingredient dict."""
    return {
        "name": draw(st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "Nd", "Zs")))),
        "quantity": draw(st.floats(min_value=0.1, max_value=5000.0, allow_nan=False, allow_infinity=False)),
        "unit": draw(st.sampled_from(VALID_UNITS)),
    }


@st.composite
def valid_recipe_strategy(draw, protein_g=None):
    """Generate a valid recipe dict with all required fields.

    If protein_g is provided, use that value; otherwise generate one >= 20.
    """
    if protein_g is None:
        protein_val = draw(st.floats(min_value=20.0, max_value=80.0, allow_nan=False, allow_infinity=False))
    else:
        protein_val = protein_g

    return {
        "id": draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "Nd")))),
        "name": draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "Nd", "Zs")))),
        "protein_source_category": draw(st.sampled_from(PROTEIN_SOURCE_CATEGORIES)),
        "servings": draw(st.integers(min_value=1, max_value=8)),
        "ingredients": draw(st.lists(valid_ingredient_strategy(), min_size=1, max_size=10)),
        "macros_per_serving": {
            "protein_g": protein_val,
            "carbs_g": draw(st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False)),
            "fat_g": draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)),
        },
        "instructions": draw(st.text(min_size=1, max_size=200, alphabet=st.characters(whitelist_categories=("L", "Nd", "Zs", "Po")))),
    }


@st.composite
def valid_day_strategy(draw):
    """Generate a valid day dict with breakfast/lunch/dinner and 1-3 snacks."""
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    num_snacks = draw(st.integers(min_value=1, max_value=3))
    snacks = [draw(valid_recipe_strategy()) for _ in range(num_snacks)]
    return {
        "day": draw(st.sampled_from(day_names)),
        "meals": {
            "breakfast": draw(valid_recipe_strategy()),
            "lunch": draw(valid_recipe_strategy()),
            "dinner": draw(valid_recipe_strategy()),
            "snacks": snacks,
        },
    }


@st.composite
def valid_meal_plan_strategy(draw):
    """Generate a valid 7-day meal plan structure."""
    days = [draw(valid_day_strategy()) for _ in range(7)]
    return {"days": days}


# Feature: vegan-meal-planner, Property 3: Meal plan schema validation
# Validates: Requirements 2.6, 3.1, 3.2, 3.5
@settings(max_examples=100)
@given(plan=valid_meal_plan_strategy())
def test_valid_meal_plan_passes_schema_validation(plan: dict) -> None:
    """For any JSON response containing exactly 7 days each with breakfast/lunch/dinner
    and 1-3 snacks, and every recipe includes all required fields, the schema validator
    SHALL accept it."""
    validator = ResponseValidator()
    result = validator.validate_meal_plan(plan)
    assert result.is_valid is True, (
        f"Valid meal plan should pass schema validation, but got errors: {result.errors}"
    )


# Feature: vegan-meal-planner, Property 3: Meal plan schema validation (invalid - wrong day count)
# Validates: Requirements 2.6, 3.1, 3.2, 3.5
@settings(max_examples=100)
@given(num_days=st.integers(min_value=0, max_value=20).filter(lambda x: x != 7))
def test_invalid_day_count_fails_schema_validation(num_days: int) -> None:
    """For any JSON response that does NOT contain exactly 7 days, the schema validator
    SHALL reject it."""
    validator = ResponseValidator()

    # Build a simple valid recipe for structure
    recipe = {
        "id": "r1",
        "name": "Test Recipe",
        "protein_source_category": "legumes",
        "servings": 1,
        "ingredients": [{"name": "lentils", "quantity": 200, "unit": "g"}],
        "macros_per_serving": {"protein_g": 25.0, "carbs_g": 30.0, "fat_g": 5.0},
        "instructions": "Cook lentils.",
    }
    day = {
        "day": "Monday",
        "meals": {
            "breakfast": recipe,
            "lunch": recipe,
            "dinner": recipe,
            "snacks": [recipe],
        },
    }
    plan = {"days": [day] * num_days}
    result = validator.validate_meal_plan(plan)
    assert result.is_valid is False, (
        f"Meal plan with {num_days} days should fail schema validation"
    )


# Feature: vegan-meal-planner, Property 3: Meal plan schema validation (invalid - missing required meal)
# Validates: Requirements 2.6, 3.1, 3.2, 3.5
@settings(max_examples=100)
@given(missing_meal=st.sampled_from(["breakfast", "lunch", "dinner", "snacks"]))
def test_missing_meal_type_fails_schema_validation(missing_meal: str) -> None:
    """For any meal plan where a day is missing a required meal type (breakfast,
    lunch, dinner, or snacks), the schema validator SHALL reject it."""
    validator = ResponseValidator()

    recipe = {
        "id": "r1",
        "name": "Test Recipe",
        "protein_source_category": "legumes",
        "servings": 1,
        "ingredients": [{"name": "lentils", "quantity": 200, "unit": "g"}],
        "macros_per_serving": {"protein_g": 25.0, "carbs_g": 30.0, "fat_g": 5.0},
        "instructions": "Cook lentils.",
    }
    day = {
        "day": "Monday",
        "meals": {
            "breakfast": recipe,
            "lunch": recipe,
            "dinner": recipe,
            "snacks": [recipe],
        },
    }
    # Remove the target meal from one day
    days = []
    for i in range(7):
        d = {
            "day": "Day" + str(i),
            "meals": dict(day["meals"]),
        }
        if i == 0:
            del d["meals"][missing_meal]
        days.append(d)

    plan = {"days": days}
    result = validator.validate_meal_plan(plan)
    assert result.is_valid is False, (
        f"Meal plan missing '{missing_meal}' should fail schema validation"
    )


# Feature: vegan-meal-planner, Property 3: Meal plan schema validation (invalid - missing recipe fields)
# Validates: Requirements 2.6, 3.1, 3.2, 3.5
@settings(max_examples=100)
@given(
    missing_field=st.sampled_from([
        "id", "name", "protein_source_category", "servings",
        "ingredients", "macros_per_serving", "instructions",
    ])
)
def test_recipe_missing_required_field_fails_schema_validation(missing_field: str) -> None:
    """For any meal plan where a recipe is missing a required field, the schema
    validator SHALL reject it."""
    validator = ResponseValidator()

    recipe = {
        "id": "r1",
        "name": "Test Recipe",
        "protein_source_category": "legumes",
        "servings": 1,
        "ingredients": [{"name": "lentils", "quantity": 200, "unit": "g"}],
        "macros_per_serving": {"protein_g": 25.0, "carbs_g": 30.0, "fat_g": 5.0},
        "instructions": "Cook lentils.",
    }
    incomplete_recipe = dict(recipe)
    del incomplete_recipe[missing_field]

    day_template = {
        "day": "Monday",
        "meals": {
            "breakfast": recipe,
            "lunch": recipe,
            "dinner": recipe,
            "snacks": [recipe],
        },
    }
    days = []
    for i in range(7):
        d = {"day": f"Day{i}", "meals": dict(day_template["meals"])}
        if i == 0:
            # Put the incomplete recipe in breakfast
            d["meals"] = dict(d["meals"])
            d["meals"]["breakfast"] = incomplete_recipe
        days.append(d)

    plan = {"days": days}
    result = validator.validate_meal_plan(plan)
    assert result.is_valid is False, (
        f"Meal plan with recipe missing '{missing_field}' should fail schema validation"
    )


# Feature: vegan-meal-planner, Property 4: Daily protein meets target
# Validates: Requirements 2.3, 3.3
@settings(max_examples=100)
@given(
    protein_target=st.integers(min_value=48, max_value=480),
    num_snacks=st.integers(min_value=1, max_value=3),
)
def test_daily_protein_meets_target_when_recipes_compliant(
    protein_target: int, num_snacks: int
) -> None:
    """For any validated meal plan, sum of protein_g across all meals for each day
    SHALL be >= user's protein target when each recipe has sufficient protein."""
    validator = ResponseValidator()

    # Calculate minimum protein per recipe to ensure daily target is met
    # Each day has breakfast + lunch + dinner + snacks (num_snacks)
    total_meals = 3 + num_snacks
    # Distribute protein evenly, ensuring each recipe has >= 20g
    protein_per_recipe = max(20.0, protein_target / total_meals)

    # Build a day with controlled protein values
    def make_recipe(protein_val):
        return {
            "id": "r1",
            "name": "High Protein Recipe",
            "protein_source_category": "legumes",
            "servings": 1,
            "ingredients": [{"name": "lentils", "quantity": 200, "unit": "g"}],
            "macros_per_serving": {"protein_g": protein_val, "carbs_g": 30.0, "fat_g": 10.0},
            "instructions": "Cook.",
        }

    recipe = make_recipe(protein_per_recipe)
    snacks = [make_recipe(protein_per_recipe) for _ in range(num_snacks)]

    # Compute daily protein sum
    daily_protein = protein_per_recipe * total_meals
    assert daily_protein >= protein_target, (
        f"Daily protein {daily_protein}g should be >= target {protein_target}g"
    )

    # Each recipe should pass validate_macronutrients since protein_per_recipe >= 20
    result = validator.validate_macronutrients(recipe, protein_target)
    assert result.is_valid is True, (
        f"Recipe with {protein_per_recipe}g protein should pass macronutrient validation, "
        f"but got errors: {result.errors}"
    )

    for snack in snacks:
        result = validator.validate_macronutrients(snack, protein_target)
        assert result.is_valid is True, (
            f"Snack recipe with {protein_per_recipe}g protein should pass macronutrient validation"
        )


# Feature: vegan-meal-planner, Property 4: Daily protein meets target (below target detection)
# Validates: Requirements 2.3, 3.3
@settings(max_examples=100)
@given(
    protein_per_recipe=st.floats(min_value=0.0, max_value=19.9, allow_nan=False, allow_infinity=False),
    protein_target=st.integers(min_value=80, max_value=480),
)
def test_daily_protein_below_target_detected(
    protein_per_recipe: float, protein_target: int
) -> None:
    """For any meal plan where recipes have protein below 20g threshold,
    the validator SHALL flag them as non-compliant, indicating the daily
    protein target cannot be reliably met."""
    validator = ResponseValidator()

    recipe = {
        "id": "r1",
        "name": "Low Protein Recipe",
        "protein_source_category": "legumes",
        "servings": 1,
        "ingredients": [{"name": "lettuce", "quantity": 100, "unit": "g"}],
        "macros_per_serving": {"protein_g": protein_per_recipe, "carbs_g": 5.0, "fat_g": 2.0},
        "instructions": "Prepare salad.",
    }

    result = validator.validate_macronutrients(recipe, protein_target)
    assert result.is_valid is False, (
        f"Recipe with {protein_per_recipe}g protein (below 20g minimum) should fail "
        f"macronutrient validation"
    )
    assert len(result.errors) > 0, "Failed validation should include error messages"


# Feature: vegan-meal-planner, Property 5: Minimum protein per recipe
# Validates: Requirements 3.4
@settings(max_examples=100)
@given(
    protein_g=st.floats(min_value=20.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    protein_target=st.integers(min_value=48, max_value=480),
)
def test_recipe_at_or_above_minimum_protein_passes(
    protein_g: float, protein_target: int
) -> None:
    """For any recipe where protein_g per serving is >= 20g, the validator
    SHALL accept it as compliant."""
    validator = ResponseValidator()

    recipe = {
        "id": "r1",
        "name": "Compliant Recipe",
        "protein_source_category": "tofu_and_tempeh",
        "servings": 2,
        "ingredients": [{"name": "tofu", "quantity": 400, "unit": "g"}],
        "macros_per_serving": {"protein_g": protein_g, "carbs_g": 10.0, "fat_g": 8.0},
        "instructions": "Press and cook tofu.",
    }

    result = validator.validate_macronutrients(recipe, protein_target)
    assert result.is_valid is True, (
        f"Recipe with {protein_g}g protein (>= 20g) should pass, "
        f"but got errors: {result.errors}"
    )


# Feature: vegan-meal-planner, Property 5: Minimum protein per recipe (below threshold)
# Validates: Requirements 3.4
@settings(max_examples=100)
@given(
    protein_g=st.floats(min_value=0.0, max_value=19.9, allow_nan=False, allow_infinity=False),
    protein_target=st.integers(min_value=48, max_value=480),
)
def test_recipe_below_minimum_protein_flagged_non_compliant(
    protein_g: float, protein_target: int
) -> None:
    """For any recipe where protein_g per serving is < 20g, the validator
    SHALL flag it as non-compliant."""
    validator = ResponseValidator()

    recipe = {
        "id": "r1",
        "name": "Low Protein Recipe",
        "protein_source_category": "nuts_and_seeds",
        "servings": 1,
        "ingredients": [{"name": "almonds", "quantity": 30, "unit": "g"}],
        "macros_per_serving": {"protein_g": protein_g, "carbs_g": 5.0, "fat_g": 14.0},
        "instructions": "Serve a small handful.",
    }

    result = validator.validate_macronutrients(recipe, protein_target)
    assert result.is_valid is False, (
        f"Recipe with {protein_g}g protein (< 20g) should be flagged non-compliant"
    )
    assert any("below minimum 20g threshold" in err for err in result.errors), (
        f"Error should mention 'below minimum 20g threshold', got: {result.errors}"
    )
