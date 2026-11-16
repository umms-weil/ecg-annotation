"""
Persistence tests for draft and completed waveform adjudications.

All input files are synthetic. Tests never access Turbo or clinical data.
"""

from __future__ import annotations

import json

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

import adjudication.paths as adjudication_paths_module

from adjudication.comparison import build_adjudication_comparison
from adjudication.config import ComparisonStatus
from adjudication.exceptions import (
    AdjudicationError,
    InvalidAnnotationError,
    SourceFilesChangedError,
)
from adjudication.paths import get_adjudication_paths
from adjudication.persistence import (
    load_existing_adjudication,
    save_adjudication_draft,
    save_completed_adjudication,
    save_reopened_adjudication_draft,
    validate_adjudication_for_finalization,
)


WAVEFORM_START: float = 1_700_000_000.125
INTERNAL_BOUNDARY: float = 1_700_000_010.625
WAVEFORM_END: float = 1_700_000_020.875

TERMINAL_STATUS: str = "does_not_continue_beyond_waveform"
TERMINAL_COMMENT: str = "Synthetic final review comment."


# =============================================================================
# Persistence fixtures
# =============================================================================

@pytest.fixture
def persistence_session(
    waveform_record,
    write_annotation_file,
    annotators,
    adjudicator,
    monkeypatch,
) -> dict[str, Any]:
    """
    Create two completed synthetic inputs and their comparison result.

    The synthetic reviewer is allowed only within this test fixture.
    Production participant configuration is not modified permanently.
    """
    monkeypatch.setattr(
        adjudication_paths_module,
        "ADJUDICATORS",
        [adjudicator],
    )

    intervals = [
        {
            "start": WAVEFORM_START,
            "end": INTERNAL_BOUNDARY,
            "cpr": "No",
            "rhythm_label": "Normal Heart Rhythm",
            "rhythm_expl": "",
        },
        {
            "start": INTERNAL_BOUNDARY,
            "end": WAVEFORM_END,
            "cpr": "No",
            "rhythm_label": "Sinus tachycardia",
            "rhythm_expl": "",
        },
    ]

    source_paths = [
        write_annotation_file(
            user=username,
            intervals=intervals,
            complete=True,
        )
        for username in annotators
    ]

    comparison = build_adjudication_comparison(
        record=waveform_record,
        adjudicator=adjudicator,
        annotators=annotators,
        allowed_adjudicators=[adjudicator],
    )

    paths = get_adjudication_paths(
        record_output_path=waveform_record["output_path"],
        subject=waveform_record["subject"],
        file_tag=waveform_record["file_tag"],
        adjudicator=adjudicator,
    )

    return {
        "record": waveform_record,
        "reviewer": adjudicator,
        "comparison": comparison,
        "paths": paths,
        "source_paths": source_paths,
        "source_bytes": {
            path: path.read_bytes()
            for path in source_paths
        },
    }


def assert_source_files_unchanged(
    session: dict[str, Any],
) -> None:
    """
    Confirm persistence operations did not change either source CSV.
    """
    for path, original_bytes in session["source_bytes"].items():
        assert path.read_bytes() == original_bytes


def read_state(path: Path) -> dict[str, Any]:
    """Read an adjudication state JSON for test assertions."""
    return json.loads(path.read_text(encoding="utf-8"))


# =============================================================================
# Draft save and resume
# =============================================================================

def test_draft_save_and_resume_preserves_timeline(
    persistence_session,
):
    """
    Draft CSV/JSON must preserve labels, precision, and navigation state.
    """
    session = persistence_session
    comparison = session["comparison"]
    paths = session["paths"]

    selected_region_id = comparison.comparison_regions[1].region_id

    saved_path = save_adjudication_draft(
        session["record"],
        comparison,
        selected_interval_index=1,
        selected_region_id=selected_region_id,
    )

    assert saved_path == paths.draft_csv
    assert paths.draft_csv.is_file()
    assert paths.state_json.is_file()
    assert not paths.complete_csv.exists()
    assert read_state(paths.state_json)["status"] == "draft"

    restored, navigation = load_existing_adjudication(
        session["record"],
        session["reviewer"],
    )

    assert navigation["complete"] is False
    assert navigation["selected_interval_index"] == 1
    assert navigation["selected_region_id"] == selected_region_id

    assert len(restored.prefilled_intervals) == 2
    assert (
        restored.prefilled_intervals[0].rhythm_label
        == "Normal Heart Rhythm"
    )
    assert (
        restored.prefilled_intervals[1].rhythm_label
        == "Sinus tachycardia"
    )

    # Exact equality checks round-trip preservation of these float values.
    assert restored.prefilled_intervals[0].start == WAVEFORM_START
    assert restored.prefilled_intervals[0].end == INTERNAL_BOUNDARY
    assert restored.prefilled_intervals[1].start == INTERNAL_BOUNDARY
    assert restored.prefilled_intervals[1].end == WAVEFORM_END

    assert all(
        not interval.waveform_complete
        for interval in restored.prefilled_intervals
    )

    assert all(
        interval.user == session["reviewer"]
        and interval.adjudicator == session["reviewer"]
        for interval in restored.prefilled_intervals
    )

    assert_source_files_unchanged(session)


