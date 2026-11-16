"""
Boundary extraction, adjacent-label comparison, and one-to-one boundary
matching for two adjudicator source timelines.
"""

from __future__ import annotations

from time import perf_counter
from typing import Optional

import numpy as np

from .config import (
    ADJUDICATION_BOUNDARY_TOLERANCE_SEC,
    ANNOTATOR_ALIASES,
    DisagreementReason,
)
from .exceptions import (
    AdjudicationError,
    InvalidAnnotationError,
)
from .models import (
    AnnotationInterval,
    BoundaryMatch,
    TimelineBoundary,
)
from .utilities import (
    _perf_log,
    clean_string,
    stable_numbered_id,
)

# =============================================================================
# Boundary extraction and matching
# =============================================================================

VALID_BOUNDARY_TYPES: frozenset[str] = frozenset(
    {
        "start",
        "internal",
        "end",
    }
)


def append_unique_reason(
    reasons: list[str],
    reason: str | DisagreementReason,
) -> None:
    """
    Add one disagreement reason without introducing duplicates.

    Parameters
    ----------
    reasons : list[str]
        Mutable reason list.

    reason : str or DisagreementReason
        Reason value to append.

    Notes
    -----
    Reason order is retained so output remains deterministic and easy to
    inspect.
    """
    reason_value = (
        reason.value
        if isinstance(reason, DisagreementReason)
        else clean_string(reason)
    )

    if reason_value and reason_value not in reasons:
        reasons.append(reason_value)


def interval_labels_equal(
    interval_a: Optional[AnnotationInterval],
    interval_b: Optional[AnnotationInterval],
) -> bool:
    """
    Compare CPR and rhythm labels for two adjacent intervals.

    Parameters
    ----------
    interval_a, interval_b : AnnotationInterval or None
        Adjacent intervals from Annotator A and Annotator B.

    Returns
    -------
    bool
        True when both intervals are absent or both contain matching CPR and
        rhythm labels.

    Notes
    -----
    Explanations are not used for agreement classification. They remain
    available for reviewer context.
    """
    if interval_a is None and interval_b is None:
        return True

    if interval_a is None or interval_b is None:
        return False

    return (
        clean_string(interval_a.cpr)
        == clean_string(interval_b.cpr)
        and clean_string(interval_a.rhythm_label)
        == clean_string(interval_b.rhythm_label)
    )


def get_interval_label_mismatch_reasons(
    interval_a: Optional[AnnotationInterval],
    interval_b: Optional[AnnotationInterval],
) -> list[str]:
    """
    Return CPR/rhythm disagreement reasons for two adjacent intervals.

    Parameters
    ----------
    interval_a, interval_b : AnnotationInterval or None
        Intervals being compared.

    Returns
    -------
    list[str]
        Unique machine-readable disagreement reasons.
    """
    reasons: list[str] = []

    if interval_a is None and interval_b is None:
        return reasons

    if interval_a is None:
        append_unique_reason(
            reasons,
            DisagreementReason.ANNOTATOR_B_ONLY,
        )
        append_unique_reason(
            reasons,
            DisagreementReason.MISSING_COVERAGE,
        )
        return reasons

    if interval_b is None:
        append_unique_reason(
            reasons,
            DisagreementReason.ANNOTATOR_A_ONLY,
        )
        append_unique_reason(
            reasons,
            DisagreementReason.MISSING_COVERAGE,
        )
        return reasons

    if (
        clean_string(interval_a.cpr)
        != clean_string(interval_b.cpr)
    ):
        append_unique_reason(
            reasons,
            DisagreementReason.CPR_MISMATCH,
        )

    if (
        clean_string(interval_a.rhythm_label)
        != clean_string(interval_b.rhythm_label)
    ):
        append_unique_reason(
            reasons,
            DisagreementReason.RHYTHM_MISMATCH,
        )

    return reasons


