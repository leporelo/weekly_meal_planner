"""Property-based tests for RecipeHistoryStore.

Uses Hypothesis to verify that history records round-trip correctly through
append/load operations, and that pruning removes only records outside the
configured retention window.
"""

import tempfile
from datetime import date, timedelta
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from src.models import HistoryRecord
from src.recipe_history import RecipeHistoryStore


# --- Strategies ---

# Strategy for generating recipe name lists (1-30 recipe names per user)
recipe_names_st = st.lists(
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
        min_size=1,
        max_size=50,
    ),
    min_size=1,
    max_size=30,
)

# Strategy for user names
user_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L",)),
    min_size=1,
    max_size=20,
)

# Strategy for a users dict (1-4 users, each with recipe name lists)
users_dict_st = st.dictionaries(
    keys=user_name_st,
    values=recipe_names_st,
    min_size=1,
    max_size=4,
)


def date_within_window_st(retention_weeks: int = 4):
    """Generate dates within the retention window (today - retention_weeks..today)."""
    today = date.today()
    cutoff = today - timedelta(weeks=retention_weeks)
    return st.dates(min_value=cutoff, max_value=today)


def date_outside_window_st(retention_weeks: int = 4):
    """Generate dates strictly outside the retention window (older than cutoff)."""
    today = date.today()
    cutoff = today - timedelta(weeks=retention_weeks)
    # At least 1 day before cutoff, up to 365 days before
    oldest = cutoff - timedelta(days=365)
    return st.dates(min_value=oldest, max_value=cutoff - timedelta(days=1))


def history_record_st(date_strategy):
    """Generate a HistoryRecord with a date from the given strategy."""
    return st.builds(
        lambda d, u: HistoryRecord(generation_date=d.isoformat(), users=u),
        d=date_strategy,
        u=users_dict_st,
    )


# Feature: vegan-meal-planner, Property 14: History record round-trip and pruning
# Validates: Requirements 8.1, 8.2, 8.6


@settings(max_examples=100)
@given(
    records=st.lists(
        history_record_st(date_within_window_st()),
        min_size=1,
        max_size=10,
    )
)
def test_history_round_trip_within_window(records: list[HistoryRecord]) -> None:
    """For any sequence of history append operations with dates within the retention
    window, reading the history file SHALL return all appended records with correct
    generation dates and recipe name lists.

    **Validates: Requirements 8.1, 8.2**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        history_path = Path(tmp_dir) / "history.yaml"
        store = RecipeHistoryStore(history_path=history_path, retention_weeks=4)

        # Append all records
        for record in records:
            store.append_record(record)

        # Load and verify all records are present
        loaded = store.load_history()
        assert len(loaded) == len(records), (
            f"Expected {len(records)} records, got {len(loaded)}"
        )

        for original, loaded_record in zip(records, loaded):
            assert loaded_record.generation_date == original.generation_date, (
                f"Date mismatch: expected {original.generation_date}, "
                f"got {loaded_record.generation_date}"
            )
            assert loaded_record.users == original.users, (
                f"Users mismatch for date {original.generation_date}"
            )


@settings(max_examples=100)
@given(
    recent_records=st.lists(
        history_record_st(date_within_window_st()),
        min_size=0,
        max_size=5,
    ),
    old_records=st.lists(
        history_record_st(date_outside_window_st()),
        min_size=1,
        max_size=5,
    ),
)
def test_history_pruning_removes_old_records(
    recent_records: list[HistoryRecord], old_records: list[HistoryRecord]
) -> None:
    """After prune_old_records(), the history SHALL NOT contain records older than
    the retention window, and SHALL retain all records within the retention window.

    **Validates: Requirements 8.2, 8.6**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        history_path = Path(tmp_dir) / "history.yaml"
        store = RecipeHistoryStore(history_path=history_path, retention_weeks=4)

        # Append a mix of recent and old records
        all_records = old_records + recent_records
        for record in all_records:
            store.append_record(record)

        # Prune
        store.prune_old_records()

        # Load and verify only recent records remain
        loaded = store.load_history()
        today = date.today()
        cutoff = today - timedelta(weeks=4)

        for loaded_record in loaded:
            record_date = date.fromisoformat(loaded_record.generation_date)
            assert record_date >= cutoff, (
                f"Record with date {loaded_record.generation_date} should have been pruned "
                f"(cutoff: {cutoff.isoformat()})"
            )

        # All recent records should still be present
        assert len(loaded) == len(recent_records), (
            f"Expected {len(recent_records)} recent records after pruning, got {len(loaded)}"
        )


@settings(max_examples=100)
@given(
    recent_records=st.lists(
        history_record_st(date_within_window_st()),
        min_size=1,
        max_size=5,
    ),
    old_records=st.lists(
        history_record_st(date_outside_window_st()),
        min_size=1,
        max_size=5,
    ),
)
def test_get_excluded_recipes_only_from_retention_window(
    recent_records: list[HistoryRecord], old_records: list[HistoryRecord]
) -> None:
    """get_excluded_recipes() SHALL return only recipes from records within the
    retention window, not from older records.

    **Validates: Requirements 8.1, 8.2, 8.6**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        history_path = Path(tmp_dir) / "history.yaml"
        store = RecipeHistoryStore(history_path=history_path, retention_weeks=4)

        # Append a mix of recent and old records
        all_records = old_records + recent_records
        for record in all_records:
            store.append_record(record)

        # Get excluded recipes
        excluded = store.get_excluded_recipes()
        excluded_set = set(excluded)

        # Collect all recipe names from recent records only
        expected_names: set[str] = set()
        for record in recent_records:
            for user_recipes in record.users.values():
                expected_names.update(user_recipes)

        # Collect all recipe names from old records
        old_names: set[str] = set()
        for record in old_records:
            for user_recipes in record.users.values():
                old_names.update(user_recipes)

        # All expected recent recipe names should be in excluded
        for name in expected_names:
            assert name in excluded_set, (
                f"Recipe '{name}' from recent record should be in excluded list"
            )

        # Old recipe names that are NOT also in recent records should NOT be excluded
        old_only_names = old_names - expected_names
        for name in old_only_names:
            assert name not in excluded_set, (
                f"Recipe '{name}' from old record (outside retention window) "
                f"should NOT be in excluded list"
            )
