"""Meal plan orchestrator that coordinates the full weekly generation pipeline."""

import logging
import os
from datetime import date, datetime
from pathlib import Path

import yaml

from src.email_dispatcher import EmailDispatcher, SmtpConfig
from src.gemini_client import DAYS_OF_WEEK, GeminiClient
from src.grocery_list_builder import GroceryListBuilder
from src.models import (
    GenerationResult,
    HistoryRecord,
    IngredientEntry,
    MealPlan,
    Recipe,
    UserProfile,
)
from src.recipe_history import RecipeHistoryStore
from src.response_validator import ResponseValidator
from src.user_profile_manager import UserProfileManager
from src.variety_enforcer import VarietyEnforcer
from src.vegan_compliance import VeganComplianceChecker
from src.website_publisher import WebsitePublisher

logger = logging.getLogger(__name__)


class MealPlanOrchestrator:
    """Coordinates the full weekly meal plan generation pipeline.

    Generates ONE shared meal plan for all users, using the highest protein
    target and merged preferences. Sends the same plan to everyone.

    Pipeline: load profiles → merge preferences → load history →
    generate shared plan → validate → check compliance → check variety →
    build grocery list (scaled for number of people) → send emails → save history.
    """

    def __init__(self, config_path: Path) -> None:
        """Initialize the orchestrator with all components.

        Args:
            config_path: Path to the config.yaml file.
        """
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.config_path = config_path

        # User profile management
        self.profile_manager = UserProfileManager()

        # Recipe history
        history_config = self.config["history"]
        self.history_store = RecipeHistoryStore(
            history_path=Path(history_config["file_path"]),
            retention_weeks=history_config["retention_weeks"],
        )

        # Gemini API client
        gemini_config = self.config["gemini"]
        api_key_env = gemini_config["api_key_env"]
        api_key = os.environ.get(api_key_env)
        self.gemini_client = GeminiClient(
            api_key=api_key,
            model=gemini_config.get("model", "gemini-2.0-flash"),
            max_retries=gemini_config.get("max_retries", 2),
        )

        # Validators and checkers
        self.response_validator = ResponseValidator()
        self.vegan_checker = VeganComplianceChecker()
        self.variety_enforcer = VarietyEnforcer()

        # Grocery list builder
        self.grocery_builder = GroceryListBuilder()

        # Email dispatcher
        email_config = self.config["email"]
        smtp_config = SmtpConfig(
            smtp_host=email_config["smtp_host"],
            smtp_port=email_config["smtp_port"],
            sender_email=os.environ.get(email_config["sender_email_env"], ""),
            sender_password=os.environ.get(email_config["sender_password_env"], ""),
        )
        self.email_dispatcher = EmailDispatcher(smtp_config=smtp_config)

        # Website publisher
        self.publish_website = self.config.get("publish_website", False)
        if self.publish_website:
            self.website_publisher = WebsitePublisher(
                repo_path=config_path.parent,
            )

    def _merge_preferences(self, profiles: list[UserProfile]) -> dict:
        """Merge preferences from all user profiles.

        Combines dislikes, likes, and supplements from all users into one set.

        Args:
            profiles: List of validated user profiles.

        Returns:
            A merged preferences dict with combined dislike, like, supplements lists.
        """
        all_dislikes: list[str] = []
        all_likes: list[str] = []
        all_supplements: list[dict] = []

        seen_dislikes: set[str] = set()
        seen_likes: set[str] = set()
        seen_supplements: set[str] = set()

        for profile in profiles:
            prefs = profile.preferences or {}

            for item in prefs.get("dislike", []):
                if item.lower() not in seen_dislikes:
                    seen_dislikes.add(item.lower())
                    all_dislikes.append(item)

            for item in prefs.get("like", []):
                if item.lower() not in seen_likes:
                    seen_likes.add(item.lower())
                    all_likes.append(item)

            for supp in prefs.get("supplements", []):
                supp_name = supp.get("name", "").lower()
                if supp_name and supp_name not in seen_supplements:
                    seen_supplements.add(supp_name)
                    all_supplements.append(supp)

        return {
            "dislike": all_dislikes,
            "like": all_likes,
            "supplements": all_supplements,
        }

    def run_weekly_generation(self) -> GenerationResult:
        """Execute the full weekly meal plan generation pipeline.

        Generates ONE shared meal plan for all users using the highest protein
        target and merged preferences. Sends the same email to all users.

        Returns:
            GenerationResult with success status, generated plan, and any errors.
        """
        errors: list[str] = []
        plans: dict[str, MealPlan] = {}
        valid_profiles: list[UserProfile] = []

        # Step 1: Load and validate profiles
        try:
            profiles = self.profile_manager.load_profiles(self.config_path)
            logger.info("Loaded %d user profiles.", len(profiles))
        except Exception as e:
            error_msg = f"Failed to load user profiles: {e}"
            logger.error(error_msg)
            return GenerationResult(success=False, errors=[error_msg])

        # Step 2: Validate each profile
        for profile in profiles:
            validation = self.profile_manager.validate_profile(profile)
            if validation.is_valid:
                valid_profiles.append(profile)
            else:
                error_msg = (
                    f"Profile '{profile.name}' failed validation: "
                    f"{', '.join(validation.errors)}"
                )
                logger.warning(error_msg)
                errors.append(error_msg)

        if not valid_profiles:
            error_msg = "No valid profiles to generate plans for."
            logger.error(error_msg)
            errors.append(error_msg)
            return GenerationResult(success=False, errors=errors)

        # Step 3: Pick the HIGHEST protein target and merge preferences
        max_protein_target = max(p.protein_target_g for p in valid_profiles)
        merged_preferences = self._merge_preferences(valid_profiles)

        # Build a combined profile for generation (uses max protein target + merged prefs)
        generation_profile = UserProfile(
            name="Shared",
            email="",
            weight_kg=valid_profiles[0].weight_kg,  # not used for generation target
            height_cm=valid_profiles[0].height_cm,
            gender=valid_profiles[0].gender,
            protein_target_g=max_protein_target,
            preferences=merged_preferences,
        )

        logger.info(
            "Using protein target: %dg (max across %d users). Merged preferences from all users.",
            max_protein_target,
            len(valid_profiles),
        )

        # Step 4: Load excluded recipes from history
        try:
            excluded_recipes = self.history_store.get_excluded_recipes()
            logger.info(
                "Loaded %d excluded recipes from history.", len(excluded_recipes)
            )
        except Exception as e:
            logger.warning("Failed to load excluded recipes: %s. Proceeding without exclusions.", e)
            excluded_recipes = []

        # Step 5: Prune old history records
        try:
            self.history_store.prune_old_records()
            logger.info("Pruned old history records.")
        except Exception as e:
            logger.warning("Failed to prune history records: %s. Continuing.", e)

        # Step 6: Generate ONE shared meal plan
        email_sent_success = False
        meal_plan: MealPlan | None = None
        try:
            meal_plan = self._generate_shared_plan(generation_profile, excluded_recipes)
            if meal_plan is not None:
                # Store the same plan under each user's name for compatibility
                for profile in valid_profiles:
                    plans[profile.name] = meal_plan
            else:
                errors.append("Generation failed for shared meal plan after validation checks.")
        except Exception as e:
            error_msg = f"Generation failed for shared meal plan: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        if meal_plan is None:
            return GenerationResult(success=False, plans=plans, errors=errors)

        # Step 7: Build grocery list (scaled proportionally for all people's servings)
        # The plan was generated for max_protein_target. Each person's ratio is
        # their_target / max_target. Total scale = sum of all ratios.
        grocery_list = None
        try:
            total_scale = sum(
                p.protein_target_g / max_protein_target for p in valid_profiles
            )
            # Round to 2 decimals for cleaner quantities
            total_scale = round(total_scale, 2)
            grocery_list = self.grocery_builder.build(
                [meal_plan], scale_factor=total_scale
            )
            logger.info(
                "Built grocery list with %d items (scale factor %.2f for %d people).",
                len(grocery_list.items),
                total_scale,
                len(valid_profiles),
            )
        except Exception as e:
            error_msg = f"Failed to build grocery list: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        # Step 8: Send the SAME email to ALL users
        if grocery_list is not None:
            try:
                results = self.email_dispatcher.send_meal_plan_emails(
                    valid_profiles, meal_plan, grocery_list
                )
                for result in results:
                    if result.success:
                        logger.info("Email sent to '%s'.", result.recipient)
                        email_sent_success = True
                    else:
                        error_msg = (
                            f"Email delivery failed for '{result.recipient}': "
                            f"{result.error_message}"
                        )
                        logger.warning(error_msg)
                        errors.append(error_msg)
            except Exception as e:
                error_msg = f"Email sending failed: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        else:
            logger.warning("Skipping emails due to missing grocery list.")

        # Step 9: Publish to website
        if self.publish_website and grocery_list is not None:
            try:
                published = self.website_publisher.publish(
                    meal_plan, valid_profiles, grocery_list
                )
                if published:
                    logger.info("Website published successfully.")
                else:
                    logger.warning("Website publish returned False.")
            except Exception as e:
                error_msg = f"Website publish failed: {e}"
                logger.warning(error_msg)
                errors.append(error_msg)

        # Step 10: Append history record
        try:
            recipe_names = [recipe.name for recipe in meal_plan.all_recipes()]
            history_users: dict[str, list[str]] = {}
            for profile in valid_profiles:
                history_users[profile.name] = recipe_names

            record = HistoryRecord(
                generation_date=date.today().isoformat(),
                users=history_users,
                email_sent=email_sent_success,
                email_sent_at=datetime.now().isoformat() if email_sent_success else None,
            )
            self.history_store.append_record(record)
            logger.info("History record appended for %d users.", len(history_users))
        except Exception as e:
            error_msg = f"Failed to append history record: {e}"
            logger.warning(error_msg)
            errors.append(error_msg)

        # Step 10: Return result
        success = meal_plan is not None
        return GenerationResult(success=success, plans=plans, errors=errors)

    def _generate_shared_plan(
        self, profile: UserProfile, excluded_recipes: list[str]
    ) -> MealPlan | None:
        """Generate and validate a shared meal plan, one day at a time.

        Uses the combined profile (max protein target + merged preferences)
        to generate 7 days. Validates schema, vegan compliance, and variety.

        Args:
            profile: The combined profile for generation.
            excluded_recipes: Recipe names to exclude.

        Returns:
            A validated MealPlan, or None if generation/validation failed.
        """
        variety_constraints = {
            "min_protein_categories": 5,
            "max_recipe_repetitions": 2,
        }

        logger.info("Generating shared meal plan (day-by-day)...")

        days: list[dict] = []
        already_used_recipes: list[str] = []

        for day_name in DAYS_OF_WEEK:
            day_data = None

            # First attempt (uses built-in retries in generate_single_day)
            try:
                day_data = self.gemini_client.generate_single_day(
                    profile=profile,
                    day_name=day_name,
                    excluded_recipes=excluded_recipes,
                    already_used_recipes=already_used_recipes,
                    variety_constraints=variety_constraints,
                )
            except RuntimeError as e:
                logger.warning(
                    "First attempt failed for %s: %s. Retrying once more...",
                    day_name,
                    e,
                )
                # One extra retry for the failed day
                try:
                    day_data = self.gemini_client.generate_single_day(
                        profile=profile,
                        day_name=day_name,
                        excluded_recipes=excluded_recipes,
                        already_used_recipes=already_used_recipes,
                        variety_constraints=variety_constraints,
                    )
                except RuntimeError as retry_error:
                    logger.error(
                        "Final retry also failed for %s: %s",
                        day_name,
                        retry_error,
                    )
                    return None

            if day_data is None:
                return None

            # Collect recipe names from this day
            meals = day_data.get("meals", {})
            for meal_slot in ("breakfast", "lunch", "dinner"):
                recipe = meals.get(meal_slot)
                if recipe and "name" in recipe:
                    already_used_recipes.append(recipe["name"])
            for snack in meals.get("snacks", []):
                if snack and "name" in snack:
                    already_used_recipes.append(snack["name"])

            days.append(day_data)

        # Assemble the full response and validate
        response = {"days": days}

        # Validate response schema
        validation = self.response_validator.validate_meal_plan(response)
        if not validation.is_valid:
            logger.warning(
                "Response validation failed for shared plan: %s",
                "; ".join(validation.errors),
            )
            return None

        # Convert response dict to MealPlan with Recipe objects
        meal_plan = self._convert_response_to_meal_plan(response)

        # Check vegan compliance for each recipe
        for recipe in meal_plan.all_recipes():
            compliance = self.vegan_checker.check_recipe(recipe)
            if not compliance.is_compliant:
                logger.warning(
                    "Recipe '%s' failed vegan compliance: "
                    "ingredient '%s' matched category '%s'.",
                    recipe.name,
                    compliance.rejected_ingredient,
                    compliance.non_vegan_category,
                )
                return None

        # Check variety constraints
        if not self.variety_enforcer.check_within_week_limits(meal_plan):
            logger.warning("Shared meal plan exceeds within-week repetition limits.")
            return None

        if not self.variety_enforcer.check_protein_source_diversity(meal_plan):
            logger.warning("Shared meal plan lacks protein source diversity.")
            return None

        logger.info("Shared meal plan generated successfully.")
        return meal_plan

    def _convert_response_to_meal_plan(self, response: dict) -> MealPlan:
        """Convert a validated Gemini API response dict to a MealPlan object.

        Args:
            response: The validated response dict from the Gemini API.

        Returns:
            A MealPlan instance with Recipe objects.
        """
        days: list[dict] = []

        for day_data in response["days"]:
            day_dict: dict = {"day": day_data["day"]}
            meals = day_data["meals"]

            # Convert main meals
            for meal_slot in ("breakfast", "lunch", "dinner"):
                recipe_dict = meals[meal_slot]
                day_dict[meal_slot] = self._convert_recipe(recipe_dict)

            # Convert snacks
            snacks = []
            for snack_dict in meals["snacks"]:
                snacks.append(self._convert_recipe(snack_dict))
            day_dict["snacks"] = snacks

            days.append(day_dict)

        return MealPlan(days=days)

    def _convert_recipe(self, recipe_dict: dict) -> Recipe:
        """Convert a recipe dict to a Recipe dataclass instance.

        Args:
            recipe_dict: A recipe dict from the Gemini API response.

        Returns:
            A Recipe instance.
        """
        ingredients = []
        for ing in recipe_dict.get("ingredients", []):
            ingredients.append(
                IngredientEntry(
                    name=ing["name"],
                    quantity=ing["quantity"],
                    unit=ing["unit"],
                )
            )

        return Recipe(
            id=recipe_dict["id"],
            name=recipe_dict["name"],
            protein_source_category=recipe_dict["protein_source_category"],
            servings=recipe_dict["servings"],
            ingredients=ingredients,
            macros_per_serving=recipe_dict["macros_per_serving"],
            instructions=recipe_dict["instructions"],
            prep_time_min=recipe_dict.get("prep_time_min", 0),
            cook_time_min=recipe_dict.get("cook_time_min", 0),
        )
