"""Property-based tests for VeganComplianceChecker.

Uses Hypothesis to verify vegan compliance with substring matching across
all non-vegan categories and keywords.

**Validates: Requirements 6.2, 6.3, 6.4**
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.vegan_compliance import VeganComplianceChecker


# --- Shared Setup ---

checker = VeganComplianceChecker()

# All non-vegan categories and their keywords
NON_VEGAN_CATEGORIES = checker.NON_VEGAN_CATEGORIES

# Flat list of all non-vegan keywords across all categories
ALL_NON_VEGAN_KEYWORDS = [
    keyword
    for keywords in NON_VEGAN_CATEGORIES.values()
    for keyword in keywords
]

# Safe vegan ingredient names that don't contain any non-vegan keywords
SAFE_VEGAN_INGREDIENTS = [
    "tofu", "tempeh", "lentils", "chickpeas", "quinoa", "rice",
    "broccoli", "spinach", "kale", "avocado", "sweet potato",
    "nutritional yeast", "soy sauce", "tahini", "flaxseed",
    "chia seeds", "hemp seeds", "black beans", "pinto beans",
    "coconut oil", "olive oil", "almond", "walnut", "cashew",
    "oats", "seitan", "spirulina", "edamame", "miso paste",
]


# --- Strategies ---


@st.composite
def vegan_ingredient_name(draw):
    """Generate a safe vegan ingredient name that contains no non-vegan keywords."""
    return draw(st.sampled_from(SAFE_VEGAN_INGREDIENTS))


@st.composite
def non_vegan_category_and_keyword(draw):
    """Generate a (category, keyword) pair from the non-vegan categories."""
    category = draw(st.sampled_from(list(NON_VEGAN_CATEGORIES.keys())))
    keyword = draw(st.sampled_from(NON_VEGAN_CATEGORIES[category]))
    return (category, keyword)


@st.composite
def recipe_with_all_vegan_ingredients(draw):
    """Generate a recipe dict with only vegan ingredients."""
    num_ingredients = draw(st.integers(min_value=1, max_value=8))
    ingredients = [
        {"name": draw(vegan_ingredient_name()), "quantity": 100, "unit": "g"}
        for _ in range(num_ingredients)
    ]
    return {"ingredients": ingredients}


@st.composite
def recipe_with_exact_non_vegan_keyword(draw):
    """Generate a recipe containing an ingredient that exactly matches a non-vegan keyword."""
    category, keyword = draw(non_vegan_category_and_keyword())
    # Create some vegan ingredients + the non-vegan one
    num_vegan = draw(st.integers(min_value=0, max_value=5))
    ingredients = [
        {"name": draw(vegan_ingredient_name()), "quantity": 100, "unit": "g"}
        for _ in range(num_vegan)
    ]
    # Insert the non-vegan ingredient at a random position
    position = draw(st.integers(min_value=0, max_value=len(ingredients)))
    ingredients.insert(position, {"name": keyword, "quantity": 50, "unit": "g"})
    return {"recipe": {"ingredients": ingredients}, "category": category, "keyword": keyword}


@st.composite
def recipe_with_substring_non_vegan_keyword(draw):
    """Generate a recipe where a non-vegan keyword appears as a SUBSTRING of an ingredient name."""
    category, keyword = draw(non_vegan_category_and_keyword())
    # Create a compound ingredient name with the keyword as a substring
    prefix = draw(st.sampled_from(["", "dark ", "organic ", "spicy ", "roasted ", "smoked "]))
    suffix = draw(st.sampled_from([
        " chocolate", " noodles", " sauce", " powder", " flavored",
        " based", " substitute", " broth", " extract", " blend",
    ]))
    # Ensure the compound name actually contains the keyword as substring
    compound_name = f"{prefix}{keyword}{suffix}".strip()

    # Create some vegan ingredients + the non-vegan substring ingredient
    num_vegan = draw(st.integers(min_value=0, max_value=5))
    ingredients = [
        {"name": draw(vegan_ingredient_name()), "quantity": 100, "unit": "g"}
        for _ in range(num_vegan)
    ]
    position = draw(st.integers(min_value=0, max_value=len(ingredients)))
    ingredients.insert(position, {"name": compound_name, "quantity": 50, "unit": "g"})
    return {
        "recipe": {"ingredients": ingredients},
        "category": category,
        "keyword": keyword,
        "ingredient_name": compound_name,
    }


@st.composite
def randomized_casing(draw, text: str):
    """Apply random casing to each character in a string."""
    result = []
    for char in text:
        if draw(st.booleans()):
            result.append(char.upper())
        else:
            result.append(char.lower())
    return "".join(result)


@st.composite
def recipe_with_random_casing_non_vegan(draw):
    """Generate a recipe with a non-vegan keyword in random casing."""
    category, keyword = draw(non_vegan_category_and_keyword())
    # Apply random casing to the keyword
    cased_keyword = draw(randomized_casing(keyword))

    num_vegan = draw(st.integers(min_value=0, max_value=5))
    ingredients = [
        {"name": draw(vegan_ingredient_name()), "quantity": 100, "unit": "g"}
        for _ in range(num_vegan)
    ]
    position = draw(st.integers(min_value=0, max_value=len(ingredients)))
    ingredients.insert(position, {"name": cased_keyword, "quantity": 50, "unit": "g"})
    return {
        "recipe": {"ingredients": ingredients},
        "category": category,
        "keyword": keyword,
        "ingredient_name": cased_keyword,
    }


# --- Property Tests ---


# Feature: vegan-meal-planner, Property 6: Vegan compliance with substring matching
# Validates: Requirements 6.2, 6.3, 6.4
@settings(max_examples=100)
@given(recipe=recipe_with_all_vegan_ingredients())
def test_all_vegan_ingredients_recipe_is_compliant(recipe: dict) -> None:
    """For any recipe where ALL ingredients are known-safe vegan ingredients,
    the compliance checker SHALL accept the recipe as compliant."""
    result = checker.check_recipe(recipe)
    assert result.is_compliant is True, (
        f"Recipe with all vegan ingredients should be compliant, "
        f"but was rejected: ingredient='{result.rejected_ingredient}', "
        f"category='{result.non_vegan_category}'"
    )


# Feature: vegan-meal-planner, Property 6: Vegan compliance with substring matching
# Validates: Requirements 6.2, 6.3, 6.4
@settings(max_examples=100)
@given(data=recipe_with_exact_non_vegan_keyword())
def test_exact_non_vegan_keyword_rejects_recipe(data: dict) -> None:
    """For any recipe containing an ingredient that exactly matches a non-vegan
    category keyword, the recipe SHALL be rejected and the rejection record SHALL
    include the offending ingredient name and its matching non-vegan category."""
    recipe = data["recipe"]
    keyword = data["keyword"]
    category = data["category"]

    result = checker.check_recipe(recipe)
    assert result.is_compliant is False, (
        f"Recipe containing non-vegan keyword '{keyword}' (category: {category}) "
        f"should be rejected"
    )
    assert result.rejected_ingredient is not None, (
        "Rejected recipe should include the offending ingredient name"
    )
    assert result.non_vegan_category is not None, (
        "Rejected recipe should include the matching non-vegan category"
    )
    # The rejected ingredient should match the keyword (case-insensitive)
    assert result.rejected_ingredient.lower() == keyword.lower(), (
        f"Rejected ingredient '{result.rejected_ingredient}' should match "
        f"keyword '{keyword}'"
    )


# Feature: vegan-meal-planner, Property 6: Vegan compliance with substring matching
# Validates: Requirements 6.2, 6.3, 6.4
@settings(max_examples=100)
@given(data=recipe_with_substring_non_vegan_keyword())
def test_substring_non_vegan_keyword_rejects_recipe(data: dict) -> None:
    """For any recipe where a non-vegan keyword appears as a SUBSTRING of an
    ingredient name (e.g., 'milk chocolate', 'egg noodles'), the recipe SHALL
    be rejected and the rejection record SHALL include the offending ingredient
    name and its matching non-vegan category."""
    recipe = data["recipe"]
    keyword = data["keyword"]
    category = data["category"]
    ingredient_name = data["ingredient_name"]

    result = checker.check_recipe(recipe)
    assert result.is_compliant is False, (
        f"Recipe containing ingredient '{ingredient_name}' with non-vegan "
        f"substring '{keyword}' (category: {category}) should be rejected"
    )
    assert result.rejected_ingredient is not None, (
        "Rejected recipe should include the offending ingredient name"
    )
    assert result.non_vegan_category is not None, (
        "Rejected recipe should include the matching non-vegan category"
    )
    # The rejected ingredient should be the one containing the non-vegan substring
    assert keyword.lower() in result.rejected_ingredient.lower(), (
        f"Rejected ingredient '{result.rejected_ingredient}' should contain "
        f"non-vegan keyword '{keyword}'"
    )


# Feature: vegan-meal-planner, Property 6: Vegan compliance with substring matching
# Validates: Requirements 6.2, 6.3, 6.4
@settings(max_examples=100)
@given(data=recipe_with_random_casing_non_vegan())
def test_case_insensitive_non_vegan_detection(data: dict) -> None:
    """For any recipe containing a non-vegan keyword with randomized casing
    (e.g., 'MILK', 'Egg', 'cHiCkEn'), the recipe SHALL be rejected,
    proving case-insensitive matching."""
    recipe = data["recipe"]
    keyword = data["keyword"]
    category = data["category"]
    ingredient_name = data["ingredient_name"]

    result = checker.check_recipe(recipe)
    assert result.is_compliant is False, (
        f"Recipe containing '{ingredient_name}' (keyword '{keyword}' in random case, "
        f"category: {category}) should be rejected regardless of casing"
    )
    assert result.rejected_ingredient is not None, (
        "Rejected recipe should include the offending ingredient name"
    )
    assert result.non_vegan_category is not None, (
        "Rejected recipe should include the matching non-vegan category"
    )
    # Category should be one of the known non-vegan categories
    assert result.non_vegan_category in NON_VEGAN_CATEGORIES, (
        f"Non-vegan category '{result.non_vegan_category}' should be a known category"
    )