def compare_adjacent_boundary_labels(
    boundary_a: TimelineBoundary,
    boundary_b: TimelineBoundary,
) -> tuple[bool, list[str]]:
    """
    Compare labels immediately before and after two candidate boundaries.

    Parameters
    ----------
    boundary_a, boundary_b : TimelineBoundary
        Candidate source boundaries.

    Returns
    -------
    tuple[bool, list[str]]
        ``(compatible, reasons)``.

    Notes
    -----
    A boundary is label-compatible only when all applicable CPR and rhythm
    labels agree on both sides.

    For start boundaries, only the interval after the boundary is applicable.

    For end boundaries, only the interval before the boundary is applicable.
    """
    reasons: list[str] = []

    if boundary_a.boundary_type != boundary_b.boundary_type:
        append_unique_reason(
            reasons,
            DisagreementReason.ADJACENT_LABEL_MISMATCH,
        )
        return False, reasons

    before_reasons = get_interval_label_mismatch_reasons(
        boundary_a.interval_before,
        boundary_b.interval_before,
    )

    after_reasons = get_interval_label_mismatch_reasons(
        boundary_a.interval_after,
        boundary_b.interval_after,
    )

    for reason in before_reasons + after_reasons:
        append_unique_reason(
            reasons,
            reason,
        )

    compatible = (
        interval_labels_equal(
            boundary_a.interval_before,
            boundary_b.interval_before,
        )
        and interval_labels_equal(
            boundary_a.interval_after,
            boundary_b.interval_after,
        )
    )

    if not compatible:
        append_unique_reason(
            reasons,
            DisagreementReason.ADJACENT_LABEL_MISMATCH,
        )

    return compatible, reasons


def extract_timeline_boundaries(
    intervals: list[AnnotationInterval],
    source_alias: str,
) -> list[TimelineBoundary]:
    """
    Extract ordered source boundaries with timing and error diagnostics.

    Parameters
    ----------
    intervals : list[AnnotationInterval]
        Validated chronological source intervals.

    source_alias : str
        Reviewer-facing alias for the source timeline.

    Returns
    -------
    list[TimelineBoundary]
        Start, internal, and end boundaries in chronological order.

    Raises
    ------
    InvalidAnnotationError
        If no intervals exist or a boundary cannot be represented.
    """
    start_time = perf_counter()
    boundaries: list[TimelineBoundary] = []

    try:
        boundaries = _extract_timeline_boundaries_impl(
            intervals=intervals,
            source_alias=source_alias,
        )

        return boundaries

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "extract_timeline_boundaries failed:",
            f"source_alias={source_alias}",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "extract_timeline_boundaries",
            perf_counter() - start_time,
            source_alias=source_alias,
            intervals=len(intervals),
            boundaries=len(boundaries),
        )


def _extract_timeline_boundaries_impl(
    intervals: list[AnnotationInterval],
    source_alias: str,
) -> list[TimelineBoundary]:
    """
    Extract source boundaries without timing or UI behavior.
    """
    if not intervals:
        raise InvalidAnnotationError(
            f"{source_alias} contains no intervals for boundary extraction."
        )

    boundaries: list[TimelineBoundary] = []

    # The first boundary has no interval before it.
    boundaries.append(
        TimelineBoundary(
            boundary_id=stable_numbered_id(
                f"{source_alias.replace(' ', '_').lower()}_boundary",
                0,
            ),
            source_alias=source_alias,
            boundary_index=0,
            boundary_type="start",
            time=float(intervals[0].start),
            interval_before=None,
            interval_after=intervals[0],
        )
    )

    # Each internal boundary sits between two sequential annotation intervals.
    for interval_index in range(
        1,
        len(intervals),
    ):
        interval_before = intervals[
            interval_index - 1
        ]
        interval_after = intervals[
            interval_index
        ]

        # Source validation permits only tiny numerical continuity differences.
        # Averaging the two source-side values creates one stable representation
        # without rounding away waveform precision.
        internal_boundary_time = (
            float(interval_before.end)
            + float(interval_after.start)
        ) / 2.0

        boundaries.append(
            TimelineBoundary(
                boundary_id=stable_numbered_id(
                    (
                        f"{source_alias.replace(' ', '_').lower()}"
                        "_boundary"
                    ),
                    interval_index,
                ),
                source_alias=source_alias,
                boundary_index=interval_index,
                boundary_type="internal",
                time=internal_boundary_time,
                interval_before=interval_before,
                interval_after=interval_after,
            )
        )

    # The final boundary has no interval after it.
    final_boundary_index = len(intervals)

    boundaries.append(
        TimelineBoundary(
            boundary_id=stable_numbered_id(
                f"{source_alias.replace(' ', '_').lower()}_boundary",
                final_boundary_index,
            ),
            source_alias=source_alias,
            boundary_index=final_boundary_index,
            boundary_type="end",
            time=float(intervals[-1].end),
            interval_before=intervals[-1],
            interval_after=None,
        )
    )

    for boundary in boundaries:
        if boundary.boundary_type not in VALID_BOUNDARY_TYPES:
            raise InvalidAnnotationError(
                f"Unsupported boundary type: {boundary.boundary_type!r}"
            )

        if not np.isfinite(boundary.time):
            raise InvalidAnnotationError(
                f"Boundary {boundary.boundary_id} has a non-finite time."
            )

    return boundaries


