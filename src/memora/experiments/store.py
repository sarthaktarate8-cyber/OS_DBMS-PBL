"""Storage and persistence for experimental evaluation results."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Sequence

__all__ = ["ResultStore"]


class ResultStore:
    """Manages saving and loading benchmark experiment outputs."""

    def __init__(self, output_dir: str | Path = "results") -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def output_dir(self) -> Path:
        return self._dir

    def save_json(self, data: Any, filename: str) -> Path:
        """Save structured data to a JSON file."""
        target = self._dir / filename
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return target

    def load_json(self, filename: str) -> Any:
        """Load JSON data from results directory."""
        target = self._dir / filename
        if not target.exists():
            raise FileNotFoundError(f"Result file not found: {target}")
        with open(target, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_csv(self, rows: Sequence[dict[str, Any]], filename: str) -> Path:
        """Save a list of dictionaries as a CSV file."""
        target = self._dir / filename
        if not rows:
            return target

        fieldnames = list(rows[0].keys())
        with open(target, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        return target

    def load_csv(self, filename: str) -> list[dict[str, Any]]:
        """Load rows from a CSV file."""
        target = self._dir / filename
        if not target.exists():
            raise FileNotFoundError(f"Result file not found: {target}")
        with open(target, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
