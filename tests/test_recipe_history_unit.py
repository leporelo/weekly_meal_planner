"""Unit tests for RecipeHistoryStore edge cases.

Tests cover:
- Missing history file creates new file after generation (Requirement 8.4)
- Empty/corrupt YAML file handling (Requirement 8.5)
- Pruning removes only records older than retention window (Requirement 8.6)
"""

from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from src.models import HistoryRecord
from src.recipe_history import RecipeHistoryStore


class TestMissingHistoryFile:
    """Test that a missing history file is handled gracefully and created on write."""

    def test_load_history_returns_empty_list_when_file_missing(self, tmp_path: Path) -> None:
        """Loading history from a non-existent path returns an empty list."""
        history_path = tmp_path / "nonexistent" / "history.yaml"
        store = RecipeHistoryStore(history_path=history_path)

        result = store.load_history()

        assert result == []

    def test_append_record_creates_file_when_missing(self, tmp_path: Path) -> None:
        """Appending a record to a non-existent file creates it."""
        history_path = tmp_path / "new_dir" / "history.yaml"
        store = RecipeHistoryStore(history_path=history_path)

        record = HistoryRecord(
            generation_date=date.today().isoformat(),
            users={"David": ["Tofu Scramble", "Lentil Curry"]},
            email_sent=True,
            email_sent_at="2025-01-12T08:00:00",
        )
        store.append_record(record)

        assert history_path.exists()
        data = yaml.safe_load(history_path.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["generation_date"] == date.today().isoformat()
        assert data[0]["users"]["David"] == ["Tofu Scramble", "Lentil Curry"]
        assert data[0]["email_sent"] is True
        assert data[0]["email_sent_at"] == "2025-01-12T08:00:00"


class TestEmptyAndCorruptFile:
    """Test graceful handling of empty and corrupt YAML history files."""

    def test_load_history_returns_empty_list_for_empty_file(self, tmp_path: Path) -> None:
        """An empty history file returns an empty list without crashing."""
        history_path = tmp_path / "history.yaml"
        history_path.write_text("", encoding="utf-8")
        store = RecipeHistoryStore(history_path=history_path)

        result = store.load_history()

        assert result == []

    def test_load_history_returns_empty_list_for_corrupt_yaml(self, tmp_path: Path) -> None:
        """A corrupt YAML file returns an empty list without crashing."""
        history_path = tmp_path / "history.yaml"
        history_path.write_text("{{invalid: yaml: [unterminated", encoding="utf-8")
        store = RecipeHistoryStore(history_path=history_path)

        result = store.load_history()

        assert result == []

    def test_load_history_returns_empty_list_for_whitespace_only_file(self, tmp_path: Path) -> None:
        """A file with only whitespace returns an empty list."""
        history_path = tmp_path / "history.yaml"
        history_path.write_text("   \n\t  \n", encoding="utf-8")
        store = RecipeHistoryStore(history_path=history_path)

        result = store.load_history()

        assert result == []


class TestPruning:
    """Test that pruning removes only records older than the retention window."""

    def test_prune_removes_records_older_than_retention_window(self, tmp_path: Path) -> None:
        """Records older than 4 weeks are pruned; recent ones are kept."""
        history_path = tmp_path / "history.yaml"
        store = RecipeHistoryStore(history_path=history_path, retention_weeks=4)

        today = date.today()
        records = [
            # 5 weeks ago — should be pruned
            {
                "generation_date": (today - timedelta(weeks=5)).isoformat(),
                "users": {"David": ["Old Recipe 1"]},
                "email_sent": True,
                "email_sent_at": None,
            },
            # 3 weeks ago — should be retained
            {
                "generation_date": (today - timedelta(weeks=3)).isoformat(),
                "users": {"David": ["Recent Recipe 1"]},
                "email_sent": True,
                "email_sent_at": None,
            },
            # 1 week ago — should be retained
            {
                "generation_date": (today - timedelta(weeks=1)).isoformat(),
                "users": {"David": ["Recent Recipe 2"]},
                "email_sent": False,
                "email_sent_at": None,
            },
        ]
        history_path.write_text(
            yaml.dump(records, default_flow_style=False),
            encoding="utf-8",
        )

        store.prune_old_records()

        data = yaml.safe_load(history_path.read_text(encoding="utf-8"))
        assert len(data) == 2
        dates = [r["generation_date"] for r in data]
        assert (today - timedelta(weeks=5)).isoformat() not in dates
        assert (today - timedelta(weeks=3)).isoformat() in dates
        assert (today - timedelta(weeks=1)).isoformat() in dates

    def test_records_at_exact_retention_boundary_are_retained(self, tmp_path: Path) -> None:
        """A record exactly 4 weeks old (at the boundary) should be retained."""
        history_path = tmp_path / "history.yaml"
        store = RecipeHistoryStore(history_path=history_path, retention_weeks=4)

        today = date.today()
        boundary_date = today - timedelta(weeks=4)

        records = [
            {
                "generation_date": boundary_date.isoformat(),
                "users": {"Sarah": ["Boundary Recipe"]},
                "email_sent": True,
                "email_sent_at": None,
            },
        ]
        history_path.write_text(
            yaml.dump(records, default_flow_style=False),
            encoding="utf-8",
        )

        store.prune_old_records()

        data = yaml.safe_load(history_path.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["generation_date"] == boundary_date.isoformat()

    def test_records_from_five_weeks_ago_are_pruned(self, tmp_path: Path) -> None:
        """A record from 5 weeks ago should be pruned."""
        history_path = tmp_path / "history.yaml"
        store = RecipeHistoryStore(history_path=history_path, retention_weeks=4)

        today = date.today()
        old_date = today - timedelta(weeks=5)

        records = [
            {
                "generation_date": old_date.isoformat(),
                "users": {"David": ["Very Old Recipe"]},
                "email_sent": False,
                "email_sent_at": None,
            },
        ]
        history_path.write_text(
            yaml.dump(records, default_flow_style=False),
            encoding="utf-8",
        )

        store.prune_old_records()

        data = yaml.safe_load(history_path.read_text(encoding="utf-8"))
        assert data is None or len(data) == 0


class TestNewFields:
    """Test that the new email_sent and email_sent_at fields work correctly."""

    def test_record_stores_email_sent_fields(self, tmp_path: Path) -> None:
        """Records correctly store email_sent and email_sent_at."""
        history_path = tmp_path / "history.yaml"
        store = RecipeHistoryStore(history_path=history_path)

        record = HistoryRecord(
            generation_date=date.today().isoformat(),
            users={"David": ["Tofu Bowl"]},
            email_sent=True,
            email_sent_at="2025-01-12T08:30:00",
        )
        store.append_record(record)

        loaded = store.load_history()
        assert len(loaded) == 1
        assert loaded[0].email_sent is True
        assert loaded[0].email_sent_at == "2025-01-12T08:30:00"

    def test_record_defaults_email_fields(self, tmp_path: Path) -> None:
        """Records default email_sent to False and email_sent_at to None."""
        history_path = tmp_path / "history.yaml"
        store = RecipeHistoryStore(history_path=history_path)

        record = HistoryRecord(
            generation_date=date.today().isoformat(),
            users={"David": ["Tempeh Stir Fry"]},
        )
        store.append_record(record)

        loaded = store.load_history()
        assert len(loaded) == 1
        assert loaded[0].email_sent is False
        assert loaded[0].email_sent_at is None
