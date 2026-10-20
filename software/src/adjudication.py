"""
Core processing and persistence logic for waveform adjudication.

This module defines the non-UI adjudication contract, including:

- Participant configuration.
- Source annotation schemas.
- Adjudication data models.
- Comparison and workflow statuses.
- Output file conventions.
- Validation types.
- Timing and serialization utilities.

(Note: Comparable to processing.py for Annotation)

PyQt widgets and user-interface callbacks do not belong in this module.
UI behavior should be implemented in ``app.py`` and
``adjudication_callbacks.py``.

All waveform interval boundaries are represented as high-precision,
floating-point UTC epoch seconds.
"""

# =============================================================================
# Imports
# =============================================================================

from __future__ import annotations

import json
import os

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

import numpy as np
import pandas as pd

# =============================================================================
# Configuration and schema constants
# =============================================================================

# Increment this value when saved adjudication state becomes incompatible with
# an earlier schema.
ADJUDICATION_SCHEMA_VERSION: int = 1

ADJUDICATION_RECORD_TYPE: str = "adjudication"
ADJUDICATION_STATE_RECORD_TYPE: str = "adjudication_state"


# ---------------------------------------------------------------------------
# Configured participants
# ---------------------------------------------------------------------------

# Source users whose completed annotation files are eligible for comparison.
# The implementation should use this list rather than scanning arbitrary user
# folders as adjudication inputs.
ANNOTATION_USERS: list[str] = [
    "kwheels",
    "gangidi",
]

# Users permitted to produce adjudication output.
ADJUDICATORS: list[str] = [
    "ghamid",
]

# The current adjudication workflow compares exactly two source annotations.
REQUIRED_ANNOTATOR_COUNT: int = 2

# Reviewer-facing aliases are assigned according to the configured annotator
# order. The original usernames remain available in source metadata.
ANNOTATOR_ALIASES: tuple[str, ...] = (
    "Annotator A",
    "Annotator B",
)

# ---------------------------------------------------------------------------
# Comparison behavior
# ---------------------------------------------------------------------------

# Two corresponding boundaries may be reconciled when their absolute
# difference is no greater than this value.
ADJUDICATION_BOUNDARY_TOLERANCE_SEC: float = 1.0

# Any final interval must have a strictly positive duration. This constant is
# retained separately so the validation policy can be adjusted later.
# Minimum of 1 second per annotation requirements
MINIMUM_VALID_INTERVAL_SEC: float = 1.0

# Tolerance used only when deciding whether sequential source intervals touch.
# This is intentionally much smaller than the one-second adjudication boundary
# matching tolerance.
SOURCE_CONTINUITY_TOLERANCE_SEC: float = 1e-6

VALID_CPR_VALUES: frozenset[str] = frozenset(
    {
        "Yes",
        "No",
        "Unable to Determine",
    }
)

RHYTHMS_REQUIRING_EXPLANATION: frozenset[str] = frozenset(
    {
        "Unable to Determine",
        "Other",
    }
)

VALID_TERMINAL_EVENT_STATUSES: frozenset[str] = frozenset(
    {
        "continues_beyond_waveform",
        "does_not_continue_beyond_waveform",
    }
)


# ---------------------------------------------------------------------------
# File and folder names
# ---------------------------------------------------------------------------

ADJUDICATION_FOLDER_NAME: str = "ADJUDICATION"

ANNOTATION_FILENAME_PREFIX: str = "annotations"
ADJUDICATION_FILENAME_PREFIX: str = "adjudication"

COMPLETE_FILENAME_SUFFIX: str = "_COMPLETE"

# Supplemental JSON sidecar for adjudication evaluations
ADJUDICATION_STATE_FILENAME_SUFFIX: str = "_state.json"


# ---------------------------------------------------------------------------
# Required annotation and adjudication columns
# ---------------------------------------------------------------------------

# These fields must be present in source annotation CSV files.
REQUIRED_ANNOTATION_COLUMNS: set[str] = {
    "user",
    "subject",
    "encounter",
    "namespace",
    "file_tag",
    "source_path",
    "cpr",
    "rhythm_label",
    "rhythm_expl",
    "start",
    "end",
    "waveform_complete",
    "terminal_event_status",
    "terminal_event_comment",
}

# These are the original annotation fields retained in adjudication output for
# compatibility with downstream annotation-processing code.
ADJUDICATION_BASE_COLUMNS: list[str] = [
    "user",
    "subject",
    "encounter",
    "namespace",
    "file_tag",
    "source_path",
    "cpr",
    "rhythm_label",
    "rhythm_expl",
    "start",
    "end",
    "waveform_complete",
    "terminal_event_status",
    "terminal_event_comment",
]

# Additional fields identify the record as an adjudication and track when the
# adjudication timeline was created or changed.
ADJUDICATION_ADDITIONAL_COLUMNS: list[str] = [
    "adjudicator",
    "record_type",
    "adjudication_created_at",
    "adjudication_updated_at",
]

ADJUDICATION_OUTPUT_COLUMNS: list[str] = (
    ADJUDICATION_BASE_COLUMNS
    + ADJUDICATION_ADDITIONAL_COLUMNS
)


# ---------------------------------------------------------------------------
# Performance diagnostics
# ---------------------------------------------------------------------------

# Set to False to suppress adjudication performance output.
ADJUDICATION_PERF_DIAGNOSTICS_ENABLED: bool = True


# =============================================================================
# Timed-wrapper convention
# =============================================================================

# Substantive discovery, comparison, validation, and persistence operations
# should use a timed public wrapper and a private implementation.
#
# Example:
#
# def discover_source_annotation_files(
#     record_output_path: str | Path,
#     annotators: Optional[list[str]] = None,
# ) -> list[SourceAnnotationFile]:
#     """
#     Discover source annotation inputs with timing and error diagnostics.
#     """
#     start_time = perf_counter()
#
#     try:
#         return _discover_source_annotation_files_impl(
#             record_output_path=record_output_path,
#             annotators=annotators,
#         )
#
#     except Exception as exc:
#         print(
#             "[ADJUDICATION] "
#             "discover_source_annotation_files failed:",
#             type(exc).__name__,
#             exc,
#         )
#         raise
#
#     finally:
#         _perf_log(
#             "discover_source_annotation_files",
#             perf_counter() - start_time,
#         )
#
#
# def _discover_source_annotation_files_impl(
#     record_output_path: str | Path,
#     annotators: Optional[list[str]] = None,
# ) -> list[SourceAnnotationFile]:
#     """
#     Perform source discovery without timing or UI behavior.
#     """
#     raise NotImplementedError

# =============================================================================
# Status and reason definitions
# =============================================================================

class ComparisonStatus(str, Enum):
    """
    Classification assigned to one comparison region.

    Values
    ------
    AGREEMENT
        Both annotators provide coverage and agree under the configured
        boundary, CPR, and rhythm rules.

    UNRESOLVED_DISAGREEMENT
        The annotators disagree and the adjudicator has not explicitly
        resolved the region.

    RESOLVED_DISAGREEMENT
        A disagreement was explicitly resolved by the adjudicator.

    MISSING_COVERAGE
        One or both source timelines do not provide valid coverage.
    """

    AGREEMENT = "agreement"
    UNRESOLVED_DISAGREEMENT = "unresolved_disagreement"
    RESOLVED_DISAGREEMENT = "resolved_disagreement"
    MISSING_COVERAGE = "missing_coverage"


class AdjudicationStatus(str, Enum):
    """
    Overall workflow state for one waveform adjudication.

    Values
    ------
    NOT_READY
        Required source inputs are missing, incomplete, or invalid.

    DRAFT
        Adjudication is editable and has not been finalized.

    COMPLETE
        Adjudication passed final validation and was finalized.

    REOPENED
        A completed adjudication was explicitly reopened for editing.
    """

    NOT_READY = "not_ready"
    DRAFT = "draft"
    COMPLETE = "complete"
    REOPENED = "reopened"


class InputReadinessStatus(str, Enum):
    """
    Readiness state for one source annotation input.

    Values
    ------
    READY
        Exactly one valid completed source file is available.

    MISSING
        No eligible completed source file was found.

    INCOMPLETE
        A source file exists but is not marked complete.

    DUPLICATE
        More than one eligible source file was found for the same annotator.

    INVALID
        The source file exists but fails schema or interval validation.
    """

    READY = "ready"
    MISSING = "missing"
    INCOMPLETE = "incomplete"
    DUPLICATE = "duplicate"
    INVALID = "invalid"


class DisagreementReason(str, Enum):
    """
    Reason explaining why a region requires review.
    """

    BOUNDARY_OUTSIDE_TOLERANCE = "boundary_outside_tolerance"
    CPR_MISMATCH = "cpr_mismatch"
    RHYTHM_MISMATCH = "rhythm_mismatch"
    ADJACENT_LABEL_MISMATCH = "adjacent_label_mismatch"
    ANNOTATOR_A_ONLY = "annotator_a_only"
    ANNOTATOR_B_ONLY = "annotator_b_only"
    MISSING_COVERAGE = "missing_coverage"
    INCOMPLETE_INPUT = "incomplete_input"
    INVALID_GAP = "invalid_gap"
    INVALID_OVERLAP = "invalid_overlap"


