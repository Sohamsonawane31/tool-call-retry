"""``_iso`` must not raise on out-of-range journal timestamps.

Regression coverage for issue #34. ``datetime.fromtimestamp`` raises
``OverflowError`` (and on some platforms ``OSError``/``ValueError``) for
values outside the platform ``time_t`` range. A corrupted or hand-edited
journal row then made ``load_saga`` fail with a traceback instead of
returning the saga.
"""

from datetime import datetime, timezone

from tool_call_retry.journal import SagaJournal, _iso


def test_iso_falls_back_for_out_of_range_timestamp() -> None:
    result = _iso(10**20)
    # Must be a parseable UTC ISO timestamp (the "now" fallback).
    parsed = datetime.fromisoformat(result)
    assert parsed.tzinfo is not None
    assert abs((parsed - datetime.now(timezone.utc)).total_seconds()) < 5


def test_iso_falls_back_for_negative_out_of_range_timestamp() -> None:
    result = _iso(-(10**20))
    parsed = datetime.fromisoformat(result)
    assert parsed.tzinfo is not None


def test_iso_preserves_valid_timestamps() -> None:
    assert _iso(0)  # falsy → "now" path (existing behaviour)
    assert _iso(1_700_000_000.0) == datetime.fromtimestamp(
        1_700_000_000.0, tz=timezone.utc
    ).isoformat()


def test_load_saga_survives_corrupted_timestamps(tmp_path) -> None:
    path = tmp_path / "journal.db"
    journal = SagaJournal(str(path))
    saga_id = journal.begin_saga(idempotency_key="order-34", name="checkout")
    # Use floats that fit in SQLite REAL but are outside platform time_t.
    journal._conn.execute(
        "UPDATE sagas SET created_at = ?, updated_at = ? WHERE id = ?",
        (1e20, -1e20, saga_id),
    )
    journal._conn.commit()

    run = journal.load_saga(saga_id)
    assert run.saga_id == saga_id
    datetime.fromisoformat(run.created_at)
    datetime.fromisoformat(run.updated_at)
