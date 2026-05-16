"""Recipe history tracking for the Vegan Meal Planner (YAML-based)."""

import logging
from datetime import date, timedelta
from pathlib import Path

import yaml

from src.models import HistoryRecord

logger = logging.getLogger(__name__)


class RecipeHistoryStore:
    """Manages the local YAML history file for tracking past meal plan recipes.

    The store persists generation records to a YAML file, supports configurable
    retention windows, and handles file I/O errors gracefully.

    Each record stores:
      - generation_date: ISO date string
      - users: mapping of user name to list of recipe names
      - email_sent: boolean indicating if email was delivered
      - email_sent_at: ISO timestamp or null
    """

    def __init__(self, history_path: Path, retention_weeks: int = 4) -> None:
        """Initialize the history store.

        Args:
            history_path: Path to the YAML history file.
            retention_weeks: Number of weeks to retain history records (default 4).
        """
        self.history_path = history_path
        self.retention_weeks = retention_weeks

    def load_history(self) -> list[HistoryRecord]:
        """Read the YAML history file and return a list of HistoryRecord objects.

        Handles missing, empty, or corrupt files gracefully by returning an empty list.

        Returns:
            List of HistoryRecord objects parsed from the history file.
        """
        try:
            if not self.history_path.exists():
                return []

            content = self.history_path.read_text(encoding="utf-8")
            if not content.strip():
                return []

            data = yaml.safe_load(content)
            if not isinstance(data, list):
                logger.warning("History file does not contain a YAML list, returning empty history.")
                return []

            records: list[HistoryRecord] = []
            for entry in data:
                if isinstance(entry, dict) and "generation_date" in entry and "users" in entry:
                    records.append(
                        HistoryRecord(
                            generation_date=str(entry["generation_date"]),
                            users=entry["users"],
                            email_sent=entry.get("email_sent", False),
                            email_sent_at=entry.get("email_sent_at"),
                        )
                    )
            return records

        except yaml.YAMLError as e:
            logger.warning("Failed to parse history file: %s. Returning empty history.", e)
            return []
        except (UnicodeDecodeError, OSError) as e:
            logger.warning("Failed to read history file: %s. Returning empty history.", e)
            return []

    def get_excluded_recipes(self) -> list[str]:
        """Return a flat deduplicated list of recipe names within the retention window.

        Loads history, filters records to those within the retention window
        (generation_date >= today - retention_weeks * 7 days), and collects
        all recipe names into a flat deduplicated list.

        Returns:
            List of unique recipe names from recent history.
        """
        records = self.load_history()
        cutoff = date.today() - timedelta(weeks=self.retention_weeks)

        recipe_names: set[str] = set()
        for record in records:
            try:
                record_date = date.fromisoformat(record.generation_date)
            except (ValueError, TypeError):
                continue

            if record_date >= cutoff:
                for user_recipes in record.users.values():
                    if isinstance(user_recipes, list):
                        recipe_names.update(user_recipes)

        return list(recipe_names)

    def append_record(self, record: HistoryRecord) -> None:
        """Add a new generation record to the history file.

        Loads the current history, appends the new record, and writes back to the file.

        Args:
            record: The HistoryRecord to append.
        """
        records = self.load_history()
        records.append(record)
        self._write_history(records)

    def prune_old_records(self) -> None:
        """Remove records older than the retention window.

        Loads history, filters out records with generation_date older than
        (today - retention_weeks * 7 days), and writes the pruned list back.
        """
        records = self.load_history()
        cutoff = date.today() - timedelta(weeks=self.retention_weeks)

        pruned: list[HistoryRecord] = []
        for record in records:
            try:
                record_date = date.fromisoformat(record.generation_date)
            except (ValueError, TypeError):
                # Keep records with unparseable dates (don't lose data)
                pruned.append(record)
                continue

            if record_date >= cutoff:
                pruned.append(record)

        self._write_history(pruned)

    def _write_history(self, records: list[HistoryRecord]) -> None:
        """Write the list of records back to the YAML file.

        Args:
            records: List of HistoryRecord objects to persist.
        """
        try:
            # Ensure parent directory exists
            self.history_path.parent.mkdir(parents=True, exist_ok=True)

            data = [
                {
                    "generation_date": record.generation_date,
                    "users": record.users,
                    "email_sent": record.email_sent,
                    "email_sent_at": record.email_sent_at,
                }
                for record in records
            ]
            self.history_path.write_text(
                yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning("Failed to write history file: %s. Continuing without persisting.", e)
