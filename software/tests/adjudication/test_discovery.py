"""
Tests for discovery of source annotator files.
"""

import pytest

from adjudication.config import (
    InputReadinessStatus,
)
from adjudication.discovery import (
    discover_source_annotation_files,
    require_ready_source_annotation_files,
)
from adjudication.exceptions import (
    MissingInputError,
)


def test_discovers_two_complete_source_files(
    waveform_record,
    write_annotation_file,
    annotators,
):
    """
    Exactly two configured completed files should be ready.
    """
    for user in annotators:
        write_annotation_file(
            user=user,
            intervals=[
                {
                    "start": 1_700_000_000.0,
                    "end": 1_700_000_010.0,
                }
            ],
        )

    sources = discover_source_annotation_files(
        record_output_path=(
            waveform_record["output_path"]
        ),
        subject=waveform_record["subject"],
        file_tag=waveform_record["file_tag"],
        annotators=annotators,
    )

    assert len(sources) == 2
    assert sources[0].alias == "Annotator A"
    assert sources[1].alias == "Annotator B"

    assert all(
        source.readiness_status
        == InputReadinessStatus.READY
        for source in sources
    )

    source_a, source_b = (
        require_ready_source_annotation_files(
            sources
        )
    )

    assert source_a.username == annotators[0]
    assert source_b.username == annotators[1]


def test_partial_source_is_flagged_incomplete(
    waveform_record,
    write_annotation_file,
    annotators,
):
    """
    A partial source file must not be accepted as ready.
    """
    write_annotation_file(
        user=annotators[0],
        intervals=[
            {
                "start": 1_700_000_000.0,
                "end": 1_700_000_010.0,
            }
        ],
        complete=True,
    )

    write_annotation_file(
        user=annotators[1],
        intervals=[
            {
                "start": 1_700_000_000.0,
                "end": 1_700_000_010.0,
            }
        ],
        complete=False,
    )

    sources = discover_source_annotation_files(
        record_output_path=(
            waveform_record["output_path"]
        ),
        subject=waveform_record["subject"],
        file_tag=waveform_record["file_tag"],
        annotators=annotators,
    )

    assert (
        sources[1].readiness_status
        == InputReadinessStatus.INCOMPLETE
    )

    with pytest.raises(MissingInputError):
        require_ready_source_annotation_files(
            sources
        )