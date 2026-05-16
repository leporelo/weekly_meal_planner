"""Variety enforcement for weekly vegan meal plans.

Ensures within-week recipe repetition limits, protein source diversity,
and cross-week overlap constraints are satisfied.
"""

from collections import Counter

from src.models import MealPlan


class VarietyEnforcer:
    """Enforces within-week and cross-week variety constraints."""

    def check_within_week_limits(self, meal_plan: MealPlan) -> bool:
        """Verify no recipe ID appears more than 2 times in a meal plan.

        Args:
            meal_plan: A 7-day meal plan to check.

        Returns:
            True if all recipe IDs appear at most 2 times, False otherwise.
        """
        recipes = meal_plan.all_recipes()
        id_counts = Counter(recipe.id for recipe in recipes)
        return all(count <= 2 for count in id_counts.values())

    def check_protein_source_diversity(self, meal_plan: MealPlan) -> bool:
        """Verify at least 5 distinct protein source categories are represented.

        Each of the 5 categories (legumes, tofu_and_tempeh, seitan,
        nuts_and_seeds, protein_rich_grains) must have at least 1 recipe.

        Args:
            meal_plan: A 7-day meal plan to check.

        Returns:
            True if at least 5 distinct categories are present with at least
            1 recipe each, False otherwise.
        """
        recipes = meal_plan.all_recipes()
        categories = set(recipe.protein_source_category for recipe in recipes)
        return len(categories) >= 5

    def check_cross_week_overlap(
        self, new_plan: MealPlan, previous_plan: MealPlan | None
    ) -> float:
        """Calculate the overlap percentage between new and previous plans.

        If no previous plan exists, returns 0.0 (no overlap).
        Otherwise calculates: number of recipe IDs in new_plan that also
        appear in previous_plan / total recipes in new_plan.

        Args:
            new_plan: The newly generated meal plan.
            previous_plan: The immediately preceding meal plan, or None.

        Returns:
            Overlap percentage as a float between 0.0 and 1.0.
        """
        if previous_plan is None:
            return 0.0

        new_recipes = new_plan.all_recipes()
        if not new_recipes:
            return 0.0

        previous_ids = set(recipe.id for recipe in previous_plan.all_recipes())
        overlap_count = sum(
            1 for recipe in new_recipes if recipe.id in previous_ids
        )

        return overlap_count / len(new_recipes)
