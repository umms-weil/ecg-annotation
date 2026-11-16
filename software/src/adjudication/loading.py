"""
Read and normalize source annotation CSV files into adjudication data models.
"""

from __future__ import annotations

from time import perf_counter
from typing import Optional

import numpy as np
import pandas as pd

from .config import (
    ANNOTATOR_ALIASES,
    REQUIRED_ANNOTATION_COLUMNS,
    InputReadinessStatus,
)
from .exceptions import (
    AdjudicationError,
    DuplicateInputError,
    InvalidAnnotationError,
    MissingInputError,
)
from .models import (
    AnnotationInterval,
    SourceAnnotationFile,
)
from .utilities import (
    _perf_log,
    clean_string,
    coerce_bool,
    validate_epoch_seconds,
)

# =============================================================================
# Source CSV loading and normalization
# =============================================================================

def read_source_annotation_csv(
    source: SourceAnnotationFile,
) -> pd.DataFrame:
    """
    Read one source annotation CSV with timing and error diagnostics.

    Parameters
    ----------
    source : SourceAnnotationFile
        Metadata describing the source annotation file.

    Returns
    -------
    pandas.DataFrame
        Raw source annotation rows.

    Raises
    ------
    MissingInputError
        If the source file no longer exists.

    InvalidAnnotationError
        If the file cannot be read, contains no rows, or is missing required
        columns.

    Notes
    -----
    The source file is opened read-only. This function never writes to,
    renames, moves, or deletes the source annotation.
    """
    start_time = perf_counter()
    dataframe: Optional[pd.DataFrame] = None

    try:
        dataframe = _read_source_annotation_csv_impl(
            source=source,
        )

        return dataframe

    except Exception as exc:
        # Preserve the failure in source metadata for UI diagnostics.
        source.readiness_status = InputReadinessStatus.INVALID
        source.readiness_message = (
            f"{type(exc).__name__}: {exc}"
        )

        print(
            "[ADJUDICATION] read_source_annotation_csv failed:",
            f"alias={source.alias}",
            f"path={source.path}",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "read_source_annotation_csv",
            perf_counter() - start_time,
            alias=source.alias,
            rows=(
                len(dataframe)
                if dataframe is not None
                else 0
            ),
            path=source.path,
        )


def _read_source_annotation_csv_impl(
    source: SourceAnnotationFile,
) -> pd.DataFrame:
    """
    Read and perform basic schema checks on one source annotation CSV.

    Parameters
    ----------
    source : SourceAnnotationFile
        Source file metadata.

    Returns
    -------
    pandas.DataFrame
        Raw annotation data with original row numbers retained in
        ``_source_row``.

    Raises
    ------
    MissingInputError
        If the source path is not an existing file.

    InvalidAnnotationError
        If the CSV cannot be read, is empty, or lacks required columns.
    """
    source_path = (
        source.path
        .expanduser()
        .resolve(strict=False)
    )

    if not source_path.is_file():
        raise MissingInputError(
            f"Source annotation file does not exist: {source_path}"
        )

    try:
        # Read text-like values consistently. Start/end are converted
        # explicitly below so floating-point epoch precision is retained.
        dataframe = pd.read_csv(
            source_path,
            dtype="string",
            keep_default_na=True,
        )
    except Exception as exc:
        raise InvalidAnnotationError(
            f"Could not read source annotation CSV "
            f"{source_path}: {exc}"
        ) from exc

    if dataframe.empty:
        raise InvalidAnnotationError(
            f"Source annotation CSV contains no rows: {source_path}"
        )

    missing_columns = (
        REQUIRED_ANNOTATION_COLUMNS
        .difference(dataframe.columns)
    )

    if missing_columns:
        raise InvalidAnnotationError(
            f"Source annotation CSV is missing required columns: "
            f"{sorted(missing_columns)}. Path: {source_path}"
        )

    dataframe = dataframe.copy()

    # Preserve the original zero-based CSV data-row index for diagnostics.
    # The CSV header is not included in this number.
    dataframe["_source_row"] = np.arange(
        len(dataframe),
        dtype=int,
    )

    return dataframe


