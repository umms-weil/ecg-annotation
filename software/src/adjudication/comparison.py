"""
Combined timeline construction, agreement classification, consensus
prefilling, and the primary adjudication comparison API.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Mapping, Optional

import numpy as np

from .boundaries import (
    append_unique_reason,
    extract_and_match_source_boundaries,
)
from .config import (
    ADJUDICATION_BOUNDARY_TOLERANCE_SEC,
    ANNOTATION_USERS,
    ANNOTATOR_ALIASES,
    BOUNDARY_COORDINATE_EPSILON_SEC,
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
from .paths import validate_adjudicator

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

def get_segment_label_disagreement_reasons(
    segment: TimelineSegment,
) -> list[str]:
    """
    Compare CPR and rhythm labels active within one atomic segment.

    Parameters
    ----------
    segment : TimelineSegment
        Atomic region containing zero, one, or two source annotations.

    Returns
    -------
    list[str]
        Unique machine-readable disagreement reasons.

    Notes
    -----
    Explanations are not used to determine annotator agreement. Required
    explanations are validated separately when loading source timelines.
    """
    reasons: list[str] = []

    annotation_a = segment.annotation_a
    annotation_b = segment.annotation_b

    if annotation_a is None and annotation_b is None:
        append_unique_reason(
            reasons,
            DisagreementReason.MISSING_COVERAGE,
        )
        return reasons

    if annotation_a is None:
        append_unique_reason(
            reasons,
            DisagreementReason.ANNOTATOR_B_ONLY,
        )
        append_unique_reason(
            reasons,
            DisagreementReason.MISSING_COVERAGE,
        )
        return reasons

    if annotation_b is None:
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
        clean_string(annotation_a.cpr)
        != clean_string(annotation_b.cpr)
    ):
        append_unique_reason(
            reasons,
            DisagreementReason.CPR_MISMATCH,
        )

    if (
        clean_string(annotation_a.rhythm_label)
        != clean_string(annotation_b.rhythm_label)
    ):
        append_unique_reason(
            reasons,
            DisagreementReason.RHYTHM_MISMATCH,
        )

    return reasons


def segment_touches_time(
    segment: TimelineSegment,
    boundary_time: float,
    *,
    epsilon_sec: float = BOUNDARY_COORDINATE_EPSILON_SEC,
) -> bool:
    """
    Return whether a segment begins or ends at one boundary coordinate.

    Parameters
    ----------
    segment : TimelineSegment
        Atomic comparison segment.

    boundary_time : float
        Absolute epoch timestamp.

    epsilon_sec : float
        Numerical comparison tolerance.

    Returns
    -------
    bool
        True when the segment start or end matches the boundary coordinate.
    """
    if not np.isfinite(boundary_time):
        return False

    return bool(
        np.isclose(
            segment.start,
            boundary_time,
            rtol=0.0,
            atol=epsilon_sec,
        )
        or np.isclose(
            segment.end,
            boundary_time,
            rtol=0.0,
            atol=epsilon_sec,
        )
    )


def segment_overlaps_boundary_conflict_span(
    segment: TimelineSegment,
    first_time: float,
    second_time: float,
    *,
    epsilon_sec: float = BOUNDARY_COORDINATE_EPSILON_SEC,
) -> bool:
    """
    Return whether a segment overlaps the span between conflicting boundaries.

    Parameters
    ----------
    segment : TimelineSegment
        Atomic comparison segment.

    first_time, second_time : float
        Conflicting source boundary coordinates.

    epsilon_sec : float
        Numerical coordinate tolerance.

    Returns
    -------
    bool
        True when the segment overlaps the positive-width conflict span.

    Notes
    -----
    When source boundaries differ, the region between them is the primary
    boundary-disagreement area.
    """
    if (
        not np.isfinite(first_time)
        or not np.isfinite(second_time)
    ):
        return False

    conflict_start = min(
        float(first_time),
        float(second_time),
    )
    conflict_end = max(
        float(first_time),
        float(second_time),
    )

    if conflict_end - conflict_start <= epsilon_sec:
        return False

    overlap_start = max(
        float(segment.start),
        conflict_start,
    )
    overlap_end = min(
        float(segment.end),
        conflict_end,
    )

    return bool(
        overlap_end - overlap_start > epsilon_sec
    )


def get_segment_boundary_disagreement_reasons(
    segment: TimelineSegment,
    boundary_matches: list[BoundaryMatch],
) -> list[str]:
    """
    Return boundary-related disagreement reasons affecting one segment.

    Parameters
    ----------
    segment : TimelineSegment
        Atomic comparison segment.

    boundary_matches : list[BoundaryMatch]
        Accepted and unmatched A/B boundary results.

    Returns
    -------
    list[str]
        Unique boundary disagreement reasons.

    Behavior
    --------
    For source boundaries at different times, the segment between those times
    receives the boundary disagreement reasons.

    For an unmatched boundary without a distinct opposite-source coordinate,
    segments touching that boundary receive the disagreement reasons.
    """
    reasons: list[str] = []

    for boundary_result in boundary_matches:
        if boundary_result.matched:
            continue

        own_boundary_time = (
            boundary_result.boundary_a
            if boundary_result.boundary_a is not None
            else boundary_result.boundary_b
        )

        nearest_boundary_time = (
            boundary_result.nearest_other_boundary
        )

        affected = False

        if (
            own_boundary_time is not None
            and nearest_boundary_time is not None
        ):
            affected = (
                segment_overlaps_boundary_conflict_span(
                    segment=segment,
                    first_time=float(
                        own_boundary_time
                    ),
                    second_time=float(
                        nearest_boundary_time
                    ),
                )
            )

            # Exact or nearly exact unmatched boundaries generally indicate
            # adjacent-label incompatibility rather than positional mismatch.
            if (
                not affected
                and np.isclose(
                    float(own_boundary_time),
                    float(nearest_boundary_time),
                    rtol=0.0,
                    atol=(
                        BOUNDARY_COORDINATE_EPSILON_SEC
                    ),
                )
            ):
                affected = segment_touches_time(
                    segment=segment,
                    boundary_time=float(
                        own_boundary_time
                    ),
                )

        elif own_boundary_time is not None:
            # An extra boundary with no same-type counterpart affects the
            # segments immediately adjacent to that boundary.
            affected = segment_touches_time(
                segment=segment,
                boundary_time=float(
                    own_boundary_time
                ),
            )

        if not affected:
            continue

        for reason in boundary_result.reasons:
            append_unique_reason(
                reasons,
                reason,
            )

    return reasons


def classify_timeline_segment(
    segment: TimelineSegment,
    boundary_matches: list[BoundaryMatch],
) -> ComparisonRegion:
    """
    Classify one atomic timeline segment.

    Parameters
    ----------
    segment : TimelineSegment
        Atomic A/B timeline segment.

    boundary_matches : list[BoundaryMatch]
        Boundary results used to attach positional and adjacency conflicts.

    Returns
    -------
    ComparisonRegion
        Green agreement, red unresolved disagreement, or gray missing coverage.

    Classification rules
    --------------------
    Missing one or both annotations
        ``MISSING_COVERAGE``.

    Both annotations present with any label or boundary reason
        ``UNRESOLVED_DISAGREEMENT``.

    Both annotations present with no disagreement reason
        ``AGREEMENT``.
    """
    reasons = get_segment_label_disagreement_reasons(
        segment
    )

    boundary_reasons = (
        get_segment_boundary_disagreement_reasons(
            segment=segment,
            boundary_matches=boundary_matches,
        )
    )

    for reason in boundary_reasons:
        append_unique_reason(
            reasons,
            reason,
        )

    if not segment.has_both_annotators:
        status = ComparisonStatus.MISSING_COVERAGE

    elif reasons:
        status = (
            ComparisonStatus
            .UNRESOLVED_DISAGREEMENT
        )

    else:
        status = ComparisonStatus.AGREEMENT

    return ComparisonRegion(
        region_id=segment.segment_id.replace(
            "segment_",
            "region_",
            1,
        ),
        start=float(segment.start),
        end=float(segment.end),
        status=status,
        reasons=reasons,
        annotation_a=segment.annotation_a,
        annotation_b=segment.annotation_b,
        resolved=False,
        resolved_at=None,
    )


def classify_comparison_regions(
    segments: list[TimelineSegment],
    boundary_matches: list[BoundaryMatch],
) -> list[ComparisonRegion]:
    """
    Classify all atomic timeline segments with timing and diagnostics.

    Parameters
    ----------
    segments : list[TimelineSegment]
        Combined timeline segments.

    boundary_matches : list[BoundaryMatch]
        Accepted and unmatched source-boundary results.

    Returns
    -------
    list[ComparisonRegion]
        Chronological comparison regions.

    Raises
    ------
    InvalidAnnotationError
        If no segments are available or classification creates an invalid
        region.
    """
    start_time = perf_counter()
    regions: list[ComparisonRegion] = []

    try:
        regions = _classify_comparison_regions_impl(
            segments=segments,
            boundary_matches=boundary_matches,
        )

        return regions

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "classify_comparison_regions failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        status_counts = {
            status.value: sum(
                region.status == status
                for region in regions
            )
            for status in ComparisonStatus
        }

        _perf_log(
            "classify_comparison_regions",
            perf_counter() - start_time,
            segments=len(segments),
            regions=len(regions),
            statuses=status_counts,
        )


def _classify_comparison_regions_impl(
    segments: list[TimelineSegment],
    boundary_matches: list[BoundaryMatch],
) -> list[ComparisonRegion]:
    """
    Classify all atomic segments without timing or UI behavior.
    """
    if not segments:
        raise InvalidAnnotationError(
            "No combined timeline segments are available for "
            "agreement classification."
        )

    regions: list[ComparisonRegion] = []

    previous_end: Optional[float] = None

    for segment in segments:
        if (
            not np.isfinite(segment.start)
            or not np.isfinite(segment.end)
            or segment.end <= segment.start
        ):
            raise InvalidAnnotationError(
                f"Segment {segment.segment_id} has invalid boundaries."
            )

        if (
            previous_end is not None
            and segment.start
            < previous_end
            - BOUNDARY_COORDINATE_EPSILON_SEC
        ):
            raise InvalidAnnotationError(
                f"Segment {segment.segment_id} overlaps the previous segment."
            )

        region = classify_timeline_segment(
            segment=segment,
            boundary_matches=boundary_matches,
        )

        regions.append(region)
        previous_end = float(segment.end)

    return regions


def summarize_comparison_regions(
    regions: list[ComparisonRegion],
) -> dict[str, Any]:
    """
    Return summary counts and durations for comparison regions.

    Parameters
    ----------
    regions : list[ComparisonRegion]
        Classified chronological regions.

    Returns
    -------
    dict[str, Any]
        Region counts, durations, and unresolved totals.
    """
    summary: dict[str, Any] = {
        "total_regions": len(regions),
        "total_duration_sec": 0.0,
        "agreement_regions": 0,
        "agreement_duration_sec": 0.0,
        "unresolved_regions": 0,
        "unresolved_duration_sec": 0.0,
        "resolved_regions": 0,
        "resolved_duration_sec": 0.0,
        "missing_coverage_regions": 0,
        "missing_coverage_duration_sec": 0.0,
    }

    for region in regions:
        duration = float(region.duration)

        summary["total_duration_sec"] += duration

        if region.status == ComparisonStatus.AGREEMENT:
            summary["agreement_regions"] += 1
            summary[
                "agreement_duration_sec"
            ] += duration

        elif (
            region.status
            == ComparisonStatus.UNRESOLVED_DISAGREEMENT
        ):
            summary["unresolved_regions"] += 1
            summary[
                "unresolved_duration_sec"
            ] += duration

        elif (
            region.status
            == ComparisonStatus.RESOLVED_DISAGREEMENT
        ):
            summary["resolved_regions"] += 1
            summary[
                "resolved_duration_sec"
            ] += duration

        elif (
            region.status
            == ComparisonStatus.MISSING_COVERAGE
        ):
            summary[
                "missing_coverage_regions"
            ] += 1
            summary[
                "missing_coverage_duration_sec"
            ] += duration

            if not region.resolved:
                summary["unresolved_regions"] += 1
                summary[
                    "unresolved_duration_sec"
                ] += duration

    comparable_duration = (
        summary["agreement_duration_sec"]
        + summary["unresolved_duration_sec"]
        + summary["resolved_duration_sec"]
    )

    if comparable_duration > 0:
        summary["agreement_percent"] = (
            100.0
            * summary["agreement_duration_sec"]
            / comparable_duration
        )
    else:
        summary["agreement_percent"] = float(
            "nan"
        )

    return summary

# =============================================================================
# Prefilled final timeline generation
# =============================================================================

def get_prefilled_explanation(
    annotation_a: AnnotationInterval,
    annotation_b: AnnotationInterval,
) -> str:
    """
    Select a safe explanation for an agreed comparison region.

    Parameters
    ----------
    annotation_a, annotation_b : AnnotationInterval
        Source intervals covering a green agreement region.

    Returns
    -------
    str
        Shared explanation when both annotators entered the same value.
        Otherwise, an empty string.

    Notes
    -----
    CPR and rhythm agreement does not require identical explanation text.
    Conflicting explanation text is not silently copied from one annotator.
    The adjudicator may provide the final explanation when needed.
    """
    explanation_a = clean_string(
        annotation_a.rhythm_expl
    )
    explanation_b = clean_string(
        annotation_b.rhythm_expl
    )

    if explanation_a == explanation_b:
        return explanation_a

    return ""


def get_prefilled_source_path(
    annotation_a: Optional[AnnotationInterval],
    annotation_b: Optional[AnnotationInterval],
) -> str:
    """
    Select waveform source-path metadata for a prefilled interval.

    Parameters
    ----------
    annotation_a, annotation_b : AnnotationInterval or None
        Source annotations covering the comparison region.

    Returns
    -------
    str
        Shared source path when available, otherwise the first nonblank path.

    Notes
    -----
    This field describes the waveform source, not the source annotation CSV.
    """
    source_path_a = (
        clean_string(annotation_a.source_path)
        if annotation_a is not None
        else ""
    )

    source_path_b = (
        clean_string(annotation_b.source_path)
        if annotation_b is not None
        else ""
    )

    if (
        source_path_a
        and source_path_a == source_path_b
    ):
        return source_path_a

    return source_path_a or source_path_b


def build_prefilled_interval_from_region(
    region: ComparisonRegion,
    adjudicator: str,
    created_at: str,
) -> AdjudicationInterval:
    """
    Create one provisional final interval from a comparison region.

    Parameters
    ----------
    region : ComparisonRegion
        Classified green, red, or gray comparison region.

    adjudicator : str
        Validated adjudicator username.

    created_at : str
        ISO-8601 UTC creation timestamp shared by the initial timeline.

    Returns
    -------
    AdjudicationInterval
        Prefilled editable final interval.

    Behavior
    --------
    Green agreement regions
        Receive the agreed CPR and rhythm values.

    Red or gray regions
        Remain unlabeled and require reviewer action.

    Notes
    -----
    The original source annotations are not modified.
    """
    annotation_a = region.annotation_a
    annotation_b = region.annotation_b

    # Use whichever source interval is available for waveform-record metadata.
    metadata_source = (
        annotation_a
        if annotation_a is not None
        else annotation_b
    )

    if metadata_source is None:
        raise InvalidAnnotationError(
            f"Comparison region {region.region_id} has no source metadata."
        )

    if region.status == ComparisonStatus.AGREEMENT:
        if annotation_a is None or annotation_b is None:
            raise InvalidAnnotationError(
                f"Agreement region {region.region_id} does not contain "
                "both source annotations."
            )

        cpr = clean_string(annotation_a.cpr)
        rhythm_label = clean_string(
            annotation_a.rhythm_label
        )

        # Preserve explanation only when both users entered the same text.
        rhythm_expl = get_prefilled_explanation(
            annotation_a=annotation_a,
            annotation_b=annotation_b,
        )

    else:
        # Disagreement and missing-coverage regions are intentionally left
        # unlabeled to avoid silently favoring either source annotator.
        cpr = ""
        rhythm_label = ""
        rhythm_expl = ""

    return AdjudicationInterval(
        # Retain backward compatibility with the annotation CSV schema.
        user=adjudicator,
        adjudicator=adjudicator,
        subject=clean_string(
            metadata_source.subject
        ),
        encounter=clean_string(
            metadata_source.encounter
        ),
        namespace=clean_string(
            metadata_source.namespace
        ),
        file_tag=clean_string(
            metadata_source.file_tag
        ),
        source_path=get_prefilled_source_path(
            annotation_a=annotation_a,
            annotation_b=annotation_b,
        ),
        cpr=cpr,
        rhythm_label=rhythm_label,
        rhythm_expl=rhythm_expl,
        start=float(region.start),
        end=float(region.end),
        waveform_complete=False,
        terminal_event_status="",
        terminal_event_comment="",
        adjudication_created_at=created_at,
        adjudication_updated_at=created_at,
    )


def prefilled_intervals_can_merge(
    previous_interval: AdjudicationInterval,
    current_interval: AdjudicationInterval,
    previous_region: ComparisonRegion,
    current_region: ComparisonRegion,
    *,
    epsilon_sec: float = BOUNDARY_COORDINATE_EPSILON_SEC,
) -> bool:
    """
    Return whether two adjacent prefilled agreement intervals may be merged.

    Parameters
    ----------
    previous_interval, current_interval : AdjudicationInterval
        Adjacent provisional final intervals.

    previous_region, current_region : ComparisonRegion
        Comparison regions that produced the intervals.

    epsilon_sec : float
        Numerical tolerance for boundary continuity.

    Returns
    -------
    bool
        True when both regions are green agreement regions, are contiguous,
        and contain identical final label values.

    Notes
    -----
    Red and gray regions are never merged automatically because their region
    boundaries and explicit resolution states must remain identifiable.
    """
    if (
        previous_region.status
        != ComparisonStatus.AGREEMENT
        or current_region.status
        != ComparisonStatus.AGREEMENT
    ):
        return False

    if not np.isclose(
        previous_interval.end,
        current_interval.start,
        rtol=0.0,
        atol=epsilon_sec,
    ):
        return False

    return bool(
        clean_string(previous_interval.cpr)
        == clean_string(current_interval.cpr)
        and clean_string(
            previous_interval.rhythm_label
        )
        == clean_string(
            current_interval.rhythm_label
        )
        and clean_string(
            previous_interval.rhythm_expl
        )
        == clean_string(
            current_interval.rhythm_expl
        )
        and clean_string(
            previous_interval.subject
        )
        == clean_string(current_interval.subject)
        and clean_string(
            previous_interval.encounter
        )
        == clean_string(current_interval.encounter)
        and clean_string(
            previous_interval.file_tag
        )
        == clean_string(current_interval.file_tag)
    )


def generate_prefilled_adjudication_timeline(
    regions: list[ComparisonRegion],
    adjudicator: str,
    *,
    allowed_adjudicators: Optional[list[str]] = None,
    merge_adjacent_agreement: bool = True,
) -> list[AdjudicationInterval]:
    """
    Generate a provisional final timeline with timing and diagnostics.

    Parameters
    ----------
    regions : list[ComparisonRegion]
        Chronological classified comparison regions.

    adjudicator : str
        Reviewer producing the final timeline.

    allowed_adjudicators : list[str] or None
        Optional adjudicator allowlist override.

    merge_adjacent_agreement : bool
        Merge adjacent green regions when all final label values match.

    Returns
    -------
    list[AdjudicationInterval]
        Editable provisional adjudication intervals.

    Raises
    ------
    AdjudicationPathError
        If the adjudicator is not configured.

    InvalidAnnotationError
        If regions are missing, invalid, overlapping, or produce an invalid
        provisional timeline.
    """
    start_time = perf_counter()
    intervals: list[AdjudicationInterval] = []

    try:
        intervals = (
            _generate_prefilled_adjudication_timeline_impl(
                regions=regions,
                adjudicator=adjudicator,
                allowed_adjudicators=(
                    allowed_adjudicators
                ),
                merge_adjacent_agreement=(
                    merge_adjacent_agreement
                ),
            )
        )

        return intervals

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "generate_prefilled_adjudication_timeline failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "generate_prefilled_adjudication_timeline",
            perf_counter() - start_time,
            regions=len(regions),
            intervals=len(intervals),
            merge_adjacent_agreement=(
                merge_adjacent_agreement
            ),
        )


def _generate_prefilled_adjudication_timeline_impl(
    regions: list[ComparisonRegion],
    adjudicator: str,
    *,
    allowed_adjudicators: Optional[list[str]],
    merge_adjacent_agreement: bool,
) -> list[AdjudicationInterval]:
    """
    Generate the provisional final timeline without UI behavior.
    """
    if not regions:
        raise InvalidAnnotationError(
            "No comparison regions are available for prefilled "
            "adjudication generation."
        )

    adjudicator_name = validate_adjudicator(
        adjudicator,
        allowed_adjudicators=allowed_adjudicators,
    )

    created_at = utc_now_iso()

    prefilled_intervals: list[
        AdjudicationInterval
    ] = []

    # Retain the source region associated with the most recently appended
    # interval so green-only merge decisions remain explicit.
    output_regions: list[ComparisonRegion] = []

    previous_region_end: Optional[float] = None

    for region in regions:
        if (
            not np.isfinite(region.start)
            or not np.isfinite(region.end)
        ):
            raise InvalidAnnotationError(
                f"Comparison region {region.region_id} contains "
                "non-finite boundaries."
            )

        if region.end <= region.start:
            raise InvalidAnnotationError(
                f"Comparison region {region.region_id} has "
                "non-positive duration."
            )

        if previous_region_end is not None:
            if (
                region.start
                < previous_region_end
                - BOUNDARY_COORDINATE_EPSILON_SEC
            ):
                raise InvalidAnnotationError(
                    f"Comparison region {region.region_id} overlaps "
                    "the previous region."
                )

            if not np.isclose(
                region.start,
                previous_region_end,
                rtol=0.0,
                atol=BOUNDARY_COORDINATE_EPSILON_SEC,
            ):
                raise InvalidAnnotationError(
                    f"Gap detected before comparison region "
                    f"{region.region_id}: previous end "
                    f"{previous_region_end:.9f}, current start "
                    f"{region.start:.9f}."
                )

        candidate_interval = (
            build_prefilled_interval_from_region(
                region=region,
                adjudicator=adjudicator_name,
                created_at=created_at,
            )
        )

        if (
            merge_adjacent_agreement
            and prefilled_intervals
            and prefilled_intervals_can_merge(
                previous_interval=(
                    prefilled_intervals[-1]
                ),
                current_interval=candidate_interval,
                previous_region=output_regions[-1],
                current_region=region,
            )
        ):
            # Extend the previous green interval without changing its start,
            # labels, creation timestamp, or floating-point precision.
            prefilled_intervals[-1].end = float(
                candidate_interval.end
            )
            prefilled_intervals[
                -1
            ].adjudication_updated_at = created_at

        else:
            prefilled_intervals.append(
                candidate_interval
            )
            output_regions.append(region)

        previous_region_end = float(
            region.end
        )

    if not prefilled_intervals:
        raise InvalidAnnotationError(
            "Prefilled adjudication generation produced no intervals."
        )

    # Final defensive validation of chronological continuity.
    for interval_index, interval in enumerate(
        prefilled_intervals
    ):
        if interval.end <= interval.start:
            raise InvalidAnnotationError(
                f"Prefilled interval {interval_index} has "
                "non-positive duration."
            )

        if interval_index == 0:
            continue

        previous_interval = prefilled_intervals[
            interval_index - 1
        ]

        if not np.isclose(
            previous_interval.end,
            interval.start,
            rtol=0.0,
            atol=BOUNDARY_COORDINATE_EPSILON_SEC,
        ):
            raise InvalidAnnotationError(
                f"Prefilled intervals {interval_index - 1} and "
                f"{interval_index} are not contiguous."
            )

    return prefilled_intervals


# =============================================================================
# Main comparison API
# =============================================================================

def get_required_record_value(
    record: Mapping[str, Any],
    key: str,
) -> str:
    """
    Return one required waveform-record value.

    Parameters
    ----------
    record : Mapping[str, Any]
        Waveform record returned by subject discovery.

    key : str
        Required dictionary key.

    Returns
    -------
    str
        Stripped record value.

    Raises
    ------
    AdjudicationError
        If the key is missing or blank.
    """
    value = clean_string(
        record.get(key, "")
    )

    if not value:
        raise AdjudicationError(
            f"Selected waveform record is missing required field "
            f"{key!r}."
        )

    return value


def validate_sources_match_selected_record(
    intervals_a: list[AnnotationInterval],
    intervals_b: list[AnnotationInterval],
    *,
    subject: str,
    encounter: str,
    file_tag: str,
) -> None:
    """
    Confirm both source timelines belong to the selected waveform record.

    Parameters
    ----------
    intervals_a, intervals_b : list[AnnotationInterval]
        Validated source annotation timelines.

    subject : str
        Subject identifier from the selected waveform record.

    encounter : str
        Encounter identifier from the selected waveform record.

    file_tag : str
        Waveform file tag from the selected record.

    Raises
    ------
    InvalidAnnotationError
        If a source timeline belongs to a different waveform record.
    """
    expected_values = {
        "subject": clean_string(subject),
        "encounter": clean_string(encounter),
        "file_tag": clean_string(file_tag),
    }

    for alias, intervals in (
        (ANNOTATOR_ALIASES[0], intervals_a),
        (ANNOTATOR_ALIASES[1], intervals_b),
    ):
        if not intervals:
            raise InvalidAnnotationError(
                f"{alias} contains no intervals."
            )

        first_interval = intervals[0]

        actual_values = {
            "subject": clean_string(
                first_interval.subject
            ),
            "encounter": clean_string(
                first_interval.encounter
            ),
            "file_tag": clean_string(
                first_interval.file_tag
            ),
        }

        for field_name, expected_value in expected_values.items():
            actual_value = actual_values[field_name]

            if actual_value != expected_value:
                raise InvalidAnnotationError(
                    f"{alias} does not match the selected waveform "
                    f"record for {field_name}. Expected "
                    f"{expected_value!r}; found {actual_value!r}."
                )


def build_adjudication_comparison(
    record: Mapping[str, Any],
    adjudicator: str,
    *,
    annotators: Optional[list[str]] = None,
    allowed_adjudicators: Optional[list[str]] = None,
    boundary_tolerance_sec: float = (
        ADJUDICATION_BOUNDARY_TOLERANCE_SEC
    ),
    merge_adjacent_agreement: bool = True,
) -> AdjudicationComparisonResult:
    """
    Build the complete initial adjudication comparison.

    Parameters
    ----------
    record : Mapping[str, Any]
        Selected waveform record returned by subject discovery. It must include
        ``output_path``, ``subject``, ``encounter``, and ``file_tag``.

    adjudicator : str
        Reviewer creating the adjudication.

    annotators : list[str] or None
        Optional ordered source-annotator override. The first user is assigned
        to Annotator A and the second to Annotator B.

    allowed_adjudicators : list[str] or None
        Optional adjudicator allowlist override.

    boundary_tolerance_sec : float
        Maximum accepted difference between corresponding A/B boundaries.

    merge_adjacent_agreement : bool
        Merge adjacent green regions with identical final labels.

    Returns
    -------
    AdjudicationComparisonResult
        Source metadata, normalized intervals, boundary matches, classified
        comparison regions, and the prefilled final adjudication timeline.

    Raises
    ------
    AdjudicationError
        If record metadata or participant configuration is invalid.

    MissingInputError
        If either completed source annotation is unavailable.

    InvalidAnnotationError
        If source files or generated comparison structures are invalid.
    """
    start_time = perf_counter()

    result: Optional[
        AdjudicationComparisonResult
    ] = None

    try:
        result = _build_adjudication_comparison_impl(
            record=record,
            adjudicator=adjudicator,
            annotators=annotators,
            allowed_adjudicators=(
                allowed_adjudicators
            ),
            boundary_tolerance_sec=(
                boundary_tolerance_sec
            ),
            merge_adjacent_agreement=(
                merge_adjacent_agreement
            ),
        )

        return result

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "build_adjudication_comparison failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "build_adjudication_comparison",
            perf_counter() - start_time,
            subject=clean_string(
                record.get("subject", "")
            ),
            file_tag=clean_string(
                record.get("file_tag", "")
            ),
            regions=(
                len(result.comparison_regions)
                if result is not None
                else 0
            ),
            prefilled_intervals=(
                len(result.prefilled_intervals)
                if result is not None
                else 0
            ),
            unresolved=(
                len(result.unresolved_regions)
                if result is not None
                else 0
            ),
        )


def _build_adjudication_comparison_impl(
    record: Mapping[str, Any],
    adjudicator: str,
    *,
    annotators: Optional[list[str]],
    allowed_adjudicators: Optional[list[str]],
    boundary_tolerance_sec: float,
    merge_adjacent_agreement: bool,
) -> AdjudicationComparisonResult:
    """
    Build the initial adjudication comparison without UI behavior.
    """
    if (
        not np.isfinite(boundary_tolerance_sec)
        or boundary_tolerance_sec < 0
    ):
        raise ValueError(
            "boundary_tolerance_sec must be finite and nonnegative."
        )

    # Validate required selected-record metadata.
    record_output_path = get_required_record_value(
        record,
        "output_path",
    )
    subject = get_required_record_value(
        record,
        "subject",
    )
    encounter = get_required_record_value(
        record,
        "encounter",
    )
    file_tag = get_required_record_value(
        record,
        "file_tag",
    )

    namespace = clean_string(
        record.get("namespace", "")
    )

    adjudicator_name = validate_adjudicator(
        adjudicator,
        allowed_adjudicators=allowed_adjudicators,
    )

    # ------------------------------------------------------------------
    # Discover exactly two configured completed source annotations.
    # ------------------------------------------------------------------
    discovered_sources = (
        discover_source_annotation_files(
            record_output_path=record_output_path,
            subject=subject,
            file_tag=file_tag,
            annotators=annotators,
        )
    )

    source_a, source_b = (
        require_ready_source_annotation_files(
            discovered_sources
        )
    )

    # ------------------------------------------------------------------
    # Load and validate both complete source timelines.
    # ------------------------------------------------------------------
    (
        intervals_a,
        intervals_b,
        validation_warnings,
    ) = load_and_validate_source_pair(
        source_a=source_a,
        source_b=source_b,
    )

    validate_sources_match_selected_record(
        intervals_a=intervals_a,
        intervals_b=intervals_b,
        subject=subject,
        encounter=encounter,
        file_tag=file_tag,
    )

    # ------------------------------------------------------------------
    # Extract and reconcile compatible A/B boundaries.
    # ------------------------------------------------------------------
    (
        boundaries_a,
        boundaries_b,
        boundary_matches,
    ) = extract_and_match_source_boundaries(
        intervals_a=intervals_a,
        intervals_b=intervals_b,
        tolerance_sec=boundary_tolerance_sec,
    )

    # ------------------------------------------------------------------
    # Build the atomic combined timeline.
    # ------------------------------------------------------------------
    timeline_segments = (
        build_combined_timeline_segments(
            intervals_a=intervals_a,
            intervals_b=intervals_b,
            boundaries_a=boundaries_a,
            boundaries_b=boundaries_b,
            boundary_matches=boundary_matches,
        )
    )

    # ------------------------------------------------------------------
    # Classify regions as agreement, disagreement, or missing coverage.
    # ------------------------------------------------------------------
    comparison_regions = (
        classify_comparison_regions(
            segments=timeline_segments,
            boundary_matches=boundary_matches,
        )
    )

    # ------------------------------------------------------------------
    # Prefill green intervals and leave red/gray intervals unlabeled.
    # ------------------------------------------------------------------
    prefilled_intervals = (
        generate_prefilled_adjudication_timeline(
            regions=comparison_regions,
            adjudicator=adjudicator_name,
            allowed_adjudicators=(
                allowed_adjudicators
            ),
            merge_adjacent_agreement=(
                merge_adjacent_agreement
            ),
        )
    )

    created_at = utc_now_iso()

    return AdjudicationComparisonResult(
        adjudicator=adjudicator_name,
        subject=subject,
        encounter=encounter,
        namespace=namespace,
        file_tag=file_tag,
        source_a=source_a,
        source_b=source_b,
        annotator_a_intervals=intervals_a,
        annotator_b_intervals=intervals_b,
        boundary_matches=boundary_matches,
        comparison_regions=comparison_regions,
        prefilled_intervals=prefilled_intervals,
        validation_issues=validation_warnings,
        boundary_tolerance_sec=float(
            boundary_tolerance_sec
        ),
        created_at=created_at,
    )