# Convenient immutable collection for validation and serialization checks.
DISAGREEMENT_REASONS: frozenset[str] = frozenset(
    reason.value
    for reason in DisagreementReason
)

# =============================================================================
# Public exception types
# =============================================================================

class AdjudicationError(Exception):
    """
    Base exception for adjudication processing failures.

    Callers may catch this exception when they want to handle all expected
    adjudication errors through one code path.
    """


class MissingInputError(AdjudicationError):
    """
    Raised when a required source annotation file cannot be found.
    """


class DuplicateInputError(AdjudicationError):
    """
    Raised when multiple eligible source files are found for one annotator.
    """


class InvalidAnnotationError(AdjudicationError):
    """
    Raised when a source or final annotation timeline is structurally invalid.
    """


class UnsupportedSchemaError(AdjudicationError):
    """
    Raised when a state file uses an unsupported adjudication schema version.
    """


class SourceFilesChangedError(AdjudicationError):
    """
    Raised when source annotation files changed after adjudication began.
    """


class AdjudicationPathError(AdjudicationError):
    """
    Raised when an output path is invalid or could overlap source annotations.
    """


# =============================================================================
# Data models
# =============================================================================

@dataclass
class SourceAnnotationFile:
    """
    Describe one source annotation CSV.

    Parameters
    ----------
    username : str
        Original configured annotator username.

    alias : str
        Reviewer-facing alias, such as ``Annotator A``.

    path : pathlib.Path
        Absolute path to the source annotation CSV.

    size_bytes : int
        File size captured when adjudication begins.

    modified_at : str
        Source modification time represented as ISO-8601 UTC.

    complete : bool
        Whether the file represents a completed annotation.

    readiness_status : InputReadinessStatus
        Current discovery or validation status.

    readiness_message : str
        Human-readable explanation of the readiness status.
    """

    username: str
    alias: str
    path: Path
    size_bytes: int
    modified_at: str
    complete: bool

    readiness_status: InputReadinessStatus = (
        InputReadinessStatus.READY
    )
    readiness_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """
        Return a JSON-safe source-file representation.

        Returns
        -------
        dict[str, Any]
            Source metadata suitable for the state JSON.
        """
        return {
            "username": self.username,
            "alias": self.alias,
            "path": str(self.path),
            "size_bytes": int(self.size_bytes),
            "modified_at": self.modified_at,
            "complete": bool(self.complete),
            "readiness_status": self.readiness_status.value,
            "readiness_message": self.readiness_message,
        }