def test_draft_resume_preserves_unresolved_region(
    persistence_session,
):
    """
    Saving a draft must not implicitly resolve a disagreement.
    """
    session = persistence_session
    comparison = session["comparison"]

    region = comparison.comparison_regions[0]
    region.status = ComparisonStatus.UNRESOLVED_DISAGREEMENT
    region.reasons = ["rhythm_mismatch"]
    region.resolved = False
    region.resolved_at = None

    # Unlabeled provisional intervals are valid draft content.
    comparison.prefilled_intervals[0].cpr = ""
    comparison.prefilled_intervals[0].rhythm_label = ""

    save_adjudication_draft(
        session["record"],
        comparison,
    )

    restored, navigation = load_existing_adjudication(
        session["record"],
        session["reviewer"],
    )

    assert navigation["complete"] is False
    assert len(restored.unresolved_regions) == 1

    restored_region = restored.unresolved_regions[0]

    assert restored_region.region_id == region.region_id
    assert restored_region.reasons == ["rhythm_mismatch"]
    assert restored_region.resolved is False
    assert restored_region.resolved_at is None

    assert restored.prefilled_intervals[0].cpr == ""
    assert restored.prefilled_intervals[0].rhythm_label == ""

    assert_source_files_unchanged(session)


# =============================================================================
# Finalization
# =============================================================================

def test_completed_save_and_resume_restores_completion(
    persistence_session,
):
    """
    Completed output must restore completion state and terminal metadata.

    The UI uses navigation['complete'] to open the session read-only.
    """
    session = persistence_session
    paths = session["paths"]

    saved_path = save_completed_adjudication(
        session["record"],
        session["comparison"],
        waveform_start=WAVEFORM_START,
        waveform_end=WAVEFORM_END,
        terminal_event_status=TERMINAL_STATUS,
        terminal_event_comment=TERMINAL_COMMENT,
    )

    assert saved_path == paths.complete_csv
    assert paths.complete_csv.is_file()
    assert paths.state_json.is_file()
    assert not paths.draft_csv.exists()
    assert read_state(paths.state_json)["status"] == "complete"

    restored, navigation = load_existing_adjudication(
        session["record"],
        session["reviewer"],
    )

    assert navigation["complete"] is True
    assert restored.unresolved_regions == []

    assert all(
        not interval.waveform_complete
        for interval in restored.prefilled_intervals[:-1]
    )

    final_interval = restored.prefilled_intervals[-1]

    assert final_interval.waveform_complete is True
    assert final_interval.terminal_event_status == TERMINAL_STATUS
    assert final_interval.terminal_event_comment == TERMINAL_COMMENT

    # The persistence function works on a copy of the input comparison.
    assert all(
        not interval.waveform_complete
        for interval in session["comparison"].prefilled_intervals
    )

    assert_source_files_unchanged(session)


def test_finalization_rejects_unresolved_regions(
    persistence_session,
):
    """
    Valid labels do not replace the explicit Mark Resolved requirement.
    """
    session = persistence_session
    comparison = session["comparison"]

    region = comparison.comparison_regions[0]
    region.status = ComparisonStatus.UNRESOLVED_DISAGREEMENT
    region.reasons = ["boundary_outside_tolerance"]
    region.resolved = False

    errors = validate_adjudication_for_finalization(
        comparison,
        WAVEFORM_START,
        WAVEFORM_END,
    )

    assert any("Mark Resolved" in error for error in errors)

    with pytest.raises(InvalidAnnotationError):
        save_completed_adjudication(
            session["record"],
            comparison,
            waveform_start=WAVEFORM_START,
            waveform_end=WAVEFORM_END,
            terminal_event_status=TERMINAL_STATUS,
            terminal_event_comment="",
        )

    assert not session["paths"].complete_csv.exists()
    assert_source_files_unchanged(session)


