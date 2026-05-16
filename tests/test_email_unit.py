"""Unit tests for EmailDispatcher retry logic.

Tests cover:
- Successful delivery on first attempt
- Exponential backoff timing: 60s, 120s, 240s
- Failure recording after all retries exhausted
- Success after initial failures

Requirements: 5.5, 5.6
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from src.email_dispatcher import EmailDispatcher, SmtpConfig
from src.models import (
    DeliveryResult,
    GroceryList,
    IngredientEntry,
    MealPlan,
    Recipe,
    UserProfile,
)


# --- Fixtures ---


@pytest.fixture
def smtp_config() -> SmtpConfig:
    """Create a test SMTP configuration."""
    return SmtpConfig(
        smtp_host="smtp.test.com",
        smtp_port=587,
        sender_email="sender@test.com",
        sender_password="password123",
    )


@pytest.fixture
def user_profile() -> UserProfile:
    """Create a test user profile."""
    return UserProfile(
        name="David",
        email="david@example.com",
        weight_kg=90.0,
        height_cm=180,
        gender="male",
    )


@pytest.fixture
def sample_recipe() -> Recipe:
    """Create a sample recipe for testing."""
    return Recipe(
        id="recipe-1",
        name="Tofu Scramble",
        protein_source_category="tofu_and_tempeh",
        servings=2,
        ingredients=[
            IngredientEntry(name="tofu", quantity=400, unit="g", category="produce"),
            IngredientEntry(name="spinach", quantity=100, unit="g", category="produce"),
        ],
        macros_per_serving={"protein_g": 25.0, "carbs_g": 10.0, "fat_g": 12.0},
        instructions="Crumble tofu and cook with spinach.",
    )


@pytest.fixture
def meal_plan(sample_recipe: Recipe) -> MealPlan:
    """Create a minimal meal plan for testing."""
    day = {
        "day": "Monday",
        "breakfast": sample_recipe,
        "lunch": sample_recipe,
        "dinner": sample_recipe,
        "snacks": [sample_recipe],
    }
    return MealPlan(days=[day] * 7)


@pytest.fixture
def grocery_list() -> GroceryList:
    """Create a minimal grocery list for testing."""
    return GroceryList(
        items=[
            IngredientEntry(name="tofu", quantity=2800, unit="g", category="produce"),
            IngredientEntry(name="spinach", quantity=700, unit="g", category="produce"),
        ],
        generated_at=datetime(2025, 1, 12, 8, 0),
    )


# --- Tests ---


class TestSuccessfulDelivery:
    """Test successful email delivery on first attempt."""

    def test_successful_delivery_returns_success_result(
        self,
        smtp_config: SmtpConfig,
        user_profile: UserProfile,
        meal_plan: MealPlan,
        grocery_list: GroceryList,
    ) -> None:
        """When _send_smtp succeeds on first attempt, DeliveryResult should be success=True."""
        sleep_calls: list[float] = []
        dispatcher = EmailDispatcher(
            smtp_config=smtp_config,
            max_retries=3,
            sleep_func=lambda t: sleep_calls.append(t),
        )

        with patch.object(dispatcher, "_send_smtp", return_value=None):
            result = dispatcher.send_meal_plan_email(user_profile, meal_plan, grocery_list)

        assert result.success is True
        assert result.recipient == "david@example.com"
        assert result.error_message is None
        assert result.final_attempt_timestamp is None

    def test_successful_delivery_no_sleep_calls(
        self,
        smtp_config: SmtpConfig,
        user_profile: UserProfile,
        meal_plan: MealPlan,
        grocery_list: GroceryList,
    ) -> None:
        """When delivery succeeds on first attempt, sleep_func should not be called."""
        sleep_calls: list[float] = []
        dispatcher = EmailDispatcher(
            smtp_config=smtp_config,
            max_retries=3,
            sleep_func=lambda t: sleep_calls.append(t),
        )

        with patch.object(dispatcher, "_send_smtp", return_value=None):
            dispatcher.send_meal_plan_email(user_profile, meal_plan, grocery_list)

        assert sleep_calls == []


class TestExponentialBackoff:
    """Test exponential backoff timing: 60s, 120s, 240s."""

    def test_backoff_intervals_on_all_failures(
        self,
        smtp_config: SmtpConfig,
        user_profile: UserProfile,
        meal_plan: MealPlan,
        grocery_list: GroceryList,
    ) -> None:
        """When all attempts fail, sleep_func should be called with [60, 120, 240]."""
        sleep_calls: list[float] = []
        dispatcher = EmailDispatcher(
            smtp_config=smtp_config,
            max_retries=3,
            sleep_func=lambda t: sleep_calls.append(t),
        )

        with patch.object(
            dispatcher, "_send_smtp", side_effect=Exception("SMTP connection failed")
        ):
            dispatcher.send_meal_plan_email(user_profile, meal_plan, grocery_list)

        assert sleep_calls == [60, 120, 240]

    def test_backoff_on_partial_failure_then_success(
        self,
        smtp_config: SmtpConfig,
        user_profile: UserProfile,
        meal_plan: MealPlan,
        grocery_list: GroceryList,
    ) -> None:
        """When first attempt fails but second succeeds, only one sleep call (60s)."""
        sleep_calls: list[float] = []
        dispatcher = EmailDispatcher(
            smtp_config=smtp_config,
            max_retries=3,
            sleep_func=lambda t: sleep_calls.append(t),
        )

        # First call raises, second call succeeds
        with patch.object(
            dispatcher,
            "_send_smtp",
            side_effect=[Exception("SMTP connection failed"), None],
        ):
            result = dispatcher.send_meal_plan_email(user_profile, meal_plan, grocery_list)

        assert result.success is True
        assert sleep_calls == [60]

    def test_backoff_on_two_failures_then_success(
        self,
        smtp_config: SmtpConfig,
        user_profile: UserProfile,
        meal_plan: MealPlan,
        grocery_list: GroceryList,
    ) -> None:
        """When first two attempts fail but third succeeds, sleep calls are [60, 120]."""
        sleep_calls: list[float] = []
        dispatcher = EmailDispatcher(
            smtp_config=smtp_config,
            max_retries=3,
            sleep_func=lambda t: sleep_calls.append(t),
        )

        with patch.object(
            dispatcher,
            "_send_smtp",
            side_effect=[
                Exception("SMTP connection failed"),
                Exception("SMTP timeout"),
                None,
            ],
        ):
            result = dispatcher.send_meal_plan_email(user_profile, meal_plan, grocery_list)

        assert result.success is True
        assert sleep_calls == [60, 120]


class TestFailureRecording:
    """Test failure recording after all retries exhausted."""

    def test_failure_result_after_all_retries_exhausted(
        self,
        smtp_config: SmtpConfig,
        user_profile: UserProfile,
        meal_plan: MealPlan,
        grocery_list: GroceryList,
    ) -> None:
        """When all retries exhausted, DeliveryResult should have success=False."""
        dispatcher = EmailDispatcher(
            smtp_config=smtp_config,
            max_retries=3,
            sleep_func=lambda t: None,
        )

        with patch.object(
            dispatcher, "_send_smtp", side_effect=Exception("Connection refused")
        ):
            result = dispatcher.send_meal_plan_email(user_profile, meal_plan, grocery_list)

        assert result.success is False

    def test_failure_includes_recipient(
        self,
        smtp_config: SmtpConfig,
        user_profile: UserProfile,
        meal_plan: MealPlan,
        grocery_list: GroceryList,
    ) -> None:
        """Failed delivery result should include the intended recipient address."""
        dispatcher = EmailDispatcher(
            smtp_config=smtp_config,
            max_retries=3,
            sleep_func=lambda t: None,
        )

        with patch.object(
            dispatcher, "_send_smtp", side_effect=Exception("Connection refused")
        ):
            result = dispatcher.send_meal_plan_email(user_profile, meal_plan, grocery_list)

        assert result.recipient == "david@example.com"

    def test_failure_includes_error_message(
        self,
        smtp_config: SmtpConfig,
        user_profile: UserProfile,
        meal_plan: MealPlan,
        grocery_list: GroceryList,
    ) -> None:
        """Failed delivery result should include the error message from the last attempt."""
        dispatcher = EmailDispatcher(
            smtp_config=smtp_config,
            max_retries=3,
            sleep_func=lambda t: None,
        )

        with patch.object(
            dispatcher, "_send_smtp", side_effect=Exception("Connection refused")
        ):
            result = dispatcher.send_meal_plan_email(user_profile, meal_plan, grocery_list)

        assert result.error_message == "Connection refused"

    def test_failure_includes_final_attempt_timestamp(
        self,
        smtp_config: SmtpConfig,
        user_profile: UserProfile,
        meal_plan: MealPlan,
        grocery_list: GroceryList,
    ) -> None:
        """Failed delivery result should include a final_attempt_timestamp."""
        dispatcher = EmailDispatcher(
            smtp_config=smtp_config,
            max_retries=3,
            sleep_func=lambda t: None,
        )

        before = datetime.now()
        with patch.object(
            dispatcher, "_send_smtp", side_effect=Exception("Connection refused")
        ):
            result = dispatcher.send_meal_plan_email(user_profile, meal_plan, grocery_list)
        after = datetime.now()

        assert result.final_attempt_timestamp is not None
        assert before <= result.final_attempt_timestamp <= after

    def test_failure_total_attempts_equals_one_plus_retries(
        self,
        smtp_config: SmtpConfig,
        user_profile: UserProfile,
        meal_plan: MealPlan,
        grocery_list: GroceryList,
    ) -> None:
        """The dispatcher should make 1 initial attempt + max_retries retry attempts."""
        call_count = 0

        def counting_send(msg):
            nonlocal call_count
            call_count += 1
            raise Exception("Connection refused")

        dispatcher = EmailDispatcher(
            smtp_config=smtp_config,
            max_retries=3,
            sleep_func=lambda t: None,
        )

        with patch.object(dispatcher, "_send_smtp", side_effect=counting_send):
            dispatcher.send_meal_plan_email(user_profile, meal_plan, grocery_list)

        assert call_count == 4  # 1 initial + 3 retries
