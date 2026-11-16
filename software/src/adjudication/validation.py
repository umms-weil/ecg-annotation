"""
Validation of source annotation timelines and cross-annotator consistency.
"""

from __future__ import annotations

from time import perf_counter
from typing import Optional

import numpy as np

from .config import (
    MINIMUM_VALID_INTERVAL_SEC,
    RHYTHMS_REQUIRING_EXPLANATION,
    SOURCE_CONTINUITY_TOLERANCE_SEC,
    VALID_CPR_VALUES,
    VALID_TERMINAL_EVENT_STATUSES,
    DisagreementReason,
    InputReadinessStatus,
)
from .exceptions import InvalidAnnotationError
from .models import (
    AnnotationInterval,
    SourceAnnotationFile,
    ValidationIssue,
    ValidationResult,
)
from .loading import load_source_annotation_pair
from .utilities import (
    _perf_log,
    clean_string,
)

# =============================================================================
# Source interval validation
# =============================================================================

def append_validation_issue(
    issues: list[ValidationIssue],
    *,
    code: str,
    message: str,
    severity: str = "error",
    interval: Optional[AnnotationInterval] = None,
    row_index: Optional[int] = None,
    start: Optional[float] = None,
    end: Optional[float] = None,
) -> None:
    """
    Append one structured validation issue.

    Parameters
    ----------
    issues : list[ValidationIssue]
        Mutable collection receiving the new issue.

    code : str
        Stable machine-readable issue code.

    message : str
        Human-readable explanation.

    severity : str
        Usually ``error`` or ``warning``.

    interval : AnnotationInterval or None
        Optional interval used to populate source row and boundary details.

    row_index : int or None
        Explicit source row. Used when no interval object is available.

    start, end : float or None
        Optional interval boundaries.

    Notes
    -----
    Explicit arguments override values derived from ``interval``.
    """
    if interval is not None:
        if row_index is None:
            row_index = interval.source_row

        if start is None:
            start = interval.start

        if end is None:
            end = interval.end

    issues.append(
        ValidationIssue(
            code=code,
            message=message,
            severity=severity,
            row_index=row_index,
            start=start,
            end=end,
        )
    )


def validate_interval_question_logic(
    interval: AnnotationInterval,
) -> list[ValidationIssue]:
    """
    Validate CPR, rhythm, and explanation values for one source interval.

    Parameters
    ----------
    interval : AnnotationInterval
        Source annotation interval to validate.

    Returns
    -------
    list[ValidationIssue]
        Question-logic errors and warnings.

    Validation rules
    ----------------
    - CPR must be Yes, No, or Unable to Determine.
    - CPR No requires a rhythm label.
    - CPR No with rhythm Other or Unable to Determine requires explanation.
    - CPR Unable to Determine requires explanation.
    - CPR Yes normally has no rhythm label. A populated rhythm is retained but
      reported as a warning.
    """
    issues: list[ValidationIssue] = []

    cpr = clean_string(interval.cpr)
    rhythm = clean_string(interval.rhythm_label)
    explanation = clean_string(
        interval.rhythm_expl
    )

    if cpr not in VALID_CPR_VALUES:
        append_validation_issue(
            issues,
            code="invalid_cpr_value",
            message=(
                f"{interval.source_alias} row "
                f"{interval.source_row} has unsupported CPR value "
                f"{cpr!r}."
            ),
            interval=interval,
        )
        return issues

    if cpr == "No":
        if not rhythm:
            append_validation_issue(
                issues,
                code="missing_rhythm_label",
                message=(
                    f"{interval.source_alias} row "
                    f"{interval.source_row} has CPR No but no rhythm label."
                ),
                interval=interval,
            )

        elif (
            rhythm in RHYTHMS_REQUIRING_EXPLANATION
            and not explanation
        ):
            append_validation_issue(
                issues,
                code="missing_rhythm_explanation",
                message=(
                    f"{interval.source_alias} row "
                    f"{interval.source_row} uses rhythm {rhythm!r} "
                    "without the required explanation."
                ),
                interval=interval,
            )

    elif cpr == "Unable to Determine":
        if not explanation:
            append_validation_issue(
                issues,
                code="missing_cpr_explanation",
                message=(
                    f"{interval.source_alias} row "
                    f"{interval.source_row} has CPR Unable to Determine "
                    "without the required explanation."
                ),
                interval=interval,
            )

        if rhythm:
            append_validation_issue(
                issues,
                code="unexpected_rhythm_label",
                message=(
                    f"{interval.source_alias} row "
                    f"{interval.source_row} has CPR Unable to Determine "
                    f"but also contains rhythm {rhythm!r}."
                ),
                severity="warning",
                interval=interval,
            )

    elif cpr == "Yes" and rhythm:
        append_validation_issue(
            issues,
            code="unexpected_rhythm_label",
            message=(
                f"{interval.source_alias} row "
                f"{interval.source_row} has CPR Yes but also contains "
                f"rhythm {rhythm!r}."
            ),
            severity="warning",
            interval=interval,
        )

    return issues


