"""Core data models and types for the Vegan Meal Planner."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


# --- Literal Types ---

Gender = Literal["male", "female", "other"]

ProteinSourceCategory = Literal[
    "legumes",
    "tofu_and_tempeh",
    "seitan",
    "nuts_and_seeds",
    "protein_rich_grains",
]

UnitType = Literal["g", "ml", "whole", "tbsp", "tsp", "cup", "kg", "l"]

GroceryCategory = Literal[
    "produce",
    "grains",
    "legumes",
    "nuts_and_seeds",
    "condiments",
    "frozen",
    "other",
]


# --- Data Models ---


@dataclass
class UserProfile:
    """A user's physical attributes and nutritional targets."""

    name: str
    email: str
    weight_kg: float  # 30.0 - 300.0
    height_cm: int  # 100 - 250
    gender: Gender
    protein_target_g: int = 0  # calculated: round(weight_kg * 1.6)
    preferences: dict = field(default_factory=dict)  # dislike, like, supplements

    def __post_init__(self) -> None:
        if self.protein_target_g == 0:
            self.protein_target_g = round(self.weight_kg * 1.6)


@dataclass
class IngredientEntry:
    """A single ingredient with quantity, unit, and category."""

    name: str  # canonical ingredient name
    quantity: float
    unit: UnitType
    category: GroceryCategory = "other"


@dataclass
class Recipe:
    """A vegan recipe with ingredients and macronutrient information."""

    id: str
    name: str
    protein_source_category: ProteinSourceCategory
    servings: int
    ingredients: list[IngredientEntry]
    macros_per_serving: dict[str, float]  # protein_g, carbs_g, fat_g
    instructions: str
    prep_time_min: int = 0
    cook_time_min: int = 0


@dataclass
class MealPlan:
    """A 7-day meal plan with breakfast, lunch, dinner, and snacks per day."""

    days: list[dict[str, "Recipe | list[Recipe]"]]
    # Each day is a dict with keys: "day", "breakfast", "lunch", "dinner", "snacks"
    # "day" maps to a string (day name), others map to Recipe or list[Recipe] for snacks

    def all_recipes(self) -> list[Recipe]:
        """Return a flat list of all recipes in the meal plan."""
        recipes: list[Recipe] = []
        for day in self.days:
            for key in ("breakfast", "lunch", "dinner"):
                meal = day.get(key)
                if isinstance(meal, Recipe):
                    recipes.append(meal)
            snacks = day.get("snacks")
            if isinstance(snacks, list):
                recipes.extend(snacks)
        return recipes


@dataclass
class GroceryList:
    """A consolidated grocery list with categorized ingredients."""

    items: list[IngredientEntry]
    generated_at: datetime

    def items_by_category(self) -> dict[str, list[IngredientEntry]]:
        """Group items by their grocery category."""
        result: dict[str, list[IngredientEntry]] = {}
        for item in self.items:
            result.setdefault(item.category, []).append(item)
        return result


@dataclass
class HistoryRecord:
    """A record of a past meal plan generation."""

    generation_date: str  # ISO date string e.g. "2025-01-12"
    users: dict[str, list[str]]  # user name -> list of recipe names
    email_sent: bool = False
    email_sent_at: str | None = None  # ISO timestamp or None