def boundaries_can_match(
    boundary_a: TimelineBoundary,
    boundary_b: TimelineBoundary,
    tolerance_sec: float,
) -> tuple[bool, float, bool, list[str]]:
    """
    Evaluate whether two candidate boundaries may be reconciled.

    Parameters
    ----------
    boundary_a, boundary_b : TimelineBoundary
        Candidate source boundaries.

    tolerance_sec : float
        Maximum permitted absolute time difference.

    Returns
    -------
    tuple
        ``(
            can_match,
            difference_seconds,
            labels_compatible,
            reasons
        )``.
    """
    difference_seconds = abs(
        float(boundary_a.time)
        - float(boundary_b.time)
    )

    within_tolerance = (
        difference_seconds <= tolerance_sec
    )

    labels_compatible, reasons = (
        compare_adjacent_boundary_labels(
            boundary_a,
            boundary_b,
        )
    )

    if not within_tolerance:
        append_unique_reason(
            reasons,
            DisagreementReason.BOUNDARY_OUTSIDE_TOLERANCE,
        )

    can_match = (
        boundary_a.boundary_type
        == boundary_b.boundary_type
        and within_tolerance
        and labels_compatible
    )

    return (
        can_match,
        float(difference_seconds),
        labels_compatible,
        reasons,
    )


def _candidate_score_is_better(
    candidate_matches: int,
    candidate_cost: float,
    candidate_priority: int,
    current_matches: int,
    current_cost: float,
    current_priority: int,
) -> bool:
    """
    Compare two dynamic-programming boundary alignment candidates.

    Higher match count is preferred. For equal counts, lower total boundary
    distance is preferred. Priority resolves otherwise identical candidates.
    """
    if candidate_matches != current_matches:
        return candidate_matches > current_matches

    if not np.isclose(
        candidate_cost,
        current_cost,
        rtol=0.0,
        atol=1e-12,
    ):
        return candidate_cost < current_cost

    return candidate_priority > current_priority


