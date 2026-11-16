"""
Tests for boundary extraction and tolerance-based matching.
"""

from adjudication.boundaries import (
    extract_and_match_source_boundaries,
)
from adjudication.models import (
    AnnotationInterval,
)


def make_interval(
    *,
    alias: str,
    user: str,
    start: float,
    end: float,
    row: int,
    rhythm: str,
) -> AnnotationInterval:
    """
    Create one normalized source interval.
    """
    return AnnotationInterval(
        user=user,
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
        source_alias=alias,
        source_row=row,
    )


def test_boundary_within_tolerance_uses_midpoint():
    """
    A one-second internal boundary offset should be accepted inclusively.
    """
    intervals_a = [
        make_interval(
            alias="Annotator A",
            user="annotator_one",
            start=100.0,
            end=105.0,
            row=0,
            rhythm="Normal Heart Rhythm",
        ),
        make_interval(
            alias="Annotator A",
            user="annotator_one",
            start=105.0,
            end=110.0,
            row=1,
            rhythm="Sinus tachycardia",
        ),
    ]

    intervals_b = [
        make_interval(
            alias="Annotator B",
            user="annotator_two",
            start=100.0,
            end=106.0,
            row=0,
            rhythm="Normal Heart Rhythm",
        ),
        make_interval(
            alias="Annotator B",
            user="annotator_two",
            start=106.0,
            end=110.0,
            row=1,
            rhythm="Sinus tachycardia",
        ),
    ]

    _, _, matches = (
        extract_and_match_source_boundaries(
            intervals_a=intervals_a,
            intervals_b=intervals_b,
            tolerance_sec=1.0,
        )
    )

    internal_matches = [
        match
        for match in matches
        if (
            match.matched
            and match.boundary_type == "internal"
        )
    ]

    assert len(internal_matches) == 1
    assert internal_matches[0].difference_seconds == 1.0
    assert internal_matches[0].midpoint == 105.5


def test_boundary_outside_tolerance_is_unmatched():
    """
    An internal boundary over one second away must not be reconciled.
    """
    intervals_a = [
        make_interval(
            alias="Annotator A",
            user="annotator_one",
            start=100.0,
            end=105.0,
            row=0,
            rhythm="Normal Heart Rhythm",
        ),
        make_interval(
            alias="Annotator A",
            user="annotator_one",
            start=105.0,
            end=111.0,
            row=1,
            rhythm="Sinus tachycardia",
        ),
    ]

    intervals_b = [
        make_interval(
            alias="Annotator B",
            user="annotator_two",
            start=100.0,
            end=106.01,
            row=0,
            rhythm="Normal Heart Rhythm",
        ),
        make_interval(
            alias="Annotator B",
            user="annotator_two",
            start=106.01,
            end=111.0,
            row=1,
            rhythm="Sinus tachycardia",
        ),
    ]

    _, _, matches = (
        extract_and_match_source_boundaries(
            intervals_a=intervals_a,
            intervals_b=intervals_b,
            tolerance_sec=1.0,
        )
    )

    assert not any(
        match.matched
        and match.boundary_type == "internal"
        for match in matches
    )

    assert any(
        "boundary_outside_tolerance"
        in match.reasons
        for match in matches
        if not match.matched
    )


def test_adjacent_label_mismatch_prevents_matching():
    """
    Close boundaries must remain unmatched when neighboring labels differ.
    """
    intervals_a = [
        make_interval(
            alias="Annotator A",
            user="annotator_one",
            start=100.0,
            end=105.0,
            row=0,
            rhythm="Normal Heart Rhythm",
        ),
        make_interval(
            alias="Annotator A",
            user="annotator_one",
            start=105.0,
            end=110.0,
            row=1,
            rhythm="Sinus tachycardia",
        ),
    ]

    intervals_b = [
        make_interval(
            alias="Annotator B",
            user="annotator_two",
            start=100.0,
            end=105.2,
            row=0,
            rhythm="Atrial Fibrillation",
        ),
        make_interval(
            alias="Annotator B",
            user="annotator_two",
            start=105.2,
            end=110.0,
            row=1,
            rhythm="Sinus tachycardia",
        ),
    ]

    _, _, matches = (
        extract_and_match_source_boundaries(
            intervals_a=intervals_a,
            intervals_b=intervals_b,
            tolerance_sec=1.0,
        )
    )

    assert not any(
        match.matched
        and match.boundary_type == "internal"
        for match in matches
    )

    assert any(
        "adjacent_label_mismatch"
        in match.reasons
        for match in matches
        if not match.matched
    )