def normalize_source_annotation_dataframe(
    dataframe: pd.DataFrame,
    source: SourceAnnotationFile,
) -> pd.DataFrame:
    """
    Normalize source annotation values without changing boundary precision.

    Parameters
    ----------
    dataframe : pandas.DataFrame
        Raw source annotation rows.

    source : SourceAnnotationFile
        Metadata describing the source file and expected annotator identity.

    Returns
    -------
    pandas.DataFrame
        Normalized rows sorted by ``start`` and ``end``.

    Raises
    ------
    InvalidAnnotationError
        If timestamps are invalid, user identity is inconsistent, or required
        values cannot be normalized.

    Notes
    -----
    Structural interval validation, including gaps and overlaps, is performed
    in the next validation section. This function focuses on type and value
    normalization.
    """
    start_time = perf_counter()
    normalized: Optional[pd.DataFrame] = None

    try:
        normalized = (
            _normalize_source_annotation_dataframe_impl(
                dataframe=dataframe,
                source=source,
            )
        )

        return normalized

    except Exception as exc:
        source.readiness_status = InputReadinessStatus.INVALID
        source.readiness_message = (
            f"{type(exc).__name__}: {exc}"
        )

        print(
            "[ADJUDICATION] "
            "normalize_source_annotation_dataframe failed:",
            f"alias={source.alias}",
            f"path={source.path}",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "normalize_source_annotation_dataframe",
            perf_counter() - start_time,
            alias=source.alias,
            rows=(
                len(normalized)
                if normalized is not None
                else 0
            ),
        )


def _normalize_source_annotation_dataframe_impl(
    dataframe: pd.DataFrame,
    source: SourceAnnotationFile,
) -> pd.DataFrame:
    """
    Normalize one source DataFrame without timing or UI behavior.
    """
    normalized = dataframe.copy()

    # ------------------------------------------------------------------
    # Normalize text columns.
    # ------------------------------------------------------------------
    text_columns = [
        "user",
        "subject",
        "encounter",
        "namespace",
        "file_tag",
        "source_path",
        "cpr",
        "rhythm_label",
        "rhythm_expl",
        "terminal_event_status",
        "terminal_event_comment",
    ]

    for column in text_columns:
        normalized[column] = normalized[column].map(
            clean_string
        )

    # ------------------------------------------------------------------
    # Validate source-user identity.
    # ------------------------------------------------------------------
    source_users = [
        value
        for value in normalized["user"].unique()
        if value
    ]

    if not source_users:
        raise InvalidAnnotationError(
            f"Source file contains no annotator username: {source.path}"
        )

    if len(source_users) != 1:
        raise InvalidAnnotationError(
            "Source file must contain exactly one annotator username, "
            f"but found {source_users}. Path: {source.path}"
        )

    file_username = source_users[0]

    if file_username != source.username:
        raise InvalidAnnotationError(
            f"Source username mismatch. Configured user is "
            f"{source.username!r}, but the CSV contains "
            f"{file_username!r}. Path: {source.path}"
        )

    # ------------------------------------------------------------------
    # Convert boundaries to float64 epoch seconds.
    #
    # No rounding or conversion to integer milliseconds is performed.
    # ------------------------------------------------------------------
    normalized["start"] = pd.to_numeric(
        normalized["start"],
        errors="coerce",
    ).astype("float64")

    normalized["end"] = pd.to_numeric(
        normalized["end"],
        errors="coerce",
    ).astype("float64")

    invalid_start = ~np.isfinite(
        normalized["start"].to_numpy(
            dtype=float
        )
    )

    invalid_end = ~np.isfinite(
        normalized["end"].to_numpy(
            dtype=float
        )
    )

    invalid_time_mask = (
        invalid_start
        | invalid_end
    )

    if np.any(invalid_time_mask):
        invalid_rows = normalized.loc[
            invalid_time_mask,
            "_source_row",
        ].astype(int).tolist()

        raise InvalidAnnotationError(
            "Source annotation contains invalid start/end timestamps "
            f"at data rows {invalid_rows}. Path: {source.path}"
        )

    # ------------------------------------------------------------------
    # Normalize completion values.
    # ------------------------------------------------------------------
    normalized["waveform_complete"] = normalized[
        "waveform_complete"
    ].map(coerce_bool)

    # Stable sorting ensures deterministic behavior when timestamps are equal.
    normalized = normalized.sort_values(
        by=[
            "start",
            "end",
            "_source_row",
        ],
        kind="stable",
    ).reset_index(drop=True)

    return normalized