@dataclass
class AnnotationInterval:
    """
    Represent one normalized interval from a source annotator CSV.

    ``start`` and ``end`` remain absolute floating-point UTC epoch seconds.
    Source-row information is retained for diagnostics only.
    """

    user: str
    subject: str
    encounter: str
    namespace: str
    file_tag: str
    source_path: str

    cpr: str
    rhythm_label: str
    rhythm_expl: str

    start: float
    end: float

    waveform_complete: bool
    terminal_event_status: str
    terminal_event_comment: str

    source_alias: str
    source_row: int

    @property
    def duration(self) -> float:
        """
        Return interval duration in seconds.

        Returns
        -------
        float
            ``end - start`` without deliberate rounding.
        """
        return float(self.end - self.start)

    def label_signature(self) -> tuple[str, str]:
        """
        Return values used for CPR/rhythm agreement comparisons.

        Returns
        -------
        tuple[str, str]
            Normalized ``(cpr, rhythm_label)`` values.
        """
        return (
            self.cpr.strip(),
            self.rhythm_label.strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable representation of the interval.

        Returns
        -------
        dict[str, Any]
            Dataclass fields represented as standard Python values.
        """
        return asdict(self)


@dataclass
class TimelineBoundary:
    """
    Represent one boundary in a source annotation timeline.

    Parameters
    ----------
    boundary_id : str
        Stable identifier within one source timeline.

    source_alias : str
        Reviewer-facing source alias, such as ``Annotator A``.

    boundary_index : int
        Zero-based boundary position in the source timeline.

    boundary_type : str
        One of ``start``, ``internal``, or ``end``.

    time : float
        Absolute floating-point UTC epoch seconds.

    interval_before : AnnotationInterval or None
        Interval immediately before the boundary.

    interval_after : AnnotationInterval or None
        Interval immediately after the boundary.

    Notes
    -----
    Internal boundaries retain both neighboring intervals so CPR and rhythm
    compatibility can be checked before midpoint reconciliation.
    """

    boundary_id: str
    source_alias: str
    boundary_index: int
    boundary_type: str
    time: float

    interval_before: Optional[
        AnnotationInterval
    ] = None

    interval_after: Optional[
        AnnotationInterval
    ] = None

    def to_dict(self) -> dict[str, Any]:
        """
        Return a JSON-safe boundary representation.

        Returns
        -------
        dict[str, Any]
            Serialized boundary and adjacent interval information.
        """
        return {
            "boundary_id": self.boundary_id,
            "source_alias": self.source_alias,
            "boundary_index": int(
                self.boundary_index
            ),
            "boundary_type": self.boundary_type,
            "time": float(self.time),
            "interval_before": (
                self.interval_before.to_dict()
                if self.interval_before is not None
                else None
            ),
            "interval_after": (
                self.interval_after.to_dict()
                if self.interval_after is not None
                else None
            ),
        }

@dataclass
class BoundaryMatch:
    """
    Describe an attempted or accepted source-boundary match.

    Parameters
    ----------
    boundary_id : str
        Stable identifier for this comparison result.

    boundary_type : str
        Boundary classification: ``start``, ``internal``, or ``end``.

    boundary_index_a, boundary_index_b : int or None
        Original boundary positions in the Annotator A and B timelines.

    boundary_a, boundary_b : float or None
        Original absolute UTC epoch boundary timestamps.

    difference_seconds : float or None
        Absolute difference between matched source boundaries.

    midpoint : float or None
        Reconciled midpoint for an accepted boundary match.

    within_tolerance : bool
        Whether the source boundaries are within the configured tolerance.

    adjacent_labels_compatible : bool
        Whether CPR and rhythm values agree on both applicable sides.

    matched : bool
        Whether the two boundaries were accepted as one reconciled boundary.

    nearest_other_boundary : float or None
        Nearest opposite-source boundary for an unmatched boundary.

    nearest_difference_seconds : float or None
        Distance to the nearest opposite-source boundary.

    reasons : list[str]
        One or more machine-readable disagreement reasons.
    """

    boundary_id: str
    boundary_type: str

    boundary_index_a: Optional[int]
    boundary_index_b: Optional[int]

    boundary_a: Optional[float]
    boundary_b: Optional[float]

    difference_seconds: Optional[float]
    midpoint: Optional[float]

    within_tolerance: bool
    adjacent_labels_compatible: bool
    matched: bool

    nearest_other_boundary: Optional[float] = None
    nearest_difference_seconds: Optional[float] = None

    reasons: list[str] = field(
        default_factory=list
    )

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable boundary-match representation.

        Returns
        -------
        dict[str, Any]
            Boundary-match fields converted to standard Python values.
        """
        return asdict(self)

@dataclass
class ComparisonRegion:
    """
    Represent one region in the combined A/B comparison timeline.

    Regions are produced by splitting the timeline at all relevant
    reconciled and unmatched boundaries.
    """

    region_id: str
    start: float
    end: float
    status: ComparisonStatus

    reasons: list[str] = field(
        default_factory=list
    )

    annotation_a: Optional[AnnotationInterval] = None
    annotation_b: Optional[AnnotationInterval] = None

    resolved: bool = False
    resolved_at: Optional[str] = None

    @property
    def duration(self) -> float:
        """
        Return region duration in seconds.
        """
        return float(self.end - self.start)

    @property
    def requires_resolution(self) -> bool:
        """
        Return whether this region requires explicit adjudicator resolution.

        Returns
        -------
        bool
            True for unresolved disagreements or missing coverage.
        """
        return self.status in {
            ComparisonStatus.UNRESOLVED_DISAGREEMENT,
            ComparisonStatus.MISSING_COVERAGE,
        }

    def to_dict(self) -> dict[str, Any]:
        """
        Return a JSON-safe comparison-region representation.
        """
        return {
            "region_id": self.region_id,
            "start": float(self.start),
            "end": float(self.end),
            "status": self.status.value,
            "reasons": list(self.reasons),
            "annotation_a": (
                self.annotation_a.to_dict()
                if self.annotation_a is not None
                else None
            ),
            "annotation_b": (
                self.annotation_b.to_dict()
                if self.annotation_b is not None
                else None
            ),
            "resolved": bool(self.resolved),
            "resolved_at": self.resolved_at,
        }


@dataclass
class AdjudicationInterval:
    """
    Represent one editable interval in the final adjudication timeline.

    The field names intentionally retain compatibility with the original
    annotation CSV schema.
    """

    user: str
    subject: str
    encounter: str
    namespace: str
    file_tag: str
    source_path: str

    cpr: str
    rhythm_label: str
    rhythm_expl: str

    start: float
    end: float

    waveform_complete: bool = False
    terminal_event_status: str = ""
    terminal_event_comment: str = ""

    adjudicator: str = ""
    record_type: str = ADJUDICATION_RECORD_TYPE
    adjudication_created_at: str = ""
    adjudication_updated_at: str = ""

    @property
    def duration(self) -> float:
        """
        Return final interval duration in seconds.
        """
        return float(self.end - self.start)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the interval into one adjudication CSV row.

        Returns
        -------
        dict[str, Any]
            Dictionary keyed by ``ADJUDICATION_OUTPUT_COLUMNS`` fields.
        """
        return {
            "user": self.user,
            "subject": self.subject,
            "encounter": self.encounter,
            "namespace": self.namespace,
            "file_tag": self.file_tag,
            "source_path": self.source_path,
            "cpr": self.cpr,
            "rhythm_label": self.rhythm_label,
            "rhythm_expl": self.rhythm_expl,
            "start": float(self.start),
            "end": float(self.end),
            "waveform_complete": bool(
                self.waveform_complete
            ),
            "terminal_event_status": (
                self.terminal_event_status
            ),
            "terminal_event_comment": (
                self.terminal_event_comment
            ),
            "adjudicator": self.adjudicator,
            "record_type": self.record_type,
            "adjudication_created_at": (
                self.adjudication_created_at
            ),
            "adjudication_updated_at": (
                self.adjudication_updated_at
            ),
        }


@dataclass
class AdjudicationPaths:
    """
    Contain all output paths for one waveform and adjudicator.
    """

    output_directory: Path
    draft_csv: Path
    complete_csv: Path
    state_json: Path

    def to_dict(self) -> dict[str, str]:
        """
        Return a JSON-safe path mapping.
        """
        return {
            "output_directory": str(
                self.output_directory
            ),
            "draft_csv": str(self.draft_csv),
            "complete_csv": str(
                self.complete_csv
            ),
            "state_json": str(self.state_json),
        }


@dataclass
class ValidationIssue:
    """
    Describe one source or final-timeline validation issue.

    Parameters
    ----------
    code : str
        Issue code.

    message : str
        Explanation.

    severity : str
        Usually ``error`` or ``warning``.

    row_index : int or None
        Source CSV row associated with the issue, if applicable.

    start, end : float or None
        Optional interval coordinates associated with the issue.
    """

    code: str
    message: str
    severity: str = "error"

    row_index: Optional[int] = None
    start: Optional[float] = None
    end: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable validation issue.
        """
        return asdict(self)


@dataclass
class ValidationResult:
    """
    Collect validation issues for one source or final timeline.
    """

    valid: bool
    issues: list[ValidationIssue] = field(
        default_factory=list
    )

    @property
    def errors(self) -> list[ValidationIssue]:
        """
        Return issues classified as errors.
        """
        return [
            issue
            for issue in self.issues
            if issue.severity == "error"
        ]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """
        Return issues classified as warnings.
        """
        return [
            issue
            for issue in self.issues
            if issue.severity == "warning"
        ]


@dataclass
class AdjudicationComparisonResult:
    """
    Contain the complete non-UI result of comparing two annotators.

    This object is the primary result consumed by adjudication callbacks.
    """

    adjudicator: str
    subject: str
    encounter: str
    namespace: str
    file_tag: str

    source_a: SourceAnnotationFile
    source_b: SourceAnnotationFile

    annotator_a_intervals: list[
        AnnotationInterval
    ] = field(default_factory=list)

    annotator_b_intervals: list[
        AnnotationInterval
    ] = field(default_factory=list)

    boundary_matches: list[
        BoundaryMatch
    ] = field(default_factory=list)

    comparison_regions: list[
        ComparisonRegion
    ] = field(default_factory=list)

    prefilled_intervals: list[
        AdjudicationInterval
    ] = field(default_factory=list)

    validation_issues: list[
        ValidationIssue
    ] = field(default_factory=list)

    boundary_tolerance_sec: float = (
        ADJUDICATION_BOUNDARY_TOLERANCE_SEC
    )

    created_at: str = ""

    @property
    def unresolved_regions(
        self,
    ) -> list[ComparisonRegion]:
        """
        Return comparison regions still requiring explicit resolution.
        """
        return [
            region
            for region in self.comparison_regions
            if region.requires_resolution
            and not region.resolved
        ]

    @property
    def ready_for_review(self) -> bool:
        """
        Return whether both source annotation inputs are ready.
        """
        return (
            self.source_a.readiness_status
            == InputReadinessStatus.READY
            and self.source_b.readiness_status
            == InputReadinessStatus.READY
        )

# =============================================================================
# General utilities
# =============================================================================

def _perf_log(
    operation: str,
    elapsed_seconds: float,
    **details: Any,
) -> None:
    """
    Print one standardized adjudication performance diagnostic.
    Provides sources of slowdowns and errors for development.

    Parameters
    ----------
    operation : str
        Name of the timed operation.

    elapsed_seconds : float
        Total elapsed wall-clock time in seconds.

    **details : Any
        Additional key/value details appended to the diagnostic line.

    Notes
    -----
    Output uses the prefix ``[PERF][ADJ]`` so adjudication measurements can be
    filtered independently from existing annotation performance logs.
    """
    if not ADJUDICATION_PERF_DIAGNOSTICS_ENABLED:
        return

    detail_text = " ".join(
        f"{key}={value}"
        for key, value in details.items()
    )

    if detail_text:
        detail_text = f" | {detail_text}"

    print(
        f"[PERF][ADJ] {operation}: "
        f"{elapsed_seconds:.4f} sec"
        f"{detail_text}"
    )


def utc_now_iso() -> str:
    """
    Return the current UTC time as an ISO-8601 string.

    Returns
    -------
    str
        UTC timestamp with microsecond precision and a trailing ``Z``.
    """
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def clean_string(value: Any) -> str:
    """
    Convert a scalar value to a stripped string.

    Parameters
    ----------
    value : Any
        Input scalar, potentially including a Pandas missing value.

    Returns
    -------
    str
        Empty string for missing values; otherwise a stripped string.

    Notes
    -----
    This helper is intended for scalar CSV values, not arrays or Series.
    """
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        # Non-scalar objects are not expected, but converting them to a string
        # is safer than failing during diagnostic processing.
        pass

    return str(value).strip()


def coerce_bool(value: Any) -> bool:
    """
    Convert a common CSV boolean representation into ``bool``.

    Parameters
    ----------
    value : Any
        Boolean-like scalar value.

    Returns
    -------
    bool
        True for values such as ``True``, ``1``, ``yes``, or ``y``.
    """
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass

    normalized = str(value).strip().lower()

    return normalized in {
        "true",
        "1",
        "yes",
        "y",
    }


def validate_epoch_seconds(
    value: Any,
    field_name: str,
) -> float:
    """
    Validate and return a floating-point UTC epoch timestamp.

    Parameters
    ----------
    value : Any
        Candidate numeric timestamp.

    field_name : str
        Field name included in validation errors.

    Returns
    -------
    float
        Finite floating-point epoch seconds without deliberate rounding.

    Raises
    ------
    InvalidAnnotationError
        If the value is non-numeric or non-finite.
    """
    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidAnnotationError(
            f"{field_name} is not numeric: {value!r}"
        ) from exc

    if not np.isfinite(numeric_value):
        raise InvalidAnnotationError(
            f"{field_name} is not finite: {value!r}"
        )

    return numeric_value


def stable_numbered_id(
    prefix: str,
    index: int,
) -> str:
    """
    Build a stable zero-padded identifier.

    Parameters
    ----------
    prefix : str
        Identifier prefix, such as ``disagreement`` or ``region``.

    index : int
        One-based or zero-based sequence value selected by the caller.

    Returns
    -------
    str
        Identifier such as ``disagreement_0001``.
    """
    return f"{prefix}_{int(index):04d}"


def json_safe_value(value: Any) -> Any:
    """
    Recursively convert common values into JSON-safe values.

    Parameters
    ----------
    value : Any
        Value to normalize.

    Returns
    -------
    Any
        A value accepted by ``json.dump``.

    Supported conversions
    ---------------------
    - Enum to its string value.
    - Path to string.
    - NumPy scalar to Python scalar.
    - Pandas Timestamp to ISO-8601 UTC.
    - Dataclass to dictionary.
    - Dictionary values recursively.
    - List, tuple, and set values recursively.
    - Pandas/NumPy missing values to ``None``.
    """
    if isinstance(value, Enum):
        return value.value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, np.generic):
        return value.item()

    if isinstance(value, pd.Timestamp):
        timestamp = value

        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")

        return (
            timestamp.tz_convert("UTC")
            .isoformat()
            .replace("+00:00", "Z")
        )

    if is_dataclass(value):
        return {
            str(key): json_safe_value(item)
            for key, item in asdict(value).items()
        }

    if isinstance(value, dict):
        return {
            str(key): json_safe_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            json_safe_value(item)
            for item in value
        ]

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    return value

# =============================================================================
# Adjudication paths and filenames
# =============================================================================