def test_finalization_rejects_incomplete_waveform_coverage(
    persistence_session,
):
    """
    The final timeline must cover the actual loaded waveform range.
    """
    session = persistence_session
    comparison = session["comparison"]

    comparison.prefilled_intervals[0].start += 1.0

    errors = validate_adjudication_for_finalization(
        comparison,
        WAVEFORM_START,
        WAVEFORM_END,
    )

    assert any(
        "does not start" in error
        for error in errors
    )

    with pytest.raises(InvalidAnnotationError):
        save_completed_adjudication(
            session["record"],
            comparison,
            waveform_start=WAVEFORM_START,
            waveform_end=WAVEFORM_END,
            terminal_event_status=TERMINAL_STATUS,
            terminal_event_comment="",
        )

    assert not session["paths"].complete_csv.exists()


# =============================================================================
# Reopening completed adjudication
# =============================================================================

def test_reopened_save_creates_draft_and_preserves_history(
    persistence_session,
):
    """
    Reopened unresolved work must save as draft, preserving prior completion.
    """
    session = persistence_session
    paths = session["paths"]

    save_completed_adjudication(
        session["record"],
        session["comparison"],
        waveform_start=WAVEFORM_START,
        waveform_end=WAVEFORM_END,
        terminal_event_status=TERMINAL_STATUS,
        terminal_event_comment=TERMINAL_COMMENT,
    )

    original_complete_bytes = paths.complete_csv.read_bytes()
    original_state_bytes = paths.state_json.read_bytes()

    restored, navigation = load_existing_adjudication(
        session["record"],
        session["reviewer"],
    )

    assert navigation["complete"] is True

    # Mirror the UI's explicit reopening behavior.
    reopened = deepcopy(restored)

    for interval in reopened.prefilled_intervals:
        interval.waveform_complete = False
        interval.terminal_event_status = ""
        interval.terminal_event_comment = ""

    reopened.prefilled_intervals[0].rhythm_label = "Bradycardia"

    region = reopened.comparison_regions[0]
    region.status = ComparisonStatus.UNRESOLVED_DISAGREEMENT
    region.reasons = ["rhythm_mismatch"]
    region.resolved = False
    region.resolved_at = None

    saved_path = save_reopened_adjudication_draft(
        session["record"],
        reopened,
        selected_interval_index=0,
        selected_region_id=region.region_id,
    )

    assert saved_path == paths.draft_csv
    assert paths.draft_csv.is_file()
    assert not paths.complete_csv.exists()
    assert read_state(paths.state_json)["status"] == "draft"

    archives = list(
        (paths.output_directory / "history").iterdir()
    )

    assert len(archives) == 1

    archive_directory = archives[0]

    assert (
        archive_directory / paths.complete_csv.name
    ).read_bytes() == original_complete_bytes

    assert (
        archive_directory / paths.state_json.name
    ).read_bytes() == original_state_bytes

    resumed, navigation = load_existing_adjudication(
        session["record"],
        session["reviewer"],
    )

    assert navigation["complete"] is False
    assert resumed.prefilled_intervals[0].rhythm_label == "Bradycardia"
    assert len(resumed.unresolved_regions) == 1

    assert all(
        not interval.waveform_complete
        and interval.terminal_event_status == ""
        and interval.terminal_event_comment == ""
        for interval in resumed.prefilled_intervals
    )

    # The reopened draft still cannot finalize while unresolved.
    with pytest.raises(InvalidAnnotationError):
        save_completed_adjudication(
            session["record"],
            resumed,
            waveform_start=WAVEFORM_START,
            waveform_end=WAVEFORM_END,
            terminal_event_status=TERMINAL_STATUS,
            terminal_event_comment="",
        )

    assert_source_files_unchanged(session)


# =============================================================================
# Integrity and input-change checks
# =============================================================================

def test_resume_rejects_csv_state_mismatch(
    persistence_session,
):
    """
    An externally changed CSV must not silently load with stale JSON state.
    """
    session = persistence_session
    paths = session["paths"]

    save_adjudication_draft(
        session["record"],
        session["comparison"],
    )

    # Alter only the synthetic adjudication CSV.
    with paths.draft_csv.open("ab") as handle:
        handle.write(b"\n")

    with pytest.raises(AdjudicationError, match="do not match"):
        load_existing_adjudication(
            session["record"],
            session["reviewer"],
        )

    assert_source_files_unchanged(session)


def test_resume_rejects_changed_source_annotation(
    persistence_session,
):
    """
    Resume must detect source changes after the draft was saved.
    """
    session = persistence_session

    save_adjudication_draft(
        session["record"],
        session["comparison"],
    )

    # Deliberately modify one synthetic input to exercise change detection.
    source_path = session["source_paths"][0]

    with source_path.open("ab") as handle:
        handle.write(b"\n")

    with pytest.raises(SourceFilesChangedError):
        load_existing_adjudication(
            session["record"],
            session["reviewer"],
        )