def validate_source_interval_timeline(
    intervals: list[AnnotationInterval],
    source: SourceAnnotationFile,
    *,
    continuity_tolerance_sec: float = SOURCE_CONTINUITY_TOLERANCE_SEC,
) -> ValidationResult:
    """
    Validate one source annotator timeline with timing diagnostics.

    Parameters
    ----------
    intervals : list[AnnotationInterval]
        Chronologically normalized source intervals.

    source : SourceAnnotationFile
        Metadata for the source annotation CSV.

    continuity_tolerance_sec : float
        Small numerical tolerance used for gap/overlap checks.

    Returns
    -------
    ValidationResult
        Structured validation result containing all detected issues.

    Notes
    -----
    This function reports all detectable issues rather than failing after the
    first one. Use ``require_valid_source_interval_timeline`` when invalid
    sources should raise an exception.
    """
    start_time = perf_counter()
    result = ValidationResult(valid=False)

    try:
        result = _validate_source_interval_timeline_impl(
            intervals=intervals,
            source=source,
            continuity_tolerance_sec=(
                continuity_tolerance_sec
            ),
        )

        return result

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "validate_source_interval_timeline failed:",
            f"alias={source.alias}",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "validate_source_interval_timeline",
            perf_counter() - start_time,
            alias=source.alias,
            intervals=len(intervals),
            valid=result.valid,
            errors=len(result.errors),
            warnings=len(result.warnings),
        )