def validate_filename_component(
    value: Any,
    field_name: str,
) -> str:
    """
    Validate a value used as one component of an adjudication filename.

    Parameters
    ----------
    value : Any
        Subject identifier, waveform file tag, or adjudicator username.

    field_name : str
        Human-readable field name included in validation errors.

    Returns
    -------
    str
        Stripped filename component.

    Raises
    ------
    AdjudicationPathError
        If the value is blank, contains a path separator, contains a null
        character, or represents a relative directory component.

    Notes
    -----
    Values are validated rather than silently rewritten. This preserves the
    subject and waveform identifiers used by existing annotation files.
    """
    component = clean_string(value)

    if not component:
        raise AdjudicationPathError(
            f"{field_name} cannot be blank."
        )

    if "\x00" in component:
        raise AdjudicationPathError(
            f"{field_name} contains a null character."
        )

    if component in {".", ".."}:
        raise AdjudicationPathError(
            f"{field_name} cannot be {component!r}."
        )

    # Reject both POSIX and Windows separators so generated names remain safe
    # on every supported operating system.
    if "/" in component or "\\" in component:
        raise AdjudicationPathError(
            f"{field_name} contains a path separator: "
            f"{component!r}"
        )

    return component


def validate_adjudicator(
    adjudicator: Any,
    allowed_adjudicators: Optional[list[str]] = None,
) -> str:
    """
    Validate an adjudicator against the configured allowlist.

    Parameters
    ----------
    adjudicator : Any
        Candidate adjudicator username.

    allowed_adjudicators : list[str] or None
        Optional allowlist override. When omitted, ``ADJUDICATORS`` is used.

    Returns
    -------
    str
        Validated adjudicator username.

    Raises
    ------
    AdjudicationPathError
        If the adjudicator is blank or is not configured.
    """
    adjudicator_name = validate_filename_component(
        adjudicator,
        "adjudicator",
    )

    configured_adjudicators = (
        ADJUDICATORS
        if allowed_adjudicators is None
        else allowed_adjudicators
    )

    normalized_allowlist = {
        clean_string(username)
        for username in configured_adjudicators
        if clean_string(username)
    }

    if adjudicator_name not in normalized_allowlist:
        raise AdjudicationPathError(
            f"Adjudicator {adjudicator_name!r} is not configured. "
            f"Allowed adjudicators: "
            f"{sorted(normalized_allowlist)}"
        )

    return adjudicator_name


def build_adjudication_filename_base(
    subject: Any,
    file_tag: Any,
    adjudicator: Any,
    *,
    allowed_adjudicators: Optional[list[str]] = None,
) -> str:
    """
    Build the common filename stem for one adjudication.

    Parameters
    ----------
    subject : Any
        Subject identifier used by the source annotation files.

    file_tag : Any
        Waveform record identifier.

    adjudicator : Any
        Reviewer username.

    allowed_adjudicators : list[str] or None
        Optional adjudicator allowlist override.

    Returns
    -------
    str
        Filename stem without extension or completion suffix.

    Examples
    --------
    ``adjudication_001234567_waveform_tag_pwalczyk``
    """
    subject_name = validate_filename_component(
        subject,
        "subject",
    )
    waveform_file_tag = validate_filename_component(
        file_tag,
        "file_tag",
    )
    adjudicator_name = validate_adjudicator(
        adjudicator,
        allowed_adjudicators=allowed_adjudicators,
    )

    return (
        f"{ADJUDICATION_FILENAME_PREFIX}_"
        f"{subject_name}_"
        f"{waveform_file_tag}_"
        f"{adjudicator_name}"
    )


def _path_is_relative_to(
    candidate: Path,
    parent: Path,
) -> bool:
    """
    Return whether one normalized path is inside another path.

    Parameters
    ----------
    candidate : pathlib.Path
        Potential child path.

    parent : pathlib.Path
        Potential parent directory.

    Returns
    -------
    bool
        True when ``candidate`` is equal to or contained by ``parent``.

    Notes
    -----
    This helper avoids requiring callers to handle ``ValueError`` from
    ``Path.relative_to``.
    """
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_adjudication_paths(
    paths: AdjudicationPaths,
    record_output_path: str | Path,
    source_paths: Optional[list[str | Path]] = None,
) -> None:
    """
    Validate that adjudication output is isolated from source annotations.

    Parameters
    ----------
    paths : AdjudicationPaths
        Generated adjudication paths.

    record_output_path : str or pathlib.Path
        Waveform-record output directory containing annotator folders.

    source_paths : list[str or Path] or None
        Optional source annotation CSV paths to protect explicitly.

    Raises
    ------
    AdjudicationPathError
        If generated output is outside the expected record output directory,
        is not inside the ``ADJUDICATION`` folder, overlaps a source file, or
        uses a source annotator folder as its output location.
    """
    normalized_record_output = Path(
        record_output_path
    ).expanduser().resolve(strict=False)

    normalized_output_directory = (
        paths.output_directory
        .expanduser()
        .resolve(strict=False)
    )

    expected_adjudication_root = (
        normalized_record_output
        / ADJUDICATION_FOLDER_NAME
    ).resolve(strict=False)

    # Every adjudication output must remain below the waveform record's
    # dedicated ADJUDICATION directory.
    if not _path_is_relative_to(
        normalized_output_directory,
        expected_adjudication_root,
    ):
        raise AdjudicationPathError(
            "Adjudication output directory is outside the expected "
            f"ADJUDICATION folder: {normalized_output_directory}"
        )

    generated_files = {
        paths.draft_csv.expanduser().resolve(strict=False),
        paths.complete_csv.expanduser().resolve(strict=False),
        paths.state_json.expanduser().resolve(strict=False),
    }

    for generated_file in generated_files:
        if generated_file.parent != normalized_output_directory:
            raise AdjudicationPathError(
                "Generated adjudication file is not directly inside the "
                f"adjudicator output directory: {generated_file}"
            )

    if not source_paths:
        return

    for source_path_value in source_paths:
        source_path = Path(
            source_path_value
        ).expanduser().resolve(strict=False)

        # Generated adjudication files must never be the same files as source
        # annotations.
        if source_path in generated_files:
            raise AdjudicationPathError(
                "Adjudication output overlaps a source annotation file: "
                f"{source_path}"
            )

        # The adjudicator output directory must not be an annotator's source
        # folder.
        if normalized_output_directory == source_path.parent:
            raise AdjudicationPathError(
                "Adjudication output directory overlaps a source "
                f"annotator folder: {source_path.parent}"
            )

        # Source annotation files should never be located beneath the generated
        # adjudicator directory.
        if _path_is_relative_to(
            source_path,
            normalized_output_directory,
        ):
            raise AdjudicationPathError(
                "A source annotation file is inside the adjudication "
                f"output directory: {source_path}"
            )


def get_adjudication_paths(
    record_output_path: str | Path,
    subject: Any,
    file_tag: Any,
    adjudicator: Any,
    *,
    source_paths: Optional[list[str | Path]] = None,
    allowed_adjudicators: Optional[list[str]] = None,
) -> AdjudicationPaths:
    """
    Build and validate all adjudication output paths.

    Parameters
    ----------
    record_output_path : str or pathlib.Path
        Waveform-record output directory. This is the directory containing the
        source annotator folders.

    subject : Any
        Subject identifier included in output filenames.

    file_tag : Any
        Waveform record identifier included in output filenames.

    adjudicator : Any
        Reviewer username used for the output folder and filenames.

    source_paths : list[str or Path] or None
        Optional source annotation paths protected from output overlap.

    allowed_adjudicators : list[str] or None
        Optional adjudicator allowlist override.

    Returns
    -------
    AdjudicationPaths
        Validated draft CSV, complete CSV, state JSON, and output-directory
        paths.

    Raises
    ------
    AdjudicationPathError
        If the input path or generated paths violate the file contract.
    """
    start_time = perf_counter()

    try:
        return _get_adjudication_paths_impl(
            record_output_path=record_output_path,
            subject=subject,
            file_tag=file_tag,
            adjudicator=adjudicator,
            source_paths=source_paths,
            allowed_adjudicators=allowed_adjudicators,
        )

    except Exception as exc:
        print(
            "[ADJUDICATION] get_adjudication_paths failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "get_adjudication_paths",
            perf_counter() - start_time,
            adjudicator=clean_string(adjudicator),
            file_tag=clean_string(file_tag),
        )


def _get_adjudication_paths_impl(
    record_output_path: str | Path,
    subject: Any,
    file_tag: Any,
    adjudicator: Any,
    *,
    source_paths: Optional[list[str | Path]] = None,
    allowed_adjudicators: Optional[list[str]] = None,
) -> AdjudicationPaths:
    """
    Construct adjudication output paths without UI behavior.

    This private implementation is called by the timed public wrapper.
    """
    record_output = Path(
        record_output_path
    ).expanduser().resolve(strict=False)

    if not clean_string(record_output_path):
        raise AdjudicationPathError(
            "record_output_path cannot be blank."
        )

    adjudicator_name = validate_adjudicator(
        adjudicator,
        allowed_adjudicators=allowed_adjudicators,
    )

    filename_base = build_adjudication_filename_base(
        subject=subject,
        file_tag=file_tag,
        adjudicator=adjudicator_name,
        allowed_adjudicators=allowed_adjudicators,
    )

    # Store adjudications separately from all source-user folders.
    output_directory = (
        record_output
        / ADJUDICATION_FOLDER_NAME
        / adjudicator_name
    )

    draft_csv = (
        output_directory
        / f"{filename_base}.csv"
    )

    complete_csv = (
        output_directory
        / (
            f"{filename_base}"
            f"{COMPLETE_FILENAME_SUFFIX}.csv"
        )
    )

    state_json = (
        output_directory
        / (
            f"{filename_base}"
            f"{ADJUDICATION_STATE_FILENAME_SUFFIX}"
        )
    )

    paths = AdjudicationPaths(
        output_directory=output_directory,
        draft_csv=draft_csv,
        complete_csv=complete_csv,
        state_json=state_json,
    )

    validate_adjudication_paths(
        paths=paths,
        record_output_path=record_output,
        source_paths=source_paths,
    )

    return paths


