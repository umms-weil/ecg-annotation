"""
Shared pytest fixtures for adjudication tests.

All test data are synthetic, temporary, and non-PHI.
"""

from __future__ import annotations

import sys

from pathlib import Path
from typing import Any, Callable

import pandas as pd
import pytest


# Make software/src importable when tests run from the repository root.
SOFTWARE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = SOFTWARE_ROOT / "src"

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


DEFAULT_SUBJECT = "MRN_TEST_001"
DEFAULT_ENCOUNTER = "CSN_TEST_001"
DEFAULT_NAMESPACE = "GEWAVE"
DEFAULT_FILE_TAG = "test_waveform_001"
DEFAULT_SOURCE_PATH = "/synthetic/test_waveform_001.h5"

DEFAULT_ANNOTATORS = [
    "annotator_one",
    "annotator_two",
]

DEFAULT_ADJUDICATOR = "reviewer_one"


def make_annotation_rows(
    *,
    user: str,
    intervals: list[dict[str, Any]],
    subject: str = DEFAULT_SUBJECT,
    encounter: str = DEFAULT_ENCOUNTER,
    namespace: str = DEFAULT_NAMESPACE,
    file_tag: str = DEFAULT_FILE_TAG,
    source_path: str = DEFAULT_SOURCE_PATH,
    complete: bool = True,
) -> list[dict[str, Any]]:
    """
    Build synthetic annotation rows using the production annotation schema.

    Parameters
    ----------
    user : str
        Synthetic annotator username.

    intervals : list[dict[str, Any]]
        Interval definitions. Each item must include ``start`` and ``end``.
        Optional values include ``cpr``, ``rhythm_label``, and
        ``rhythm_expl``.

    complete : bool
        Whether the final row should contain completion metadata.

    Returns
    -------
    list[dict[str, Any]]
        Annotation rows ready to write to CSV.
    """
    rows: list[dict[str, Any]] = []

    for index, interval in enumerate(intervals):
        is_final_row = (
            complete
            and index == len(intervals) - 1
        )

        rows.append(
            {
                "user": user,
                "subject": subject,
                "encounter": encounter,
                "namespace": namespace,
                "file_tag": file_tag,
                "source_path": source_path,
                "cpr": interval.get("cpr", "No"),
                "rhythm_label": interval.get(
                    "rhythm_label",
                    "Normal Heart Rhythm",
                ),
                "rhythm_expl": interval.get(
                    "rhythm_expl",
                    "",
                ),
                "start": float(interval["start"]),
                "end": float(interval["end"]),
                "waveform_complete": is_final_row,
                "terminal_event_status": (
                    "does_not_continue_beyond_waveform"
                    if is_final_row
                    else ""
                ),
                "terminal_event_comment": (
                    interval.get(
                        "terminal_event_comment",
                        "",
                    )
                    if is_final_row
                    else ""
                ),
            }
        )

    return rows


@pytest.fixture
def annotators() -> list[str]:
    """
    Return the two configured synthetic annotators.
    """
    return list(DEFAULT_ANNOTATORS)


@pytest.fixture
def adjudicator() -> str:
    """
    Return the configured synthetic adjudicator.
    """
    return DEFAULT_ADJUDICATOR


@pytest.fixture
def waveform_record(
    tmp_path: Path,
) -> dict[str, Any]:
    """
    Create a synthetic waveform record and its output folder.
    """
    output_path = (
        tmp_path
        / DEFAULT_SUBJECT
        / DEFAULT_ENCOUNTER
        / "output"
        / DEFAULT_FILE_TAG
    )

    output_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    return {
        "name": (
            f"{DEFAULT_SUBJECT} | "
            f"{DEFAULT_ENCOUNTER} | "
            f"{DEFAULT_FILE_TAG}"
        ),
        "subject": DEFAULT_SUBJECT,
        "encounter": DEFAULT_ENCOUNTER,
        "namespace": DEFAULT_NAMESPACE,
        "file_tag": DEFAULT_FILE_TAG,
        "output_path": str(output_path),
        "kind": "h5_multi",
    }


@pytest.fixture
def write_annotation_file(
    waveform_record: dict[str, Any],
) -> Callable[..., Path]:
    """
    Return a helper that writes one synthetic annotation CSV.
    """

    def _write_annotation_file(
        *,
        user: str,
        intervals: list[dict[str, Any]],
        complete: bool = True,
        subject: str = DEFAULT_SUBJECT,
        encounter: str = DEFAULT_ENCOUNTER,
        namespace: str = DEFAULT_NAMESPACE,
        file_tag: str = DEFAULT_FILE_TAG,
        source_path: str = DEFAULT_SOURCE_PATH,
        filename: str | None = None,
    ) -> Path:
        output_path = Path(
            waveform_record["output_path"]
        )

        user_directory = output_path / user
        user_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        if filename is None:
            suffix = (
                "_COMPLETE.csv"
                if complete
                else ".csv"
            )

            filename = (
                f"annotations_{subject}_"
                f"{file_tag}_{user}{suffix}"
            )

        csv_path = user_directory / filename

        rows = make_annotation_rows(
            user=user,
            intervals=intervals,
            subject=subject,
            encounter=encounter,
            namespace=namespace,
            file_tag=file_tag,
            source_path=source_path,
            complete=complete,
        )

        pd.DataFrame(rows).to_csv(
            csv_path,
            index=False,
        )

        return csv_path

    return _write_annotation_file