def dataframe_to_annotation_intervals(
    dataframe: pd.DataFrame,
    source: SourceAnnotationFile,
) -> list[AnnotationInterval]:
    """
    Convert normalized source rows into interval dataclasses.

    Parameters
    ----------
    dataframe : pandas.DataFrame
        Normalized annotation rows.

    source : SourceAnnotationFile
        Source metadata providing the stable Annotator A/B alias.

    Returns
    -------
    list[AnnotationInterval]
        Intervals ordered by start time.

    Raises
    ------
    InvalidAnnotationError
        If a row cannot be converted into an interval.
    """
    start_time = perf_counter()
    intervals: list[AnnotationInterval] = []

    try:
        intervals = _dataframe_to_annotation_intervals_impl(
            dataframe=dataframe,
            source=source,
        )

        return intervals

    except Exception as exc:
        source.readiness_status = InputReadinessStatus.INVALID
        source.readiness_message = (
            f"{type(exc).__name__}: {exc}"
        )

        print(
            "[ADJUDICATION] "
            "dataframe_to_annotation_intervals failed:",
            f"alias={source.alias}",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "dataframe_to_annotation_intervals",
            perf_counter() - start_time,
            alias=source.alias,
            intervals=len(intervals),
        )


def _dataframe_to_annotation_intervals_impl(
    dataframe: pd.DataFrame,
    source: SourceAnnotationFile,
) -> list[AnnotationInterval]:
    """
    Convert normalized rows without timing or UI behavior.
    """
    intervals: list[AnnotationInterval] = []

    for normalized_index, row in dataframe.iterrows():
        source_row = int(
            row.get(
                "_source_row",
                normalized_index,
            )
        )

        try:
            interval_start = validate_epoch_seconds(
                row["start"],
                f"start at source row {source_row}",
            )

            interval_end = validate_epoch_seconds(
                row["end"],
                f"end at source row {source_row}",
            )

            interval = AnnotationInterval(
                user=clean_string(row["user"]),
                subject=clean_string(row["subject"]),
                encounter=clean_string(
                    row["encounter"]
                ),
                namespace=clean_string(
                    row["namespace"]
                ),
                file_tag=clean_string(
                    row["file_tag"]
                ),
                source_path=clean_string(
                    row["source_path"]
                ),
                cpr=clean_string(row["cpr"]),
                rhythm_label=clean_string(
                    row["rhythm_label"]
                ),
                rhythm_expl=clean_string(
                    row["rhythm_expl"]
                ),
                start=interval_start,
                end=interval_end,
                waveform_complete=coerce_bool(
                    row["waveform_complete"]
                ),
                terminal_event_status=clean_string(
                    row["terminal_event_status"]
                ),
                terminal_event_comment=clean_string(
                    row["terminal_event_comment"]
                ),
                source_alias=source.alias,
                source_row=source_row,
            )

        except Exception as exc:
            raise InvalidAnnotationError(
                f"Could not normalize source row {source_row} "
                f"from {source.path}: {exc}"
            ) from exc

        intervals.append(interval)

    return intervals


