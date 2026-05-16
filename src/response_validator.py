"""Response validation for Gemini API meal plan responses."""

import jsonschema

from src.models import MEAL_PLAN_JSON_SCHEMA, ValidationResult


class ResponseValidator:
    """Validates Gemini API responses against the expected JSON schema and nutritional rules."""

    REQUIRED_RECIPE_FIELDS = [
        "id",
        "name",
        "protein_source_category",
        "servings",
        "ingredients",
        "macros_per_serving",
        "instructions",
    ]

    REQUIRED_MACRO_FIELDS = ["protein_g", "carbs_g", "fat_g"]

    def validate_meal_plan(self, response: dict) -> ValidationResult:
        """Validate a meal plan response against the JSON schema.

        Uses jsonschema to verify structure: 7 days, each with breakfast/lunch/dinner
        and 1-3 snacks, all recipes with required fields.

        Args:
            response: The raw dict from Gemini API response.

        Returns:
            ValidationResult with is_valid=True if valid, otherwise errors populated.
        """
        try:
            jsonschema.validate(instance=response, schema=MEAL_PLAN_JSON_SCHEMA)
            return ValidationResult(is_valid=True)
        except jsonschema.ValidationError as e:
            return ValidationResult(
                is_valid=False,
                errors=[e.message],
            )

    def validate_recipe(self, recipe: dict) -> ValidationResult:
        """Validate a single recipe dict has all required fields and numeric macros.

        Args:
            recipe: A recipe dict from the Gemini API response.

        Returns:
            ValidationResult with errors listing missing/invalid fields.
        """
        errors: list[str] = []
        invalid_fields: list[str] = []

        # Check required top-level fields
        for field_name in self.REQUIRED_RECIPE_FIELDS:
            if field_name not in recipe:
                errors.append(f"Missing required field: {field_name}")
                invalid_fields.append(field_name)

        # Check macros_per_serving if present
        macros = recipe.get("macros_per_serving")
        if macros is not None:
            if not isinstance(macros, dict):
                errors.append("macros_per_serving must be a dict")
                invalid_fields.append("macros_per_serving")
            else:
                for macro_field in self.REQUIRED_MACRO_FIELDS:
                    if macro_field not in macros:
                        errors.append(
                            f"Missing required macro field: {macro_field}"
                        )
                        invalid_fields.append(macro_field)
                    elif not isinstance(macros[macro_field], (int, float)):
                        errors.append(
                            f"Macro field {macro_field} must be numeric, "
                            f"got {type(macros[macro_field]).__name__}"
                        )
                        invalid_fields.append(macro_field)

        if errors:
            return ValidationResult(
                is_valid=False, errors=errors, invalid_fields=invalid_fields
            )
        return ValidationResult(is_valid=True)

    def validate_macronutrients(
        self, recipe: dict, protein_target: int
    ) -> ValidationResult:
        """Validate that a recipe meets minimum protein requirements.

        Flags any recipe with protein_g < 20 per serving as non-compliant.

        Args:
            recipe: A recipe dict from the Gemini API response.
            protein_target: The user's daily protein target in grams.

        Returns:
            ValidationResult with errors if protein is below minimum threshold.
        """
        errors: list[str] = []

        macros = recipe.get("macros_per_serving")
        if macros is None:
            return ValidationResult(
                is_valid=False,
                errors=["Recipe missing macros_per_serving"],
            )

        protein_g = macros.get("protein_g")
        if protein_g is None:
            return ValidationResult(
                is_valid=False,
                errors=["Recipe missing protein_g in macros_per_serving"],
            )

        if not isinstance(protein_g, (int, float)):
            return ValidationResult(
                is_valid=False,
                errors=[f"protein_g must be numeric, got {type(protein_g).__name__}"],
            )

        # Flag as non-compliant if protein_g < 20 per serving
        if protein_g < 20:
            recipe_name = recipe.get("name", "Unknown")
            errors.append(
                f"Recipe '{recipe_name}' has {protein_g}g protein per serving, "
                f"below minimum 20g threshold"
            )
            return ValidationResult(is_valid=False, errors=errors)

        return ValidationResult(is_valid=True)
