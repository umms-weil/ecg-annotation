"""
Draft persistence for waveform adjudication.

The CSV stores the editable final timeline.
The companion JSON stores comparison and review state.

Source annotator files are never modified.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile

from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Optional
import shutil
import uuid
import numpy as np
import pandas as pd
from copy import deepcopy

from .config import (
    ADJUDICATION_OUTPUT_COLUMNS,
    ADJUDICATION_SCHEMA_VERSION,
    ADJUDICATION_STATE_RECORD_TYPE,
    ComparisonStatus,
    InputReadinessStatus,
)
from .exceptions import (
    AdjudicationError,
    InvalidAnnotationError,
    SourceFilesChangedError,
    UnsupportedSchemaError,
)
from .models import (
    AdjudicationComparisonResult,
    AdjudicationInterval,
    AnnotationInterval,
    BoundaryMatch,
    ComparisonRegion,
    SourceAnnotationFile,
    ValidationIssue,
)
from .config import (
    ADJUDICATION_OUTPUT_COLUMNS,
    ADJUDICATION_SCHEMA_VERSION,
    ADJUDICATION_STATE_RECORD_TYPE,
    MINIMUM_VALID_INTERVAL_SEC,
    VALID_TERMINAL_EVENT_STATUSES,
    ComparisonStatus,
    InputReadinessStatus,
)
from .paths import (
    ensure_adjudication_output_directory,
    get_adjudication_paths,
)
from .utilities import (
    _perf_log,
    coerce_bool,
    json_safe_value,
    utc_now_iso,
)



# =============================================================================
# Atomic file writing
# =============================================================================

def _atomic_write_bytes(path: Path, content: bytes) -> None:
    """
    Write a file through a temporary file in the destination directory.

    Replacement occurs only after the temporary file is fully written.
    Atomicity applies to this individual file, not to the CSV/JSON pair.
    """
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _sha256(content: bytes) -> str:
    """Return a content hash used to verify a matching CSV/state pair."""
    return hashlib.sha256(content).hexdigest()


# =============================================================================
# Draft timeline validation
# =============================================================================

def _validate_draft_intervals(
    intervals: list[AdjudicationInterval],
) -> None:
    """
    Validate structural draft data while allowing unlabeled review regions.

    Drafts may contain short atomic comparison fragments. The final minimum
    interval-length policy will be enforced during finalization.
    """
    if not intervals:
        raise InvalidAnnotationError("The final timeline is empty.")

    previous_end: Optional[float] = None

    for index, interval in enumerate(intervals):
        if (
            not np.isfinite(interval.start)
            or not np.isfinite(interval.end)
            or interval.end <= interval.start
        ):
            raise InvalidAnnotationError(
                f"Final interval {index + 1} has invalid boundaries."
            )

        if (
            previous_end is not None
            and abs(interval.start - previous_end) > 1e-6
        ):
            raise InvalidAnnotationError(
                f"Final interval {index + 1} is not contiguous "
                "with the previous interval."
            )

        previous_end = float(interval.end)


# =============================================================================
# Source-change detection
# =============================================================================

def _capture_source_signature(source: SourceAnnotationFile) -> dict[str, Any]:
    """
    Capture size and nanosecond modification time for one source file.

    These checks detect ordinary file changes without rereading source CSVs.
    """
    stat = source.path.stat()

    return {
        "path": str(source.path),
        "size_bytes": int(stat.st_size),
        "modified_ns": int(stat.st_mtime_ns),
    }


def _verify_source_signature(signature: Mapping[str, Any]) -> None:
    """
    Reject a missing or changed source file during draft resume.
    """
    path = Path(str(signature["path"]))

    if not path.is_file():
        raise SourceFilesChangedError(
            f"Source annotation is missing: {path}"
        )

    stat = path.stat()

    if (
        stat.st_size != int(signature["size_bytes"])
        or stat.st_mtime_ns != int(signature["modified_ns"])
    ):
        raise SourceFilesChangedError(
            f"Source annotation changed since this draft was saved: {path}"
        )


# =============================================================================
# Draft saving
# =============================================================================

def save_adjudication_draft(
    record: Mapping[str, Any],
    comparison: AdjudicationComparisonResult,
    *,
    selected_interval_index: Optional[int] = None,
    selected_region_id: Optional[str] = None,
) -> Path:
    """
    Save a draft final timeline and matching review-state JSON.

    Parameters
    ----------
    record : Mapping[str, Any]
        Loaded waveform record containing its output_path.

    comparison : AdjudicationComparisonResult
        Current final intervals and comparison/resolution state.

    selected_interval_index : int or None
        Final interval to select when resuming.

    selected_region_id : str or None
        Comparison region to restore when resuming.

    Returns
    -------
    pathlib.Path
        Successfully written draft CSV path.

    Notes
    -----
    The state stores a CSV hash. If writing is interrupted between the two
    file replacements, resume reports a mismatch rather than loading unrelated
    CSV and JSON versions.
    """
    started = perf_counter()

    try:
        return _save_adjudication_draft_impl(
            record=record,
            comparison=comparison,
            selected_interval_index=selected_interval_index,
            selected_region_id=selected_region_id,
        )
    except Exception as exc:
        print("[ADJ] Draft save failed:", type(exc).__name__, exc)
        raise
    finally:
        _perf_log(
            "save_adjudication_draft",
            perf_counter() - started,
            intervals=len(comparison.prefilled_intervals),
        )


def _save_adjudication_draft_impl(
    record: Mapping[str, Any],
    comparison: AdjudicationComparisonResult,
    *,
    selected_interval_index: Optional[int],
    selected_region_id: Optional[str],
    allow_completed: bool = False,
) -> Path:
    """Serialize and write one draft without UI behavior."""
    _validate_draft_intervals(comparison.prefilled_intervals)

    paths = get_adjudication_paths(
        record_output_path=record["output_path"],
        subject=comparison.subject,
        file_tag=comparison.file_tag,
        adjudicator=comparison.adjudicator,
        source_paths=[
            comparison.source_a.path,
            comparison.source_b.path,
        ],
    )

    # Completed-file reopening will be implemented separately.
    if paths.complete_csv.exists() and not allow_completed:
        raise AdjudicationError(
            "A completed adjudication exists. "
            "Load it and explicitly reopen it before saving a draft."
        )

    ensure_adjudication_output_directory(paths)

    rows = []

    for interval in comparison.prefilled_intervals:
        row = interval.to_dict()

        # Persist explicit reviewer identity even for older in-memory models.
        row["user"] = comparison.adjudicator
        row["adjudicator"] = comparison.adjudicator
        rows.append(row)

    columns = list(ADJUDICATION_OUTPUT_COLUMNS)

    if "adjudicator" not in columns:
        columns.append("adjudicator")

    csv_text = pd.DataFrame(rows).reindex(columns=columns).to_csv(
        index=False,
    )
    csv_bytes = csv_text.encode("utf-8")

    state = {
        "schema_version": ADJUDICATION_SCHEMA_VERSION,
        "record_type": ADJUDICATION_STATE_RECORD_TYPE,
        "status": "draft",
        "adjudicator": comparison.adjudicator,
        "subject": comparison.subject,
        "encounter": comparison.encounter,
        "namespace": comparison.namespace,
        "file_tag": comparison.file_tag,
        "boundary_tolerance_sec": comparison.boundary_tolerance_sec,
        "created_at": comparison.created_at,
        "updated_at": utc_now_iso(),
        "csv_sha256": _sha256(csv_bytes),
        "source_a": comparison.source_a.to_dict(),
        "source_b": comparison.source_b.to_dict(),
        "source_signatures": [
            _capture_source_signature(comparison.source_a),
            _capture_source_signature(comparison.source_b),
        ],
        # Saved comparison context allows resume without recomputation.
        "annotator_a_intervals": [
            item.to_dict()
            for item in comparison.annotator_a_intervals
        ],
        "annotator_b_intervals": [
            item.to_dict()
            for item in comparison.annotator_b_intervals
        ],
        "boundary_matches": [
            item.to_dict()
            for item in comparison.boundary_matches
        ],
        "comparison_regions": [
            item.to_dict()
            for item in comparison.comparison_regions
        ],
        "validation_issues": [
            item.to_dict()
            for item in comparison.validation_issues
        ],
        "selected_interval_index": selected_interval_index,
        "selected_region_id": selected_region_id,
    }

    state_bytes = json.dumps(
        json_safe_value(state),
        indent=2,
        allow_nan=False,
    ).encode("utf-8")

    _atomic_write_bytes(paths.draft_csv, csv_bytes)
    _atomic_write_bytes(paths.state_json, state_bytes)

    # Verify both files before the UI reports success.
    if _sha256(paths.draft_csv.read_bytes()) != state["csv_sha256"]:
        raise AdjudicationError("Draft CSV verification failed.")

    saved_state = json.loads(paths.state_json.read_text(encoding="utf-8"))

    if saved_state["csv_sha256"] != state["csv_sha256"]:
        raise AdjudicationError("Draft state verification failed.")

    return paths.draft_csv

# =============================================================================
# First draft save after reopening
# =============================================================================

def save_reopened_adjudication_draft(
    record: Mapping[str, Any],
    comparison: AdjudicationComparisonResult,
    *,
    selected_interval_index: Optional[int] = None,
    selected_region_id: Optional[str] = None,
) -> Path:
    """
    Archive completed output and save the first reopened draft.

    Completed CSV/JSON remain unchanged until this operation is requested.
    A verified archive preserves the previous completed version before the
    state JSON is replaced.

    If draft saving fails, the previous completed JSON is restored.
    """
    started = perf_counter()

    try:
        return _save_reopened_adjudication_draft_impl(
            record,
            comparison,
            selected_interval_index=selected_interval_index,
            selected_region_id=selected_region_id,
        )
    except Exception as exc:
        print("[ADJ] Reopened draft save failed:", type(exc).__name__, exc)
        raise
    finally:
        _perf_log(
            "save_reopened_adjudication_draft",
            perf_counter() - started,
        )


def _save_reopened_adjudication_draft_impl(
    record: Mapping[str, Any],
    comparison: AdjudicationComparisonResult,
    *,
    selected_interval_index: Optional[int],
    selected_region_id: Optional[str],
) -> Path:
    """Preserve completed output before saving reopened draft state."""
    paths = get_adjudication_paths(
        record_output_path=record["output_path"],
        subject=comparison.subject,
        file_tag=comparison.file_tag,
        adjudicator=comparison.adjudicator,
        source_paths=[
            comparison.source_a.path,
            comparison.source_b.path,
        ],
    )

    if not paths.complete_csv.is_file() or not paths.state_json.is_file():
        raise AdjudicationError(
            "The completed CSV and JSON must both exist before reopening."
        )

    original_state_bytes = paths.state_json.read_bytes()
    completed_bytes = paths.complete_csv.read_bytes()
    original_state = json.loads(original_state_bytes)

    if (
        original_state.get("status") != "complete"
        or original_state.get("csv_sha256") != _sha256(completed_bytes)
    ):
        raise AdjudicationError(
            "The completed CSV and JSON are inconsistent."
        )

    # Keep previous completed versions outside normal draft/complete discovery.
    archive_directory = (
        paths.output_directory
        / "history"
        / uuid.uuid4().hex
    )
    archive_directory.mkdir(parents=True, exist_ok=False)

    archived_csv = archive_directory / paths.complete_csv.name
    archived_json = archive_directory / paths.state_json.name

    shutil.copy2(paths.complete_csv, archived_csv)
    shutil.copy2(paths.state_json, archived_json)

    if (
        archived_csv.read_bytes() != completed_bytes
        or archived_json.read_bytes() != original_state_bytes
    ):
        raise AdjudicationError(
            "Completed adjudication archive verification failed."
        )

    # Reopened output must be a draft, regardless of old completion metadata.
    working = deepcopy(comparison)

    for interval in working.prefilled_intervals:
        interval.waveform_complete = False
        interval.terminal_event_status = ""
        interval.terminal_event_comment = ""

    try:
        draft_path = _save_adjudication_draft_impl(
            record,
            working,
            selected_interval_index=selected_interval_index,
            selected_region_id=selected_region_id,
            allow_completed=True,
        )
    except Exception:
        # Restore the complete state pairing. The archive remains available.
        _atomic_write_bytes(paths.state_json, original_state_bytes)
        raise

    # Delete the old active COMPLETE file only after draft verification.
    try:
        paths.complete_csv.unlink()
    except OSError as exc:
        # The JSON now identifies the verified draft as authoritative.
        print(
            "[ADJ] Draft saved; previous COMPLETE cleanup failed:",
            exc,
        )

    return draft_path


# =============================================================================
# Draft restoration helpers
# =============================================================================

def _restore_source(data: Mapping[str, Any]) -> SourceAnnotationFile:
    """Restore source metadata from JSON."""
    return SourceAnnotationFile(
        username=str(data["username"]),
        alias=str(data["alias"]),
        path=Path(str(data["path"])),
        size_bytes=int(data["size_bytes"]),
        modified_at=str(data["modified_at"]),
        complete=bool(data["complete"]),
        readiness_status=InputReadinessStatus(data["readiness_status"]),
        readiness_message=str(data.get("readiness_message", "")),
    )


def _restore_region(data: Mapping[str, Any]) -> ComparisonRegion:
    """Restore a comparison region and its explicit resolution state."""
    annotation_a = data.get("annotation_a")
    annotation_b = data.get("annotation_b")

    return ComparisonRegion(
        region_id=str(data["region_id"]),
        start=float(data["start"]),
        end=float(data["end"]),
        status=ComparisonStatus(data["status"]),
        reasons=list(data.get("reasons", [])),
        annotation_a=(
            AnnotationInterval(**annotation_a)
            if annotation_a is not None
            else None
        ),
        annotation_b=(
            AnnotationInterval(**annotation_b)
            if annotation_b is not None
            else None
        ),
        resolved=bool(data.get("resolved", False)),
        resolved_at=data.get("resolved_at"),
    )


# =============================================================================
# Draft loading
# =============================================================================

def load_existing_adjudication(
    record: Mapping[str, Any],
    adjudicator: str,
) -> tuple[AdjudicationComparisonResult, dict[str, Any]]:
    """
    Restore a draft or completed adjudication and its matching state JSON.

    The JSON status identifies the authoritative CSV. A completed CSV may
    temporarily coexist with a reopened draft after cleanup failure.

    Returns
    -------
    tuple
        Restored comparison and navigation/completion metadata.
    """
    started = perf_counter()

    try:
        return _load_existing_adjudication_impl(
            record,
            adjudicator,
        )
    except Exception as exc:
        print("[ADJ] Resume failed:", type(exc).__name__, exc)
        raise
    finally:
        _perf_log(
            "load_existing_adjudication",
            perf_counter() - started,
        )


def _load_existing_adjudication_impl(
    record: Mapping[str, Any],
    adjudicator: str,
) -> tuple[AdjudicationComparisonResult, dict[str, Any]]:
    """Restore the CSV selected by the saved workflow status."""
    paths = get_adjudication_paths(
        record_output_path=record["output_path"],
        subject=record["subject"],
        file_tag=record["file_tag"],
        adjudicator=adjudicator,
    )

    if not paths.state_json.is_file():
        raise AdjudicationError(
            "No companion adjudication state JSON was found."
        )

    state = json.loads(
        paths.state_json.read_text(encoding="utf-8")
    )

    if state.get("schema_version") != ADJUDICATION_SCHEMA_VERSION:
        raise UnsupportedSchemaError(
            f"Unsupported schema: {state.get('schema_version')}"
        )

    if state.get("record_type") != ADJUDICATION_STATE_RECORD_TYPE:
        raise AdjudicationError(
            "This is not an adjudication state file."
        )

    status = state.get("status")

    if status == "complete":
        csv_path = paths.complete_csv
    elif status == "draft":
        csv_path = paths.draft_csv
    else:
        raise AdjudicationError(
            f"Unsupported saved adjudication status: {status!r}"
        )

    if not csv_path.is_file():
        raise AdjudicationError(
            f"The state references a missing {status} CSV: {csv_path}"
        )

    expected = {
        "subject": str(record["subject"]),
        "encounter": str(record["encounter"]),
        "file_tag": str(record["file_tag"]),
        "adjudicator": adjudicator,
    }

    for name, value in expected.items():
        if str(state.get(name, "")) != value:
            raise AdjudicationError(
                f"Saved {name} does not match the selected record/reviewer."
            )

    csv_bytes = csv_path.read_bytes()

    if _sha256(csv_bytes) != state.get("csv_sha256"):
        raise AdjudicationError(
            "The adjudication CSV and JSON do not match. "
            "Do not overwrite them; investigate the interrupted save "
            "or external modification."
        )

    signatures = state.get("source_signatures", [])

    if len(signatures) != 2:
        raise AdjudicationError(
            "Saved state must contain two source-file signatures."
        )

    for signature in signatures:
        _verify_source_signature(signature)

    dataframe = pd.read_csv(
        io.BytesIO(csv_bytes),
        dtype={
            column: str
            for column in ADJUDICATION_OUTPUT_COLUMNS
            if column not in {"start", "end"}
        },
        keep_default_na=False,
        float_precision="round_trip",
    )

    required = set(ADJUDICATION_OUTPUT_COLUMNS) | {"adjudicator"}
    missing = required.difference(dataframe.columns)

    if missing:
        raise InvalidAnnotationError(
            f"Saved CSV is missing columns: {sorted(missing)}"
        )

    final_intervals: list[AdjudicationInterval] = []

    for row in dataframe.to_dict(orient="records"):
        row["start"] = float(row["start"])
        row["end"] = float(row["end"])
        row["waveform_complete"] = coerce_bool(
            row["waveform_complete"]
        )

        if (
            row["user"] != adjudicator
            or row["adjudicator"] != adjudicator
        ):
            raise InvalidAnnotationError(
                "Saved adjudication contains another reviewer."
            )

        fields = {
            name: row[name]
            for name in AdjudicationInterval.__dataclass_fields__
        }

        final_intervals.append(
            AdjudicationInterval(**fields)
        )

    _validate_draft_intervals(final_intervals)

    is_complete = status == "complete"

    if is_complete and not final_intervals[-1].waveform_complete:
        raise InvalidAnnotationError(
            "Completed adjudication lacks its final completion flag."
        )

    if not is_complete and any(
        interval.waveform_complete
        for interval in final_intervals
    ):
        raise InvalidAnnotationError(
            "Draft adjudication contains completion flags."
        )

    comparison = AdjudicationComparisonResult(
        adjudicator=adjudicator,
        subject=str(state["subject"]),
        encounter=str(state["encounter"]),
        namespace=str(state.get("namespace", "")),
        file_tag=str(state["file_tag"]),
        source_a=_restore_source(state["source_a"]),
        source_b=_restore_source(state["source_b"]),
        annotator_a_intervals=[
            AnnotationInterval(**item)
            for item in state["annotator_a_intervals"]
        ],
        annotator_b_intervals=[
            AnnotationInterval(**item)
            for item in state["annotator_b_intervals"]
        ],
        boundary_matches=[
            BoundaryMatch(**item)
            for item in state["boundary_matches"]
        ],
        comparison_regions=[
            _restore_region(item)
            for item in state["comparison_regions"]
        ],
        prefilled_intervals=final_intervals,
        validation_issues=[
            ValidationIssue(**item)
            for item in state.get("validation_issues", [])
        ],
        boundary_tolerance_sec=float(
            state["boundary_tolerance_sec"]
        ),
        created_at=str(state["created_at"]),
    )

    return comparison, {
        "selected_interval_index": state.get("selected_interval_index"),
        "selected_region_id": state.get("selected_region_id"),
        "complete": is_complete,
    }

# =============================================================================
# Finalization validation
# =============================================================================

def validate_adjudication_for_finalization(
    comparison: AdjudicationComparisonResult,
    waveform_start: float,
    waveform_end: float,
) -> list[str]:
    """
    Return errors preventing finalization.

    Parameters
    ----------
    comparison : AdjudicationComparisonResult
        Current final timeline and resolution state.

    waveform_start, waveform_end : float
        Loaded waveform bounds in floating-point UTC epoch seconds.

    Returns
    -------
    list[str]
        Empty when the adjudication is eligible for finalization.

    Notes
    -----
    Validation does not change interval data or resolution state.
    """
    started = perf_counter()

    try:
        return _validate_adjudication_for_finalization_impl(
            comparison,
            waveform_start,
            waveform_end,
        )
    finally:
        _perf_log(
            "validate_adjudication_for_finalization",
            perf_counter() - started,
        )


def _validate_adjudication_for_finalization_impl(
    comparison: AdjudicationComparisonResult,
    waveform_start: float,
    waveform_end: float,
) -> list[str]:
    """Check final coverage, labels, interval lengths, and resolution."""
    errors: list[str] = []
    intervals = comparison.prefilled_intervals
    epsilon = 1e-6

    if (
        not np.isfinite(waveform_start)
        or not np.isfinite(waveform_end)
        or waveform_end <= waveform_start
    ):
        return ["The loaded waveform bounds are invalid."]

    if not intervals:
        return ["The final timeline is empty."]

    if comparison.unresolved_regions:
        errors.append(
            f"{len(comparison.unresolved_regions)} review region(s) "
            "still require Mark Resolved."
        )

    if abs(intervals[0].start - waveform_start) > epsilon:
        errors.append(
            "The final timeline does not start at the loaded waveform start."
        )

    if abs(intervals[-1].end - waveform_end) > epsilon:
        errors.append(
            "The final timeline does not end at the loaded waveform end."
        )

    previous_end: Optional[float] = None

    for index, interval in enumerate(intervals, start=1):
        prefix = f"Interval {index}:"

        if (
            not np.isfinite(interval.start)
            or not np.isfinite(interval.end)
            or interval.end <= interval.start
        ):
            errors.append(f"{prefix} invalid boundaries.")
            continue

        if interval.duration + epsilon < MINIMUM_VALID_INTERVAL_SEC:
            errors.append(
                f"{prefix} duration is below "
                f"{MINIMUM_VALID_INTERVAL_SEC:g} second(s). "
                "Adjust or merge this interval."
            )

        if (
            interval.start < waveform_start - epsilon
            or interval.end > waveform_end + epsilon
        ):
            errors.append(f"{prefix} extends outside the loaded waveform.")

        if previous_end is not None:
            delta = interval.start - previous_end

            if delta > epsilon:
                errors.append(f"{prefix} a gap precedes this interval.")
            elif delta < -epsilon:
                errors.append(f"{prefix} overlaps the previous interval.")

        previous_end = interval.end

        if interval.cpr not in {"Yes", "No", "Unable to Determine"}:
            errors.append(f"{prefix} select a CPR answer.")

        elif interval.cpr == "No":
            if not interval.rhythm_label.strip():
                errors.append(f"{prefix} select a rhythm.")

            if (
                interval.rhythm_label in {"Other", "Unable to Determine"}
                and not interval.rhythm_expl.strip()
            ):
                errors.append(f"{prefix} an explanation is required.")

        elif interval.cpr == "Unable to Determine":
            if not interval.rhythm_expl.strip():
                errors.append(f"{prefix} a CPR explanation is required.")

        if interval.cpr != "No" and interval.rhythm_label.strip():
            errors.append(
                f"{prefix} rhythm must be blank for this CPR answer."
            )

    return errors


# =============================================================================
# Completed adjudication saving
# =============================================================================

def save_completed_adjudication(
    record: Mapping[str, Any],
    comparison: AdjudicationComparisonResult,
    *,
    waveform_start: float,
    waveform_end: float,
    terminal_event_status: str,
    terminal_event_comment: str,
) -> Path:
    """
    Save a validated completed CSV and companion state JSON.

    A draft is saved first as a recovery copy. The draft is removed only after
    the completed CSV and JSON have been written and verified.

    This function works on a copy and never modifies source annotations.
    """
    started = perf_counter()

    try:
        return _save_completed_adjudication_impl(
            record,
            comparison,
            waveform_start=waveform_start,
            waveform_end=waveform_end,
            terminal_event_status=terminal_event_status,
            terminal_event_comment=terminal_event_comment,
        )
    except Exception as exc:
        print("[ADJ] Finalization save failed:", type(exc).__name__, exc)
        raise
    finally:
        _perf_log(
            "save_completed_adjudication",
            perf_counter() - started,
        )


def _save_completed_adjudication_impl(
    record: Mapping[str, Any],
    comparison: AdjudicationComparisonResult,
    *,
    waveform_start: float,
    waveform_end: float,
    terminal_event_status: str,
    terminal_event_comment: str,
) -> Path:
    """Write completed output while retaining a draft until verification."""
    errors = validate_adjudication_for_finalization(
        comparison,
        waveform_start,
        waveform_end,
    )

    if errors:
        raise InvalidAnnotationError("\n".join(errors))

    if terminal_event_status not in VALID_TERMINAL_EVENT_STATUSES:
        raise InvalidAnnotationError("Select a valid terminal-event status.")

    working = deepcopy(comparison)

    # Save recoverable draft state before creating completed output.
    for interval in working.prefilled_intervals:
        interval.waveform_complete = False
        interval.terminal_event_status = ""
        interval.terminal_event_comment = ""

    save_adjudication_draft(record, working)

    paths = get_adjudication_paths(
        record_output_path=record["output_path"],
        subject=working.subject,
        file_tag=working.file_tag,
        adjudicator=working.adjudicator,
        source_paths=[working.source_a.path, working.source_b.path],
    )

    finalized_at = utc_now_iso()

    for interval in working.prefilled_intervals:
        interval.adjudication_updated_at = finalized_at

    final_interval = working.prefilled_intervals[-1]
    final_interval.waveform_complete = True
    final_interval.terminal_event_status = terminal_event_status
    final_interval.terminal_event_comment = terminal_event_comment.strip()

    rows = []

    for interval in working.prefilled_intervals:
        row = interval.to_dict()
        row["user"] = working.adjudicator
        row["adjudicator"] = working.adjudicator
        rows.append(row)

    columns = list(ADJUDICATION_OUTPUT_COLUMNS)

    if "adjudicator" not in columns:
        columns.append("adjudicator")

    csv_bytes = (
        pd.DataFrame(rows)
        .reindex(columns=columns)
        .to_csv(index=False)
        .encode("utf-8")
    )

    state = json.loads(paths.state_json.read_text(encoding="utf-8"))
    state["status"] = "complete"
    state["updated_at"] = finalized_at
    state["finalized_at"] = finalized_at
    state["csv_sha256"] = _sha256(csv_bytes)

    state_bytes = json.dumps(
        json_safe_value(state),
        indent=2,
        allow_nan=False,
    ).encode("utf-8")

    _atomic_write_bytes(paths.complete_csv, csv_bytes)
    _atomic_write_bytes(paths.state_json, state_bytes)

    # CSV/JSON are separate writes; verify their pairing before reporting success.
    if _sha256(paths.complete_csv.read_bytes()) != state["csv_sha256"]:
        raise AdjudicationError("Completed CSV verification failed.")

    verified_state = json.loads(
        paths.state_json.read_text(encoding="utf-8")
    )

    if (
        verified_state.get("status") != "complete"
        or verified_state.get("csv_sha256") != state["csv_sha256"]
    ):
        raise AdjudicationError("Completed state verification failed.")

    # A cleanup failure must not invalidate successfully saved completed output.
    try:
        paths.draft_csv.unlink(missing_ok=True)
    except OSError as exc:
        print("[ADJ] Completed output saved; draft cleanup failed:", exc)

    return paths.complete_csv