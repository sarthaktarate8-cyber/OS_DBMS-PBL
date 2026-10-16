"""Unit tests for TraceLoader."""

import tempfile
from pathlib import Path

import pytest
from memora.core.types import AccessRecord, Operation
from memora.simulator.trace_loader import TraceFormat, TraceLoader


def test_trace_loader_from_int_list():
    loader = TraceLoader([1, 2, 3, 1, 4])
    records = loader.load()
    assert len(records) == 5
    assert [r.page_id for r in records] == [1, 2, 3, 1, 4]
    assert all(r.operation == Operation.READ for r in records)


def test_trace_loader_from_record_list():
    raw = [
        AccessRecord(page_id=10, timestamp=1, operation=Operation.WRITE),
        AccessRecord(page_id=20, timestamp=2, operation=Operation.READ),
    ]
    loader = TraceLoader(raw)
    records = loader.load()
    assert len(records) == 2
    assert records[0].page_id == 10
    assert records[0].operation == Operation.WRITE


def test_trace_loader_simple_file():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as f:
        f.write("1\n2\n# comment\n3\n\n4\n")
        tmp_path = f.name

    try:
        loader = TraceLoader(tmp_path, fmt=TraceFormat.SIMPLE)
        records = loader.load()
        assert len(records) == 4
        assert [r.page_id for r in records] == [1, 2, 3, 4]
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_trace_loader_structured_file():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv") as f:
        f.write("timestamp,page_id,operation,query_id\n")
        f.write("10,1,R,Q1\n")
        f.write("11,2,W,Q2\n")
        tmp_path = f.name

    try:
        loader = TraceLoader(tmp_path, fmt=TraceFormat.AUTO)
        records = loader.load()
        assert len(records) == 2
        assert records[0].page_id == 1
        assert records[0].operation == Operation.READ
        assert records[0].query_id == "Q1"
        assert records[1].page_id == 2
        assert records[1].operation == Operation.WRITE
        assert records[1].query_id == "Q2"

        summary = loader.get_summary()
        assert summary["total_records"] == 2
        assert summary["distinct_pages"] == 2
        assert summary["total_reads"] == 1
        assert summary["total_writes"] == 1
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_trace_loader_file_not_found():
    loader = TraceLoader("non_existent_path_xyz.txt")
    with pytest.raises(FileNotFoundError):
        loader.load()


def test_trace_loader_block_file_header():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv") as f:
        f.write("timestamp,lba,size,op,asu\n")
        f.write("1,1024,4096,R,ASU1\n")
        f.write("2,2048,4096,W,ASU1\n")
        tmp_path = f.name

    try:
        loader = TraceLoader(tmp_path, page_size_sectors=1)
        records = loader.load()
        assert len(records) == 2
        assert records[0].page_id == 1024
        assert records[0].operation == Operation.READ
        assert records[1].page_id == 2048
        assert records[1].operation == Operation.WRITE
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_trace_loader_block_raw_umass():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".trace") as f:
        # Standard UMass line: ASU, LBA, Size, Op, Timestamp
        f.write("0, 5000, 8, r, 0.01\n")
        f.write("0, 6000, 8, w, 0.02\n")
        tmp_path = f.name

    try:
        loader = TraceLoader(tmp_path, fmt=TraceFormat.BLOCK, page_size_sectors=1)
        records = loader.load()
        assert len(records) == 2
        assert records[0].page_id == 5000
        assert records[0].operation == Operation.READ
        assert records[1].page_id == 6000
        assert records[1].operation == Operation.WRITE
    finally:
        Path(tmp_path).unlink(missing_ok=True)