def _validate_source_interval_timeline_impl(
    intervals: list[AnnotationInterval],
    source: SourceAnnotationFile,
    *,
    continuity_tolerance_sec: float,
) -> ValidationResult:
    """
    Validate one source timeline without timing or UI behavior.
    """
    issues: list[ValidationIssue] = []

    if not intervals:
        append_validation_issue(
            issues,
            code="empty_timeline",
            message=(
                f"{source.alias} contains no annotation intervals."
            ),
        )

        return ValidationResult(
            valid=False,
            issues=issues,
        )

    if (
        not np.isfinite(continuity_tolerance_sec)
        or continuity_tolerance_sec < 0
    ):
        raise ValueError(
            "continuity_tolerance_sec must be finite and nonnegative."
        )

    expected_user = clean_string(
        source.username
    )

    # Metadata from the first interval becomes the expected record identity.
    first_interval = intervals[0]

    expected_subject = clean_string(
        first_interval.subject
    )
    expected_encounter = clean_string(
        first_interval.encounter
    )
    expected_namespace = clean_string(
        first_interval.namespace
    )
    expected_file_tag = clean_string(
        first_interval.file_tag
    )

    if not expected_subject:
        append_validation_issue(
            issues,
            code="missing_subject",
            message=(
                f"{source.alias} does not contain a subject identifier."
            ),
            interval=first_interval,
        )

    if not expected_encounter:
        append_validation_issue(
            issues,
            code="missing_encounter",
            message=(
                f"{source.alias} does not contain an encounter identifier."
            ),
            interval=first_interval,
        )

    if not expected_file_tag:
        append_validation_issue(
            issues,
            code="missing_file_tag",
            message=(
                f"{source.alias} does not contain a waveform file tag."
            ),
            interval=first_interval,
        )

    previous_interval: Optional[
        AnnotationInterval
    ] = None

    for interval_index, interval in enumerate(
        intervals
    ):
        # --------------------------------------------------------------
        # Validate finite, positive-duration boundaries.
        # --------------------------------------------------------------
        if (
            not np.isfinite(interval.start)
            or not np.isfinite(interval.end)
        ):
            append_validation_issue(
                issues,
                code="invalid_timestamp",
                message=(
                    f"{source.alias} row {interval.source_row} "
                    "contains a non-finite boundary."
                ),
                interval=interval,
            )

        elif (
            interval.end - interval.start
            < MINIMUM_VALID_INTERVAL_SEC
        ):
            append_validation_issue(
                issues,
                code="invalid_duration",
                message=(
                    f"{source.alias} row {interval.source_row} "
                    "has end less than or equal to start."
                ),
                interval=interval,
            )

        # --------------------------------------------------------------
        # Validate row identity and record consistency.
        # --------------------------------------------------------------
        if clean_string(interval.user) != expected_user:
            append_validation_issue(
                issues,
                code="source_user_mismatch",
                message=(
                    f"{source.alias} row {interval.source_row} "
                    f"contains user {interval.user!r}; expected "
                    f"{expected_user!r}."
                ),
                interval=interval,
            )

        if (
            clean_string(interval.subject)
            != expected_subject
        ):
            append_validation_issue(
                issues,
                code="inconsistent_subject",
                message=(
                    f"{source.alias} row {interval.source_row} "
                    "contains a different subject identifier."
                ),
                interval=interval,
            )

        if (
            clean_string(interval.encounter)
            != expected_encounter
        ):
            append_validation_issue(
                issues,
                code="inconsistent_encounter",
                message=(
                    f"{source.alias} row {interval.source_row} "
                    "contains a different encounter identifier."
                ),
                interval=interval,
            )

        if (
            clean_string(interval.namespace)
            != expected_namespace
        ):
            append_validation_issue(
                issues,
                code="inconsistent_namespace",
                message=(
                    f"{source.alias} row {interval.source_row} "
                    "contains a different namespace."
                ),
                interval=interval,
            )

        if (
            clean_string(interval.file_tag)
            != expected_file_tag
        ):
            append_validation_issue(
                issues,
                code="inconsistent_file_tag",
                message=(
                    f"{source.alias} row {interval.source_row} "
                    "contains a different waveform file tag."
                ),
                interval=interval,
            )

        # --------------------------------------------------------------
        # Apply the same CPR/rhythm requirements used by annotation mode.
        # --------------------------------------------------------------
        issues.extend(
            validate_interval_question_logic(
                interval
            )
        )

        # --------------------------------------------------------------
        # Validate timeline ordering, gaps, and overlaps.
        # --------------------------------------------------------------
        if previous_interval is not None:
            boundary_delta = (
                interval.start
                - previous_interval.end
            )

            if (
                boundary_delta
                > continuity_tolerance_sec
            ):
                append_validation_issue(
                    issues,
                    code=(
                        DisagreementReason
                        .INVALID_GAP
                        .value
                    ),
                    message=(
                        f"{source.alias} has a gap of "
                        f"{boundary_delta:.9f} seconds between "
                        f"source rows {previous_interval.source_row} "
                        f"and {interval.source_row}."
                    ),
                    row_index=interval.source_row,
                    start=previous_interval.end,
                    end=interval.start,
                )

            elif (
                boundary_delta
                < -continuity_tolerance_sec
            ):
                append_validation_issue(
                    issues,
                    code=(
                        DisagreementReason
                        .INVALID_OVERLAP
                        .value
                    ),
                    message=(
                        f"{source.alias} has an overlap of "
                        f"{abs(boundary_delta):.9f} seconds between "
                        f"source rows {previous_interval.source_row} "
                        f"and {interval.source_row}."
                    ),
                    row_index=interval.source_row,
                    start=interval.start,
                    end=previous_interval.end,
                )

            elif interval.start < previous_interval.start:
                append_validation_issue(
                    issues,
                    code="out_of_order_interval",
                    message=(
                        f"{source.alias} row {interval.source_row} "
                        "is not in chronological order."
                    ),
                    interval=interval,
                )

        previous_interval = interval

    # ------------------------------------------------------------------
    # Validate completion metadata.
    #
    # Earlier rows should not be marked complete. The final row of a completed
    # source must carry the completion flag.
    # ------------------------------------------------------------------
    for interval in intervals[:-1]:
        if interval.waveform_complete:
            append_validation_issue(
                issues,
                code="early_completion_flag",
                message=(
                    f"{source.alias} row {interval.source_row} "
                    "is marked waveform_complete before the final interval."
                ),
                interval=interval,
            )

    final_interval = intervals[-1]

    if source.complete and not final_interval.waveform_complete:
        append_validation_issue(
            issues,
            code="missing_final_completion_flag",
            message=(
                f"{source.alias} uses a COMPLETE filename but its final "
                "interval is not marked waveform_complete."
            ),
            interval=final_interval,
        )

    final_status = clean_string(
        final_interval.terminal_event_status
    )

    if source.complete:
        if not final_status:
            append_validation_issue(
                issues,
                code="missing_terminal_event_status",
                message=(
                    f"{source.alias} is complete but its final interval "
                    "does not contain terminal_event_status."
                ),
                severity="warning",
                interval=final_interval,
            )

        elif (
            final_status
            not in VALID_TERMINAL_EVENT_STATUSES
        ):
            append_validation_issue(
                issues,
                code="invalid_terminal_event_status",
                message=(
                    f"{source.alias} final interval contains unsupported "
                    f"terminal_event_status {final_status!r}."
                ),
                interval=final_interval,
            )

    valid = not any(
        issue.severity == "error"
        for issue in issues
    )

    return ValidationResult(
        valid=valid,
        issues=issues,
    )


