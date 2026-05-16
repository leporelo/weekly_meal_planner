"""User profile management for the Vegan Meal Planner."""

from pathlib import Path

import yaml

from .models import UserProfile, ValidationResult


class UserProfileManager:
    """Loads, validates, and provides user profiles from configuration."""

    # Valid ranges for profile fields
    WEIGHT_MIN = 30.0
    WEIGHT_MAX = 300.0
    HEIGHT_MIN = 100
    HEIGHT_MAX = 250

    def load_profiles(self, config_path: Path) -> list[UserProfile]:
        """Parse config.yaml and return a list of UserProfile instances.

        Args:
            config_path: Path to the config.yaml file.

        Returns:
            List of UserProfile objects with calculated protein targets.
        """
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        profiles: list[UserProfile] = []
        for user_data in config["users"]:
            protein_target = self.calculate_protein_target(user_data["weight_kg"])
            profile = UserProfile(
                name=user_data["name"],
                email=user_data["email"],
                weight_kg=user_data["weight_kg"],
                height_cm=user_data["height_cm"],
                gender=user_data["gender"],
                protein_target_g=protein_target,
                preferences=user_data.get("preferences", {}),
            )
            profiles.append(profile)

        return profiles

    @staticmethod
    def calculate_protein_target(weight_kg: float) -> int:
        """Calculate daily protein target based on body weight.

        Uses the formula: round(weight_kg * 1.6) grams per day.

        Args:
            weight_kg: User's body weight in kilograms.

        Returns:
            Daily protein target in whole grams.
        """
        return round(weight_kg * 1.6)

    def validate_profile(self, profile: UserProfile) -> ValidationResult:
        """Validate a user profile's weight and height are within acceptable ranges.

        Weight must be in [30.0, 300.0] kg and height must be in [100, 250] cm.

        Args:
            profile: The UserProfile to validate.

        Returns:
            ValidationResult with is_valid=True if all fields are in range,
            or is_valid=False with invalid_fields listing which fields are out of range.
        """
        invalid_fields: list[str] = []
        errors: list[str] = []

        if not (self.WEIGHT_MIN <= profile.weight_kg <= self.WEIGHT_MAX):
            invalid_fields.append("weight")
            errors.append(
                f"weight_kg {profile.weight_kg} is outside valid range "
                f"[{self.WEIGHT_MIN}, {self.WEIGHT_MAX}]"
            )

        if not (self.HEIGHT_MIN <= profile.height_cm <= self.HEIGHT_MAX):
            invalid_fields.append("height")
            errors.append(
                f"height_cm {profile.height_cm} is outside valid range "
                f"[{self.HEIGHT_MIN}, {self.HEIGHT_MAX}]"
            )

        if invalid_fields:
            return ValidationResult(
                is_valid=False,
                errors=errors,
                invalid_fields=invalid_fields,
            )

        return ValidationResult(is_valid=True)
