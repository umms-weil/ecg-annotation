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
class BoundaryMatch:
    """
    Describe an attempted match between one A and one B boundary.

    ``midpoint`` is populated only when a compatible match is accepted.
    """

    boundary_id: str

    boundary_a: Optional[float]
    boundary_b: Optional[float]

    difference_seconds: Optional[float]
    midpoint: Optional[float]

    within_tolerance: bool
    adjacent_labels_compatible: bool
    matched: bool

    reasons: list[str] = field(
        default_factory=list
    )

    def to_dict(self) -> dict[str, Any]:
        """
        Return a serializable boundary-match representation.
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

# Functions for:
#
# - loading annotation CSV
# - confirming required columns
# - preserving floating-point epoch seconds
# - normalizing blank/null values
# - sorting intervals
# - converting rows into AnnotationInterval objects
# - retaining source-row information for diagnostics only


# =============================================================================
# Source interval validation
# =============================================================================

# Functions for:
#
# - end > start validation
# - finite timestamp validation
# - overlap detection
# - gap detection
# - complete-file validation
# - CPR/rhythm/explanation validation
# - producing structured validation results and warnings


# =============================================================================
# Boundary extraction and matching
# =============================================================================

# Functions for:
#
# - extracting internal boundaries from each timeline
# - finding candidate A/B boundary matches
# - enforcing one-to-one matching
# - applying configurable tolerance
# - checking labels before each boundary
# - checking labels after each boundary
# - calculating midpoint boundaries
# - identifying unmatched/extra boundaries


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