def ensure_adjudication_output_directory(
    paths: AdjudicationPaths,
) -> Path:
    """
    Create the adjudicator output directory when it does not exist.

    Parameters
    ----------
    paths : AdjudicationPaths
        Previously validated adjudication output paths.

    Returns
    -------
    pathlib.Path
        Created or existing adjudicator output directory.

    Raises
    ------
    OSError
        If the directory cannot be created because of permissions, network
        storage availability, or another filesystem error.

    Notes
    -----
    This function creates directories only. It does not create, modify, or
    delete annotation or adjudication files.
    """
    start_time = perf_counter()

    try:
        return _ensure_adjudication_output_directory_impl(
            paths=paths,
        )

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "ensure_adjudication_output_directory failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "ensure_adjudication_output_directory",
            perf_counter() - start_time,
            output_directory=paths.output_directory,
        )


def _ensure_adjudication_output_directory_impl(
    paths: AdjudicationPaths,
) -> Path:
    """
    Create the adjudicator directory without timing or UI behavior.
    """
    output_directory = (
        paths.output_directory
        .expanduser()
        .resolve(strict=False)
    )

    # parents=True creates ADJUDICATION and the adjudicator folder as needed.
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not output_directory.is_dir():
        raise AdjudicationPathError(
            "Adjudication output path was not created as a directory: "
            f"{output_directory}"
        )

    return output_directory


# =============================================================================
# Source annotation discovery
# =============================================================================

def get_file_modified_at_iso(
    path: str | Path,
) -> str:
    """
    Return a file's modification time as an ISO-8601 UTC timestamp.

    Parameters
    ----------
    path : str or pathlib.Path
        Existing file path.

    Returns
    -------
    str
        Modification timestamp with microsecond precision and a trailing
        ``Z``.

    Raises
    ------
    OSError
        If file metadata cannot be read.
    """
    file_path = Path(path).expanduser()

    modified_epoch = file_path.stat().st_mtime

    return (
        datetime.fromtimestamp(
            modified_epoch,
            tz=timezone.utc,
        )
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def build_source_annotation_filenames(
    subject: Any,
    file_tag: Any,
    username: Any,
) -> tuple[str, str]:
    """
    Build the expected partial and complete source annotation filenames.

    Parameters
    ----------
    subject : Any
        Subject identifier used in the annotation filename.

    file_tag : Any
        Waveform-record identifier.

    username : Any
        Configured source annotator username.

    Returns
    -------
    tuple[str, str]
        ``(partial_filename, complete_filename)``.

    Examples
    --------
    Partial file:

    ``annotations_001234567_waveform_tag_user.csv``

    Completed file:

    ``annotations_001234567_waveform_tag_user_COMPLETE.csv``
    """
    subject_name = validate_filename_component(
        subject,
        "subject",
    )
    waveform_file_tag = validate_filename_component(
        file_tag,
        "file_tag",
    )
    annotator_name = validate_filename_component(
        username,
        "annotator username",
    )

    filename_base = (
        f"{ANNOTATION_FILENAME_PREFIX}_"
        f"{subject_name}_"
        f"{waveform_file_tag}_"
        f"{annotator_name}"
    )

    partial_filename = f"{filename_base}.csv"

    complete_filename = (
        f"{filename_base}"
        f"{COMPLETE_FILENAME_SUFFIX}.csv"
    )

    return (
        partial_filename,
        complete_filename,
    )


def normalize_source_annotators(
    annotators: Optional[list[str]] = None,
) -> list[str]:
    """
    Validate and normalize the configured source annotator list.

    Parameters
    ----------
    annotators : list[str] or None
        Optional source-user override. When omitted, ``ANNOTATION_USERS`` is
        used.

    Returns
    -------
    list[str]
        Ordered source usernames. Their order determines the stable assignment
        to Annotator A and Annotator B.

    Raises
    ------
    MissingInputError
        If the number of configured annotators does not equal
        ``REQUIRED_ANNOTATOR_COUNT``.

    DuplicateInputError
        If the same annotator appears more than once.

    AdjudicationPathError
        If an annotator name is blank or unsafe for use as a folder component.
    """
    configured_users = (
        ANNOTATION_USERS
        if annotators is None
        else annotators
    )

    normalized_users = [
        validate_filename_component(
            username,
            "annotator username",
        )
        for username in configured_users
    ]

    if len(normalized_users) != REQUIRED_ANNOTATOR_COUNT:
        raise MissingInputError(
            "Adjudication currently requires exactly "
            f"{REQUIRED_ANNOTATOR_COUNT} configured annotators, "
            f"but {len(normalized_users)} were provided."
        )

    if len(set(normalized_users)) != len(normalized_users):
        raise DuplicateInputError(
            "Configured source annotators must be unique: "
            f"{normalized_users}"
        )

    if len(ANNOTATOR_ALIASES) < len(normalized_users):
        raise AdjudicationError(
            "Not enough reviewer-facing annotator aliases are configured."
        )

    return normalized_users


def find_complete_annotation_candidates(
    user_directory: str | Path,
    subject: Any,
    file_tag: Any,
    username: Any,
) -> list[Path]:
    """
    Find completed source annotation files for one configured annotator.

    Parameters
    ----------
    user_directory : str or pathlib.Path
        User-specific folder under the waveform record's output directory.

    subject : Any
        Subject identifier expected in the filename.

    file_tag : Any
        Waveform-record identifier expected in the filename.

    username : Any
        Configured source annotator username.

    Returns
    -------
    list[pathlib.Path]
        Sorted completed annotation candidates.

    Notes
    -----
    The exact contract filename is preferred. A constrained fallback search is
    used to support an existing completed annotation whose filename differs
    slightly while still residing in the correct user and waveform folder.
    """
    user_path = Path(
        user_directory
    ).expanduser().resolve(strict=False)

    if not user_path.is_dir():
        return []

    _, expected_complete_filename = (
        build_source_annotation_filenames(
            subject=subject,
            file_tag=file_tag,
            username=username,
        )
    )

    expected_complete_path = (
        user_path
        / expected_complete_filename
    )

    # The exact contract path is authoritative when present.
    if expected_complete_path.is_file():
        return [expected_complete_path]

    subject_name = validate_filename_component(
        subject,
        "subject",
    )
    waveform_file_tag = validate_filename_component(
        file_tag,
        "file_tag",
    )
    annotator_name = validate_filename_component(
        username,
        "annotator username",
    )

    candidates: list[Path] = []

    # Search only the configured user's immediate folder. Do not recurse into
    # unrelated directories or the ADJUDICATION output tree.
    for candidate in user_path.glob(
        f"{ANNOTATION_FILENAME_PREFIX}_*"
        f"{COMPLETE_FILENAME_SUFFIX}.csv"
    ):
        if not candidate.is_file():
            continue

        filename = candidate.name

        # Require the selected record and configured username to appear in the
        # fallback filename to avoid selecting an unrelated annotation file.
        if waveform_file_tag not in filename:
            continue

        if subject_name not in filename:
            continue

        expected_user_suffix = (
            f"_{annotator_name}"
            f"{COMPLETE_FILENAME_SUFFIX}.csv"
        )

        if not filename.endswith(expected_user_suffix):
            continue

        candidates.append(
            candidate.resolve(strict=False)
        )

    return sorted(
        candidates,
        key=lambda path: path.name,
    )


def find_partial_annotation_candidates(
    user_directory: str | Path,
    subject: Any,
    file_tag: Any,
    username: Any,
) -> list[Path]:
    """
    Find partial source annotation files for one configured annotator.

    Parameters
    ----------
    user_directory : str or pathlib.Path
        User-specific annotation folder.

    subject : Any
        Subject identifier expected in the filename.

    file_tag : Any
        Waveform-record identifier expected in the filename.

    username : Any
        Configured source annotator username.

    Returns
    -------
    list[pathlib.Path]
        Sorted partial annotation candidates.

    Notes
    -----
    Partial files are discovered only to report an incomplete input. They are
    not treated as normal adjudication inputs.
    """
    user_path = Path(
        user_directory
    ).expanduser().resolve(strict=False)

    if not user_path.is_dir():
        return []

    expected_partial_filename, _ = (
        build_source_annotation_filenames(
            subject=subject,
            file_tag=file_tag,
            username=username,
        )
    )

    expected_partial_path = (
        user_path
        / expected_partial_filename
    )

    if expected_partial_path.is_file():
        return [expected_partial_path]

    subject_name = validate_filename_component(
        subject,
        "subject",
    )
    waveform_file_tag = validate_filename_component(
        file_tag,
        "file_tag",
    )
    annotator_name = validate_filename_component(
        username,
        "annotator username",
    )

    candidates: list[Path] = []

    for candidate in user_path.glob(
        f"{ANNOTATION_FILENAME_PREFIX}_*.csv"
    ):
        if not candidate.is_file():
            continue

        filename = candidate.name

        # Completed files are not partial candidates.
        if filename.endswith(
            f"{COMPLETE_FILENAME_SUFFIX}.csv"
        ):
            continue

        if waveform_file_tag not in filename:
            continue

        if subject_name not in filename:
            continue

        if not filename.endswith(
            f"_{annotator_name}.csv"
        ):
            continue

        candidates.append(
            candidate.resolve(strict=False)
        )

    return sorted(
        candidates,
        key=lambda path: path.name,
    )


def make_source_annotation_file(
    username: str,
    alias: str,
    path: Path,
    *,
    complete: bool,
    readiness_status: InputReadinessStatus,
    readiness_message: str,
) -> SourceAnnotationFile:
    """
    Create source-file metadata for discovery results.

    Parameters
    ----------
    username : str
        Original source annotator username.

    alias : str
        Stable reviewer-facing alias.

    path : pathlib.Path
        Discovered or expected annotation path.

    complete : bool
        Whether the selected path is a completed annotation file.

    readiness_status : InputReadinessStatus
        Discovery readiness classification.

    readiness_message : str
        Human-readable status explanation.

    Returns
    -------
    SourceAnnotationFile
        Structured source-file metadata.

    Notes
    -----
    Missing expected paths receive zero size and an empty modification
    timestamp because no filesystem metadata exists.
    """
    normalized_path = (
        Path(path)
        .expanduser()
        .resolve(strict=False)
    )

    if normalized_path.is_file():
        size_bytes = int(
            normalized_path.stat().st_size
        )
        modified_at = get_file_modified_at_iso(
            normalized_path
        )
    else:
        size_bytes = 0
        modified_at = ""

    return SourceAnnotationFile(
        username=username,
        alias=alias,
        path=normalized_path,
        size_bytes=size_bytes,
        modified_at=modified_at,
        complete=complete,
        readiness_status=readiness_status,
        readiness_message=readiness_message,
    )


def discover_source_annotation_files(
    record_output_path: str | Path,
    subject: Any,
    file_tag: Any,
    *,
    annotators: Optional[list[str]] = None,
) -> list[SourceAnnotationFile]:
    """
    Discover adjudication source files with timing and error diagnostics.

    Parameters
    ----------
    record_output_path : str or pathlib.Path
        Waveform-record output directory containing the configured user
        folders.

    subject : Any
        Subject identifier expected in annotation filenames.

    file_tag : Any
        Waveform record identifier expected in annotation filenames.

    annotators : list[str] or None
        Optional ordered source-user override. The order determines assignment
        to Annotator A and Annotator B.

    Returns
    -------
    list[SourceAnnotationFile]
        One discovery result per configured annotator, including missing,
        incomplete, duplicate, and ready states.

    Raises
    ------
    AdjudicationPathError
        If the record output path or participant configuration is invalid.
    """
    start_time = perf_counter()

    result: list[SourceAnnotationFile] = []

    try:
        result = _discover_source_annotation_files_impl(
            record_output_path=record_output_path,
            subject=subject,
            file_tag=file_tag,
            annotators=annotators,
        )

        return result

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "discover_source_annotation_files failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        status_summary = {
            status.value: sum(
                source.readiness_status == status
                for source in result
            )
            for status in InputReadinessStatus
        }

        _perf_log(
            "discover_source_annotation_files",
            perf_counter() - start_time,
            sources=len(result),
            statuses=status_summary,
            file_tag=clean_string(file_tag),
        )