def _find_optimal_boundary_pairs(
    boundaries_a: list[TimelineBoundary],
    boundaries_b: list[TimelineBoundary],
    tolerance_sec: float,
) -> list[tuple[int, int]]:
    """
    Find ordered one-to-one compatible boundary matches.

    Dynamic programming maximizes the number of accepted matches and then
    minimizes total boundary offset. This avoids unstable nearest-neighbor
    pairings when one annotator has an extra boundary.
    """
    count_a = len(boundaries_a)
    count_b = len(boundaries_b)

    match_counts = np.zeros(
        (count_a + 1, count_b + 1),
        dtype=int,
    )

    total_costs = np.zeros(
        (count_a + 1, count_b + 1),
        dtype=float,
    )

    actions: list[list[str]] = [
        [""] * (count_b + 1)
        for _ in range(count_a + 1)
    ]

    for index_a in range(1, count_a + 1):
        actions[index_a][0] = "skip_a"

    for index_b in range(1, count_b + 1):
        actions[0][index_b] = "skip_b"

    for index_a in range(1, count_a + 1):
        for index_b in range(1, count_b + 1):
            # Begin with skipping the current A boundary.
            best_matches = int(
                match_counts[index_a - 1, index_b]
            )
            best_cost = float(
                total_costs[index_a - 1, index_b]
            )
            best_action = "skip_a"
            best_priority = 1

            # Consider skipping the current B boundary.
            candidate_matches = int(
                match_counts[index_a, index_b - 1]
            )
            candidate_cost = float(
                total_costs[index_a, index_b - 1]
            )

            if _candidate_score_is_better(
                candidate_matches,
                candidate_cost,
                0,
                best_matches,
                best_cost,
                best_priority,
            ):
                best_matches = candidate_matches
                best_cost = candidate_cost
                best_action = "skip_b"
                best_priority = 0

            # Consider accepting a compatible ordered match.
            (
                can_match,
                difference_seconds,
                _labels_compatible,
                _reasons,
            ) = boundaries_can_match(
                boundaries_a[index_a - 1],
                boundaries_b[index_b - 1],
                tolerance_sec,
            )

            if can_match:
                candidate_matches = (
                    int(
                        match_counts[
                            index_a - 1,
                            index_b - 1,
                        ]
                    )
                    + 1
                )

                candidate_cost = (
                    float(
                        total_costs[
                            index_a - 1,
                            index_b - 1,
                        ]
                    )
                    + difference_seconds
                )

                if _candidate_score_is_better(
                    candidate_matches,
                    candidate_cost,
                    2,
                    best_matches,
                    best_cost,
                    best_priority,
                ):
                    best_matches = candidate_matches
                    best_cost = candidate_cost
                    best_action = "match"
                    best_priority = 2

            match_counts[index_a, index_b] = (
                best_matches
            )
            total_costs[index_a, index_b] = (
                best_cost
            )
            actions[index_a][index_b] = (
                best_action
            )

    # Reconstruct ordered accepted pairs.
    matched_pairs: list[tuple[int, int]] = []

    index_a = count_a
    index_b = count_b

    while index_a > 0 or index_b > 0:
        action = actions[index_a][index_b]

        if action == "match":
            matched_pairs.append(
                (
                    index_a - 1,
                    index_b - 1,
                )
            )
            index_a -= 1
            index_b -= 1

        elif action == "skip_a":
            index_a -= 1

        elif action == "skip_b":
            index_b -= 1

        else:
            break

    matched_pairs.reverse()

    return matched_pairs


def _get_nearest_boundary(
    boundary: TimelineBoundary,
    opposite_boundaries: list[TimelineBoundary],
) -> tuple[
    Optional[TimelineBoundary],
    Optional[float],
]:
    """
    Return the nearest opposite-source boundary of the same type.
    """
    compatible_type_candidates = [
        candidate
        for candidate in opposite_boundaries
        if (
            candidate.boundary_type
            == boundary.boundary_type
        )
    ]

    if not compatible_type_candidates:
        return None, None

    nearest = min(
        compatible_type_candidates,
        key=lambda candidate: abs(
            float(candidate.time)
            - float(boundary.time)
        ),
    )

    difference = abs(
        float(nearest.time)
        - float(boundary.time)
    )

    return nearest, float(difference)


def match_timeline_boundaries(
    boundaries_a: list[TimelineBoundary],
    boundaries_b: list[TimelineBoundary],
    *,
    tolerance_sec: float = ADJUDICATION_BOUNDARY_TOLERANCE_SEC,
) -> list[BoundaryMatch]:
    """
    Match Annotator A and B boundaries with timing and diagnostics.

    Parameters
    ----------
    boundaries_a, boundaries_b : list[TimelineBoundary]
        Ordered source boundary lists.

    tolerance_sec : float
        Maximum accepted A/B boundary difference.

    Returns
    -------
    list[BoundaryMatch]
        Accepted matches and unmatched source boundaries.

    Raises
    ------
    ValueError
        If tolerance is invalid.

    InvalidAnnotationError
        If either boundary list is empty.
    """
    start_time = perf_counter()
    matches: list[BoundaryMatch] = []

    try:
        matches = _match_timeline_boundaries_impl(
            boundaries_a=boundaries_a,
            boundaries_b=boundaries_b,
            tolerance_sec=tolerance_sec,
        )

        return matches

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "match_timeline_boundaries failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "match_timeline_boundaries",
            perf_counter() - start_time,
            boundaries_a=len(boundaries_a),
            boundaries_b=len(boundaries_b),
            results=len(matches),
            matched=sum(
                result.matched
                for result in matches
            ),
            tolerance_sec=tolerance_sec,
        )


