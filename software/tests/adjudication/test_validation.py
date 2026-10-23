"""
Tests for source annotation interval validation.
"""

from pathlib import Path

import pytest

from adjudication.config import (
    InputReadinessStatus,
)
from adjudication.exceptions import (
    InvalidAnnotationError,
)
from adjudication.models import (
    AnnotationInterval,
    SourceAnnotationFile,
)
from adjudication.validation import (
    require_valid_source_interval_timeline,
    validate_source_interval_timeline,
)


def make_source() -> SourceAnnotationFile:
    """
    Create synthetic source metadata.
    """
    return SourceAnnotationFile(
        username="annotator_one",
        alias="Annotator A",
        path=Path("/synthetic/source.csv"),
        size_bytes=100,
        modified_at="2026-01-01T00:00:00Z",
        complete=True,
        readiness_status=InputReadinessStatus.READY,
    )


def make_interval(
    *,
    start: float,
    end: float,
    row: int,
    rhythm: str = "Normal Heart Rhythm",
) -> AnnotationInterval:
    """
    Create a synthetic normalized source interval.
    """
    return AnnotationInterval(
        user="annotator_one",
        subject="MRN_TEST_001",
        encounter="CSN_TEST_001",
        namespace="GEWAVE",
        file_tag="test_waveform_001",
        source_path="/synthetic/waveform.h5",
        cpr="No",
        rhythm_label=rhythm,
        rhythm_expl="",
        start=start,
        end=end,
        waveform_complete=False,
        terminal_event_status="",
        terminal_event_comment="",
        source_alias="Annotator A",
        source_row=row,
    )


def test_exactly_one_second_interval_is_valid():
    """
    The configured minimum is inclusive: duration >= 1 second is valid.
    """
    source = make_source()

    interval = make_interval(
        start=1_700_000_000.0,
        end=1_700_000_001.0,
        row=0,
    )

    interval.waveform_complete = True
    interval.terminal_event_status = (
        "does_not_continue_beyond_waveform"
    )

    result = validate_source_interval_timeline(
        intervals=[interval],
        source=source,
    )

    assert result.valid is True


def test_interval_shorter_than_one_second_is_invalid():
    """
    Durations under one second must fail validation.
    """
    source = make_source()

    interval = make_interval(
        start=1_700_000_000.0,
        end=1_700_000_000.5,
        row=0,
    )

    interval.waveform_complete = True
    interval.terminal_event_status = (
        "does_not_continue_beyond_waveform"
    )

    result = validate_source_interval_timeline(
        intervals=[interval],
        source=source,
    )

    assert result.valid is False

    assert any(
        issue.code == "invalid_duration"
        for issue in result.errors
    )

    with pytest.raises(InvalidAnnotationError):
        require_valid_source_interval_timeline(
            intervals=[interval],
            source=source,
        )


def test_gap_is_invalid():
    """
    Gaps in a supposedly complete source timeline must be reported.
    """
    source = make_source()

    intervals = [
        make_interval(
            start=1_700_000_000.0,
            end=1_700_000_005.0,
            row=0,
        ),
        make_interval(
            start=1_700_000_006.0,
            end=1_700_000_010.0,
            row=1,
        ),
    ]

    intervals[-1].waveform_complete = True
    intervals[-1].terminal_event_status = (
        "does_not_continue_beyond_waveform"
    )

    result = validate_source_interval_timeline(
        intervals=intervals,
        source=source,
    )

    assert result.valid is False

    assert any(
        issue.code == "invalid_gap"
        for issue in result.errors
    )


def test_overlap_is_invalid():
    """
    Overlapping source intervals must be reported.
    """
    source = make_source()

    intervals = [
        make_interval(
            start=1_700_000_000.0,
            end=1_700_000_006.0,
            row=0,
        ),
        make_interval(
            start=1_700_000_005.0,
            end=1_700_000_010.0,
            row=1,
        ),
    ]

    intervals[-1].waveform_complete = True
    intervals[-1].terminal_event_status = (
        "does_not_continue_beyond_waveform"
    )

    result = validate_source_interval_timeline(
        intervals=intervals,
        source=source,
    )

    assert result.valid is False

    assert any(
        issue.code == "invalid_overlap"
        for issue in result.errors
    )