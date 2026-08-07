"""Candidate payment-vector generators, one per shape.

Every generator produces payment vectors of length ``k`` summing exactly to
``total`` (constraint 2), for the front-loading objective: keep early payments
as low as the rules allow and defer weight to later payments. They are
deliberately *structured* generators (not exhaustive search) — each is small
enough to reason about, and every candidate is re-checked by
``constraints.is_valid_payment_vector`` and the ledger simulation before it is
ever selected, so an over-eager generator can only under-produce, never
produce something wrongly accepted.

``SHAPE_GENERATORS`` maps a shape name to its generator function; the
orchestration in ``engine.py`` decides which shapes apply from the creditor
flags and in what order to try them.
"""

from __future__ import annotations

from collections.abc import Iterator

from feasibility.constraints import block_floor, position_floor
from feasibility.models import CreditorRules


def even_candidates(total: int, k: int, rules: CreditorRules) -> list[list[int]]:
    """All payments equal; remainder cents pushed onto the *latest* payments so
    the sequence stays non-decreasing."""
    quotient, remainder = divmod(total, k)
    vector = [quotient] * (k - remainder) + [quotient + 1] * remainder
    return [vector]


def balloon_candidates(total: int, k: int, rules: CreditorRules) -> list[list[int]]:
    """Every payment but the last pinned at its floor; the last absorbs the
    remainder. Only emitted when it is a genuine balloon (last strictly
    exceeds the payment before it) — otherwise it degenerates into a flat or
    near-flat vector that the staircase generator already covers."""
    if k < 2:
        return []
    leading = [position_floor(i + 1, rules) for i in range(k - 1)]
    last = total - sum(leading)
    if last <= leading[-1]:
        return []
    return [leading + [last]]


def _segment_sizes(k: int, num_segments: int) -> Iterator[list[int]]:
    """Every composition of ``k`` into ``num_segments`` positive parts, in the
    order the front-most segments are tried smallest-first (irrelevant to
    correctness, just keeps the search stable)."""

    def rec(remaining: int, parts_left: int) -> Iterator[list[int]]:
        if parts_left == 1:
            if remaining >= 1:
                yield [remaining]
            return
        for size in range(1, remaining - (parts_left - 1) + 1):
            for rest in rec(remaining - size, parts_left - 1):
                yield [size] + rest

    yield from rec(k, num_segments)


def _fill_partition(total: int, sizes: list[int], rules: CreditorRules) -> list[int] | None:
    """For one choice of segment sizes, find levels for each segment such
    that: each segment is a single constant payment level, levels are
    non-decreasing, every segment clears its own floor, and the levels sum
    exactly to ``total``.

    All segments but the second-to-last are pinned at their own floor (the
    lowest the front-loading objective would ever want). Segment floors are
    non-decreasing in position (tiers only step up), so pinned segments are
    automatically non-decreasing. The second-to-last segment is then the only
    free variable, searched upward from its floor within one period of the
    final segment's size — enough to guarantee a value dividing the remainder
    evenly if one exists in that window, exactly as a single free variable in
    a two-term integer equation only needs one full period of search. The
    final segment absorbs whatever remains.
    """
    starts = [1]
    for size in sizes[:-1]:
        starts.append(starts[-1] + size)
    ends = [s + sz - 1 for s, sz in zip(starts, sizes)]
    floors = [block_floor(s, e, rules) for s, e in zip(starts, ends)]

    if len(sizes) == 1:
        if total % sizes[0] != 0:
            return None
        level = total // sizes[0]
        return [level] * sizes[0] if level >= floors[0] else None

    pinned_levels = floors[:-2]  # segments before the flexible one, at their floor
    flex_floor = max(floors[-2], pinned_levels[-1] if pinned_levels else 0)
    pinned_sum = sum(lvl * sz for lvl, sz in zip(pinned_levels, sizes[:-2]))
    last_size = sizes[-1]

    for delta in range(last_size):
        flex_level = flex_floor + delta
        used = pinned_sum + flex_level * sizes[-2]
        remaining = total - used
        if remaining <= 0 or remaining % last_size != 0:
            continue
        last_level = remaining // last_size
        if last_level < flex_level or last_level < floors[-1]:
            continue
        levels = pinned_levels + [flex_level, last_level]
        vector: list[int] = []
        for lvl, sz in zip(levels, sizes):
            vector.extend([lvl] * sz)
        return vector
    return None


def staircase_candidates(total: int, k: int, rules: CreditorRules) -> list[list[int]]:
    """Non-decreasing vectors using at most ``rules.max_segments`` distinct
    payment levels, front-loading weight toward the later segments."""
    candidates: list[list[int]] = []

    flat = _fill_partition(total, [k], rules)
    if flat is not None:
        candidates.append(flat)

    max_segments = max(1, min(rules.max_segments, k))
    for num_segments in range(2, max_segments + 1):
        for sizes in _segment_sizes(k, num_segments):
            vector = _fill_partition(total, sizes, rules)
            if vector is not None:
                candidates.append(vector)
    return candidates


SHAPE_GENERATORS = {
    "even": even_candidates,
    "balloon": balloon_candidates,
    "staircase": staircase_candidates,
}
