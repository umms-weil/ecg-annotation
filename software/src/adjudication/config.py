"""
Configuration constants, schemas, statuses, and reason definitions for
waveform adjudication.
"""

from __future__ import annotations

from enum import Enum

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