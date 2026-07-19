"""GFS retention policy tests (retention.py) — pure logic, no I/O."""

from __future__ import annotations

from backuper.config import RetentionConfig
from backuper.retention import select_chains_to_drop
from helpers import make_chain, make_entry


def _policy(**kwargs) -> RetentionConfig:
    defaults = {"keep_last": 0, "daily": 0, "weekly": 0, "monthly": 0}
    defaults.update(kwargs)
    return RetentionConfig(**defaults)


def _single_chain(chain_id: str, end_time: str, created: str | None = None) -> "Chain":
    created = created or end_time
    return make_chain(chain_id, [make_entry(created, level=0), make_entry(end_time, level=1)])


def test_empty_chains_returns_nothing():
    drop, keep = select_chains_to_drop([], _policy(keep_last=3))
    assert drop == []
    assert keep == set()


def test_keep_last_only():
    chains = [
        _single_chain("c1", "2026-01-01T00:00:00"),
        _single_chain("c2", "2026-01-02T00:00:00"),
        _single_chain("c3", "2026-01-03T00:00:00"),
    ]
    drop, keep = select_chains_to_drop(chains, _policy(keep_last=2))
    assert {c.id for c in drop} == {"c1"}
    assert keep == {"c2", "c3"}


def test_keep_last_zero_disables_bucket():
    chains = [_single_chain("c1", "2026-01-01T00:00:00")]
    drop, keep = select_chains_to_drop(chains, _policy(keep_last=0))
    assert {c.id for c in drop} == {"c1"}
    assert keep == set()


def test_keep_last_negative_treated_as_zero():
    chains = [_single_chain("c1", "2026-01-01T00:00:00")]
    drop, keep = select_chains_to_drop(chains, _policy(keep_last=-5))
    assert {c.id for c in drop} == {"c1"}


def test_daily_bucket_keeps_newest_per_day():
    chains = [
        _single_chain("morning", "2026-01-01T08:00:00"),
        _single_chain("evening", "2026-01-01T20:00:00"),
        _single_chain("other-day", "2026-01-02T08:00:00"),
    ]
    drop, keep = select_chains_to_drop(chains, _policy(daily=2))
    # newest-per-day: 2026-01-02 -> other-day, 2026-01-01 -> evening (later)
    assert keep == {"other-day", "evening"}
    assert {c.id for c in drop} == {"morning"}


def test_weekly_bucket_iso_year_boundary():
    """Dec 29 2025 (a Monday) falls in ISO week 1 of 2026; Jan 5 2026 is in the
    same ISO week. A chain from late December in ISO-week-52-of-2025 must NOT
    be merged into that bucket."""
    chains = [
        _single_chain("late-dec", "2025-12-22T00:00:00"),  # ISO week 52, 2025
        _single_chain("new-year", "2026-01-05T00:00:00"),  # ISO week 2, 2026
    ]
    drop, keep = select_chains_to_drop(chains, _policy(weekly=2))
    assert keep == {"late-dec", "new-year"}
    assert drop == []


def test_monthly_bucket_year_boundary_not_merged():
    chains = [
        _single_chain("december", "2025-12-15T00:00:00"),
        _single_chain("january", "2026-01-15T00:00:00"),
    ]
    drop, keep = select_chains_to_drop(chains, _policy(monthly=2))
    assert keep == {"december", "january"}
    assert drop == []


def test_monthly_bucket_keeps_newest_in_same_month():
    chains = [
        _single_chain("early", "2026-01-05T00:00:00"),
        _single_chain("late", "2026-01-25T00:00:00"),
    ]
    drop, keep = select_chains_to_drop(chains, _policy(monthly=1))
    assert keep == {"late"}
    assert {c.id for c in drop} == {"early"}


def test_combined_policy_is_union_of_keeps():
    """A chain kept only by `daily` survives even though `keep_last` alone
    wouldn't have kept it."""
    chains = [
        _single_chain("c1", "2026-01-01T00:00:00"),
        _single_chain("c2", "2026-01-02T00:00:00"),
        _single_chain("c3", "2026-01-03T00:00:00"),
    ]
    # keep_last=1 alone would only keep c3; daily=3 keeps all three distinct days.
    drop, keep = select_chains_to_drop(chains, _policy(keep_last=1, daily=3))
    assert keep == {"c1", "c2", "c3"}
    assert drop == []


def test_ordering_driven_by_end_time_not_created():
    """A chain with an early `created` but late `end_time` (a long-running
    chain with many incrementals) is treated as "newest" by its end_time."""
    old_start_long_chain = make_chain(
        "long-chain",
        [make_entry("2026-01-01T00:00:00", level=0), make_entry("2026-01-31T00:00:00", level=5)],
    )
    fresh_full = _single_chain("fresh-full", "2026-01-15T00:00:00")
    drop, keep = select_chains_to_drop(
        [old_start_long_chain, fresh_full], _policy(keep_last=1)
    )
    # long-chain's end_time (01-31) is later than fresh-full's (01-15) -> kept
    assert keep == {"long-chain"}
    assert {c.id for c in drop} == {"fresh-full"}