def _discover_source_annotation_files_impl(
    record_output_path: str | Path,
    subject: Any,
    file_tag: Any,
    *,
    annotators: Optional[list[str]] = None,
) -> list[SourceAnnotationFile]:
    """
    Discover completed source files without UI behavior.

    This private implementation returns a result for every configured
    annotator, even when a source file is missing or incomplete.
    """
    if not clean_string(record_output_path):
        raise AdjudicationPathError(
            "record_output_path cannot be blank."
        )

    record_output = Path(
        record_output_path
    ).expanduser().resolve(strict=False)

    if not record_output.is_dir():
        raise AdjudicationPathError(
            "Waveform record output directory does not exist: "
            f"{record_output}"
        )

    source_users = normalize_source_annotators(
        annotators
    )

    discovered_sources: list[
        SourceAnnotationFile
    ] = []

    for index, username in enumerate(source_users):
        alias = ANNOTATOR_ALIASES[index]

        user_directory = (
            record_output
            / username
        )

        expected_partial_name, expected_complete_name = (
            build_source_annotation_filenames(
                subject=subject,
                file_tag=file_tag,
                username=username,
            )
        )

        expected_complete_path = (
            user_directory
            / expected_complete_name
        )

        expected_partial_path = (
            user_directory
            / expected_partial_name
        )

        # A missing user directory is classified separately from an invalid
        # source file.
        if not user_directory.is_dir():
            discovered_sources.append(
                make_source_annotation_file(
                    username=username,
                    alias=alias,
                    path=expected_complete_path,
                    complete=False,
                    readiness_status=(
                        InputReadinessStatus.MISSING
                    ),
                    readiness_message=(
                        "Configured annotator folder does not exist."
                    ),
                )
            )
            continue

        complete_candidates = (
            find_complete_annotation_candidates(
                user_directory=user_directory,
                subject=subject,
                file_tag=file_tag,
                username=username,
            )
        )

        if len(complete_candidates) > 1:
            discovered_sources.append(
                make_source_annotation_file(
                    username=username,
                    alias=alias,
                    path=complete_candidates[0],
                    complete=True,
                    readiness_status=(
                        InputReadinessStatus.DUPLICATE
                    ),
                    readiness_message=(
                        "Multiple completed annotation files were found: "
                        + ", ".join(
                            candidate.name
                            for candidate in complete_candidates
                        )
                    ),
                )
            )
            continue

        if len(complete_candidates) == 1:
            discovered_sources.append(
                make_source_annotation_file(
                    username=username,
                    alias=alias,
                    path=complete_candidates[0],
                    complete=True,
                    readiness_status=(
                        InputReadinessStatus.READY
                    ),
                    readiness_message=(
                        "Completed annotation input is ready."
                    ),
                )
            )
            continue

        partial_candidates = (
            find_partial_annotation_candidates(
                user_directory=user_directory,
                subject=subject,
                file_tag=file_tag,
                username=username,
            )
        )

        if partial_candidates:
            discovered_sources.append(
                make_source_annotation_file(
                    username=username,
                    alias=alias,
                    path=partial_candidates[0],
                    complete=False,
                    readiness_status=(
                        InputReadinessStatus.INCOMPLETE
                    ),
                    readiness_message=(
                        "A partial annotation exists, but no completed "
                        "annotation file was found."
                    ),
                )
            )
            continue

        # The folder exists, but neither a complete nor partial annotation
        # file exists for this waveform record.
        discovered_sources.append(
            make_source_annotation_file(
                username=username,
                alias=alias,
                path=expected_complete_path,
                complete=False,
                readiness_status=(
                    InputReadinessStatus.MISSING
                ),
                readiness_message=(
                    "No annotation file was found for this waveform."
                ),
            )
        )

    return discovered_sources


def require_ready_source_annotation_files(
    sources: list[SourceAnnotationFile],
) -> tuple[SourceAnnotationFile, SourceAnnotationFile]:
    """
    Require exactly two ready source annotation inputs.

    Parameters
    ----------
    sources : list[SourceAnnotationFile]
        Results returned by ``discover_source_annotation_files``.

    Returns
    -------
    tuple[SourceAnnotationFile, SourceAnnotationFile]
        Ready source files assigned to Annotator A and Annotator B.

    Raises
    ------
    MissingInputError
        If a source is missing or incomplete.

    DuplicateInputError
        If a source has duplicate completed files.

    InvalidAnnotationError
        If a source is marked invalid.

    AdjudicationError
        If the source list has an unexpected size or state.
    """
    start_time = perf_counter()

    try:
        return _require_ready_source_annotation_files_impl(
            sources=sources,
        )

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "require_ready_source_annotation_files failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "require_ready_source_annotation_files",
            perf_counter() - start_time,
            sources=len(sources),
        )