def require_valid_source_interval_timeline(
    intervals: list[AnnotationInterval],
    source: SourceAnnotationFile,
    *,
    continuity_tolerance_sec: float = SOURCE_CONTINUITY_TOLERANCE_SEC,
) -> ValidationResult:
    """
    Validate one source timeline and raise when errors are present.

    Parameters
    ----------
    intervals : list[AnnotationInterval]
        Source intervals to validate.

    source : SourceAnnotationFile
        Source annotation metadata.

    continuity_tolerance_sec : float
        Numerical tolerance for source gap/overlap detection.

    Returns
    -------
    ValidationResult
        Successful validation result, including non-fatal warnings.

    Raises
    ------
    InvalidAnnotationError
        If one or more validation errors are present.
    """
    start_time = perf_counter()
    result = ValidationResult(valid=False)

    try:
        result = validate_source_interval_timeline(
            intervals=intervals,
            source=source,
            continuity_tolerance_sec=(
                continuity_tolerance_sec
            ),
        )

        if not result.valid:
            source.readiness_status = (
                InputReadinessStatus.INVALID
            )

            source.readiness_message = "; ".join(
                issue.message
                for issue in result.errors
            )

            error_summary = "\n".join(
                f"- [{issue.code}] {issue.message}"
                for issue in result.errors
            )

            raise InvalidAnnotationError(
                f"{source.alias} failed source timeline validation:\n"
                f"{error_summary}"
            )

        source.readiness_status = (
            InputReadinessStatus.READY
        )

        if result.warnings:
            source.readiness_message = "; ".join(
                issue.message
                for issue in result.warnings
            )
        else:
            source.readiness_message = (
                "Completed annotation input is valid."
            )

        return result

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "require_valid_source_interval_timeline failed:",
            f"alias={source.alias}",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "require_valid_source_interval_timeline",
            perf_counter() - start_time,
            alias=source.alias,
            valid=result.valid,
            errors=len(result.errors),
            warnings=len(result.warnings),
        )


