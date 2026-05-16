"""Property-based tests for GroceryListBuilder.

Uses Hypothesis to verify universal properties of grocery list ingredient
completeness, aggregation, incompatible unit separation, and output normalization.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from src.grocery_list_builder import (
    COUNT_UNITS,
    GroceryListBuilder,
    VOLUME_UNITS,
    WEIGHT_UNITS,
)
from src.models import GroceryCategory, IngredientEntry, MealPlan, Recipe


# --- Constants ---

PROTEIN_SOURCE_CATEGORIES = [
    "legumes",
    "tofu_and_tempeh",
    "seitan",
    "nuts_and_seeds",
    "protein_rich_grains",
]

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

VALID_CATEGORIES: list[GroceryCategory] = [
    "produce",
    "grains",
    "legumes",
    "nuts_and_seeds",
    "condiments",
    "frozen",
    "other",
]

BASE_UNITS = ["g", "ml", "whole"]

WEIGHT_UNIT_LIST = list(WEIGHT_UNITS.keys())
VOLUME_UNIT_LIST = list(VOLUME_UNITS.keys())
COUNT_UNIT_LIST = list(COUNT_UNITS.keys())

ALL_UNITS = WEIGHT_UNIT_LIST + VOLUME_UNIT_LIST + COUNT_UNIT_LIST


# --- Strategies ---


@st.composite
def ingredient_strategy(draw, name=None, unit=None, exclude_names=None):
    """Generate a valid IngredientEntry."""
    if name is not None:
        ing_name = name
    else:
        available_names = [
            "tofu", "rice", "broccoli", "almonds", "olive oil",
            "chickpeas", "spinach", "quinoa", "oats", "lentils",
        ]
        if exclude_names:
            available_names = [n for n in available_names if n not in exclude_names]
        ing_name = draw(st.sampled_from(available_names))
    ing_unit = unit if unit is not None else draw(st.sampled_from(ALL_UNITS))
    quantity = draw(st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False))

    return IngredientEntry(
        name=ing_name,
        quantity=quantity,
        unit=ing_unit,
        category="other",
    )


@st.composite
def recipe_strategy(draw, ingredients=None, exclude_names=None):
    """Generate a valid Recipe with given or random ingredients."""
    if ingredients is None:
        num_ingredients = draw(st.integers(min_value=1, max_value=5))
        ingredients = [draw(ingredient_strategy(exclude_names=exclude_names)) for _ in range(num_ingredients)]

    return Recipe(
        id=draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "Nd")))),
        name=draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "Nd", "Zs")))),
        protein_source_category=draw(st.sampled_from(PROTEIN_SOURCE_CATEGORIES)),
        servings=draw(st.integers(min_value=1, max_value=4)),
        ingredients=ingredients,
        macros_per_serving={"protein_g": 25.0, "carbs_g": 30.0, "fat_g": 10.0},
        instructions="Prepare and serve.",
    )


@st.composite
def meal_plan_strategy(draw, recipes_per_day=None):
    """Generate a valid MealPlan with random recipes."""
    days = []
    for i in range(7):
        day_recipes = {"day": DAY_NAMES[i]}
        for slot in ("breakfast", "lunch", "dinner"):
            day_recipes[slot] = draw(recipe_strategy())
        num_snacks = draw(st.integers(min_value=1, max_value=2))
        snacks = [draw(recipe_strategy()) for _ in range(num_snacks)]
        day_recipes["snacks"] = snacks
        days.append(day_recipes)
    return MealPlan(days=days)


@st.composite
def meal_plans_with_shared_compatible_ingredients(draw):
    """Generate meal plans where multiple recipes use the same ingredient
    with compatible units (same unit family), enabling aggregation testing.
    """
    # Pick a shared ingredient name and unit family
    shared_name = draw(st.sampled_from(["tofu", "rice", "chickpeas", "quinoa", "oats"]))
    family = draw(st.sampled_from(["weight", "volume", "count"]))

    if family == "weight":
        units = WEIGHT_UNIT_LIST
    elif family == "volume":
        units = VOLUME_UNIT_LIST
    else:
        units = COUNT_UNIT_LIST

    # Create at least 2 recipes that share this ingredient with compatible units
    num_shared_recipes = draw(st.integers(min_value=2, max_value=4))
    shared_ingredients = []
    for _ in range(num_shared_recipes):
        unit = draw(st.sampled_from(units))
        qty = draw(st.floats(min_value=0.1, max_value=500.0, allow_nan=False, allow_infinity=False))
        shared_ingredients.append(
            IngredientEntry(name=shared_name, quantity=qty, unit=unit, category="other")
        )

    # Build recipes containing the shared ingredient
    recipes = []
    for ing in shared_ingredients:
        # Each recipe has the shared ingredient plus possibly others (excluding the shared name)
        other_ingredients = [
            draw(ingredient_strategy(exclude_names={shared_name}))
            for _ in range(draw(st.integers(min_value=0, max_value=2)))
        ]
        all_ings = [ing] + other_ingredients
        recipes.append(draw(recipe_strategy(ingredients=all_ings)))

    # Distribute recipes across a single meal plan, filler recipes exclude the shared name
    days = []
    recipe_idx = 0
    for i in range(7):
        day_recipes = {"day": DAY_NAMES[i]}
        for slot in ("breakfast", "lunch", "dinner"):
            if recipe_idx < len(recipes):
                day_recipes[slot] = recipes[recipe_idx]
                recipe_idx += 1
            else:
                day_recipes[slot] = draw(recipe_strategy(exclude_names={shared_name}))
        day_recipes["snacks"] = [draw(recipe_strategy(exclude_names={shared_name}))]
        days.append(day_recipes)

    plan = MealPlan(days=days)
    return [plan], shared_name, shared_ingredients, family


@st.composite
def meal_plans_with_incompatible_units(draw):
    """Generate meal plans where the same ingredient appears with incompatible
    unit types (e.g., weight and whole) across recipes.
    """
    shared_name = draw(st.sampled_from(["tofu", "chickpeas", "oats"]))

    # Pick two incompatible families
    families = draw(st.permutations(["weight", "volume", "count"]).map(lambda x: x[:2]))
    family_a, family_b = families

    def get_units(fam):
        if fam == "weight":
            return WEIGHT_UNIT_LIST
        elif fam == "volume":
            return VOLUME_UNIT_LIST
        else:
            return COUNT_UNIT_LIST

    unit_a = draw(st.sampled_from(get_units(family_a)))
    unit_b = draw(st.sampled_from(get_units(family_b)))

    qty_a = draw(st.floats(min_value=0.1, max_value=500.0, allow_nan=False, allow_infinity=False))
    qty_b = draw(st.floats(min_value=0.1, max_value=500.0, allow_nan=False, allow_infinity=False))

    ing_a = IngredientEntry(name=shared_name, quantity=qty_a, unit=unit_a, category="other")
    ing_b = IngredientEntry(name=shared_name, quantity=qty_b, unit=unit_b, category="other")

    recipe_a = draw(recipe_strategy(ingredients=[ing_a]))
    recipe_b = draw(recipe_strategy(ingredients=[ing_b]))

    # Build a meal plan with both recipes
    days = []
    days.append({
        "day": DAY_NAMES[0],
        "breakfast": recipe_a,
        "lunch": recipe_b,
        "dinner": draw(recipe_strategy()),
        "snacks": [draw(recipe_strategy())],
    })
    for i in range(1, 7):
        days.append({
            "day": DAY_NAMES[i],
            "breakfast": draw(recipe_strategy()),
            "lunch": draw(recipe_strategy()),
            "dinner": draw(recipe_strategy()),
            "snacks": [draw(recipe_strategy())],
        })

    plan = MealPlan(days=days)
    return [plan], shared_name, family_a, family_b


# =============================================================================
# Feature: vegan-meal-planner, Property 10: Grocery list ingredient completeness and aggregation
# Validates: Requirements 4.1, 4.2
# =============================================================================


@settings(max_examples=100)
@given(data=meal_plans_with_shared_compatible_ingredients())
def test_grocery_list_contains_all_ingredients_aggregated(
    data: tuple,
) -> None:
    """For any set of meal plans, the consolidated grocery list SHALL contain every
    ingredient from every recipe, and ingredients with the same canonical name and
    compatible unit types SHALL be aggregated into a single line item with the sum
    of their quantities.

    **Validates: Requirements 4.1, 4.2**
    """
    meal_plans, shared_name, shared_ingredients, family = data
    builder = GroceryListBuilder()
    grocery_list = builder.build(meal_plans)

    # Verify completeness: every unique ingredient name from all recipes
    # must appear in the grocery list
    all_ingredient_names = set()
    for plan in meal_plans:
        for recipe in plan.all_recipes():
            for ing in recipe.ingredients:
                all_ingredient_names.add(ing.name.strip().lower())

    grocery_names = {item.name for item in grocery_list.items}
    missing = all_ingredient_names - grocery_names
    assert not missing, (
        f"Grocery list is missing ingredients: {missing}. "
        f"Expected all of: {all_ingredient_names}"
    )

    # Verify aggregation: the shared ingredient with compatible units
    # should appear as exactly one line item for that unit family
    if family == "weight":
        base_unit = "g"
    elif family == "volume":
        base_unit = "ml"
    else:
        base_unit = "whole"

    # Find entries for the shared ingredient with the expected base unit
    shared_entries = [
        item for item in grocery_list.items
        if item.name == shared_name and item.unit == base_unit
    ]
    assert len(shared_entries) == 1, (
        f"Expected exactly 1 aggregated entry for '{shared_name}' in unit '{base_unit}', "
        f"but found {len(shared_entries)}. Entries: {shared_entries}"
    )

    # Verify the quantity is the sum of all input quantities converted to base unit
    expected_total = 0.0
    for ing in shared_ingredients:
        if family == "weight":
            expected_total += ing.quantity * WEIGHT_UNITS[ing.unit]
        elif family == "volume":
            expected_total += ing.quantity * VOLUME_UNITS[ing.unit]
        else:
            expected_total += ing.quantity * COUNT_UNITS[ing.unit]

    actual_total = shared_entries[0].quantity
    assert abs(actual_total - expected_total) < 1e-6, (
        f"Aggregated quantity for '{shared_name}' should be {expected_total:.6f}, "
        f"but got {actual_total:.6f}"
    )


# =============================================================================
# Feature: vegan-meal-planner, Property 11: Incompatible units yield separate line items
# Validates: Requirements 4.3
# =============================================================================


@settings(max_examples=100)
@given(data=meal_plans_with_incompatible_units())
def test_incompatible_units_yield_separate_line_items(
    data: tuple,
) -> None:
    """For any ingredient that appears with incompatible unit types (e.g., weight
    and whole) across recipes, the grocery list SHALL list each unit-type occurrence
    as a separate line item.

    **Validates: Requirements 4.3**
    """
    meal_plans, shared_name, family_a, family_b = data
    builder = GroceryListBuilder()
    grocery_list = builder.build(meal_plans)

    def base_unit_for_family(fam):
        if fam == "weight":
            return "g"
        elif fam == "volume":
            return "ml"
        else:
            return "whole"

    base_a = base_unit_for_family(family_a)
    base_b = base_unit_for_family(family_b)

    # Find all entries for the shared ingredient
    shared_entries = [
        item for item in grocery_list.items
        if item.name == shared_name
    ]

    # There should be at least 2 entries (one for each incompatible unit family)
    assert len(shared_entries) >= 2, (
        f"Expected at least 2 separate line items for '{shared_name}' "
        f"(one for '{base_a}', one for '{base_b}'), but found {len(shared_entries)}. "
        f"Entries: {[(e.name, e.quantity, e.unit) for e in shared_entries]}"
    )

    # Verify both base units are represented
    entry_units = {item.unit for item in shared_entries}
    assert base_a in entry_units, (
        f"Expected a line item for '{shared_name}' with unit '{base_a}', "
        f"but units found: {entry_units}"
    )
    assert base_b in entry_units, (
        f"Expected a line item for '{shared_name}' with unit '{base_b}', "
        f"but units found: {entry_units}"
    )


# =============================================================================
# Feature: vegan-meal-planner, Property 12: Grocery list output normalization
# Validates: Requirements 4.4, 4.5
# =============================================================================


@settings(max_examples=100)
@given(plans=st.lists(meal_plan_strategy(), min_size=1, max_size=2))
def test_grocery_list_output_normalization(plans: list[MealPlan]) -> None:
    """For any item in the final grocery list, the quantity SHALL be expressed in a
    base unit (grams for weight, milliliters for volume, or whole for countable items)
    and SHALL be assigned to exactly one valid category.

    **Validates: Requirements 4.4, 4.5**
    """
    builder = GroceryListBuilder()
    grocery_list = builder.build(plans)

    for item in grocery_list.items:
        # Verify base unit
        assert item.unit in BASE_UNITS, (
            f"Grocery item '{item.name}' has unit '{item.unit}', "
            f"but expected one of the base units: {BASE_UNITS}"
        )

        # Verify valid category
        assert item.category in VALID_CATEGORIES, (
            f"Grocery item '{item.name}' has category '{item.category}', "
            f"but expected one of: {VALID_CATEGORIES}"
        )

        # Verify positive quantity
        assert item.quantity > 0, (
            f"Grocery item '{item.name}' has non-positive quantity: {item.quantity}"
        )
