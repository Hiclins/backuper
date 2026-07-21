"""Grandfather-Father-Son retention over whole chains.

Because an incremental is useless without its full and the earlier incrementals
of the same chain, retention keeps or drops *entire chains* (never individual
artifacts). A chain's age is the time of its most recent backup.
"""

from __future__ import annotations

from datetime import datetime

from .catalog import Chain
from .config import RetentionConfig


def _keep_by_bucket(
    chains_newest_first: list[Chain], key, count: int, keep: set[str]
) -> None:
    """Keep the newest chain in each of the most recent `count` period buckets."""
    if count <= 0:
        return
    newest_per_bucket: dict[object, Chain] = {}
    for chain in chains_newest_first:  # newest first -> first seen wins
        bucket = key(chain.end_time)
        if bucket not in newest_per_bucket:
            newest_per_bucket[bucket] = chain
    for bucket in sorted(newest_per_bucket, reverse=True)[:count]:
        keep.add(newest_per_bucket[bucket].id)


def select_chains_to_drop(
    chains: list[Chain], policy: RetentionConfig
) -> tuple[list[Chain], set[str]]:
    """Return (chains_to_drop, kept_ids) according to the GFS policy."""
    if not chains:
        return [], set()

    newest_first = sorted(chains, key=lambda c: c.end_time, reverse=True)
    keep: set[str] = set()

    # Always keep the N most recent chains.
    for chain in newest_first[: max(policy.keep_last, 0)]:
        keep.add(chain.id)

    _keep_by_bucket(newest_first, lambda t: t.date(), policy.daily, keep)
    _keep_by_bucket(
        newest_first,
        lambda t: (t.isocalendar().year, t.isocalendar().week),
        policy.weekly,
        keep,
    )
    _keep_by_bucket(newest_first, lambda t: (t.year, t.month), policy.monthly, keep)
    _keep_by_bucket(newest_first, lambda t: t.year, policy.yearly, keep)

    drop = [c for c in chains if c.id not in keep]
    return drop, keep