def validate_source_pair_consistency(
    intervals_a: list[AnnotationInterval],
    intervals_b: list[AnnotationInterval],
    source_a: SourceAnnotationFile,
    source_b: SourceAnnotationFile,
) -> ValidationResult:
    """
    Validate record identity and coverage consistency across both sources.

    Parameters
    ----------
    intervals_a, intervals_b : list[AnnotationInterval]
        Validated Annotator A and Annotator B timelines.

    source_a, source_b : SourceAnnotationFile
        Source metadata for diagnostics.

    Returns
    -------
    ValidationResult
        Pair-level errors and warnings.

    Notes
    -----
    Different coverage bounds are reported as warnings rather than immediate
    errors. The comparison engine will convert one-sided coverage into gray
    review regions.
    """
    start_time = perf_counter()
    result = ValidationResult(valid=False)

    try:
        result = _validate_source_pair_consistency_impl(
            intervals_a=intervals_a,
            intervals_b=intervals_b,
            source_a=source_a,
            source_b=source_b,
        )

        return result

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "validate_source_pair_consistency failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "validate_source_pair_consistency",
            perf_counter() - start_time,
            valid=result.valid,
            errors=len(result.errors),
            warnings=len(result.warnings),
        )


def _validate_source_pair_consistency_impl(
    intervals_a: list[AnnotationInterval],
    intervals_b: list[AnnotationInterval],
    source_a: SourceAnnotationFile,
    source_b: SourceAnnotationFile,
) -> ValidationResult:
    """
    Validate both source timelines without timing or UI behavior.
    """
    issues: list[ValidationIssue] = []

    if not intervals_a or not intervals_b:
        append_validation_issue(
            issues,
            code="missing_source_timeline",
            message=(
                "Both Annotator A and Annotator B must provide "
                "non-empty timelines."
            ),
        )

        return ValidationResult(
            valid=False,
            issues=issues,
        )

    first_a = intervals_a[0]
    first_b = intervals_b[0]

    identity_fields = [
        "subject",
        "encounter",
        "file_tag",
    ]

    for field_name in identity_fields:
        value_a = clean_string(
            getattr(first_a, field_name)
        )
        value_b = clean_string(
            getattr(first_b, field_name)
        )

        if value_a != value_b:
            append_validation_issue(
                issues,
                code=f"{field_name}_mismatch",
                message=(
                    f"Annotator A and Annotator B have different "
                    f"{field_name} values: {value_a!r} versus "
                    f"{value_b!r}."
                ),
            )

    namespace_a = clean_string(
        first_a.namespace
    )
    namespace_b = clean_string(
        first_b.namespace
    )

    if namespace_a != namespace_b:
        append_validation_issue(
            issues,
            code="namespace_mismatch",
            message=(
                "Annotator A and Annotator B have different namespace "
                f"values: {namespace_a!r} versus {namespace_b!r}."
            ),
            severity="warning",
        )

    start_a = float(intervals_a[0].start)
    end_a = float(intervals_a[-1].end)
    start_b = float(intervals_b[0].start)
    end_b = float(intervals_b[-1].end)

    start_difference = abs(
        start_a - start_b
    )
    end_difference = abs(
        end_a - end_b
    )

    if start_difference > SOURCE_CONTINUITY_TOLERANCE_SEC:
        append_validation_issue(
            issues,
            code="source_start_coverage_mismatch",
            message=(
                "Annotator source timelines begin at different times: "
                f"{source_a.alias}={start_a:.9f}, "
                f"{source_b.alias}={start_b:.9f}, "
                f"difference={start_difference:.9f} seconds."
            ),
            severity="warning",
            start=min(start_a, start_b),
            end=max(start_a, start_b),
        )

    if end_difference > SOURCE_CONTINUITY_TOLERANCE_SEC:
        append_validation_issue(
            issues,
            code="source_end_coverage_mismatch",
            message=(
                "Annotator source timelines end at different times: "
                f"{source_a.alias}={end_a:.9f}, "
                f"{source_b.alias}={end_b:.9f}, "
                f"difference={end_difference:.9f} seconds."
            ),
            severity="warning",
            start=min(end_a, end_b),
            end=max(end_a, end_b),
        )

    overlap_start = max(
        start_a,
        start_b,
    )
    overlap_end = min(
        end_a,
        end_b,
    )

    if overlap_end <= overlap_start:
        append_validation_issue(
            issues,
            code="no_shared_coverage",
            message=(
                "Annotator A and Annotator B timelines do not overlap "
                "in time."
            ),
        )

    valid = not any(
        issue.severity == "error"
        for issue in issues
    )

    return ValidationResult(
        valid=valid,
        issues=issues,
    )