def _require_ready_source_annotation_files_impl(
    sources: list[SourceAnnotationFile],
) -> tuple[SourceAnnotationFile, SourceAnnotationFile]:
    """
    Validate source readiness without UI behavior.
    """
    if len(sources) != REQUIRED_ANNOTATOR_COUNT:
        raise AdjudicationError(
            "Expected exactly "
            f"{REQUIRED_ANNOTATOR_COUNT} source results, "
            f"but received {len(sources)}."
        )

    for source in sources:
        status = source.readiness_status

        if status == InputReadinessStatus.MISSING:
            raise MissingInputError(
                f"{source.alias} ({source.username}) is missing: "
                f"{source.readiness_message} "
                f"Expected path: {source.path}"
            )

        if status == InputReadinessStatus.INCOMPLETE:
            raise MissingInputError(
                f"{source.alias} ({source.username}) is incomplete: "
                f"{source.readiness_message} "
                f"Path: {source.path}"
            )

        if status == InputReadinessStatus.DUPLICATE:
            raise DuplicateInputError(
                f"{source.alias} ({source.username}) has duplicate "
                f"inputs: {source.readiness_message}"
            )

        if status == InputReadinessStatus.INVALID:
            raise InvalidAnnotationError(
                f"{source.alias} ({source.username}) is invalid: "
                f"{source.readiness_message}"
            )

        if status != InputReadinessStatus.READY:
            raise AdjudicationError(
                f"{source.alias} has unsupported readiness status: "
                f"{status.value}"
            )

        if not source.path.is_file():
            raise MissingInputError(
                f"Ready source file no longer exists: {source.path}"
            )

        if not source.complete:
            raise MissingInputError(
                f"Ready source is not marked complete: {source.path}"
            )

    # Preserve the configured ordering and stable A/B alias assignment.
    source_a = sources[0]
    source_b = sources[1]

    if source_a.alias != ANNOTATOR_ALIASES[0]:
        raise AdjudicationError(
            "The first source is not assigned to Annotator A."
        )

    if source_b.alias != ANNOTATOR_ALIASES[1]:
        raise AdjudicationError(
            "The second source is not assigned to Annotator B."
        )

    return source_a, source_b


# =============================================================================
# Source CSV loading and normalization
# =============================================================================

def read_source_annotation_csv(
    source: SourceAnnotationFile,
) -> pd.DataFrame:
    """
    Read one source annotation CSV with timing and error diagnostics.

    Parameters
    ----------
    source : SourceAnnotationFile
        Metadata describing the source annotation file.

    Returns
    -------
    pandas.DataFrame
        Raw source annotation rows.

    Raises
    ------
    MissingInputError
        If the source file no longer exists.

    InvalidAnnotationError
        If the file cannot be read, contains no rows, or is missing required
        columns.

    Notes
    -----
    The source file is opened read-only. This function never writes to,
    renames, moves, or deletes the source annotation.
    """
    start_time = perf_counter()
    dataframe: Optional[pd.DataFrame] = None

    try:
        dataframe = _read_source_annotation_csv_impl(
            source=source,
        )

        return dataframe

    except Exception as exc:
        # Preserve the failure in source metadata for UI diagnostics.
        source.readiness_status = InputReadinessStatus.INVALID
        source.readiness_message = (
            f"{type(exc).__name__}: {exc}"
        )

        print(
            "[ADJUDICATION] read_source_annotation_csv failed:",
            f"alias={source.alias}",
            f"path={source.path}",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "read_source_annotation_csv",
            perf_counter() - start_time,
            alias=source.alias,
            rows=(
                len(dataframe)
                if dataframe is not None
                else 0
            ),
            path=source.path,
        )


def _read_source_annotation_csv_impl(
    source: SourceAnnotationFile,
) -> pd.DataFrame:
    """
    Read and perform basic schema checks on one source annotation CSV.

    Parameters
    ----------
    source : SourceAnnotationFile
        Source file metadata.

    Returns
    -------
    pandas.DataFrame
        Raw annotation data with original row numbers retained in
        ``_source_row``.

    Raises
    ------
    MissingInputError
        If the source path is not an existing file.

    InvalidAnnotationError
        If the CSV cannot be read, is empty, or lacks required columns.
    """
    source_path = (
        source.path
        .expanduser()
        .resolve(strict=False)
    )

    if not source_path.is_file():
        raise MissingInputError(
            f"Source annotation file does not exist: {source_path}"
        )

    try:
        # Read text-like values consistently. Start/end are converted
        # explicitly below so floating-point epoch precision is retained.
        dataframe = pd.read_csv(
            source_path,
            dtype="string",
            keep_default_na=True,
        )
    except Exception as exc:
        raise InvalidAnnotationError(
            f"Could not read source annotation CSV "
            f"{source_path}: {exc}"
        ) from exc

    if dataframe.empty:
        raise InvalidAnnotationError(
            f"Source annotation CSV contains no rows: {source_path}"
        )

    missing_columns = (
        REQUIRED_ANNOTATION_COLUMNS
        .difference(dataframe.columns)
    )

    if missing_columns:
        raise InvalidAnnotationError(
            f"Source annotation CSV is missing required columns: "
            f"{sorted(missing_columns)}. Path: {source_path}"
        )

    dataframe = dataframe.copy()

    # Preserve the original zero-based CSV data-row index for diagnostics.
    # The CSV header is not included in this number.
    dataframe["_source_row"] = np.arange(
        len(dataframe),
        dtype=int,
    )

    return dataframe


def normalize_source_annotation_dataframe(
    dataframe: pd.DataFrame,
    source: SourceAnnotationFile,
) -> pd.DataFrame:
    """
    Normalize source annotation values without changing boundary precision.

    Parameters
    ----------
    dataframe : pandas.DataFrame
        Raw source annotation rows.

    source : SourceAnnotationFile
        Metadata describing the source file and expected annotator identity.

    Returns
    -------
    pandas.DataFrame
        Normalized rows sorted by ``start`` and ``end``.

    Raises
    ------
    InvalidAnnotationError
        If timestamps are invalid, user identity is inconsistent, or required
        values cannot be normalized.

    Notes
    -----
    Structural interval validation, including gaps and overlaps, is performed
    in the next validation section. This function focuses on type and value
    normalization.
    """
    start_time = perf_counter()
    normalized: Optional[pd.DataFrame] = None

    try:
        normalized = (
            _normalize_source_annotation_dataframe_impl(
                dataframe=dataframe,
                source=source,
            )
        )

        return normalized

    except Exception as exc:
        source.readiness_status = InputReadinessStatus.INVALID
        source.readiness_message = (
            f"{type(exc).__name__}: {exc}"
        )

        print(
            "[ADJUDICATION] "
            "normalize_source_annotation_dataframe failed:",
            f"alias={source.alias}",
            f"path={source.path}",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "normalize_source_annotation_dataframe",
            perf_counter() - start_time,
            alias=source.alias,
            rows=(
                len(normalized)
                if normalized is not None
                else 0
            ),
        )


def _normalize_source_annotation_dataframe_impl(
    dataframe: pd.DataFrame,
    source: SourceAnnotationFile,
) -> pd.DataFrame:
    """
    Normalize one source DataFrame without timing or UI behavior.
    """
    normalized = dataframe.copy()

    # ------------------------------------------------------------------
    # Normalize text columns.
    # ------------------------------------------------------------------
    text_columns = [
        "user",
        "subject",
        "encounter",
        "namespace",
        "file_tag",
        "source_path",
        "cpr",
        "rhythm_label",
        "rhythm_expl",
        "terminal_event_status",
        "terminal_event_comment",
    ]

    for column in text_columns:
        normalized[column] = normalized[column].map(
            clean_string
        )

    # ------------------------------------------------------------------
    # Validate source-user identity.
    # ------------------------------------------------------------------
    source_users = [
        value
        for value in normalized["user"].unique()
        if value
    ]

    if not source_users:
        raise InvalidAnnotationError(
            f"Source file contains no annotator username: {source.path}"
        )

    if len(source_users) != 1:
        raise InvalidAnnotationError(
            "Source file must contain exactly one annotator username, "
            f"but found {source_users}. Path: {source.path}"
        )

    file_username = source_users[0]

    if file_username != source.username:
        raise InvalidAnnotationError(
            f"Source username mismatch. Configured user is "
            f"{source.username!r}, but the CSV contains "
            f"{file_username!r}. Path: {source.path}"
        )

    # ------------------------------------------------------------------
    # Convert boundaries to float64 epoch seconds.
    #
    # No rounding or conversion to integer milliseconds is performed.
    # ------------------------------------------------------------------
    normalized["start"] = pd.to_numeric(
        normalized["start"],
        errors="coerce",
    ).astype("float64")

    normalized["end"] = pd.to_numeric(
        normalized["end"],
        errors="coerce",
    ).astype("float64")

    invalid_start = ~np.isfinite(
        normalized["start"].to_numpy(
            dtype=float
        )
    )

    invalid_end = ~np.isfinite(
        normalized["end"].to_numpy(
            dtype=float
        )
    )

    invalid_time_mask = (
        invalid_start
        | invalid_end
    )

    if np.any(invalid_time_mask):
        invalid_rows = normalized.loc[
            invalid_time_mask,
            "_source_row",
        ].astype(int).tolist()

        raise InvalidAnnotationError(
            "Source annotation contains invalid start/end timestamps "
            f"at data rows {invalid_rows}. Path: {source.path}"
        )

    # ------------------------------------------------------------------
    # Normalize completion values.
    # ------------------------------------------------------------------
    normalized["waveform_complete"] = normalized[
        "waveform_complete"
    ].map(coerce_bool)

    # Stable sorting ensures deterministic behavior when timestamps are equal.
    normalized = normalized.sort_values(
        by=[
            "start",
            "end",
            "_source_row",
        ],
        kind="stable",
    ).reset_index(drop=True)

    return normalized


