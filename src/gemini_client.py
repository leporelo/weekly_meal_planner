"""Gemini API client for generating vegan meal plans."""

import json
import logging
import os

import google.generativeai as genai
import jsonschema

from src.models import MEAL_PLAN_JSON_SCHEMA, SINGLE_DAY_JSON_SCHEMA, UserProfile

logger = logging.getLogger(__name__)

DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class GeminiClient:
    """Handles communication with Google's Gemini API for meal plan generation.

    Constructs structured prompts based on user profiles and constraints,
    validates responses against the expected JSON schema, and implements
    retry logic for robustness.
    """

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.0-flash", max_retries: int = 2) -> None:
        """Configure the Gemini API client.

        Args:
            api_key: The Gemini API key. If None, reads from GEMINI_API_KEY env var.
            model: The Gemini model to use. Defaults to "gemini-2.0-flash".
            max_retries: Maximum number of retries on failure.

        Raises:
            ValueError: If no API key is provided or found in environment.
        """
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Gemini API key must be provided or set in GEMINI_API_KEY environment variable"
            )
        self.model_name = model
        self.max_retries = max_retries
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)

    def generate_meal_plan(
        self,
        profile: UserProfile,
        excluded_recipes: list[str],
        variety_constraints: dict | None = None,
    ) -> dict:
        """Generate a 7-day vegan meal plan by calling generate_single_day for each day.

        Builds the plan one day at a time, passing already-used recipes to each
        subsequent day's prompt for variety enforcement.

        Args:
            profile: The user profile with protein target and preferences.
            excluded_recipes: List of recipe names to exclude from the plan.
            variety_constraints: Optional dict with variety requirements such as
                min_protein_categories (default 5) and max_recipe_repetitions (default 2).

        Returns:
            A dict matching the MEAL_PLAN_JSON_SCHEMA structure.

        Raises:
            RuntimeError: If any day fails after all retries.
        """
        if variety_constraints is None:
            variety_constraints = {
                "min_protein_categories": 5,
                "max_recipe_repetitions": 2,
            }

        days: list[dict] = []
        already_used_recipes: list[str] = []

        for day_name in DAYS_OF_WEEK:
            day_data = self.generate_single_day(
                profile=profile,
                day_name=day_name,
                excluded_recipes=excluded_recipes,
                already_used_recipes=already_used_recipes,
                variety_constraints=variety_constraints,
            )
            days.append(day_data)

            # Collect recipe names from this day for variety in subsequent days
            meals = day_data.get("meals", {})
            for meal_slot in ("breakfast", "lunch", "dinner"):
                recipe = meals.get(meal_slot)
                if recipe and "name" in recipe:
                    already_used_recipes.append(recipe["name"])
            for snack in meals.get("snacks", []):
                if snack and "name" in snack:
                    already_used_recipes.append(snack["name"])

        return {"days": days}

    def generate_single_day(
        self,
        profile: UserProfile,
        day_name: str,
        excluded_recipes: list[str],
        already_used_recipes: list[str],
        variety_constraints: dict | None = None,
    ) -> dict:
        """Generate a single day's meals via the Gemini API.

        Asks Gemini for one day's meals (breakfast, lunch, dinner, 1-3 snacks)
        with full recipe details including ingredients, instructions, prep/cook time.

        Args:
            profile: The user profile with protein target and preferences.
            day_name: The day of the week (e.g., "Monday").
            excluded_recipes: List of recipe names to exclude (from history).
            already_used_recipes: Recipes already used in previous days this week.
            variety_constraints: Optional variety requirements.

        Returns:
            A dict matching the SINGLE_DAY_JSON_SCHEMA structure.

        Raises:
            RuntimeError: If all retries are exhausted without a valid response.
        """
        if variety_constraints is None:
            variety_constraints = {
                "min_protein_categories": 5,
                "max_recipe_repetitions": 2,
            }

        prompt = self._build_single_day_prompt(
            profile, day_name, excluded_recipes, already_used_recipes, variety_constraints
        )
        max_retries = self.max_retries
        last_error: Exception | None = None

        for attempt in range(1 + max_retries):
            try:
                response = self.model.generate_content(prompt)
                day_data = self._parse_response(response)
                # Normalize non-standard units before validation
                self._normalize_units(day_data)
                jsonschema.validate(instance=day_data, schema=SINGLE_DAY_JSON_SCHEMA)
                return day_data
            except jsonschema.ValidationError as e:
                last_error = e
                logger.warning(
                    "Schema validation failed for %s on attempt %d/%d: %s",
                    day_name,
                    attempt + 1,
                    1 + max_retries,
                    str(e.message),
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    "API error for %s on attempt %d/%d: %s",
                    day_name,
                    attempt + 1,
                    1 + max_retries,
                    str(e),
                )

        raise RuntimeError(
            f"Failed to generate valid meal plan for {day_name} after {1 + max_retries} attempts. "
            f"Last error: {last_error}"
        )

    def _build_single_day_prompt(
        self,
        profile: UserProfile,
        day_name: str,
        excluded_recipes: list[str],
        already_used_recipes: list[str],
        variety_constraints: dict,
    ) -> str:
        """Construct the prompt for generating a single day's meals.

        Args:
            profile: The user profile with nutritional targets.
            day_name: The day to generate meals for.
            excluded_recipes: Recipe names to exclude (from history).
            already_used_recipes: Recipes already used earlier this week.
            variety_constraints: Variety requirements for the plan.

        Returns:
            A formatted prompt string.
        """
        # Excluded recipes section (from history)
        excluded_section = ""
        if excluded_recipes:
            excluded_list = "\n".join(f"  - {name}" for name in excluded_recipes)
            excluded_section = (
                f"\n## Excluded Recipes (used in previous weeks)\n"
                f"Do NOT include any of the following recipes:\n"
                f"{excluded_list}\n"
            )

        # Already used this week section
        already_used_section = ""
        if already_used_recipes:
            used_list = "\n".join(f"  - {name}" for name in already_used_recipes)
            already_used_section = (
                f"\n## Recipes Already Used This Week\n"
                f"The following recipes have already been assigned to earlier days this week. "
                f"Try to use DIFFERENT recipes for variety (avoid repeating these unless necessary):\n"
                f"{used_list}\n"
            )

        min_categories = variety_constraints.get("min_protein_categories", 5)
        max_repetitions = variety_constraints.get("max_recipe_repetitions", 2)

        schema_json = json.dumps(SINGLE_DAY_JSON_SCHEMA, indent=2)

        # Build preferences section
        preferences_section = ""
        if profile.preferences:
            parts = []
            dislikes = profile.preferences.get("dislike", [])
            likes = profile.preferences.get("like", [])
            supplements = profile.preferences.get("supplements", [])

            if dislikes:
                parts.append("Foods/meals to ABSOLUTELY AVOID (user dislikes these):")
                for item in dislikes:
                    parts.append(f"  - Do NOT include {item}")

            if likes:
                parts.append("Foods/meals the user ENJOYS (prefer these):")
                for item in likes:
                    parts.append(f"  - {item}")

            if supplements:
                parts.append("Available protein supplements (can be used as snack recipes):")
                for supp in supplements:
                    name = supp.get("name", "Unknown")
                    protein = supp.get("protein_per_serving_g", 0)
                    notes = supp.get("notes", "")
                    parts.append(f"  - {name}: {protein}g protein per serving. {notes}")

            if parts:
                preferences_section = "\n## User Preferences\n" + "\n".join(parts) + "\n"

        # Determine number of people from profile name
        num_people = 2 if profile.name == "Shared" else 1
        sharing_note = ""
        if num_people > 1:
            sharing_note = (
                "\n**Note:** This meal plan is for 2 people cooking together. "
                "Generate recipes that work well for meal prep and sharing. "
                "Portions should be easy to scale.\n"
            )

        prompt = f"""You are a professional vegan nutritionist and meal planner.

Generate a complete meal plan for **{day_name}** for the following user:
{sharing_note}
## User Profile
- Name: {profile.name}
- Daily Protein Target: {profile.protein_target_g}g minimum
- Weight: {profile.weight_kg}kg
{preferences_section}
## Requirements
1. ALL recipes must be 100% vegan. No meat, poultry, fish, shellfish, dairy, eggs, honey, gelatin, or animal-derived additives (casein, whey, carmine, lanolin, shellac).
2. The day must include breakfast, lunch, dinner, and 1-3 snacks.
3. The combined daily protein from all meals and snacks MUST meet or exceed {profile.protein_target_g}g.
4. Each recipe must provide at least 20g of protein per serving.
5. Use protein sources from these categories: legumes, tofu_and_tempeh, seitan, nuts_and_seeds, protein_rich_grains.
6. RESPECT the user's food preferences — do NOT include disliked foods, DO include liked foods where possible, and use their available supplements as valid snack/shake recipes.
7. Each recipe MUST include detailed step-by-step cooking instructions (not just "Cook and serve"). Describe the actual cooking process: how to prepare ingredients, cooking temperatures, timing, and assembly steps.
8. Each recipe MUST include realistic prep_time_min and cook_time_min values.
{excluded_section}{already_used_section}
## Variety Constraints
- Use protein sources from at least {min_categories} of the 5 categories across the week.
- No recipe should appear more than {max_repetitions} times in the entire week.
- Prioritize variety — use different recipes from previous days.

## Output Format
Return ONLY valid JSON matching this exact schema (no markdown, no explanation, just JSON):

{schema_json}

CRITICAL RULES FOR THE JSON OUTPUT:
- "day" must be the string "{day_name}"
- "meals" has "breakfast", "lunch", "dinner" (each a recipe object) and "snacks" (array of 1-3 recipe objects)
- Each recipe must have: id (unique string), name, protein_source_category (one of the 5 categories), servings (integer >= 1), ingredients (array of objects with name/quantity/unit), macros_per_serving (object with protein_g/carbs_g/fat_g as numbers >= 0), instructions (string with DETAILED step-by-step cooking instructions), prep_time_min (integer), cook_time_min (integer)
- UNITS MUST BE EXACTLY ONE OF: "g", "ml", "whole", "tbsp", "tsp", "cup" — NO other units allowed. Convert any other measurement to one of these (e.g., "clove" → use "whole", "slice" → use "whole", "scoop" → use "g", "oz" → convert to "g", "piece" → use "whole")
- Instructions must be DETAILED: include preparation steps, cooking method, temperature if applicable, timing, and how to assemble/serve. Minimum 3-4 sentences per recipe.
- Do NOT include any text before or after the JSON.
"""
        return prompt

    def _build_prompt(
        self,
        profile: UserProfile,
        excluded_recipes: list[str],
        variety_constraints: dict,
    ) -> str:
        """Construct the structured prompt for the Gemini API (legacy 7-day).

        Args:
            profile: The user profile with nutritional targets.
            excluded_recipes: Recipe names to exclude.
            variety_constraints: Variety requirements for the plan.

        Returns:
            A formatted prompt string.
        """
        excluded_section = ""
        if excluded_recipes:
            excluded_list = "\n".join(f"  - {name}" for name in excluded_recipes)
            excluded_section = (
                f"\n## Excluded Recipes\n"
                f"Do NOT include any of the following recipes (they were used recently):\n"
                f"{excluded_list}\n"
            )

        min_categories = variety_constraints.get("min_protein_categories", 5)
        max_repetitions = variety_constraints.get("max_recipe_repetitions", 2)

        schema_json = json.dumps(MEAL_PLAN_JSON_SCHEMA, indent=2)

        # Build preferences section
        preferences_section = ""
        if profile.preferences:
            parts = []
            dislikes = profile.preferences.get("dislike", [])
            likes = profile.preferences.get("like", [])
            supplements = profile.preferences.get("supplements", [])

            if dislikes:
                parts.append("Foods/meals to AVOID (user dislikes these):")
                for item in dislikes:
                    parts.append(f"  - {item}")

            if likes:
                parts.append("Foods/meals the user ENJOYS:")
                for item in likes:
                    parts.append(f"  - {item}")

            if supplements:
                parts.append("Available protein supplements (can be used as snack recipes):")
                for supp in supplements:
                    name = supp.get("name", "Unknown")
                    protein = supp.get("protein_per_serving_g", 0)
                    notes = supp.get("notes", "")
                    parts.append(f"  - {name}: {protein}g protein per serving. {notes}")

            if parts:
                preferences_section = "\n## User Preferences\n" + "\n".join(parts) + "\n"

        prompt = f"""You are a professional vegan nutritionist and meal planner.

Generate a complete 7-day high-protein vegan meal plan for the following user:

## User Profile
- Name: {profile.name}
- Daily Protein Target: {profile.protein_target_g}g minimum
- Weight: {profile.weight_kg}kg
{preferences_section}
## Requirements
1. ALL recipes must be 100% vegan. No meat, poultry, fish, shellfish, dairy, eggs, honey, gelatin, or animal-derived additives (casein, whey, carmine, lanolin, shellac).
2. Each day must include breakfast, lunch, dinner, and 1-3 snacks.
3. The combined daily protein from all meals and snacks MUST meet or exceed {profile.protein_target_g}g.
4. Each recipe must provide at least 20g of protein per serving.
5. Use at least {min_categories} distinct protein source categories across the week: legumes, tofu_and_tempeh, seitan, nuts_and_seeds, protein_rich_grains.
6. No single recipe (by ID) should appear more than {max_repetitions} times in the entire week.
7. RESPECT the user's food preferences — do NOT include disliked foods, DO include liked foods where possible, and use their available supplements as valid snack/shake recipes.
{excluded_section}
## Variety Constraints
- Include recipes from at least {min_categories} of the 5 protein source categories (legumes, tofu_and_tempeh, seitan, nuts_and_seeds, protein_rich_grains), with at least 1 recipe from each included category.
- Maximum {max_repetitions} repetitions of any single recipe across the week.

## Output Format
Return ONLY valid JSON matching this exact schema (no markdown, no explanation, just JSON):

{schema_json}

CRITICAL RULES FOR THE JSON OUTPUT:
- "days" must be an array of exactly 7 objects
- Each day has "day" (string like "Monday") and "meals" object
- "meals" has "breakfast", "lunch", "dinner" (each a recipe object) and "snacks" (array of 1-3 recipe objects)
- Each recipe must have: id (unique string), name, protein_source_category (one of the 5 categories), servings (integer >= 1), ingredients (array of objects with name/quantity/unit), macros_per_serving (object with protein_g/carbs_g/fat_g as numbers >= 0), instructions (string)
- UNITS MUST BE EXACTLY ONE OF: "g", "ml", "whole", "tbsp", "tsp", "cup" — NO other units allowed. Convert any other measurement to one of these (e.g., "clove" → use "whole", "slice" → use "whole", "scoop" → use "g", "oz" → convert to "g", "piece" → use "whole")
- Keep the JSON concise. Limit instructions to 1-2 sentences max.
- Do NOT include any text before or after the JSON.
"""
        return prompt

    def _parse_response(self, response) -> dict:
        """Parse the Gemini API response into a dict.

        Handles potential markdown code blocks and extracts the JSON content.

        Args:
            response: The raw Gemini API response object.

        Returns:
            Parsed JSON as a dict.

        Raises:
            ValueError: If the response cannot be parsed as JSON.
        """
        text = response.text.strip()

        # Strip markdown code block if present
        if text.startswith("```"):
            # Remove opening ```json or ```
            first_newline = text.index("\n")
            text = text[first_newline + 1:]
            # Remove closing ```
            if text.endswith("```"):
                text = text[:-3].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse Gemini response as JSON: {e}") from e

    # Mapping of non-standard units to valid schema units
    UNIT_NORMALIZATION: dict[str, str] = {
        "scoop": "g",
        "scoops": "g",
        "serving": "g",
        "servings": "g",
        "block": "g",
        "blocks": "g",
        "clove": "whole",
        "cloves": "whole",
        "slice": "whole",
        "slices": "whole",
        "piece": "whole",
        "pieces": "whole",
        "bunch": "whole",
        "bunches": "whole",
        "handful": "g",
        "handfuls": "g",
        "pinch": "g",
        "dash": "ml",
        "can": "whole",
        "cans": "whole",
        "package": "whole",
        "packages": "whole",
        "packet": "whole",
        "oz": "g",
        "ounce": "g",
        "ounces": "g",
        "lb": "g",
        "lbs": "g",
        "pound": "g",
        "pounds": "g",
        "inch": "whole",
        "cm": "whole",
        "leaf": "whole",
        "leaves": "whole",
        "stalk": "whole",
        "stalks": "whole",
        "sprig": "whole",
        "sprigs": "whole",
        "medium": "whole",
        "large": "whole",
        "small": "whole",
    }

    # Conversion factors to base unit quantity (approximate)
    UNIT_QUANTITY_MULTIPLIER: dict[str, float] = {
        "oz": 28.35,
        "ounce": 28.35,
        "ounces": 28.35,
        "lb": 453.6,
        "lbs": 453.6,
        "pound": 453.6,
        "pounds": 453.6,
        "scoop": 53.0,  # typical protein scoop ~53g
        "scoops": 53.0,
        "block": 400.0,  # typical tofu block ~400g
        "blocks": 400.0,
    }

    def _normalize_units(self, day_data: dict) -> None:
        """Normalize non-standard units and categories in the response.

        Modifies the dict in place, converting units like 'scoop', 'block',
        'clove' etc. to valid schema units (g, ml, whole, tbsp, tsp, cup).
        Also normalizes protein_source_category values.
        """
        meals = day_data.get("meals", {})
        for meal_slot in ("breakfast", "lunch", "dinner"):
            recipe = meals.get(meal_slot)
            if recipe:
                self._normalize_recipe_units(recipe)
                self._normalize_recipe_category(recipe)
        for snack in meals.get("snacks", []):
            if snack:
                self._normalize_recipe_units(snack)
                self._normalize_recipe_category(snack)

    def _normalize_recipe_units(self, recipe: dict) -> None:
        """Normalize units in a single recipe's ingredients."""
        for ing in recipe.get("ingredients", []):
            unit = ing.get("unit", "").lower().strip()
            if unit in self.UNIT_NORMALIZATION:
                new_unit = self.UNIT_NORMALIZATION[unit]
                # Apply quantity conversion if available
                if unit in self.UNIT_QUANTITY_MULTIPLIER:
                    ing["quantity"] = ing.get("quantity", 1) * self.UNIT_QUANTITY_MULTIPLIER[unit]
                ing["unit"] = new_unit

    # Mapping of non-standard categories to valid ones
    CATEGORY_NORMALIZATION: dict[str, str] = {
        "supplement": "nuts_and_seeds",
        "supplements": "nuts_and_seeds",
        "protein_powder": "nuts_and_seeds",
        "plant_protein": "nuts_and_seeds",
        "soy": "legumes",
        "tofu": "tofu_and_tempeh",
        "tempeh": "tofu_and_tempeh",
        "lentils": "legumes",
        "beans": "legumes",
        "chickpeas": "legumes",
        "peas": "legumes",
        "quinoa": "protein_rich_grains",
        "oats": "protein_rich_grains",
        "grains": "protein_rich_grains",
        "nuts": "nuts_and_seeds",
        "seeds": "nuts_and_seeds",
    }

    def _normalize_recipe_category(self, recipe: dict) -> None:
        """Normalize protein_source_category to a valid enum value."""
        cat = recipe.get("protein_source_category", "").lower().strip()
        valid_categories = {"legumes", "tofu_and_tempeh", "seitan", "nuts_and_seeds", "protein_rich_grains"}
        if cat not in valid_categories and cat in self.CATEGORY_NORMALIZATION:
            recipe["protein_source_category"] = self.CATEGORY_NORMALIZATION[cat]
        elif cat not in valid_categories:
            # Default fallback
            recipe["protein_source_category"] = "nuts_and_seeds"