def load_and_validate_source_pair(
    source_a: SourceAnnotationFile,
    source_b: SourceAnnotationFile,
) -> tuple[
    list[AnnotationInterval],
    list[AnnotationInterval],
    list[ValidationIssue],
]:
    """
    Load and fully validate both source annotator timelines.

    Parameters
    ----------
    source_a, source_b : SourceAnnotationFile
        Ready source annotation files assigned to Annotator A and B.

    Returns
    -------
    tuple
        ``(
            annotator_a_intervals,
            annotator_b_intervals,
            validation_warnings
        )``

    Raises
    ------
    InvalidAnnotationError
        If either source timeline or the source pair has validation errors.
    """
    start_time = perf_counter()

    intervals_a: list[AnnotationInterval] = []
    intervals_b: list[AnnotationInterval] = []
    warnings: list[ValidationIssue] = []

    try:
        (
            intervals_a,
            intervals_b,
            warnings,
        ) = _load_and_validate_source_pair_impl(
            source_a=source_a,
            source_b=source_b,
        )

        return (
            intervals_a,
            intervals_b,
            warnings,
        )

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "load_and_validate_source_pair failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "load_and_validate_source_pair",
            perf_counter() - start_time,
            intervals_a=len(intervals_a),
            intervals_b=len(intervals_b),
            warnings=len(warnings),
        )


def _load_and_validate_source_pair_impl(
    source_a: SourceAnnotationFile,
    source_b: SourceAnnotationFile,
) -> tuple[
    list[AnnotationInterval],
    list[AnnotationInterval],
    list[ValidationIssue],
]:
    """
    Load and validate both sources without timing or UI behavior.
    """
    (
        intervals_a,
        intervals_b,
    ) = load_source_annotation_pair(
        source_a=source_a,
        source_b=source_b,
    )

    validation_a = require_valid_source_interval_timeline(
        intervals=intervals_a,
        source=source_a,
    )

    validation_b = require_valid_source_interval_timeline(
        intervals=intervals_b,
        source=source_b,
    )

    pair_validation = validate_source_pair_consistency(
        intervals_a=intervals_a,
        intervals_b=intervals_b,
        source_a=source_a,
        source_b=source_b,
    )

    if not pair_validation.valid:
        error_summary = "\n".join(
            f"- [{issue.code}] {issue.message}"
            for issue in pair_validation.errors
        )

        raise InvalidAnnotationError(
            "Source annotation pair failed validation:\n"
            f"{error_summary}"
        )

    warnings = (
        validation_a.warnings
        + validation_b.warnings
        + pair_validation.warnings
    )

    return (
        intervals_a,
        intervals_b,
        warnings,
    )

