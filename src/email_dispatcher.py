"""Email dispatcher for sending weekly meal plans with retry logic."""

import smtplib
import time
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Callable

from src.models import DeliveryResult, GroceryList, MealPlan, Recipe, UserProfile


@dataclass
class SmtpConfig:
    """SMTP configuration for email delivery."""

    smtp_host: str
    smtp_port: int
    sender_email: str
    sender_password: str


class EmailDispatcher:
    """Formats and sends weekly meal plan emails with retry logic."""

    def __init__(
        self,
        smtp_config: SmtpConfig,
        max_retries: int = 3,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialize the email dispatcher.

        Args:
            smtp_config: SMTP server configuration.
            max_retries: Maximum number of retry attempts on failure.
            sleep_func: Function to call for delays (for testability).
        """
        self.smtp_config = smtp_config
        self.max_retries = max_retries
        self._sleep = sleep_func
        self._base_interval = 60  # seconds

    def format_email_body(
        self, meal_plan: MealPlan, grocery_list: GroceryList, profiles: list[UserProfile]
    ) -> str:
        """Generate a plain text email with full recipes, per-person servings, and grocery list.

        Shows per-user protein targets at the top. For each recipe, calculates
        and displays recommended servings per person based on their individual
        protein targets relative to the highest target (which the plan was generated for).

        Args:
            meal_plan: The 7-day shared meal plan to format.
            grocery_list: The consolidated grocery list (scaled for all users).
            profiles: All user profiles (for showing protein targets and serving ratios).

        Returns:
            Formatted plain text email body.
        """
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("YOUR WEEKLY VEGAN MEAL PLAN")
        lines.append("=" * 60)
        lines.append("")

        # Determine the max protein target (plan was generated for this)
        max_target = max(p.protein_target_g for p in profiles)

        # Per-user protein targets
        targets = " | ".join(
            f"{p.name}: {p.protein_target_g}g/day" for p in profiles
        )
        lines.append(f"Daily protein targets: {targets}")
        lines.append("")

        # Day-by-day breakdown with full recipes
        for day_data in meal_plan.days:
            day_name = day_data.get("day", "Unknown")
            lines.append(f"{'─' * 60}")
            lines.append(f"  {day_name.upper()}")
            lines.append(f"{'─' * 60}")
            lines.append("")

            # Format each meal slot
            for meal_slot in ("breakfast", "lunch", "dinner"):
                recipe = day_data.get(meal_slot)
                if isinstance(recipe, Recipe):
                    lines.append(f"▸ {meal_slot.capitalize()}")
                    lines.extend(
                        self._format_recipe_with_servings(recipe, profiles, max_target)
                    )
                    lines.append("")

            # Format snacks
            snacks = day_data.get("snacks")
            if isinstance(snacks, list):
                for i, snack in enumerate(snacks, 1):
                    if isinstance(snack, Recipe):
                        label = f"Snack {i}" if len(snacks) > 1 else "Snack"
                        lines.append(f"▸ {label}")
                        lines.extend(
                            self._format_recipe_with_servings(snack, profiles, max_target)
                        )
                        lines.append("")

            lines.append("")

        # Grocery list section (scaled for all people)
        num_people = len(profiles)
        lines.append("=" * 60)
        lines.append(f"Grocery List (for {num_people} people)")
        lines.append("=" * 60)
        lines.append("")
        categories = grocery_list.items_by_category()
        for category, items in sorted(categories.items()):
            lines.append(f"  [{category.replace('_', ' ').title()}]")
            for item in items:
                qty = round(item.quantity, 1)
                lines.append(f"    • {item.name}: {qty} {item.unit}")
            lines.append("")

        return "\n".join(lines)

    def _calculate_servings_for_profile(
        self, recipe: Recipe, profile: UserProfile, max_target: int
    ) -> float:
        """Calculate recommended servings for a profile based on their protein ratio.

        The plan was generated targeting max_target grams. Each person's servings
        are proportional: their_target / max_target * recipe.servings.

        Args:
            recipe: The recipe with stated servings (for the max target user).
            profile: The user profile to calculate for.
            max_target: The highest protein target (plan was generated for this).

        Returns:
            Recommended number of servings (rounded to 1 decimal).
        """
        ratio = profile.protein_target_g / max_target
        return round(ratio * recipe.servings, 1)

    def _format_recipe_with_servings(
        self, recipe: Recipe, profiles: list[UserProfile], max_target: int
    ) -> list[str]:
        """Format a single recipe with per-person serving recommendations.

        Args:
            recipe: The Recipe object to format.
            profiles: All user profiles.
            max_target: The highest protein target used for plan generation.

        Returns:
            List of formatted lines for this recipe.
        """
        lines: list[str] = []
        protein = recipe.macros_per_serving.get("protein_g", 0)
        carbs = recipe.macros_per_serving.get("carbs_g", 0)
        fat = recipe.macros_per_serving.get("fat_g", 0)

        lines.append(f"  {recipe.name}")
        lines.append(
            f"  Protein: {protein}g per serving | "
            f"Prep: {recipe.prep_time_min} min | Cook: {recipe.cook_time_min} min"
        )

        # Per-person serving recommendations
        total_servings = 0.0
        for profile in profiles:
            person_servings = self._calculate_servings_for_profile(
                recipe, profile, max_target
            )
            person_protein = round(person_servings * protein, 1)
            lines.append(
                f"    → {profile.name}: {person_servings} servings ({person_protein}g protein)"
            )
            total_servings += person_servings

        lines.append("")
        lines.append(
            f"  Macros per serving: Protein {protein}g | Carbs {carbs}g | Fat {fat}g"
        )

        # Ingredients (scaled for total servings across all people)
        lines.append("")
        lines.append(f"  Ingredients (for {round(total_servings, 1)} total servings):")
        # Scale factor: total_servings / recipe.servings
        scale = total_servings / recipe.servings if recipe.servings > 0 else 1.0
        for ing in recipe.ingredients:
            scaled_qty = round(ing.quantity * scale, 1)
            lines.append(f"    - {scaled_qty} {ing.unit} {ing.name}")

        # Instructions
        lines.append("")
        lines.append("  Instructions:")
        instructions = recipe.instructions.strip()
        if instructions:
            steps = [s.strip() for s in instructions.split(". ") if s.strip()]
            for i, step in enumerate(steps, 1):
                step_text = step.rstrip(".")
                lines.append(f"    {i}. {step_text}.")

        return lines

    def send_meal_plan_emails(
        self,
        profiles: list[UserProfile],
        meal_plan: MealPlan,
        grocery_list: GroceryList,
    ) -> list[DeliveryResult]:
        """Send the same formatted meal plan email to all users.

        Generates one email body and sends it to each user's email address.

        Args:
            profiles: All user profiles (used for email addresses and protein targets).
            meal_plan: The shared meal plan to send.
            grocery_list: The grocery list to include (already scaled).

        Returns:
            List of DeliveryResult, one per user.
        """
        body = self.format_email_body(meal_plan, grocery_list, profiles)
        results: list[DeliveryResult] = []

        for profile in profiles:
            result = self._send_to_user(profile, body)
            results.append(result)

        return results

    def send_meal_plan_email(
        self, profile: UserProfile, meal_plan: MealPlan, grocery_list: GroceryList
    ) -> DeliveryResult:
        """Send formatted meal plan email to a single user with retry logic.

        Legacy method kept for backwards compatibility. For the shared plan flow,
        use send_meal_plan_emails instead.

        Args:
            profile: The user profile (contains email address).
            meal_plan: The meal plan to send.
            grocery_list: The grocery list to include.

        Returns:
            DeliveryResult indicating success or failure.
        """
        body = self.format_email_body(meal_plan, grocery_list, [profile])
        return self._send_to_user(profile, body)

    def _send_to_user(self, profile: UserProfile, body: str) -> DeliveryResult:
        """Send a pre-formatted email body to a single user with retry logic.

        Makes an initial attempt, then retries up to max_retries times with
        exponential backoff (60s, 120s, 240s) on failure.

        Args:
            profile: The user profile (contains email address).
            body: The formatted email body text.

        Returns:
            DeliveryResult indicating success or failure.
        """
        msg = MIMEMultipart()
        msg["From"] = self.smtp_config.sender_email
        msg["To"] = profile.email
        msg["Subject"] = f"Weekly Vegan Meal Plan - {profile.name}"
        msg.attach(MIMEText(body, "plain"))

        last_error: str | None = None
        total_attempts = 1 + self.max_retries  # initial + retries

        for attempt in range(total_attempts):
            try:
                self._send_smtp(msg)
                return DeliveryResult(success=True, recipient=profile.email)
            except Exception as e:
                last_error = str(e)
                # Wait with exponential backoff before next retry
                if attempt < total_attempts - 1:
                    backoff = self._base_interval * (2**attempt)
                    self._sleep(backoff)

        # All retries exhausted
        return DeliveryResult(
            success=False,
            recipient=profile.email,
            error_message=last_error,
            final_attempt_timestamp=datetime.now(),
        )

    def _send_smtp(self, msg: MIMEMultipart) -> None:
        """Send email via SMTP.

        Uses SMTP_SSL for port 465, STARTTLS for other ports.

        Args:
            msg: The email message to send.

        Raises:
            smtplib.SMTPException: On any SMTP failure.
        """
        if self.smtp_config.smtp_port == 465:
            with smtplib.SMTP_SSL(self.smtp_config.smtp_host, self.smtp_config.smtp_port) as server:
                server.login(self.smtp_config.sender_email, self.smtp_config.sender_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(self.smtp_config.smtp_host, self.smtp_config.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self.smtp_config.sender_email, self.smtp_config.sender_password)
                server.send_message(msg)
