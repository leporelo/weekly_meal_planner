"""Property-based tests for UserProfileManager.

Uses Hypothesis to verify universal properties of protein target calculation
and profile validation across all valid/invalid inputs.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from src.models import UserProfile
from src.user_profile_manager import UserProfileManager


# Feature: vegan-meal-planner, Property 1: Protein target calculation
# Validates: Requirements 1.2, 1.3, 1.5
@settings(max_examples=100)
@given(weight=st.floats(min_value=30.0, max_value=300.0))
def test_protein_target_calculation(weight: float) -> None:
    """For any valid weight in [30.0, 300.0] kg, the calculated protein target
    SHALL equal round(weight_kg * 1.6) grams."""
    manager = UserProfileManager()
    result = manager.calculate_protein_target(weight)
    expected = round(weight * 1.6)
    assert result == expected, (
        f"Protein target for {weight}kg should be {expected}g, got {result}g"
    )


# Feature: vegan-meal-planner, Property 2: Profile validation accepts valid and rejects invalid
# Validates: Requirements 1.1, 1.6
@settings(max_examples=100)
@given(
    weight=st.floats(min_value=30.0, max_value=300.0),
    height=st.integers(min_value=100, max_value=250),
)
def test_profile_validation_accepts_valid(weight: float, height: int) -> None:
    """For any UserProfile with weight in [30.0, 300.0] and height in [100, 250],
    the system SHALL accept the profile."""
    manager = UserProfileManager()
    profile = UserProfile(
        name="Test User",
        email="test@example.com",
        weight_kg=weight,
        height_cm=height,
        gender="male",
    )
    result = manager.validate_profile(profile)
    assert result.is_valid is True, (
        f"Profile with weight={weight}, height={height} should be valid, "
        f"but got errors: {result.errors}"
    )
    assert result.invalid_fields == [], (
        f"Valid profile should have no invalid fields, got: {result.invalid_fields}"
    )


@settings(max_examples=100)
@given(
    weight=st.one_of(
        st.floats(min_value=-1e6, max_value=29.9),
        st.floats(min_value=300.1, max_value=1e6),
    ),
    height=st.integers(min_value=100, max_value=250),
)
def test_profile_validation_rejects_invalid_weight(weight: float, height: int) -> None:
    """For any UserProfile with weight outside [30.0, 300.0], the system SHALL
    reject the profile and identify 'weight' as the out-of-range field."""
    manager = UserProfileManager()
    profile = UserProfile(
        name="Test User",
        email="test@example.com",
        weight_kg=weight,
        height_cm=height,
        gender="female",
    )
    result = manager.validate_profile(profile)
    assert result.is_valid is False, (
        f"Profile with weight={weight} should be invalid"
    )
    assert "weight" in result.invalid_fields, (
        f"Invalid weight={weight} should identify 'weight' field, "
        f"got: {result.invalid_fields}"
    )


@settings(max_examples=100)
@given(
    weight=st.floats(min_value=30.0, max_value=300.0),
    height=st.one_of(
        st.integers(min_value=-1000, max_value=99),
        st.integers(min_value=251, max_value=1000),
    ),
)
def test_profile_validation_rejects_invalid_height(weight: float, height: int) -> None:
    """For any UserProfile with height outside [100, 250], the system SHALL
    reject the profile and identify 'height' as the out-of-range field."""
    manager = UserProfileManager()
    profile = UserProfile(
        name="Test User",
        email="test@example.com",
        weight_kg=weight,
        height_cm=height,
        gender="other",
    )
    result = manager.validate_profile(profile)
    assert result.is_valid is False, (
        f"Profile with height={height} should be invalid"
    )
    assert "height" in result.invalid_fields, (
        f"Invalid height={height} should identify 'height' field, "
        f"got: {result.invalid_fields}"
    )
