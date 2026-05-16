"""Vegan compliance checking for meal plan recipes."""

from src.models import ComplianceResult, Recipe


class VeganComplianceChecker:
    """Checks recipes for non-vegan ingredients using keyword matching."""

    # Known vegan ingredients that contain non-vegan substrings
    VEGAN_WHITELIST: set[str] = {
        "soy milk", "oat milk", "almond milk", "coconut milk", "rice milk",
        "cashew milk", "hemp milk", "flax milk", "pea milk",
        "plant milk", "unsweetened plant milk", "plant-based milk",
        "soy cream", "coconut cream", "cashew cream", "oat cream",
        "plant-based sour cream", "vegan sour cream", "cashew sour cream",
        "vegan butter", "plant butter", "coconut butter",
        "peanut butter", "almond butter", "cashew butter", "sunflower butter",
        "seed butter", "nut butter", "cocoa butter", "shea butter",
        "vegan cheese", "cashew cheese", "nutritional yeast cheese",
        "coconut yogurt", "soy yogurt", "almond yogurt", "oat yogurt",
        "vegan egg", "flax egg", "chia egg",
        "coconut honey", "vegan honey",
        "eggplant", "egg plant",
        "kala namak", "black salt",
        "butternut squash", "butternut", "butterbeans", "butter beans",
        "butter lettuce",
        "cream of tartar",
        "honeydew", "honeydew melon",
        "crab apple", "crabapple",
    }

    # Vegan brand/product patterns — if ingredient contains these prefixes, it's vegan
    VEGAN_BRAND_PREFIXES: list[str] = [
        "planted",     # Planted. brand (vegan chicken, etc.)
        "beyond",      # Beyond Meat
        "impossible",  # Impossible Foods
        "quorn",       # Quorn (vegan range)
        "gardein",     # Gardein
        "tofurky",     # Tofurky
        "field roast", # Field Roast
        "daring",      # Daring Foods
        "simulate",    # Simulate (vegan chicken)
        "green mountain", # Green Mountain
        "vegan chicken", "vegan beef", "vegan pork", "vegan fish",
        "vegan bacon", "vegan sausage", "vegan ham", "vegan turkey",
        "plant-based chicken", "plant-based beef", "plant-based pork",
        "plant based chicken", "plant based beef", "plant based pork",
        "mock chicken", "mock duck", "mock meat",
        "tvp",  # textured vegetable protein
    ]

    NON_VEGAN_CATEGORIES: dict[str, list[str]] = {
        "meat": [
            "beef", "pork", "lamb", "veal", "venison", "bacon", "ham",
            "sausage", "salami", "prosciutto", "steak", "ribs", "brisket",
        ],
        "poultry": [
            "chicken", "turkey", "duck", "goose", "quail", "pheasant",
        ],
        "fish": [
            "salmon", "tuna", "cod", "anchovy", "sardine", "trout",
            "mackerel", "herring", "halibut", "swordfish", "bass",
        ],
        "shellfish": [
            "shrimp", "crab", "lobster", "mussel", "oyster", "clam",
            "scallop", "prawn", "crawfish", "squid",
        ],
        "dairy": [
            "milk", "cheese", "yogurt", "ghee",
            "casein", "whey", "lactose", "curd",
            "dairy butter", "cow butter", "salted butter", "unsalted butter",
            "heavy cream", "whipping cream", "sour cream", "ice cream",
            "half and half", "half-and-half",
            "cottage cheese", "cream cheese",
        ],
        "eggs": [
            "egg",
        ],
        "honey": [
            "honey",
        ],
        "gelatin": [
            "gelatin",
        ],
        "animal-derived additives": [
            "casein", "whey", "carmine", "lanolin", "shellac",
            "isinglass", "tallow", "lard",
        ],
    }

    def check_recipe(self, recipe: "Recipe | dict") -> ComplianceResult:
        """Check all ingredients in a recipe for vegan compliance.

        Args:
            recipe: A Recipe dataclass or a dict with an "ingredients" key
                    containing a list of dicts with "name" fields.

        Returns:
            ComplianceResult with is_compliant=True if all ingredients pass,
            or is_compliant=False with rejected_ingredient and non_vegan_category
            on the first non-vegan ingredient found.
        """
        if isinstance(recipe, dict):
            ingredients = recipe.get("ingredients", [])
        else:
            ingredients = recipe.ingredients

        for ingredient in ingredients:
            if isinstance(ingredient, dict):
                name = ingredient.get("name", "")
            else:
                name = ingredient.name

            category = self._find_non_vegan_category(name)
            if category is not None:
                return ComplianceResult(
                    is_compliant=False,
                    rejected_ingredient=name,
                    non_vegan_category=category,
                )

        return ComplianceResult(is_compliant=True)

    def is_ingredient_vegan(self, ingredient_name: str) -> bool:
        """Check if an ingredient name is vegan.

        Uses case-insensitive exact match AND substring match against
        all non-vegan keywords. For example, "milk chocolate" would be
        flagged because it contains "milk" as a substring.

        Args:
            ingredient_name: The ingredient name to check.

        Returns:
            True if the ingredient is vegan (no matches), False otherwise.
        """
        return self._find_non_vegan_category(ingredient_name) is None

    def _find_non_vegan_category(self, ingredient_name: str) -> str | None:
        """Find the non-vegan category for an ingredient, if any.

        Args:
            ingredient_name: The ingredient name to check.

        Returns:
            The non-vegan category name if matched, or None if vegan.
        """
        name_lower = ingredient_name.lower().strip()

        # Check whitelist first — known vegan items that contain non-vegan substrings
        if name_lower in self.VEGAN_WHITELIST:
            return None

        # Also check if ingredient contains a whitelisted term as substring
        for safe_term in self.VEGAN_WHITELIST:
            if safe_term in name_lower:
                return None

        # Check vegan brand prefixes — products from vegan brands are safe
        for prefix in self.VEGAN_BRAND_PREFIXES:
            if prefix in name_lower:
                return None

        for category, keywords in self.NON_VEGAN_CATEGORIES.items():
            for keyword in keywords:
                # Exact match or substring match (case-insensitive)
                if keyword in name_lower:
                    return category

        return None