@dataclass
class ValidationResult:
    """Result of a validation check."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    invalid_fields: list[str] = field(default_factory=list)


@dataclass
class ComplianceResult:
    """Result of a vegan compliance check."""

    is_compliant: bool
    rejected_ingredient: str | None = None
    non_vegan_category: str | None = None


@dataclass
class DeliveryResult:
    """Result of an email delivery attempt."""

    success: bool
    recipient: str
    error_message: str | None = None
    final_attempt_timestamp: datetime | None = None


@dataclass
class GenerationResult:
    """Result of the weekly meal plan generation pipeline."""

    success: bool
    plans: dict[str, MealPlan] = field(default_factory=dict)  # user name -> MealPlan
    errors: list[str] = field(default_factory=list)


# --- Meal Plan JSON Schema ---

MEAL_PLAN_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "days": {
            "type": "array",
            "minItems": 7,
            "maxItems": 7,
            "items": {
                "type": "object",
                "properties": {
                    "day": {"type": "string"},
                    "meals": {
                        "type": "object",
                        "properties": {
                            "breakfast": {"$ref": "#/$defs/recipe"},
                            "lunch": {"$ref": "#/$defs/recipe"},
                            "dinner": {"$ref": "#/$defs/recipe"},
                            "snacks": {
                                "type": "array",
                                "minItems": 1,
                                "maxItems": 3,
                                "items": {"$ref": "#/$defs/recipe"},
                            },
                        },
                        "required": ["breakfast", "lunch", "dinner", "snacks"],
                    },
                },
                "required": ["day", "meals"],
            },
        }
    },
    "required": ["days"],
    "$defs": {
        "recipe": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "protein_source_category": {
                    "type": "string",
                    "enum": [
                        "legumes",
                        "tofu_and_tempeh",
                        "seitan",
                        "nuts_and_seeds",
                        "protein_rich_grains",
                    ],
                },
                "servings": {"type": "integer", "minimum": 1},
                "ingredients": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "quantity": {"type": "number"},
                            "unit": {
                                "type": "string",
                                "enum": ["g", "ml", "whole", "tbsp", "tsp", "cup"],
                            },
                        },
                        "required": ["name", "quantity", "unit"],
                    },
                },
                "macros_per_serving": {
                    "type": "object",
                    "properties": {
                        "protein_g": {"type": "number", "minimum": 0},
                        "carbs_g": {"type": "number", "minimum": 0},
                        "fat_g": {"type": "number", "minimum": 0},
                    },
                    "required": ["protein_g", "carbs_g", "fat_g"],
                },
                "instructions": {"type": "string"},
            },
            "required": [
                "id",
                "name",
                "protein_source_category",
                "servings",
                "ingredients",
                "macros_per_serving",
                "instructions",
            ],
        }
    },
}


# --- Single Day JSON Schema (for per-day generation) ---

SINGLE_DAY_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "day": {"type": "string"},
        "meals": {
            "type": "object",
            "properties": {
                "breakfast": {"$ref": "#/$defs/recipe"},
                "lunch": {"$ref": "#/$defs/recipe"},
                "dinner": {"$ref": "#/$defs/recipe"},
                "snacks": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {"$ref": "#/$defs/recipe"},
                },
            },
            "required": ["breakfast", "lunch", "dinner", "snacks"],
        },
    },
    "required": ["day", "meals"],
    "$defs": {
        "recipe": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "protein_source_category": {
                    "type": "string",
                    "enum": [
                        "legumes",
                        "tofu_and_tempeh",
                        "seitan",
                        "nuts_and_seeds",
                        "protein_rich_grains",
                    ],
                },
                "servings": {"type": "integer", "minimum": 1},
                "ingredients": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "quantity": {"type": "number"},
                            "unit": {
                                "type": "string",
                                "enum": ["g", "ml", "whole", "tbsp", "tsp", "cup"],
                            },
                        },
                        "required": ["name", "quantity", "unit"],
                    },
                },
                "macros_per_serving": {
                    "type": "object",
                    "properties": {
                        "protein_g": {"type": "number", "minimum": 0},
                        "carbs_g": {"type": "number", "minimum": 0},
                        "fat_g": {"type": "number", "minimum": 0},
                    },
                    "required": ["protein_g", "carbs_g", "fat_g"],
                },
                "instructions": {"type": "string"},
                "prep_time_min": {"type": "integer", "minimum": 0},
                "cook_time_min": {"type": "integer", "minimum": 0},
            },
            "required": [
                "id",
                "name",
                "protein_source_category",
                "servings",
                "ingredients",
                "macros_per_serving",
                "instructions",
                "prep_time_min",
                "cook_time_min",
            ],
        }
    },
}
