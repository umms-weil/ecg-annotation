"""
Dataclasses used by the adjudication processing and persistence layers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .config import (
    ADJUDICATION_BOUNDARY_TOLERANCE_SEC,
    ADJUDICATION_RECORD_TYPE,
    ComparisonStatus,
    InputReadinessStatus,
)

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
class TimelineSegment:
    """
    Represent one atomic segment in the combined annotator timeline.

    A segment is created between consecutive reconciled boundaries from either
    source timeline. Agreement classification is applied later.

    Parameters
    ----------
    segment_id : str
        Stable identifier such as ``segment_0001``.

    start, end : float
        Absolute floating-point UTC epoch seconds.

    annotation_a : AnnotationInterval or None
        Annotator A interval active within this segment.

    annotation_b : AnnotationInterval or None
        Annotator B interval active within this segment.
    """

    segment_id: str
    start: float
    end: float

    annotation_a: Optional[AnnotationInterval] = None
    annotation_b: Optional[AnnotationInterval] = None

    @property
    def duration(self) -> float:
        """
        Return segment duration in seconds.

        Returns
        -------
        float
            ``end - start`` without deliberate rounding.
        """
        return float(self.end - self.start)

    @property
    def has_both_annotators(self) -> bool:
        """
        Return whether both annotators cover this segment.
        """
        return (
            self.annotation_a is not None
            and self.annotation_b is not None
        )

    @property
    def has_any_coverage(self) -> bool:
        """
        Return whether at least one annotator covers this segment.
        """
        return (
            self.annotation_a is not None
            or self.annotation_b is not None
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Return a JSON-safe segment representation.
        """
        return {
            "segment_id": self.segment_id,
            "start": float(self.start),
            "end": float(self.end),
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
        }


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
