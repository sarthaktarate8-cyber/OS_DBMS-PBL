"""Trace loader for MEMORA.

Supports two trace formats:
1. Simple format (one page ID per line)::
       1
       2
       3
       1
       4

2. Structured CSV format (header required)::
       timestamp,page_id,operation,query_id
       100,1,R,Q1
       101,2,R,Q1
       102,4,W,Q2

   Columns:
       - timestamp (int, optional, defaults to sequential counter)
       - page_id (int, required)
       - operation (R|W, optional, default=R)
       - query_id (str, optional)
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Iterator, Sequence, Union

from memora.core.types import AccessRecord, Operation

__all__ = ["TraceLoader", "TraceFormat"]

logger = logging.getLogger(__name__)


class TraceFormat:
    """Trace format identifiers."""
    SIMPLE = "simple"
    STRUCTURED = "structured"
    BLOCK = "block"
    AUTO = "auto"


class TraceLoader:
    """Loads page access traces from disk or memory."""

    def __init__(
        self,
        source: Union[str, Path, Sequence[Union[AccessRecord, int]]],
        fmt: str = TraceFormat.AUTO,
        page_size_sectors: int = 1,
    ) -> None:
        """Initialize the trace loader.

        Args:
            source: File path (str or Path) or sequence of AccessRecord/ints.
            fmt: Trace format ('simple', 'structured', 'block', 'auto').
            page_size_sectors: Divisor to map storage LBA to logical page IDs.
        """
        self._source = source
        self._fmt = fmt
        self._page_size_sectors = max(1, page_size_sectors)
        self._records: list[AccessRecord] = []
        self._parse_errors: list[str] = []
        self._loaded: bool = False

    @property
    def is_loaded(self) -> bool:
        """True if records have already been parsed into memory."""
        return self._loaded

    @property
    def parse_errors(self) -> list[str]:
        """List of warning messages encountered during parsing."""
        return list(self._parse_errors)

    def load(self) -> list[AccessRecord]:
        """Parse the source and return list of AccessRecord objects."""
        if self._loaded:
            return self._records

        if isinstance(self._source, (str, Path)):
            path = Path(self._source)
            if not path.exists():
                raise FileNotFoundError(f"Trace file not found: {path}")
            self._load_from_file(path)
        elif isinstance(self._source, Sequence):
            self._load_from_sequence(self._source)
        else:
            raise TypeError(f"Unsupported trace source type: {type(self._source)}")

        if not self._records:
            raise ValueError(f"Trace source yielded 0 valid access records: {self._source}")

        self._loaded = True
        return self._records

    def _load_from_sequence(self, seq: Sequence[Union[AccessRecord, int]]) -> None:
        """Parse an in-memory list of records or page ID integers."""
        for idx, item in enumerate(seq, start=1):
            if isinstance(item, AccessRecord):
                self._records.append(item)
            elif isinstance(item, int):
                self._records.append(
                    AccessRecord(page_id=item, timestamp=idx, operation=Operation.READ)
                )
            else:
                self._parse_errors.append(f"Item #{idx}: unexpected item type {type(item)}")

    def _load_from_file(self, path: Path) -> None:
        """Parse trace file based on format."""
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        if not lines:
            return

        fmt = self._fmt
        if fmt == TraceFormat.AUTO:
            first_line = lines[0].lower()
            if any(k in first_line for k in ("lba", "asu", "blk")):
                fmt = TraceFormat.BLOCK
            elif "," in first_line or any(c.isalpha() for c in first_line):
                fmt = TraceFormat.STRUCTURED
            else:
                fmt = TraceFormat.SIMPLE

        if fmt == TraceFormat.BLOCK:
            self._parse_block(lines)
        elif fmt == TraceFormat.STRUCTURED:
            self._parse_structured(lines)
        else:
            self._parse_simple(lines)

    def _parse_block(self, lines: list[str]) -> None:
        """Parse block-level trace (e.g., UMass, SPC, or block traces)."""
        first = lines[0].lower()
        if any(h in first for h in ("lba", "blk", "block", "asu")):
            reader = csv.DictReader(lines)
            for row_num, row in enumerate(reader, start=2):
                try:
                    lba_val = None
                    for k in ("lba", "blk", "block", "page_id"):
                        if k in row and row[k]:
                            lba_val = int(row[k])
                            break
                    if lba_val is None:
                        continue

                    page_id = lba_val // self._page_size_sectors
                    op_val = row.get("op", row.get("operation", "r")).strip().lower()
                    op = Operation.WRITE if op_val in ("w", "write", "1") else Operation.READ
                    ts_str = row.get("timestamp", row.get("ts"))
                    ts = int(float(ts_str)) if ts_str is not None else row_num
                    qid = row.get("asu", row.get("query_id"))

                    self._records.append(
                        AccessRecord(page_id=page_id, timestamp=ts, operation=op, query_id=str(qid) if qid else None)
                    )
                except Exception as e:
                    self._parse_errors.append(f"Line {row_num}: {e}")
        else:
            for line_num, line in enumerate(lines, start=1):
                try:
                    parts = [p.strip() for p in line.replace(",", " ").split() if p.strip()]
                    if not parts:
                        continue
                    if len(parts) >= 4 and parts[3].lower() in ("r", "w", "0", "1"):
                        lba = int(parts[1])
                        op_str = parts[3].lower()
                        op = Operation.WRITE if op_str in ("w", "1") else Operation.READ
                        ts = int(float(parts[4])) if len(parts) >= 5 else line_num
                        qid = f"ASU_{parts[0]}"
                    elif len(parts) >= 2 and parts[1].lower() in ("r", "w", "0", "1"):
                        lba = int(parts[0])
                        op = Operation.WRITE if parts[1].lower() in ("w", "1") else Operation.READ
                        ts = line_num
                        qid = None
                    else:
                        lba = int(parts[0])
                        op = Operation.READ
                        ts = line_num
                        qid = None

                    page_id = lba // self._page_size_sectors
                    self._records.append(
                        AccessRecord(page_id=page_id, timestamp=ts, operation=op, query_id=qid)
                    )
                except Exception as e:
                    self._parse_errors.append(f"Line {line_num}: {e}")

    def _parse_simple(self, lines: list[str]) -> None:
        """Parse single integer per line."""
        for line_num, line in enumerate(lines, start=1):
            try:
                page_id = int(line)
                self._records.append(
                    AccessRecord(page_id=page_id, timestamp=line_num, operation=Operation.READ)
                )
            except ValueError:
                self._parse_errors.append(f"Line {line_num}: invalid integer '{line}'")

    def _parse_structured(self, lines: list[str]) -> None:
        """Parse CSV structured trace."""
        reader = csv.DictReader(lines)
        for row_num, row in enumerate(reader, start=2):
            try:
                page_id_str = row.get("page_id")
                if page_id_str is None:
                    continue
                page_id = int(page_id_str)

                ts_str = row.get("timestamp")
                ts = int(ts_str) if ts_str is not None else row_num

                op_str = row.get("operation", "R").strip().upper()
                op = Operation.WRITE if op_str == "W" else Operation.READ
                qid = row.get("query_id")

                self._records.append(
                    AccessRecord(page_id=page_id, timestamp=ts, operation=op, query_id=qid)
                )
            except Exception as e:
                self._parse_errors.append(f"Line {row_num}: {e}")

    def __iter__(self) -> Iterator[AccessRecord]:
        return iter(self.load())

    def __len__(self) -> int:
        return len(self.load())

    def get_summary(self) -> dict:
        """Return high-level statistics of the loaded trace."""
        records = self.load()
        pages = {r.page_id for r in records}
        writes = sum(1 for r in records if r.operation == Operation.WRITE)
        return {
            "total_records": len(records),
            "distinct_pages": len(pages),
            "total_reads": len(records) - writes,
            "total_writes": writes,
            "min_page_id": min(pages) if pages else 0,
            "max_page_id": max(pages) if pages else 0,
        }
