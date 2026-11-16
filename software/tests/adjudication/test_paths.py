"""
Tests for adjudication output path and filename contracts.
"""

from pathlib import Path

import pytest

from adjudication.exceptions import (
    AdjudicationPathError,
)
from adjudication.paths import (
    get_adjudication_paths,
)


def test_adjudication_paths_use_separate_folder(
    waveform_record,
    adjudicator,
):
    """
    Adjudication output must remain below ADJUDICATION/<adjudicator>.
    """
    paths = get_adjudication_paths(
        record_output_path=(
            waveform_record["output_path"]
        ),
        subject=waveform_record["subject"],
        file_tag=waveform_record["file_tag"],
        adjudicator=adjudicator,
        allowed_adjudicators=[adjudicator],
    )

    expected_directory = (
        Path(waveform_record["output_path"])
        / "ADJUDICATION"
        / adjudicator
    )

    assert paths.output_directory == expected_directory

    assert paths.draft_csv.parent == expected_directory
    assert paths.complete_csv.parent == expected_directory
    assert paths.state_json.parent == expected_directory

    assert paths.draft_csv.name.endswith(
        f"_{adjudicator}.csv"
    )

    assert paths.complete_csv.name.endswith(
        f"_{adjudicator}_COMPLETE.csv"
    )

    assert paths.state_json.name.endswith(
        f"_{adjudicator}_state.json"
    )


def test_adjudication_paths_do_not_overlap_source_files(
    waveform_record,
    write_annotation_file,
    annotators,
    adjudicator,
):
    """
    Generated adjudication files must not overlap source annotation files.
    """
    source_path = write_annotation_file(
        user=annotators[0],
        intervals=[
            {
                "start": 1_700_000_000.0,
                "end": 1_700_000_010.0,
            }
        ],
    )

    paths = get_adjudication_paths(
        record_output_path=(
            waveform_record["output_path"]
        ),
        subject=waveform_record["subject"],
        file_tag=waveform_record["file_tag"],
        adjudicator=adjudicator,
        source_paths=[source_path],
        allowed_adjudicators=[adjudicator],
    )

    assert paths.draft_csv != source_path
    assert paths.complete_csv != source_path
    assert paths.output_directory != source_path.parent


def test_unknown_adjudicator_is_rejected(
    waveform_record,
):
    """
    Only configured adjudicators may receive output paths.
    """
    with pytest.raises(AdjudicationPathError):
        get_adjudication_paths(
            record_output_path=(
                waveform_record["output_path"]
            ),
            subject=waveform_record["subject"],
            file_tag=waveform_record["file_tag"],
            adjudicator="not_configured",
            allowed_adjudicators=["reviewer_one"],
        )