def _match_timeline_boundaries_impl(
    boundaries_a: list[TimelineBoundary],
    boundaries_b: list[TimelineBoundary],
    *,
    tolerance_sec: float,
) -> list[BoundaryMatch]:
    """
    Match source boundaries without timing or UI behavior.
    """
    if not boundaries_a or not boundaries_b:
        raise InvalidAnnotationError(
            "Both source timelines require boundaries for comparison."
        )

    if (
        not np.isfinite(tolerance_sec)
        or tolerance_sec < 0
    ):
        raise ValueError(
            "tolerance_sec must be finite and nonnegative."
        )

    accepted_pairs = _find_optimal_boundary_pairs(
        boundaries_a=boundaries_a,
        boundaries_b=boundaries_b,
        tolerance_sec=tolerance_sec,
    )

    accepted_a_indices = {
        index_a
        for index_a, _index_b in accepted_pairs
    }

    accepted_b_indices = {
        index_b
        for _index_a, index_b in accepted_pairs
    }

    results: list[BoundaryMatch] = []
    result_index = 1

    # Add accepted midpoint-reconciled boundary matches.
    for index_a, index_b in accepted_pairs:
        boundary_a = boundaries_a[index_a]
        boundary_b = boundaries_b[index_b]

        (
            can_match,
            difference_seconds,
            labels_compatible,
            reasons,
        ) = boundaries_can_match(
            boundary_a,
            boundary_b,
            tolerance_sec,
        )

        if not can_match:
            raise AdjudicationError(
                "Dynamic boundary alignment returned an incompatible match."
            )

        midpoint = (
            float(boundary_a.time)
            + float(boundary_b.time)
        ) / 2.0

        results.append(
            BoundaryMatch(
                boundary_id=stable_numbered_id(
                    "boundary_match",
                    result_index,
                ),
                boundary_type=boundary_a.boundary_type,
                boundary_index_a=(
                    boundary_a.boundary_index
                ),
                boundary_index_b=(
                    boundary_b.boundary_index
                ),
                boundary_a=float(boundary_a.time),
                boundary_b=float(boundary_b.time),
                difference_seconds=(
                    difference_seconds
                ),
                midpoint=float(midpoint),
                within_tolerance=True,
                adjacent_labels_compatible=(
                    labels_compatible
                ),
                matched=True,
                reasons=reasons,
            )
        )

        result_index += 1

    # Retain unmatched Annotator A boundaries for disagreement generation.
    for index_a, boundary_a in enumerate(
        boundaries_a
    ):
        if index_a in accepted_a_indices:
            continue

        nearest_b, nearest_difference = (
            _get_nearest_boundary(
                boundary_a,
                boundaries_b,
            )
        )

        reasons: list[str] = []

        append_unique_reason(
            reasons,
            DisagreementReason.ANNOTATOR_A_ONLY,
        )

        labels_compatible = False
        within_tolerance = False

        if nearest_b is not None:
            within_tolerance = bool(
                nearest_difference is not None
                and nearest_difference
                <= tolerance_sec
            )

            (
                labels_compatible,
                label_reasons,
            ) = compare_adjacent_boundary_labels(
                boundary_a,
                nearest_b,
            )

            for reason in label_reasons:
                append_unique_reason(
                    reasons,
                    reason,
                )

        if not within_tolerance:
            append_unique_reason(
                reasons,
                DisagreementReason.BOUNDARY_OUTSIDE_TOLERANCE,
            )

        results.append(
            BoundaryMatch(
                boundary_id=stable_numbered_id(
                    "boundary_match",
                    result_index,
                ),
                boundary_type=boundary_a.boundary_type,
                boundary_index_a=(
                    boundary_a.boundary_index
                ),
                boundary_index_b=None,
                boundary_a=float(boundary_a.time),
                boundary_b=None,
                difference_seconds=None,
                midpoint=None,
                within_tolerance=within_tolerance,
                adjacent_labels_compatible=(
                    labels_compatible
                ),
                matched=False,
                nearest_other_boundary=(
                    float(nearest_b.time)
                    if nearest_b is not None
                    else None
                ),
                nearest_difference_seconds=(
                    nearest_difference
                ),
                reasons=reasons,
            )
        )

        result_index += 1

    # Retain unmatched Annotator B boundaries for disagreement generation.
    for index_b, boundary_b in enumerate(
        boundaries_b
    ):
        if index_b in accepted_b_indices:
            continue

        nearest_a, nearest_difference = (
            _get_nearest_boundary(
                boundary_b,
                boundaries_a,
            )
        )

        reasons = []

        append_unique_reason(
            reasons,
            DisagreementReason.ANNOTATOR_B_ONLY,
        )

        labels_compatible = False
        within_tolerance = False

        if nearest_a is not None:
            within_tolerance = bool(
                nearest_difference is not None
                and nearest_difference
                <= tolerance_sec
            )

            (
                labels_compatible,
                label_reasons,
            ) = compare_adjacent_boundary_labels(
                nearest_a,
                boundary_b,
            )

            for reason in label_reasons:
                append_unique_reason(
                    reasons,
                    reason,
                )

        if not within_tolerance:
            append_unique_reason(
                reasons,
                DisagreementReason.BOUNDARY_OUTSIDE_TOLERANCE,
            )

        results.append(
            BoundaryMatch(
                boundary_id=stable_numbered_id(
                    "boundary_match",
                    result_index,
                ),
                boundary_type=boundary_b.boundary_type,
                boundary_index_a=None,
                boundary_index_b=(
                    boundary_b.boundary_index
                ),
                boundary_a=None,
                boundary_b=float(boundary_b.time),
                difference_seconds=None,
                midpoint=None,
                within_tolerance=within_tolerance,
                adjacent_labels_compatible=(
                    labels_compatible
                ),
                matched=False,
                nearest_other_boundary=(
                    float(nearest_a.time)
                    if nearest_a is not None
                    else None
                ),
                nearest_difference_seconds=(
                    nearest_difference
                ),
                reasons=reasons,
            )
        )

        result_index += 1

    # Keep result ordering deterministic for plotting and JSON persistence.
    results.sort(
        key=lambda result: (
            (
                result.midpoint
                if result.midpoint is not None
                else (
                    result.boundary_a
                    if result.boundary_a is not None
                    else result.boundary_b
                )
            ),
            0 if result.matched else 1,
            result.boundary_id,
        )
    )

    return results