def dataframe_to_annotation_intervals(
    dataframe: pd.DataFrame,
    source: SourceAnnotationFile,
) -> list[AnnotationInterval]:
    """
    Convert normalized source rows into interval dataclasses.

    Parameters
    ----------
    dataframe : pandas.DataFrame
        Normalized annotation rows.

    source : SourceAnnotationFile
        Source metadata providing the stable Annotator A/B alias.

    Returns
    -------
    list[AnnotationInterval]
        Intervals ordered by start time.

    Raises
    ------
    InvalidAnnotationError
        If a row cannot be converted into an interval.
    """
    start_time = perf_counter()
    intervals: list[AnnotationInterval] = []

    try:
        intervals = _dataframe_to_annotation_intervals_impl(
            dataframe=dataframe,
            source=source,
        )

        return intervals

    except Exception as exc:
        source.readiness_status = InputReadinessStatus.INVALID
        source.readiness_message = (
            f"{type(exc).__name__}: {exc}"
        )

        print(
            "[ADJUDICATION] "
            "dataframe_to_annotation_intervals failed:",
            f"alias={source.alias}",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "dataframe_to_annotation_intervals",
            perf_counter() - start_time,
            alias=source.alias,
            intervals=len(intervals),
        )


def _dataframe_to_annotation_intervals_impl(
    dataframe: pd.DataFrame,
    source: SourceAnnotationFile,
) -> list[AnnotationInterval]:
    """
    Convert normalized rows without timing or UI behavior.
    """
    intervals: list[AnnotationInterval] = []

    for normalized_index, row in dataframe.iterrows():
        source_row = int(
            row.get(
                "_source_row",
                normalized_index,
            )
        )

        try:
            interval_start = validate_epoch_seconds(
                row["start"],
                f"start at source row {source_row}",
            )

            interval_end = validate_epoch_seconds(
                row["end"],
                f"end at source row {source_row}",
            )

            interval = AnnotationInterval(
                user=clean_string(row["user"]),
                subject=clean_string(row["subject"]),
                encounter=clean_string(
                    row["encounter"]
                ),
                namespace=clean_string(
                    row["namespace"]
                ),
                file_tag=clean_string(
                    row["file_tag"]
                ),
                source_path=clean_string(
                    row["source_path"]
                ),
                cpr=clean_string(row["cpr"]),
                rhythm_label=clean_string(
                    row["rhythm_label"]
                ),
                rhythm_expl=clean_string(
                    row["rhythm_expl"]
                ),
                start=interval_start,
                end=interval_end,
                waveform_complete=coerce_bool(
                    row["waveform_complete"]
                ),
                terminal_event_status=clean_string(
                    row["terminal_event_status"]
                ),
                terminal_event_comment=clean_string(
                    row["terminal_event_comment"]
                ),
                source_alias=source.alias,
                source_row=source_row,
            )

        except Exception as exc:
            raise InvalidAnnotationError(
                f"Could not normalize source row {source_row} "
                f"from {source.path}: {exc}"
            ) from exc

        intervals.append(interval)

    return intervals


def load_source_annotation_intervals(
    source: SourceAnnotationFile,
) -> list[AnnotationInterval]:
    """
    Load and normalize one source annotator timeline.

    Parameters
    ----------
    source : SourceAnnotationFile
        Ready source-file metadata.

    Returns
    -------
    list[AnnotationInterval]
        Normalized source intervals in chronological order.

    Raises
    ------
    InvalidAnnotationError
        If the source is not ready or cannot be normalized.

    Notes
    -----
    This function does not yet perform full gap/overlap validation. That is
    handled by the source interval-validation section.
    """
    start_time = perf_counter()
    intervals: list[AnnotationInterval] = []

    try:
        intervals = _load_source_annotation_intervals_impl(
            source=source,
        )

        return intervals

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "load_source_annotation_intervals failed:",
            f"alias={source.alias}",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "load_source_annotation_intervals",
            perf_counter() - start_time,
            alias=source.alias,
            intervals=len(intervals),
            path=source.path,
        )


def _load_source_annotation_intervals_impl(
    source: SourceAnnotationFile,
) -> list[AnnotationInterval]:
    """
    Load one source timeline without timing or UI behavior.
    """
    if (
        source.readiness_status
        != InputReadinessStatus.READY
    ):
        raise InvalidAnnotationError(
            f"{source.alias} is not ready for loading: "
            f"{source.readiness_status.value}. "
            f"{source.readiness_message}"
        )

    raw_dataframe = read_source_annotation_csv(
        source
    )

    normalized_dataframe = (
        normalize_source_annotation_dataframe(
            dataframe=raw_dataframe,
            source=source,
        )
    )

    intervals = dataframe_to_annotation_intervals(
        dataframe=normalized_dataframe,
        source=source,
    )

    if not intervals:
        raise InvalidAnnotationError(
            f"{source.alias} produced no usable intervals."
        )

    return intervals


def load_source_annotation_pair(
    source_a: SourceAnnotationFile,
    source_b: SourceAnnotationFile,
) -> tuple[
    list[AnnotationInterval],
    list[AnnotationInterval],
]:
    """
    Load and normalize the two required source timelines.

    Parameters
    ----------
    source_a : SourceAnnotationFile
        Source assigned to Annotator A.

    source_b : SourceAnnotationFile
        Source assigned to Annotator B.

    Returns
    -------
    tuple[list[AnnotationInterval], list[AnnotationInterval]]
        Chronological Annotator A and Annotator B interval lists.

    Raises
    ------
    AdjudicationError
        If source aliases are incorrect or both paths resolve to the same file.

    InvalidAnnotationError
        If either source timeline cannot be loaded.
    """
    start_time = perf_counter()

    intervals_a: list[AnnotationInterval] = []
    intervals_b: list[AnnotationInterval] = []

    try:
        (
            intervals_a,
            intervals_b,
        ) = _load_source_annotation_pair_impl(
            source_a=source_a,
            source_b=source_b,
        )

        return intervals_a, intervals_b

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "load_source_annotation_pair failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "load_source_annotation_pair",
            perf_counter() - start_time,
            intervals_a=len(intervals_a),
            intervals_b=len(intervals_b),
        )


def _load_source_annotation_pair_impl(
    source_a: SourceAnnotationFile,
    source_b: SourceAnnotationFile,
) -> tuple[
    list[AnnotationInterval],
    list[AnnotationInterval],
]:
    """
    Load both source timelines without timing or UI behavior.
    """
    if source_a.alias != ANNOTATOR_ALIASES[0]:
        raise AdjudicationError(
            f"Expected first source alias "
            f"{ANNOTATOR_ALIASES[0]!r}, but received "
            f"{source_a.alias!r}."
        )

    if source_b.alias != ANNOTATOR_ALIASES[1]:
        raise AdjudicationError(
            f"Expected second source alias "
            f"{ANNOTATOR_ALIASES[1]!r}, but received "
            f"{source_b.alias!r}."
        )

    normalized_path_a = (
        source_a.path
        .expanduser()
        .resolve(strict=False)
    )

    normalized_path_b = (
        source_b.path
        .expanduser()
        .resolve(strict=False)
    )

    if normalized_path_a == normalized_path_b:
        raise DuplicateInputError(
            "Annotator A and Annotator B resolve to the same source file: "
            f"{normalized_path_a}"
        )

    intervals_a = load_source_annotation_intervals(
        source_a
    )

    intervals_b = load_source_annotation_intervals(
        source_b
    )

    return intervals_a, intervals_b


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


# =============================================================================
# Combined timeline segmentation
# =============================================================================

# Functions for:
#
# - collecting reconciled and unmatched boundaries
# - splitting the full time range into atomic regions
# - finding active A/B intervals at each region midpoint
# - distinguishing complete, one-sided, and missing coverage


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


# =============================================================================
# Adjudication timeline validation
# =============================================================================

# Functions for:
#
# - final interval ordering
# - gap/overlap detection
# - required CPR/rhythm/explanation checks
# - complete waveform-range coverage
# - unresolved-region checks
# - terminal completion checks
# - finalization eligibility result


# =============================================================================
# CSV serialization
# =============================================================================

# Functions for:
#
# - converting final intervals to a DataFrame
# - preserving all original annotation columns
# - adding adjudication metadata columns
# - writing draft CSV atomically
# - writing COMPLETE CSV atomically
# - removing redundant draft only after successful final save
# - never modifying source files


# =============================================================================
# State JSON serialization
# =============================================================================

# Functions for:
#
# - building schema-versioned state dictionaries
# - storing source-file metadata
# - storing A/B mapping
# - storing comparison tolerance
# - storing disagreement and resolution state
# - storing current navigation index
# - writing JSON atomically
# - loading and validating JSON
# - rejecting unsupported schema versions


# =============================================================================
# Resume and input-change detection
# =============================================================================

# Functions for:
#
# - locating existing draft/complete adjudication files
# - comparing current source size/mtime with saved metadata
# - reporting unchanged/changed/missing inputs
# - loading draft CSV + state JSON
# - loading completed adjudication read-only
# - preparing a completed adjudication for explicit reopening

