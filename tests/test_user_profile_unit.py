"""Unit tests for UserProfileManager.

Validates: Requirements 1.2, 1.3, 1.4, 1.6
"""

from pathlib import Path

import pytest

from src.models import UserProfile
from src.user_profile_manager import UserProfileManager


@pytest.fixture
def manager() -> UserProfileManager:
    return UserProfileManager()


class TestCalculateProteinTarget:
    """Test protein target calculation (Requirement 1.2, 1.3)."""

    def test_90kg_yields_144g(self, manager: UserProfileManager) -> None:
        """90kg * 1.6 = 144g protein target."""
        assert manager.calculate_protein_target(90.0) == 144

    def test_70kg_yields_112g(self, manager: UserProfileManager) -> None:
        """70kg * 1.6 = 112g protein target."""
        assert manager.calculate_protein_target(70.0) == 112


class TestLoadProfiles:
    """Test loading profiles from config.yaml (Requirement 1.4)."""

    def test_loads_two_profiles(self, manager: UserProfileManager) -> None:
        """config.yaml should contain exactly 2 user profiles (David and Sarah)."""
        config_path = Path(__file__).parent.parent / "config.yaml"
        profiles = manager.load_profiles(config_path)

        assert len(profiles) == 2
        assert profiles[0].name == "David"
        assert profiles[1].name == "Sarah"

    def test_profiles_have_correct_protein_targets(self, manager: UserProfileManager) -> None:
        """Loaded profiles should have calculated protein targets."""
        config_path = Path(__file__).parent.parent / "config.yaml"
        profiles = manager.load_profiles(config_path)

        assert profiles[0].protein_target_g == 144  # David: 90kg
        assert profiles[1].protein_target_g == 112  # Sarah: 70kg


class TestValidateProfile:
    """Test profile validation (Requirement 1.6)."""

    def test_rejects_weight_below_minimum(self, manager: UserProfileManager) -> None:
        """Weight below 30.0 should be rejected with 'weight' in invalid_fields."""
        profile = UserProfile(
            name="Test",
            email="test@example.com",
            weight_kg=25.0,
            height_cm=170,
            gender="male",
        )
        result = manager.validate_profile(profile)

        assert result.is_valid is False
        assert "weight" in result.invalid_fields

    def test_rejects_height_above_maximum(self, manager: UserProfileManager) -> None:
        """Height above 250 should be rejected with 'height' in invalid_fields."""
        profile = UserProfile(
            name="Test",
            email="test@example.com",
            weight_kg=80.0,
            height_cm=260,
            gender="female",
        )
        result = manager.validate_profile(profile)

        assert result.is_valid is False
        assert "height" in result.invalid_fields

    def test_rejects_multiple_invalid_fields(self, manager: UserProfileManager) -> None:
        """Both weight and height out of range should both appear in invalid_fields."""
        profile = UserProfile(
            name="Test",
            email="test@example.com",
            weight_kg=20.0,
            height_cm=300,
            gender="other",
        )
        result = manager.validate_profile(profile)

        assert result.is_valid is False
        assert "weight" in result.invalid_fields
        assert "height" in result.invalid_fields

    def test_accepts_valid_profile(self, manager: UserProfileManager) -> None:
        """A profile with valid weight and height should be accepted."""
        profile = UserProfile(
            name="Valid",
            email="valid@example.com",
            weight_kg=75.0,
            height_cm=175,
            gender="male",
        )
        result = manager.validate_profile(profile)

        assert result.is_valid is True
        assert result.invalid_fields == []
