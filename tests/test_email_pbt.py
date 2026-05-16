"""Property-based tests for EmailDispatcher formatting.

Uses Hypothesis to verify universal properties of email content completeness.
"""

from datetime import datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from src.email_dispatcher import EmailDispatcher, SmtpConfig
from src.models import GroceryCategory, GroceryList, IngredientEntry, MealPlan, Recipe, UserProfile


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

VALID_UNITS = ["g", "ml", "whole", "tbsp", "tsp", "cup", "kg", "l"]


# --- Strategies ---


@st.composite
def ingredient_strategy(draw):
    """Generate a valid IngredientEntry."""
    name = draw(st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("L",)),
    ))
    quantity = draw(st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False))
    unit = draw(st.sampled_from(VALID_UNITS))
    category = draw(st.sampled_from(VALID_CATEGORIES))
    return IngredientEntry(name=name, quantity=quantity, unit=unit, category=category)


@st.composite
def recipe_strategy(draw):
    """Generate a valid Recipe with a unique name and protein_g value."""
    recipe_name = draw(st.text(
        min_size=1,
        max_size=30,
        alphabet=st.characters(whitelist_categories=("L", "Nd", "Zs")),
    ))
    protein_g = draw(st.floats(min_value=5.0, max_value=60.0, allow_nan=False, allow_infinity=False))
    num_ingredients = draw(st.integers(min_value=1, max_value=4))
    ingredients = [draw(ingredient_strategy()) for _ in range(num_ingredients)]

    return Recipe(
        id=draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "Nd")))),
        name=recipe_name,
        protein_source_category=draw(st.sampled_from(PROTEIN_SOURCE_CATEGORIES)),
        servings=draw(st.integers(min_value=1, max_value=4)),
        ingredients=ingredients,
        macros_per_serving={"protein_g": protein_g, "carbs_g": 30.0, "fat_g": 10.0},
        instructions="Prepare and serve.",
    )


@st.composite
def meal_plan_strategy(draw):
    """Generate a valid 7-day MealPlan with recipes in each slot."""
    days = []
    for i in range(7):
        day_data = {"day": DAY_NAMES[i]}
        for slot in ("breakfast", "lunch", "dinner"):
            day_data[slot] = draw(recipe_strategy())
        num_snacks = draw(st.integers(min_value=1, max_value=3))
        day_data["snacks"] = [draw(recipe_strategy()) for _ in range(num_snacks)]
        days.append(day_data)
    return MealPlan(days=days)


@st.composite
def grocery_list_strategy(draw):
    """Generate a valid GroceryList with ingredient entries."""
    num_items = draw(st.integers(min_value=1, max_value=15))
    items = [draw(ingredient_strategy()) for _ in range(num_items)]
    return GroceryList(items=items, generated_at=datetime.now())


# =============================================================================
# Feature: vegan-meal-planner, Property 13: Email content completeness
# Validates: Requirements 5.2, 5.3
# =============================================================================


@settings(max_examples=100)
@given(meal_plan=meal_plan_strategy(), grocery_list=grocery_list_strategy())
def test_email_content_completeness(meal_plan: MealPlan, grocery_list: GroceryList) -> None:
    """For any meal plan and grocery list, the formatted email body SHALL contain
    every recipe name and its protein_g value organized by day, AND SHALL include
    the complete grocery list in a distinct section.

    **Validates: Requirements 5.2, 5.3**
    """
    smtp_config = SmtpConfig(
        smtp_host="smtp.example.com",
        smtp_port=587,
        sender_email="test@example.com",
        sender_password="password",
    )
    dispatcher = EmailDispatcher(smtp_config=smtp_config)

    profiles = [
        UserProfile(name="David", email="david@example.com", weight_kg=90.0, height_cm=180, gender="male"),
        UserProfile(name="Baska", email="baska@example.com", weight_kg=70.0, height_cm=171, gender="female"),
    ]
    body = dispatcher.format_email_body(meal_plan, grocery_list, profiles)

    # 1. Every recipe name from every day must appear in the body
    for day_data in meal_plan.days:
        for slot in ("breakfast", "lunch", "dinner"):
            recipe = day_data.get(slot)
            if isinstance(recipe, Recipe):
                assert recipe.name in body, (
                    f"Recipe name '{recipe.name}' from {day_data['day']} {slot} "
                    f"is missing from the email body"
                )

        snacks = day_data.get("snacks")
        if isinstance(snacks, list):
            for snack in snacks:
                if isinstance(snack, Recipe):
                    assert snack.name in body, (
                        f"Snack recipe name '{snack.name}' from {day_data['day']} "
                        f"is missing from the email body"
                    )

    # 2. Every protein_g value corresponding to recipes must appear in the body
    for day_data in meal_plan.days:
        for slot in ("breakfast", "lunch", "dinner"):
            recipe = day_data.get(slot)
            if isinstance(recipe, Recipe):
                protein = recipe.macros_per_serving.get("protein_g", 0)
                protein_str = str(protein)
                assert protein_str in body, (
                    f"Protein value '{protein_str}' for recipe '{recipe.name}' "
                    f"from {day_data['day']} {slot} is missing from the email body"
                )

        snacks = day_data.get("snacks")
        if isinstance(snacks, list):
            for snack in snacks:
                if isinstance(snack, Recipe):
                    protein = snack.macros_per_serving.get("protein_g", 0)
                    protein_str = str(protein)
                    assert protein_str in body, (
                        f"Protein value '{protein_str}' for snack '{snack.name}' "
                        f"from {day_data['day']} is missing from the email body"
                    )

    # 3. The grocery list section header must be present
    assert "Grocery List" in body, (
        "The email body is missing the 'Grocery List' section header"
    )

    # 4. Every ingredient name from the grocery list must appear in the body
    for item in grocery_list.items:
        assert item.name in body, (
            f"Grocery ingredient '{item.name}' is missing from the email body"
        )