def extract_and_match_source_boundaries(
    intervals_a: list[AnnotationInterval],
    intervals_b: list[AnnotationInterval],
    *,
    tolerance_sec: float = ADJUDICATION_BOUNDARY_TOLERANCE_SEC,
) -> tuple[
    list[TimelineBoundary],
    list[TimelineBoundary],
    list[BoundaryMatch],
]:
    """
    Extract and compare both source boundary sets.

    Parameters
    ----------
    intervals_a, intervals_b : list[AnnotationInterval]
        Validated source timelines.

    tolerance_sec : float
        Maximum accepted source boundary difference.

    Returns
    -------
    tuple
        ``(
            boundaries_a,
            boundaries_b,
            boundary_matches
        )``.
    """
    start_time = perf_counter()

    boundaries_a: list[TimelineBoundary] = []
    boundaries_b: list[TimelineBoundary] = []
    matches: list[BoundaryMatch] = []

    try:
        boundaries_a = extract_timeline_boundaries(
            intervals=intervals_a,
            source_alias=ANNOTATOR_ALIASES[0],
        )

        boundaries_b = extract_timeline_boundaries(
            intervals=intervals_b,
            source_alias=ANNOTATOR_ALIASES[1],
        )

        matches = match_timeline_boundaries(
            boundaries_a=boundaries_a,
            boundaries_b=boundaries_b,
            tolerance_sec=tolerance_sec,
        )

        return (
            boundaries_a,
            boundaries_b,
            matches,
        )

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "extract_and_match_source_boundaries failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "extract_and_match_source_boundaries",
            perf_counter() - start_time,
            boundaries_a=len(boundaries_a),
            boundaries_b=len(boundaries_b),
            matched=sum(
                result.matched
                for result in matches
            ),
            unmatched=sum(
                not result.matched
                for result in matches
            ),
        )

