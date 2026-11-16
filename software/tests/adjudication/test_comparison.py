"""
Tests for agreement classification and prefilled final timelines.
"""

from adjudication.config import (
    ComparisonStatus,
)
from adjudication.models import (
    AnnotationInterval,
    BoundaryMatch,
    TimelineSegment,
)
from adjudication.comparison import (
    classify_comparison_regions,
    generate_prefilled_adjudication_timeline,
)


def make_interval(
    *,
    alias: str,
    user: str,
    start: float,
    end: float,
    cpr: str = "No",
    rhythm: str = "Normal Heart Rhythm",
) -> AnnotationInterval:
    """
    Create one synthetic normalized source interval.
    """
    return AnnotationInterval(
        user=user,
        subject="MRN_TEST_001",
        encounter="CSN_TEST_001",
        namespace="GEWAVE",
        file_tag="test_waveform_001",
        source_path="/synthetic/waveform.h5",
        cpr=cpr,
        rhythm_label=rhythm,
        rhythm_expl="",
        start=start,
        end=end,
        waveform_complete=False,
        terminal_event_status="",
        terminal_event_comment="",
        source_alias=alias,
        source_row=0,
    )


def test_exact_matching_segment_is_green():
    """
    Matching coverage, CPR, and rhythm should produce agreement.
    """
    annotation_a = make_interval(
        alias="Annotator A",
        user="annotator_one",
        start=100.0,
        end=110.0,
    )

    annotation_b = make_interval(
        alias="Annotator B",
        user="annotator_two",
        start=100.0,
        end=110.0,
    )

    segment = TimelineSegment(
        segment_id="segment_0001",
        start=100.0,
        end=110.0,
        annotation_a=annotation_a,
        annotation_b=annotation_b,
    )

    regions = classify_comparison_regions(
        segments=[segment],
        boundary_matches=[],
    )

    assert len(regions) == 1
    assert regions[0].status == ComparisonStatus.AGREEMENT
    assert regions[0].reasons == []


def test_cpr_and_rhythm_mismatch_both_recorded():
    """
    One region may contain multiple disagreement reasons.
    """
    annotation_a = make_interval(
        alias="Annotator A",
        user="annotator_one",
        start=100.0,
        end=110.0,
        cpr="No",
        rhythm="Normal Heart Rhythm",
    )

    annotation_b = make_interval(
        alias="Annotator B",
        user="annotator_two",
        start=100.0,
        end=110.0,
        cpr="Yes",
        rhythm="Ventricular Fibrillation",
    )

    segment = TimelineSegment(
        segment_id="segment_0001",
        start=100.0,
        end=110.0,
        annotation_a=annotation_a,
        annotation_b=annotation_b,
    )

    regions = classify_comparison_regions(
        segments=[segment],
        boundary_matches=[],
    )

    region = regions[0]

    assert (
        region.status
        == ComparisonStatus.UNRESOLVED_DISAGREEMENT
    )

    assert "cpr_mismatch" in region.reasons
    assert "rhythm_mismatch" in region.reasons


def test_missing_coverage_is_gray():
    """
    One-sided coverage should produce a missing-coverage region.
    """
    annotation_a = make_interval(
        alias="Annotator A",
        user="annotator_one",
        start=100.0,
        end=110.0,
    )

    segment = TimelineSegment(
        segment_id="segment_0001",
        start=100.0,
        end=110.0,
        annotation_a=annotation_a,
        annotation_b=None,
    )

    regions = classify_comparison_regions(
        segments=[segment],
        boundary_matches=[],
    )

    region = regions[0]

    assert (
        region.status
        == ComparisonStatus.MISSING_COVERAGE
    )

    assert "annotator_a_only" in region.reasons
    assert "missing_coverage" in region.reasons


def test_adjacent_identical_green_regions_merge(
    adjudicator,
):
    """
    Sequential green regions with the same labels should become one interval.
    """
    annotation_a = make_interval(
        alias="Annotator A",
        user="annotator_one",
        start=100.0,
        end=120.0,
    )

    annotation_b = make_interval(
        alias="Annotator B",
        user="annotator_two",
        start=100.0,
        end=120.0,
    )

    segments = [
        TimelineSegment(
            segment_id="segment_0001",
            start=100.0,
            end=110.0,
            annotation_a=annotation_a,
            annotation_b=annotation_b,
        ),
        TimelineSegment(
            segment_id="segment_0002",
            start=110.0,
            end=120.0,
            annotation_a=annotation_a,
            annotation_b=annotation_b,
        ),
    ]

    regions = classify_comparison_regions(
        segments=segments,
        boundary_matches=[],
    )

    final_intervals = (
        generate_prefilled_adjudication_timeline(
            regions=regions,
            adjudicator=adjudicator,
            allowed_adjudicators=[adjudicator],
            merge_adjacent_agreement=True,
        )
    )

    assert len(final_intervals) == 1
    assert final_intervals[0].start == 100.0
    assert final_intervals[0].end == 120.0
    assert (
        final_intervals[0].rhythm_label
        == "Normal Heart Rhythm"
    )


def test_red_region_remains_unlabeled(
    adjudicator,
):
    """
    Prefilled disagreement regions must not favor either annotator.
    """
    annotation_a = make_interval(
        alias="Annotator A",
        user="annotator_one",
        start=100.0,
        end=110.0,
        rhythm="Normal Heart Rhythm",
    )

    annotation_b = make_interval(
        alias="Annotator B",
        user="annotator_two",
        start=100.0,
        end=110.0,
        rhythm="Atrial Fibrillation",
    )

    segment = TimelineSegment(
        segment_id="segment_0001",
        start=100.0,
        end=110.0,
        annotation_a=annotation_a,
        annotation_b=annotation_b,
    )

    regions = classify_comparison_regions(
        segments=[segment],
        boundary_matches=[],
    )

    final_intervals = (
        generate_prefilled_adjudication_timeline(
            regions=regions,
            adjudicator=adjudicator,
            allowed_adjudicators=[adjudicator],
        )
    )

    assert len(final_intervals) == 1
    assert final_intervals[0].cpr == ""
    assert final_intervals[0].rhythm_label == ""
    assert final_intervals[0].rhythm_expl == ""