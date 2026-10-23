"""
Combined timeline construction, agreement classification, consensus
prefilling, and the primary adjudication comparison API.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Optional

import numpy as np

from .boundaries import extract_and_match_source_boundaries
from .config import (
    ADJUDICATION_BOUNDARY_TOLERANCE_SEC,
    ANNOTATION_USERS,
    ComparisonStatus,
    DisagreementReason,
)
from .discovery import (
    discover_source_annotation_files,
    require_ready_source_annotation_files,
)
from .exceptions import (
    AdjudicationError,
    InvalidAnnotationError,
)
from .models import (
    AdjudicationComparisonResult,
    AdjudicationInterval,
    AnnotationInterval,
    BoundaryMatch,
    ComparisonRegion,
    SourceAnnotationFile,
    TimelineBoundary,
    TimelineSegment,
    ValidationIssue,
)
from .utilities import (
    _perf_log,
    clean_string,
    stable_numbered_id,
    utc_now_iso,
)
from .validation import load_and_validate_source_pair

# =============================================================================
# Combined timeline segmentation
# =============================================================================

def build_reconciled_boundary_times(
    boundaries: list[TimelineBoundary],
    boundary_matches: list[BoundaryMatch],
    source_alias: str,
) -> dict[int, float]:
    """
    Build reconciled boundary coordinates for one source timeline.

    Parameters
    ----------
    boundaries : list[TimelineBoundary]
        Ordered boundaries from one source timeline.

    boundary_matches : list[BoundaryMatch]
        Accepted and unmatched A/B boundary comparison results.

    source_alias : str
        ``Annotator A`` or ``Annotator B``.

    Returns
    -------
    dict[int, float]
        Mapping from source boundary index to the coordinate used in the
        combined comparison timeline.

    Notes
    -----
    Accepted A/B boundaries are replaced by their shared midpoint. Unmatched
    boundaries retain their original source timestamp.
    """
    start_time = perf_counter()
    reconciled_times: dict[int, float] = {}

    try:
        reconciled_times = (
            _build_reconciled_boundary_times_impl(
                boundaries=boundaries,
                boundary_matches=boundary_matches,
                source_alias=source_alias,
            )
        )

        return reconciled_times

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "build_reconciled_boundary_times failed:",
            f"source_alias={source_alias}",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "build_reconciled_boundary_times",
            perf_counter() - start_time,
            source_alias=source_alias,
            boundaries=len(boundaries),
            reconciled=len(reconciled_times),
        )


def _build_reconciled_boundary_times_impl(
    boundaries: list[TimelineBoundary],
    boundary_matches: list[BoundaryMatch],
    source_alias: str,
) -> dict[int, float]:
    """
    Build one source's reconciled boundary mapping without UI behavior.
    """
    if source_alias not in ANNOTATOR_ALIASES:
        raise AdjudicationError(
            f"Unsupported source alias: {source_alias!r}"
        )

    if not boundaries:
        raise InvalidAnnotationError(
            f"{source_alias} contains no boundaries."
        )

    # Begin with each boundary's original absolute epoch timestamp.
    reconciled_times: dict[int, float] = {
        boundary.boundary_index: float(
            boundary.time
        )
        for boundary in boundaries
    }

    for match in boundary_matches:
        if not match.matched:
            continue

        if match.midpoint is None:
            raise AdjudicationError(
                f"Matched boundary {match.boundary_id} "
                "does not contain a midpoint."
            )

        midpoint = float(match.midpoint)

        if not np.isfinite(midpoint):
            raise AdjudicationError(
                f"Matched boundary {match.boundary_id} "
                "contains a non-finite midpoint."
            )

        if source_alias == ANNOTATOR_ALIASES[0]:
            boundary_index = (
                match.boundary_index_a
            )
        else:
            boundary_index = (
                match.boundary_index_b
            )

        if boundary_index is None:
            raise AdjudicationError(
                f"Matched boundary {match.boundary_id} "
                f"does not contain an index for {source_alias}."
            )

        if boundary_index not in reconciled_times:
            raise AdjudicationError(
                f"Boundary index {boundary_index} from "
                f"{match.boundary_id} is not present in "
                f"{source_alias}."
            )

        # Both accepted source boundaries use the same midpoint.
        reconciled_times[boundary_index] = midpoint

    ordered_boundary_indices = [
        boundary.boundary_index
        for boundary in boundaries
    ]

    ordered_times = [
        reconciled_times[index]
        for index in ordered_boundary_indices
    ]

    # Midpoint reconciliation must not reverse or collapse source intervals.
    for previous_time, current_time in zip(
        ordered_times[:-1],
        ordered_times[1:],
    ):
        if current_time <= previous_time:
            raise InvalidAnnotationError(
                f"Boundary reconciliation produced a non-increasing "
                f"timeline for {source_alias}: "
                f"{previous_time:.9f} followed by "
                f"{current_time:.9f}."
            )

    return reconciled_times


def build_reconciled_interval_spans(
    intervals: list[AnnotationInterval],
    boundaries: list[TimelineBoundary],
    reconciled_boundary_times: dict[int, float],
    source_alias: str,
) -> list[
    tuple[float, float, AnnotationInterval]
]:
    """
    Build source intervals using reconciled boundary coordinates.

    Parameters
    ----------
    intervals : list[AnnotationInterval]
        Validated source intervals.

    boundaries : list[TimelineBoundary]
        Ordered source boundaries. There must be one more boundary than
        interval.

    reconciled_boundary_times : dict[int, float]
        Mapping produced by ``build_reconciled_boundary_times``.

    source_alias : str
        Source alias used in validation errors.

    Returns
    -------
    list[tuple[float, float, AnnotationInterval]]
        Reconciled ``(start, end, interval)`` spans.

    Notes
    -----
    Original annotation interval timestamps are not modified. Reconciled
    coordinates are used only for comparison and prefilling.
    """
    start_time = perf_counter()

    spans: list[
        tuple[float, float, AnnotationInterval]
    ] = []

    try:
        spans = _build_reconciled_interval_spans_impl(
            intervals=intervals,
            boundaries=boundaries,
            reconciled_boundary_times=(
                reconciled_boundary_times
            ),
            source_alias=source_alias,
        )

        return spans

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "build_reconciled_interval_spans failed:",
            f"source_alias={source_alias}",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "build_reconciled_interval_spans",
            perf_counter() - start_time,
            source_alias=source_alias,
            intervals=len(intervals),
            spans=len(spans),
        )


def _build_reconciled_interval_spans_impl(
    intervals: list[AnnotationInterval],
    boundaries: list[TimelineBoundary],
    reconciled_boundary_times: dict[int, float],
    source_alias: str,
) -> list[
    tuple[float, float, AnnotationInterval]
]:
    """
    Build reconciled source spans without timing or UI behavior.
    """
    if len(boundaries) != len(intervals) + 1:
        raise InvalidAnnotationError(
            f"{source_alias} has {len(intervals)} intervals but "
            f"{len(boundaries)} boundaries. Expected "
            f"{len(intervals) + 1} boundaries."
        )

    spans: list[
        tuple[float, float, AnnotationInterval]
    ] = []

    for interval_index, interval in enumerate(
        intervals
    ):
        start_boundary = boundaries[
            interval_index
        ]
        end_boundary = boundaries[
            interval_index + 1
        ]

        try:
            reconciled_start = float(
                reconciled_boundary_times[
                    start_boundary.boundary_index
                ]
            )
            reconciled_end = float(
                reconciled_boundary_times[
                    end_boundary.boundary_index
                ]
            )
        except KeyError as exc:
            raise InvalidAnnotationError(
                f"Missing reconciled boundary for "
                f"{source_alias} interval {interval_index}."
            ) from exc

        if (
            not np.isfinite(reconciled_start)
            or not np.isfinite(reconciled_end)
        ):
            raise InvalidAnnotationError(
                f"{source_alias} interval {interval_index} "
                "contains non-finite reconciled boundaries."
            )

        if reconciled_end <= reconciled_start:
            raise InvalidAnnotationError(
                f"{source_alias} interval {interval_index} "
                "has non-positive reconciled duration."
            )

        spans.append(
            (
                reconciled_start,
                reconciled_end,
                interval,
            )
        )

    return spans


def find_active_reconciled_interval(
    spans: list[
        tuple[float, float, AnnotationInterval]
    ],
    time_value: float,
) -> Optional[AnnotationInterval]:
    """
    Return the source interval active at one reconciled time coordinate.

    Parameters
    ----------
    spans : list[tuple[float, float, AnnotationInterval]]
        Reconciled source intervals.

    time_value : float
        Absolute epoch timestamp, normally an atomic-segment midpoint.

    Returns
    -------
    AnnotationInterval or None
        Active source annotation, or None when the source does not cover the
        requested time.
    """
    for span_index, (
        span_start,
        span_end,
        interval,
    ) in enumerate(spans):
        is_final_span = (
            span_index == len(spans) - 1
        )

        # Use half-open intervals except for the final span, whose end is
        # included for defensive completeness.
        if (
            span_start <= time_value < span_end
            or (
                is_final_span
                and span_start
                <= time_value
                <= span_end
            )
        ):
            return interval

    return None


def collect_combined_reconciled_boundaries(
    reconciled_times_a: dict[int, float],
    reconciled_times_b: dict[int, float],
) -> np.ndarray:
    """
    Collect sorted unique boundaries from both reconciled timelines.

    Parameters
    ----------
    reconciled_times_a, reconciled_times_b : dict[int, float]
        Boundary-index mappings for Annotator A and Annotator B.

    Returns
    -------
    numpy.ndarray
        Sorted finite floating-point absolute epoch timestamps.

    Raises
    ------
    InvalidAnnotationError
        If fewer than two usable boundaries are available.
    """
    values = np.asarray(
        list(reconciled_times_a.values())
        + list(reconciled_times_b.values()),
        dtype=np.float64,
    )

    values = values[
        np.isfinite(values)
    ]

    if values.size < 2:
        raise InvalidAnnotationError(
            "Combined comparison timeline requires at least two "
            "finite boundaries."
        )

    # Matched boundaries have identical midpoint values and collapse naturally.
    unique_boundaries = np.unique(values)
    unique_boundaries.sort()

    if unique_boundaries.size < 2:
        raise InvalidAnnotationError(
            "Combined comparison timeline has no positive time range."
        )

    return unique_boundaries


def build_combined_timeline_segments(
    intervals_a: list[AnnotationInterval],
    intervals_b: list[AnnotationInterval],
    boundaries_a: list[TimelineBoundary],
    boundaries_b: list[TimelineBoundary],
    boundary_matches: list[BoundaryMatch],
) -> list[TimelineSegment]:
    """
    Build atomic A/B timeline segments with timing and diagnostics.

    Parameters
    ----------
    intervals_a, intervals_b : list[AnnotationInterval]
        Validated Annotator A and Annotator B timelines.

    boundaries_a, boundaries_b : list[TimelineBoundary]
        Extracted source boundaries.

    boundary_matches : list[BoundaryMatch]
        Accepted midpoint matches and unmatched boundaries.

    Returns
    -------
    list[TimelineSegment]
        Chronological atomic segments with active source annotations.

    Notes
    -----
    This function performs segmentation only. It does not assign green, red,
    gray, or resolved comparison statuses.
    """
    start_time = perf_counter()
    segments: list[TimelineSegment] = []

    try:
        segments = (
            _build_combined_timeline_segments_impl(
                intervals_a=intervals_a,
                intervals_b=intervals_b,
                boundaries_a=boundaries_a,
                boundaries_b=boundaries_b,
                boundary_matches=boundary_matches,
            )
        )

        return segments

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "build_combined_timeline_segments failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "build_combined_timeline_segments",
            perf_counter() - start_time,
            intervals_a=len(intervals_a),
            intervals_b=len(intervals_b),
            boundary_matches=len(
                boundary_matches
            ),
            segments=len(segments),
        )


def _build_combined_timeline_segments_impl(
    intervals_a: list[AnnotationInterval],
    intervals_b: list[AnnotationInterval],
    boundaries_a: list[TimelineBoundary],
    boundaries_b: list[TimelineBoundary],
    boundary_matches: list[BoundaryMatch],
) -> list[TimelineSegment]:
    """
    Build atomic comparison segments without timing or UI behavior.
    """
    reconciled_times_a = (
        build_reconciled_boundary_times(
            boundaries=boundaries_a,
            boundary_matches=boundary_matches,
            source_alias=ANNOTATOR_ALIASES[0],
        )
    )

    reconciled_times_b = (
        build_reconciled_boundary_times(
            boundaries=boundaries_b,
            boundary_matches=boundary_matches,
            source_alias=ANNOTATOR_ALIASES[1],
        )
    )

    spans_a = build_reconciled_interval_spans(
        intervals=intervals_a,
        boundaries=boundaries_a,
        reconciled_boundary_times=(
            reconciled_times_a
        ),
        source_alias=ANNOTATOR_ALIASES[0],
    )

    spans_b = build_reconciled_interval_spans(
        intervals=intervals_b,
        boundaries=boundaries_b,
        reconciled_boundary_times=(
            reconciled_times_b
        ),
        source_alias=ANNOTATOR_ALIASES[1],
    )

    combined_boundaries = (
        collect_combined_reconciled_boundaries(
            reconciled_times_a=(
                reconciled_times_a
            ),
            reconciled_times_b=(
                reconciled_times_b
            ),
        )
    )

    segments: list[TimelineSegment] = []

    for boundary_start, boundary_end in zip(
        combined_boundaries[:-1],
        combined_boundaries[1:],
    ):
        segment_start = float(
            boundary_start
        )
        segment_end = float(
            boundary_end
        )

        if segment_end <= segment_start:
            continue

        midpoint = (
            segment_start
            + segment_end
        ) / 2.0

        annotation_a = (
            find_active_reconciled_interval(
                spans=spans_a,
                time_value=midpoint,
            )
        )

        annotation_b = (
            find_active_reconciled_interval(
                spans=spans_b,
                time_value=midpoint,
            )
        )

        # Ignore a region outside both source timelines.
        if (
            annotation_a is None
            and annotation_b is None
        ):
            continue

        segments.append(
            TimelineSegment(
                segment_id=stable_numbered_id(
                    "segment",
                    len(segments) + 1,
                ),
                start=segment_start,
                end=segment_end,
                annotation_a=annotation_a,
                annotation_b=annotation_b,
            )
        )

    if not segments:
        raise InvalidAnnotationError(
            "Combined timeline segmentation produced no usable regions."
        )

    return segments

# =============================================================================
# Agreement classification
# =============================================================================

# Functions for:
#
# - comparing CPR values
# - comparing rhythm labels
# - checking adjacent-label compatibility
# - assigning agreement/disagreement/missing status
# - attaching machine-readable disagreement reasons
# - creating stable disagreement IDs


# =============================================================================
# Prefilled final timeline generation
# =============================================================================

# Functions for:
#
# - pre-filling green agreement regions
# - using midpoint-reconciled boundaries
# - leaving red/gray regions unresolved
# - optionally merging adjacent identical green intervals
# - preventing gaps and overlaps introduced by reconciliation
# - generating AdjudicationInterval objects


# =============================================================================
# Main comparison API
# =============================================================================

def build_adjudication_comparison(
    record,
    adjudicator,
    *,
    annotators=None,
    boundary_tolerance_sec=ADJUDICATION_BOUNDARY_TOLERANCE_SEC,
):
    """
    Discover, validate, and compare the two source annotation files.

    Returns an AdjudicationComparisonResult.

    This should be the primary function called by adjudication callbacks.
    """
    raise NotImplementedError

