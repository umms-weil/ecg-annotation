"""
End-to-end tests for the non-UI adjudication comparison engine.
"""

from pathlib import Path

import pytest

from adjudication.comparison import (
    build_adjudication_comparison,
)
from adjudication.config import (
    ComparisonStatus,
)


def test_build_adjudication_comparison_exact_agreement(
    waveform_record,
    write_annotation_file,
    annotators,
    adjudicator,
):
    """
    Two identical complete timelines should produce green agreement.
    """
    intervals = [
        {
            "start": 1_700_000_000.123456,
            "end": 1_700_000_010.654321,
            "rhythm_label": "Normal Heart Rhythm",
        },
        {
            "start": 1_700_000_010.654321,
            "end": 1_700_000_020.987654,
            "rhythm_label": "Sinus tachycardia",
        },
    ]

    source_paths = []

    for user in annotators:
        source_paths.append(
            write_annotation_file(
                user=user,
                intervals=intervals,
            )
        )

    source_bytes_before = {
        path: path.read_bytes()
        for path in source_paths
    }

    result = build_adjudication_comparison(
        record=waveform_record,
        adjudicator=adjudicator,
        annotators=annotators,
        allowed_adjudicators=[adjudicator],
        boundary_tolerance_sec=1.0,
    )

    assert result.ready_for_review is True
    assert result.unresolved_regions == []

    assert all(
        region.status
        == ComparisonStatus.AGREEMENT
        for region in result.comparison_regions
    )

    assert len(result.prefilled_intervals) == 2

    # Floating-point boundaries must remain unchanged.
    assert result.prefilled_intervals[0].start == pytest.approx(
        1_700_000_000.123456,
        abs=1e-9,
    )

    assert result.prefilled_intervals[-1].end == pytest.approx(
        1_700_000_020.987654,
        abs=1e-9,
    )

    # The comparison engine must never modify source files.
    for path in source_paths:
        assert path.read_bytes() == source_bytes_before[path]


def test_build_adjudication_comparison_midpoint_boundary(
    waveform_record,
    write_annotation_file,
    annotators,
    adjudicator,
):
    """
    Matching labels with boundaries within tolerance should use the midpoint.
    """
    write_annotation_file(
        user=annotators[0],
        intervals=[
            {
                "start": 1_700_000_000.0,
                "end": 1_700_000_005.0,
                "rhythm_label": "Normal Heart Rhythm",
            },
            {
                "start": 1_700_000_005.0,
                "end": 1_700_000_011.0,
                "rhythm_label": "Sinus tachycardia",
            },
        ],
    )

    write_annotation_file(
        user=annotators[1],
        intervals=[
            {
                "start": 1_700_000_000.0,
                "end": 1_700_000_006.0,
                "rhythm_label": "Normal Heart Rhythm",
            },
            {
                "start": 1_700_000_006.0,
                "end": 1_700_000_011.0,
                "rhythm_label": "Sinus tachycardia",
            },
        ],
    )

    result = build_adjudication_comparison(
        record=waveform_record,
        adjudicator=adjudicator,
        annotators=annotators,
        allowed_adjudicators=[adjudicator],
        boundary_tolerance_sec=1.0,
    )

    assert result.unresolved_regions == []
    assert len(result.prefilled_intervals) == 2

    reconciled_boundary = (
        result.prefilled_intervals[0].end
    )

    assert reconciled_boundary == pytest.approx(
        1_700_000_005.5,
        abs=1e-9,
    )

    assert (
        result.prefilled_intervals[1].start
        == pytest.approx(
            1_700_000_005.5,
            abs=1e-9,
        )
    )


def test_build_adjudication_comparison_detects_disagreement(
    waveform_record,
    write_annotation_file,
    annotators,
    adjudicator,
):
    """
    Different CPR and rhythm labels should create unresolved regions.
    """
    write_annotation_file(
        user=annotators[0],
        intervals=[
            {
                "start": 1_700_000_000.0,
                "end": 1_700_000_010.0,
                "cpr": "No",
                "rhythm_label": "Normal Heart Rhythm",
            }
        ],
    )

    write_annotation_file(
        user=annotators[1],
        intervals=[
            {
                "start": 1_700_000_000.0,
                "end": 1_700_000_010.0,
                "cpr": "Yes",
                "rhythm_label": "",
            }
        ],
    )

    result = build_adjudication_comparison(
        record=waveform_record,
        adjudicator=adjudicator,
        annotators=annotators,
        allowed_adjudicators=[adjudicator],
    )

    assert len(result.unresolved_regions) >= 1

    reasons = {
        reason
        for region in result.unresolved_regions
        for reason in region.reasons
    }

    assert "cpr_mismatch" in reasons
    assert "rhythm_mismatch" in reasons

    assert result.prefilled_intervals[0].cpr == ""
    assert result.prefilled_intervals[0].rhythm_label == ""