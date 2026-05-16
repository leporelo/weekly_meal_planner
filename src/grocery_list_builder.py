"""Grocery list builder that consolidates ingredients from meal plans."""

from datetime import datetime

from src.models import GroceryCategory, GroceryList, IngredientEntry, MealPlan

# Unit family definitions with conversions to base units
# Weight family: base unit is "g"
WEIGHT_UNITS: dict[str, float] = {
    "g": 1.0,
    "kg": 1000.0,
}

# Volume family: base unit is "ml"
VOLUME_UNITS: dict[str, float] = {
    "ml": 1.0,
    "l": 1000.0,
    "tbsp": 15.0,
    "tsp": 5.0,
    "cup": 236.588,
}

# Count family: base unit is "whole"
COUNT_UNITS: dict[str, float] = {
    "whole": 1.0,
}


def _get_unit_family(unit: str) -> tuple[dict[str, float], str] | None:
    """Return the unit family dict and base unit for a given unit, or None if unknown."""
    if unit in WEIGHT_UNITS:
        return WEIGHT_UNITS, "g"
    if unit in VOLUME_UNITS:
        return VOLUME_UNITS, "ml"
    if unit in COUNT_UNITS:
        return COUNT_UNITS, "whole"
    return None


# Category mapping for common vegan ingredients
CATEGORY_MAP: dict[str, GroceryCategory] = {
    # Legumes
    "tofu": "legumes",
    "tempeh": "legumes",
    "lentils": "legumes",
    "red lentils": "legumes",
    "green lentils": "legumes",
    "chickpeas": "legumes",
    "black beans": "legumes",
    "kidney beans": "legumes",
    "edamame": "legumes",
    "pinto beans": "legumes",
    "cannellini beans": "legumes",
    "soybeans": "legumes",
    "split peas": "legumes",
    "mung beans": "legumes",
    "seitan": "legumes",
    # Grains
    "rice": "grains",
    "brown rice": "grains",
    "white rice": "grains",
    "quinoa": "grains",
    "oats": "grains",
    "rolled oats": "grains",
    "pasta": "grains",
    "bread": "grains",
    "couscous": "grains",
    "bulgur": "grains",
    "farro": "grains",
    "barley": "grains",
    "buckwheat": "grains",
    "millet": "grains",
    "flour": "grains",
    "whole wheat flour": "grains",
    "tortilla": "grains",
    "noodles": "grains",
    # Nuts and seeds
    "almonds": "nuts_and_seeds",
    "walnuts": "nuts_and_seeds",
    "cashews": "nuts_and_seeds",
    "peanuts": "nuts_and_seeds",
    "peanut butter": "nuts_and_seeds",
    "almond butter": "nuts_and_seeds",
    "chia seeds": "nuts_and_seeds",
    "flax seeds": "nuts_and_seeds",
    "hemp seeds": "nuts_and_seeds",
    "sunflower seeds": "nuts_and_seeds",
    "pumpkin seeds": "nuts_and_seeds",
    "sesame seeds": "nuts_and_seeds",
    "tahini": "nuts_and_seeds",
    "pine nuts": "nuts_and_seeds",
    "pecans": "nuts_and_seeds",
    "hazelnuts": "nuts_and_seeds",
    # Produce
    "broccoli": "produce",
    "spinach": "produce",
    "kale": "produce",
    "tomato": "produce",
    "tomatoes": "produce",
    "onion": "produce",
    "garlic": "produce",
    "bell pepper": "produce",
    "carrot": "produce",
    "carrots": "produce",
    "potato": "produce",
    "potatoes": "produce",
    "sweet potato": "produce",
    "avocado": "produce",
    "banana": "produce",
    "berries": "produce",
    "blueberries": "produce",
    "strawberries": "produce",
    "lemon": "produce",
    "lime": "produce",
    "cucumber": "produce",
    "zucchini": "produce",
    "mushrooms": "produce",
    "cauliflower": "produce",
    "lettuce": "produce",
    "cabbage": "produce",
    "ginger": "produce",
    "celery": "produce",
    "corn": "produce",
    "peas": "produce",
    "green beans": "produce",
    "asparagus": "produce",
    "eggplant": "produce",
    # Condiments
    "soy sauce": "condiments",
    "olive oil": "condiments",
    "coconut oil": "condiments",
    "vegetable oil": "condiments",
    "sesame oil": "condiments",
    "vinegar": "condiments",
    "apple cider vinegar": "condiments",
    "balsamic vinegar": "condiments",
    "maple syrup": "condiments",
    "agave": "condiments",
    "mustard": "condiments",
    "hot sauce": "condiments",
    "sriracha": "condiments",
    "nutritional yeast": "condiments",
    "miso paste": "condiments",
    "tamari": "condiments",
    "salt": "condiments",
    "pepper": "condiments",
    "cumin": "condiments",
    "turmeric": "condiments",
    "paprika": "condiments",
    "chili powder": "condiments",
    "cinnamon": "condiments",
    "curry powder": "condiments",
    "oregano": "condiments",
    "basil": "condiments",
    "thyme": "condiments",
    # Frozen
    "frozen peas": "frozen",
    "frozen berries": "frozen",
    "frozen spinach": "frozen",
    "frozen corn": "frozen",
    "frozen edamame": "frozen",
    "frozen broccoli": "frozen",
}


