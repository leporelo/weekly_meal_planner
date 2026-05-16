"""Property-based tests for VarietyEnforcer.

Uses Hypothesis to verify universal properties of within-week recipe
repetition limits, protein source diversity, and cross-week overlap.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from src.models import IngredientEntry, MealPlan, Recipe
from src.variety_enforcer import VarietyEnforcer


# --- Constants ---

PROTEIN_SOURCE_CATEGORIES = [
    "legumes",
    "tofu_and_tempeh",
    "seitan",
    "nuts_and_seeds",
    "protein_rich_grains",
]

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# --- Strategies ---


@st.composite
def recipe_strategy(draw, recipe_id=None, category=None):
    """Generate a valid Recipe object.

    If recipe_id is provided, use that ID; otherwise generate one.
    If category is provided, use that category; otherwise draw one.
    """
    rid = recipe_id if recipe_id is not None else draw(
        st.text(min_size=1, max_size=15, alphabet=st.characters(whitelist_categories=("L", "Nd")))
    )
    cat = category if category is not None else draw(st.sampled_from(PROTEIN_SOURCE_CATEGORIES))

    return Recipe(
        id=rid,
        name=draw(st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "Nd", "Zs")))),
        protein_source_category=cat,
        servings=draw(st.integers(min_value=1, max_value=4)),
        ingredients=[
            IngredientEntry(
                name="ingredient",
                quantity=100.0,
                unit="g",
                category="other",
            )
        ],
        macros_per_serving={"protein_g": 25.0, "carbs_g": 30.0, "fat_g": 10.0},
        instructions="Prepare and serve.",
    )


@st.composite
def meal_plan_with_controlled_repetition(draw, max_repeats=2):
    """Generate a MealPlan where no recipe ID appears more than max_repeats times.

    Creates unique recipe IDs and distributes them across the plan so that
    each ID appears at most max_repeats times.
    """
    days = []
    id_usage = {}  # track how many times each ID is used

    for i in range(7):
        day_recipes = {}
        for slot in ("breakfast", "lunch", "dinner"):
            recipe_id = f"recipe_{i}_{slot}"
            id_usage[recipe_id] = id_usage.get(recipe_id, 0) + 1
            day_recipes[slot] = draw(recipe_strategy(recipe_id=recipe_id))

        num_snacks = draw(st.integers(min_value=1, max_value=3))
        snacks = []
        for s in range(num_snacks):
            snack_id = f"snack_{i}_{s}"
            id_usage[snack_id] = id_usage.get(snack_id, 0) + 1
            snacks.append(draw(recipe_strategy(recipe_id=snack_id)))

        day_recipes["snacks"] = snacks
        day_recipes["day"] = DAY_NAMES[i]
        days.append(day_recipes)

    return MealPlan(days=days)


@st.composite
def meal_plan_with_excessive_repetition(draw):
    """Generate a MealPlan where at least one recipe ID appears more than 2 times.

    Uses a single repeated recipe ID for at least 3 meal slots.
    """
    repeated_id = "repeated_recipe"
    days = []

    for i in range(7):
        day_recipes = {}
        for slot in ("breakfast", "lunch", "dinner"):
            # For the first day, use the repeated ID for all 3 main meals (3 appearances)
            if i == 0:
                day_recipes[slot] = draw(recipe_strategy(recipe_id=repeated_id))
            else:
                day_recipes[slot] = draw(recipe_strategy(recipe_id=f"unique_{i}_{slot}"))

        num_snacks = draw(st.integers(min_value=1, max_value=2))
        snacks = []
        for s in range(num_snacks):
            snacks.append(draw(recipe_strategy(recipe_id=f"snack_{i}_{s}")))
        day_recipes["snacks"] = snacks
        day_recipes["day"] = DAY_NAMES[i]
        days.append(day_recipes)

    return MealPlan(days=days)


@st.composite
def meal_plan_with_all_categories(draw):
    """Generate a MealPlan that uses all 5 protein source categories.

    Ensures at least one recipe from each category is present.
    """
    days = []

    # Assign categories across the first 5 main meals to guarantee all 5
    category_assignments = list(PROTEIN_SOURCE_CATEGORIES)

    for i in range(7):
        day_recipes = {}
        for j, slot in enumerate(("breakfast", "lunch", "dinner")):
            slot_index = i * 3 + j
            if slot_index < 5:
                cat = category_assignments[slot_index]
            else:
                cat = draw(st.sampled_from(PROTEIN_SOURCE_CATEGORIES))
            day_recipes[slot] = draw(recipe_strategy(
                recipe_id=f"cat_{i}_{slot}",
                category=cat,
            ))

        num_snacks = draw(st.integers(min_value=1, max_value=2))
        snacks = []
        for s in range(num_snacks):
            snacks.append(draw(recipe_strategy(
                recipe_id=f"snack_{i}_{s}",
                category=draw(st.sampled_from(PROTEIN_SOURCE_CATEGORIES)),
            )))
        day_recipes["snacks"] = snacks
        day_recipes["day"] = DAY_NAMES[i]
        days.append(day_recipes)

    return MealPlan(days=days)


@st.composite
def meal_plan_with_limited_categories(draw, num_categories=None):
    """Generate a MealPlan that uses fewer than 5 protein source categories.

    Selects a subset of categories (1-4) and uses only those.
    """
    if num_categories is None:
        num_categories = draw(st.integers(min_value=1, max_value=4))
    chosen_categories = draw(
        st.lists(
            st.sampled_from(PROTEIN_SOURCE_CATEGORIES),
            min_size=num_categories,
            max_size=num_categories,
            unique=True,
        )
    )

    days = []
    for i in range(7):
        day_recipes = {}
        for slot in ("breakfast", "lunch", "dinner"):
            cat = draw(st.sampled_from(chosen_categories))
            day_recipes[slot] = draw(recipe_strategy(
                recipe_id=f"ltd_{i}_{slot}",
                category=cat,
            ))

        num_snacks = draw(st.integers(min_value=1, max_value=2))
        snacks = []
        for s in range(num_snacks):
            cat = draw(st.sampled_from(chosen_categories))
            snacks.append(draw(recipe_strategy(
                recipe_id=f"snack_{i}_{s}",
                category=cat,
            )))
        day_recipes["snacks"] = snacks
        day_recipes["day"] = DAY_NAMES[i]
        days.append(day_recipes)

    return MealPlan(days=days)


@st.composite
def two_plans_with_low_overlap(draw):
    """Generate two MealPlans where overlap is <= 30%.

    Uses completely unique recipe IDs between the two plans.
    """
    # Plan 1 - all unique IDs with prefix "old_"
    days1 = []
    for i in range(7):
        day_recipes = {}
        for slot in ("breakfast", "lunch", "dinner"):
            day_recipes[slot] = draw(recipe_strategy(recipe_id=f"old_{i}_{slot}"))
        num_snacks = draw(st.integers(min_value=1, max_value=2))
        snacks = []
        for s in range(num_snacks):
            snacks.append(draw(recipe_strategy(recipe_id=f"old_snack_{i}_{s}")))
        day_recipes["snacks"] = snacks
        day_recipes["day"] = DAY_NAMES[i]
        days1.append(day_recipes)

    # Plan 2 - all unique IDs with prefix "new_" (0% overlap)
    days2 = []
    for i in range(7):
        day_recipes = {}
        for slot in ("breakfast", "lunch", "dinner"):
            day_recipes[slot] = draw(recipe_strategy(recipe_id=f"new_{i}_{slot}"))
        num_snacks = draw(st.integers(min_value=1, max_value=2))
        snacks = []
        for s in range(num_snacks):
            snacks.append(draw(recipe_strategy(recipe_id=f"new_snack_{i}_{s}")))
        day_recipes["snacks"] = snacks
        day_recipes["day"] = DAY_NAMES[i]
        days2.append(day_recipes)

    return MealPlan(days=days1), MealPlan(days=days2)


@st.composite
def two_plans_with_high_overlap(draw):
    """Generate two MealPlans where overlap exceeds 30%.

    Uses mostly identical recipe IDs between the two plans (>30% shared).
    """
    # Both plans use mostly the same IDs — use "shared_" prefix
    days1 = []
    days2 = []
    for i in range(7):
        day_recipes1 = {}
        day_recipes2 = {}
        for slot in ("breakfast", "lunch", "dinner"):
            shared_id = f"shared_{i}_{slot}"
            day_recipes1[slot] = draw(recipe_strategy(recipe_id=shared_id))
            day_recipes2[slot] = draw(recipe_strategy(recipe_id=shared_id))

        num_snacks = draw(st.integers(min_value=1, max_value=2))
        snacks1 = []
        snacks2 = []
        for s in range(num_snacks):
            shared_snack_id = f"shared_snack_{i}_{s}"
            snacks1.append(draw(recipe_strategy(recipe_id=shared_snack_id)))
            snacks2.append(draw(recipe_strategy(recipe_id=shared_snack_id)))

        day_recipes1["snacks"] = snacks1
        day_recipes1["day"] = DAY_NAMES[i]
        days1.append(day_recipes1)

        day_recipes2["snacks"] = snacks2
        day_recipes2["day"] = DAY_NAMES[i]
        days2.append(day_recipes2)

    return MealPlan(days=days1), MealPlan(days=days2)


# =============================================================================
# Feature: vegan-meal-planner, Property 7: Within-week recipe repetition limit
# Validates: Requirements 7.1, 2.8
# =============================================================================


@settings(max_examples=100)
@given(plan=meal_plan_with_controlled_repetition())
def test_within_week_limits_pass_when_recipes_appear_at_most_twice(plan: MealPlan) -> None:
    """For any valid 7-day meal plan where no recipe ID appears more than 2 times,
    check_within_week_limits SHALL return True."""
    enforcer = VarietyEnforcer()
    result = enforcer.check_within_week_limits(plan)
    assert result is True, (
        f"Plan with unique recipe IDs (max 2 repeats) should pass within-week limits, "
        f"but got False"
    )


@settings(max_examples=100)
@given(plan=meal_plan_with_excessive_repetition())
def test_within_week_limits_fail_when_recipe_exceeds_twice(plan: MealPlan) -> None:
    """For any valid 7-day meal plan where a recipe ID appears more than 2 times,
    check_within_week_limits SHALL return False."""
    enforcer = VarietyEnforcer()
    result = enforcer.check_within_week_limits(plan)
    assert result is False, (
        f"Plan with 'repeated_recipe' appearing 3 times should fail within-week limits, "
        f"but got True"
    )


# =============================================================================
# Feature: vegan-meal-planner, Property 8: Protein source diversity
# Validates: Requirements 7.2
# =============================================================================


@settings(max_examples=100)
@given(plan=meal_plan_with_all_categories())
def test_protein_source_diversity_pass_with_all_categories(plan: MealPlan) -> None:
    """For any valid 7-day meal plan with at least 5 distinct protein source categories
    represented, check_protein_source_diversity SHALL return True."""
    enforcer = VarietyEnforcer()
    result = enforcer.check_protein_source_diversity(plan)
    assert result is True, (
        f"Plan with all 5 protein source categories should pass diversity check, "
        f"but got False. Categories present: "
        f"{set(r.protein_source_category for r in plan.all_recipes())}"
    )


@settings(max_examples=100)
@given(plan=meal_plan_with_limited_categories())
def test_protein_source_diversity_fail_with_fewer_than_5_categories(plan: MealPlan) -> None:
    """For any valid 7-day meal plan with fewer than 5 distinct protein source categories,
    check_protein_source_diversity SHALL return False."""
    enforcer = VarietyEnforcer()
    result = enforcer.check_protein_source_diversity(plan)
    categories = set(r.protein_source_category for r in plan.all_recipes())
    assert result is False, (
        f"Plan with only {len(categories)} categories ({categories}) should fail "
        f"diversity check, but got True"
    )


# =============================================================================
# Feature: vegan-meal-planner, Property 9: Cross-week overlap limit
# Validates: Requirements 7.3
# =============================================================================


@settings(max_examples=100)
@given(plans=two_plans_with_low_overlap())
def test_cross_week_overlap_within_limit(plans: tuple[MealPlan, MealPlan]) -> None:
    """For any new meal plan and previous plan with <= 30% overlap,
    check_cross_week_overlap SHALL return a value <= 0.30."""
    previous_plan, new_plan = plans
    enforcer = VarietyEnforcer()
    overlap = enforcer.check_cross_week_overlap(new_plan, previous_plan)
    assert overlap <= 0.30, (
        f"Plans with no shared recipe IDs should have overlap <= 0.30, "
        f"but got {overlap:.4f}"
    )


@settings(max_examples=100)
@given(plans=two_plans_with_high_overlap())
def test_cross_week_overlap_exceeds_limit(plans: tuple[MealPlan, MealPlan]) -> None:
    """For any new meal plan and previous plan that share >30% of recipes,
    check_cross_week_overlap SHALL return a value > 0.30."""
    previous_plan, new_plan = plans
    enforcer = VarietyEnforcer()
    overlap = enforcer.check_cross_week_overlap(new_plan, previous_plan)
    assert overlap > 0.30, (
        f"Plans with 100% shared recipe IDs should have overlap > 0.30, "
        f"but got {overlap:.4f}"
    )


@settings(max_examples=100)
@given(plan=meal_plan_with_controlled_repetition())
def test_cross_week_overlap_none_previous_returns_zero(plan: MealPlan) -> None:
    """When no previous plan exists (None), check_cross_week_overlap SHALL return 0.0."""
    enforcer = VarietyEnforcer()
    overlap = enforcer.check_cross_week_overlap(plan, None)
    assert overlap == 0.0, (
        f"Cross-week overlap with no previous plan should be 0.0, but got {overlap}"
    )