def load_source_annotation_intervals(
    source: SourceAnnotationFile,
) -> list[AnnotationInterval]:
    """
    Load and normalize one source annotator timeline.

    Parameters
    ----------
    source : SourceAnnotationFile
        Ready source-file metadata.

    Returns
    -------
    list[AnnotationInterval]
        Normalized source intervals in chronological order.

    Raises
    ------
    InvalidAnnotationError
        If the source is not ready or cannot be normalized.

    Notes
    -----
    This function does not yet perform full gap/overlap validation. That is
    handled by the source interval-validation section.
    """
    start_time = perf_counter()
    intervals: list[AnnotationInterval] = []

    try:
        intervals = _load_source_annotation_intervals_impl(
            source=source,
        )

        return intervals

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "load_source_annotation_intervals failed:",
            f"alias={source.alias}",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "load_source_annotation_intervals",
            perf_counter() - start_time,
            alias=source.alias,
            intervals=len(intervals),
            path=source.path,
        )


def _load_source_annotation_intervals_impl(
    source: SourceAnnotationFile,
) -> list[AnnotationInterval]:
    """
    Load one source timeline without timing or UI behavior.
    """
    if (
        source.readiness_status
        != InputReadinessStatus.READY
    ):
        raise InvalidAnnotationError(
            f"{source.alias} is not ready for loading: "
            f"{source.readiness_status.value}. "
            f"{source.readiness_message}"
        )

    raw_dataframe = read_source_annotation_csv(
        source
    )

    normalized_dataframe = (
        normalize_source_annotation_dataframe(
            dataframe=raw_dataframe,
            source=source,
        )
    )

    intervals = dataframe_to_annotation_intervals(
        dataframe=normalized_dataframe,
        source=source,
    )

    if not intervals:
        raise InvalidAnnotationError(
            f"{source.alias} produced no usable intervals."
        )

    return intervals


def load_source_annotation_pair(
    source_a: SourceAnnotationFile,
    source_b: SourceAnnotationFile,
) -> tuple[
    list[AnnotationInterval],
    list[AnnotationInterval],
]:
    """
    Load and normalize the two required source timelines.

    Parameters
    ----------
    source_a : SourceAnnotationFile
        Source assigned to Annotator A.

    source_b : SourceAnnotationFile
        Source assigned to Annotator B.

    Returns
    -------
    tuple[list[AnnotationInterval], list[AnnotationInterval]]
        Chronological Annotator A and Annotator B interval lists.

    Raises
    ------
    AdjudicationError
        If source aliases are incorrect or both paths resolve to the same file.

    InvalidAnnotationError
        If either source timeline cannot be loaded.
    """
    start_time = perf_counter()

    intervals_a: list[AnnotationInterval] = []
    intervals_b: list[AnnotationInterval] = []

    try:
        (
            intervals_a,
            intervals_b,
        ) = _load_source_annotation_pair_impl(
            source_a=source_a,
            source_b=source_b,
        )

        return intervals_a, intervals_b

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "load_source_annotation_pair failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "load_source_annotation_pair",
            perf_counter() - start_time,
            intervals_a=len(intervals_a),
            intervals_b=len(intervals_b),
        )


def _load_source_annotation_pair_impl(
    source_a: SourceAnnotationFile,
    source_b: SourceAnnotationFile,
) -> tuple[
    list[AnnotationInterval],
    list[AnnotationInterval],
]:
    """
    Load both source timelines without timing or UI behavior.
    """
    if source_a.alias != ANNOTATOR_ALIASES[0]:
        raise AdjudicationError(
            f"Expected first source alias "
            f"{ANNOTATOR_ALIASES[0]!r}, but received "
            f"{source_a.alias!r}."
        )

    if source_b.alias != ANNOTATOR_ALIASES[1]:
        raise AdjudicationError(
            f"Expected second source alias "
            f"{ANNOTATOR_ALIASES[1]!r}, but received "
            f"{source_b.alias!r}."
        )

    normalized_path_a = (
        source_a.path
        .expanduser()
        .resolve(strict=False)
    )

    normalized_path_b = (
        source_b.path
        .expanduser()
        .resolve(strict=False)
    )

    if normalized_path_a == normalized_path_b:
        raise DuplicateInputError(
            "Annotator A and Annotator B resolve to the same source file: "
            f"{normalized_path_a}"
        )

    intervals_a = load_source_annotation_intervals(
        source_a
    )

    intervals_b = load_source_annotation_intervals(
        source_b
    )

    return intervals_a, intervals_b