class GroceryListBuilder:
    """Consolidates ingredients from meal plans into a single grocery list."""

    CATEGORY_MAP = CATEGORY_MAP

    def convert_units(self, quantity: float, from_unit: str, to_unit: str) -> float | None:
        """Convert quantity between units of the same family.

        Returns the converted quantity, or None if units are incompatible
        (different families).
        """
        from_family = _get_unit_family(from_unit)
        to_family = _get_unit_family(to_unit)

        if from_family is None or to_family is None:
            return None

        from_dict, from_base = from_family
        to_dict, to_base = to_family

        # Units must be in the same family
        if from_base != to_base:
            return None

        # Convert: from_unit -> base -> to_unit
        base_quantity = quantity * from_dict[from_unit]
        return base_quantity / to_dict[to_unit]

    def aggregate_ingredient(self, items: list[IngredientEntry]) -> list[IngredientEntry]:
        """Aggregate ingredients by canonical name and compatible unit families.

        Groups items by canonical name (case-insensitive, stripped).
        For items with compatible units (same family), converts all to base unit
        and sums quantities into a single line item.
        For items with incompatible units, lists as separate line items.
        """
        if not items:
            return []

        # Group by unit family
        # Key: base unit string ("g", "ml", "whole")
        # Value: total quantity in base units
        family_totals: dict[str, float] = {}

        for item in items:
            family_info = _get_unit_family(item.unit)
            if family_info is None:
                # Unknown unit — treat as its own family
                base_unit = item.unit
                base_quantity = item.quantity
            else:
                family_dict, base_unit = family_info
                base_quantity = item.quantity * family_dict[item.unit]

            family_totals[base_unit] = family_totals.get(base_unit, 0.0) + base_quantity

        # Use the canonical name from the first item
        canonical_name = items[0].name.strip().lower()
        category = self._get_category(canonical_name)

        # Build result: one entry per unit family
        result: list[IngredientEntry] = []
        for base_unit, total_qty in sorted(family_totals.items()):
            result.append(
                IngredientEntry(
                    name=canonical_name,
                    quantity=total_qty,
                    unit=base_unit,
                    category=category,
                )
            )

        return result

    def build(self, meal_plans: list[MealPlan], scale_factor: float = 1.0) -> GroceryList:
        """Build a consolidated grocery list from all meal plans.

        Extracts all ingredients from all recipes in all plans, groups by
        canonical name, aggregates compatible units, keeps incompatible units
        separate, assigns categories, and scales quantities by scale_factor.

        Args:
            meal_plans: List of MealPlan objects to extract ingredients from.
            scale_factor: Multiply all quantities by this factor (e.g., sum of
                protein ratios for all people). Defaults to 1.0.
        """
        # Collect all ingredients grouped by canonical name
        ingredient_groups: dict[str, list[IngredientEntry]] = {}

        for plan in meal_plans:
            for recipe in plan.all_recipes():
                for ingredient in recipe.ingredients:
                    canonical = ingredient.name.strip().lower()
                    ingredient_groups.setdefault(canonical, []).append(ingredient)

        # Aggregate each group
        all_items: list[IngredientEntry] = []
        for _name, items in sorted(ingredient_groups.items()):
            aggregated = self.aggregate_ingredient(items)
            all_items.extend(aggregated)

        # Apply scale factor
        if scale_factor != 1.0:
            for item in all_items:
                item.quantity *= scale_factor

        return GroceryList(
            items=all_items,
            generated_at=datetime.now(),
        )

    def _get_category(self, canonical_name: str) -> GroceryCategory:
        """Look up the grocery category for an ingredient name."""
        return self.CATEGORY_MAP.get(canonical_name, "other")
