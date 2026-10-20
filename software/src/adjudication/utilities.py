"""
General validation, serialization, timestamp, identifier, and performance
utilities for adjudication.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import ADJUDICATION_PERF_DIAGNOSTICS_ENABLED
from .exceptions import InvalidAnnotationError

# =============================================================================
# Timed-wrapper convention
# =============================================================================

# Substantive discovery, comparison, validation, and persistence operations
# should use a timed public wrapper and a private implementation.
#
# Example:
#
# def discover_source_annotation_files(
#     record_output_path: str | Path,
#     annotators: Optional[list[str]] = None,
# ) -> list[SourceAnnotationFile]:
#     """
#     Discover source annotation inputs with timing and error diagnostics.
#     """
#     start_time = perf_counter()
#
#     try:
#         return _discover_source_annotation_files_impl(
#             record_output_path=record_output_path,
#             annotators=annotators,
#         )
#
#     except Exception as exc:
#         print(
#             "[ADJUDICATION] "
#             "discover_source_annotation_files failed:",
#             type(exc).__name__,
#             exc,
#         )
#         raise
#
#     finally:
#         _perf_log(
#             "discover_source_annotation_files",
#             perf_counter() - start_time,
#         )
#
#
# def _discover_source_annotation_files_impl(
#     record_output_path: str | Path,
#     annotators: Optional[list[str]] = None,
# ) -> list[SourceAnnotationFile]:
#     """
#     Perform source discovery without timing or UI behavior.
#     """
#     raise NotImplementedError



# =============================================================================
# General utilities
# =============================================================================

def _perf_log(
    operation: str,
    elapsed_seconds: float,
    **details: Any,
) -> None:
    """
    Print one standardized adjudication performance diagnostic.
    Provides sources of slowdowns and errors for development.

    Parameters
    ----------
    operation : str
        Name of the timed operation.

    elapsed_seconds : float
        Total elapsed wall-clock time in seconds.

    **details : Any
        Additional key/value details appended to the diagnostic line.

    Notes
    -----
    Output uses the prefix ``[PERF][ADJ]`` so adjudication measurements can be
    filtered independently from existing annotation performance logs.
    """
    if not ADJUDICATION_PERF_DIAGNOSTICS_ENABLED:
        return

    detail_text = " ".join(
        f"{key}={value}"
        for key, value in details.items()
    )

    if detail_text:
        detail_text = f" | {detail_text}"

    print(
        f"[PERF][ADJ] {operation}: "
        f"{elapsed_seconds:.4f} sec"
        f"{detail_text}"
    )


def utc_now_iso() -> str:
    """
    Return the current UTC time as an ISO-8601 string.

    Returns
    -------
    str
        UTC timestamp with microsecond precision and a trailing ``Z``.
    """
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def clean_string(value: Any) -> str:
    """
    Convert a scalar value to a stripped string.

    Parameters
    ----------
    value : Any
        Input scalar, potentially including a Pandas missing value.

    Returns
    -------
    str
        Empty string for missing values; otherwise a stripped string.

    Notes
    -----
    This helper is intended for scalar CSV values, not arrays or Series.
    """
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        # Non-scalar objects are not expected, but converting them to a string
        # is safer than failing during diagnostic processing.
        pass

    return str(value).strip()


def coerce_bool(value: Any) -> bool:
    """
    Convert a common CSV boolean representation into ``bool``.

    Parameters
    ----------
    value : Any
        Boolean-like scalar value.

    Returns
    -------
    bool
        True for values such as ``True``, ``1``, ``yes``, or ``y``.
    """
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass

    normalized = str(value).strip().lower()

    return normalized in {
        "true",
        "1",
        "yes",
        "y",
    }


def validate_epoch_seconds(
    value: Any,
    field_name: str,
) -> float:
    """
    Validate and return a floating-point UTC epoch timestamp.

    Parameters
    ----------
    value : Any
        Candidate numeric timestamp.

    field_name : str
        Field name included in validation errors.

    Returns
    -------
    float
        Finite floating-point epoch seconds without deliberate rounding.

    Raises
    ------
    InvalidAnnotationError
        If the value is non-numeric or non-finite.
    """
    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidAnnotationError(
            f"{field_name} is not numeric: {value!r}"
        ) from exc

    if not np.isfinite(numeric_value):
        raise InvalidAnnotationError(
            f"{field_name} is not finite: {value!r}"
        )

    return numeric_value


def stable_numbered_id(
    prefix: str,
    index: int,
) -> str:
    """
    Build a stable zero-padded identifier.

    Parameters
    ----------
    prefix : str
        Identifier prefix, such as ``disagreement`` or ``region``.

    index : int
        One-based or zero-based sequence value selected by the caller.

    Returns
    -------
    str
        Identifier such as ``disagreement_0001``.
    """
    return f"{prefix}_{int(index):04d}"


def json_safe_value(value: Any) -> Any:
    """
    Recursively convert common values into JSON-safe values.

    Parameters
    ----------
    value : Any
        Value to normalize.

    Returns
    -------
    Any
        A value accepted by ``json.dump``.

    Supported conversions
    ---------------------
    - Enum to its string value.
    - Path to string.
    - NumPy scalar to Python scalar.
    - Pandas Timestamp to ISO-8601 UTC.
    - Dataclass to dictionary.
    - Dictionary values recursively.
    - List, tuple, and set values recursively.
    - Pandas/NumPy missing values to ``None``.
    """
    if isinstance(value, Enum):
        return value.value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, np.generic):
        return value.item()

    if isinstance(value, pd.Timestamp):
        timestamp = value

        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")

        return (
            timestamp.tz_convert("UTC")
            .isoformat()
            .replace("+00:00", "Z")
        )

    if is_dataclass(value):
        return {
            str(key): json_safe_value(item)
            for key, item in asdict(value).items()
        }

    if isinstance(value, dict):
        return {
            str(key): json_safe_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            json_safe_value(item)
            for item in value
        ]

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    return value
