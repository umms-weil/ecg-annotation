"""
Discovery and readiness classification of source annotator CSV files.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

from .config import (
    ANNOTATION_FILENAME_PREFIX,
    ANNOTATION_USERS,
    ANNOTATOR_ALIASES,
    COMPLETE_FILENAME_SUFFIX,
    REQUIRED_ANNOTATOR_COUNT,
    InputReadinessStatus,
)
from .exceptions import (
    AdjudicationError,
    AdjudicationPathError,
    DuplicateInputError,
    InvalidAnnotationError,
    MissingInputError,
)
from .models import SourceAnnotationFile
from .paths import validate_filename_component
from .utilities import (
    _perf_log,
    clean_string,
)

# =============================================================================
# Source annotation discovery
# =============================================================================

def get_file_modified_at_iso(
    path: str | Path,
) -> str:
    """
    Return a file's modification time as an ISO-8601 UTC timestamp.

    Parameters
    ----------
    path : str or pathlib.Path
        Existing file path.

    Returns
    -------
    str
        Modification timestamp with microsecond precision and a trailing
        ``Z``.

    Raises
    ------
    OSError
        If file metadata cannot be read.
    """
    file_path = Path(path).expanduser()

    modified_epoch = file_path.stat().st_mtime

    return (
        datetime.fromtimestamp(
            modified_epoch,
            tz=timezone.utc,
        )
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def build_source_annotation_filenames(
    subject: Any,
    file_tag: Any,
    username: Any,
) -> tuple[str, str]:
    """
    Build the expected partial and complete source annotation filenames.

    Parameters
    ----------
    subject : Any
        Subject identifier used in the annotation filename.

    file_tag : Any
        Waveform-record identifier.

    username : Any
        Configured source annotator username.

    Returns
    -------
    tuple[str, str]
        ``(partial_filename, complete_filename)``.

    Examples
    --------
    Partial file:

    ``annotations_001234567_waveform_tag_user.csv``

    Completed file:

    ``annotations_001234567_waveform_tag_user_COMPLETE.csv``
    """
    subject_name = validate_filename_component(
        subject,
        "subject",
    )
    waveform_file_tag = validate_filename_component(
        file_tag,
        "file_tag",
    )
    annotator_name = validate_filename_component(
        username,
        "annotator username",
    )

    filename_base = (
        f"{ANNOTATION_FILENAME_PREFIX}_"
        f"{subject_name}_"
        f"{waveform_file_tag}_"
        f"{annotator_name}"
    )

    partial_filename = f"{filename_base}.csv"

    complete_filename = (
        f"{filename_base}"
        f"{COMPLETE_FILENAME_SUFFIX}.csv"
    )

    return (
        partial_filename,
        complete_filename,
    )


def normalize_source_annotators(
    annotators: Optional[list[str]] = None,
) -> list[str]:
    """
    Validate and normalize the configured source annotator list.

    Parameters
    ----------
    annotators : list[str] or None
        Optional source-user override. When omitted, ``ANNOTATION_USERS`` is
        used.

    Returns
    -------
    list[str]
        Ordered source usernames. Their order determines the stable assignment
        to Annotator A and Annotator B.

    Raises
    ------
    MissingInputError
        If the number of configured annotators does not equal
        ``REQUIRED_ANNOTATOR_COUNT``.

    DuplicateInputError
        If the same annotator appears more than once.

    AdjudicationPathError
        If an annotator name is blank or unsafe for use as a folder component.
    """
    configured_users = (
        ANNOTATION_USERS
        if annotators is None
        else annotators
    )

    normalized_users = [
        validate_filename_component(
            username,
            "annotator username",
        )
        for username in configured_users
    ]

    if len(normalized_users) != REQUIRED_ANNOTATOR_COUNT:
        raise MissingInputError(
            "Adjudication currently requires exactly "
            f"{REQUIRED_ANNOTATOR_COUNT} configured annotators, "
            f"but {len(normalized_users)} were provided."
        )

    if len(set(normalized_users)) != len(normalized_users):
        raise DuplicateInputError(
            "Configured source annotators must be unique: "
            f"{normalized_users}"
        )

    if len(ANNOTATOR_ALIASES) < len(normalized_users):
        raise AdjudicationError(
            "Not enough reviewer-facing annotator aliases are configured."
        )

    return normalized_users


def find_complete_annotation_candidates(
    user_directory: str | Path,
    subject: Any,
    file_tag: Any,
    username: Any,
) -> list[Path]:
    """
    Find completed source annotation files for one configured annotator.

    Parameters
    ----------
    user_directory : str or pathlib.Path
        User-specific folder under the waveform record's output directory.

    subject : Any
        Subject identifier expected in the filename.

    file_tag : Any
        Waveform-record identifier expected in the filename.

    username : Any
        Configured source annotator username.

    Returns
    -------
    list[pathlib.Path]
        Sorted completed annotation candidates.

    Notes
    -----
    The exact contract filename is preferred. A constrained fallback search is
    used to support an existing completed annotation whose filename differs
    slightly while still residing in the correct user and waveform folder.
    """
    user_path = Path(
        user_directory
    ).expanduser().resolve(strict=False)

    if not user_path.is_dir():
        return []

    _, expected_complete_filename = (
        build_source_annotation_filenames(
            subject=subject,
            file_tag=file_tag,
            username=username,
        )
    )

    expected_complete_path = (
        user_path
        / expected_complete_filename
    )

    # The exact contract path is authoritative when present.
    if expected_complete_path.is_file():
        return [expected_complete_path]

    subject_name = validate_filename_component(
        subject,
        "subject",
    )
    waveform_file_tag = validate_filename_component(
        file_tag,
        "file_tag",
    )
    annotator_name = validate_filename_component(
        username,
        "annotator username",
    )

    candidates: list[Path] = []

    # Search only the configured user's immediate folder. Do not recurse into
    # unrelated directories or the ADJUDICATION output tree.
    for candidate in user_path.glob(
        f"{ANNOTATION_FILENAME_PREFIX}_*"
        f"{COMPLETE_FILENAME_SUFFIX}.csv"
    ):
        if not candidate.is_file():
            continue

        filename = candidate.name

        # Require the selected record and configured username to appear in the
        # fallback filename to avoid selecting an unrelated annotation file.
        if waveform_file_tag not in filename:
            continue

        if subject_name not in filename:
            continue

        expected_user_suffix = (
            f"_{annotator_name}"
            f"{COMPLETE_FILENAME_SUFFIX}.csv"
        )

        if not filename.endswith(expected_user_suffix):
            continue

        candidates.append(
            candidate.resolve(strict=False)
        )

    return sorted(
        candidates,
        key=lambda path: path.name,
    )


def find_partial_annotation_candidates(
    user_directory: str | Path,
    subject: Any,
    file_tag: Any,
    username: Any,
) -> list[Path]:
    """
    Find partial source annotation files for one configured annotator.

    Parameters
    ----------
    user_directory : str or pathlib.Path
        User-specific annotation folder.

    subject : Any
        Subject identifier expected in the filename.

    file_tag : Any
        Waveform-record identifier expected in the filename.

    username : Any
        Configured source annotator username.

    Returns
    -------
    list[pathlib.Path]
        Sorted partial annotation candidates.

    Notes
    -----
    Partial files are discovered only to report an incomplete input. They are
    not treated as normal adjudication inputs.
    """
    user_path = Path(
        user_directory
    ).expanduser().resolve(strict=False)

    if not user_path.is_dir():
        return []

    expected_partial_filename, _ = (
        build_source_annotation_filenames(
            subject=subject,
            file_tag=file_tag,
            username=username,
        )
    )

    expected_partial_path = (
        user_path
        / expected_partial_filename
    )

    if expected_partial_path.is_file():
        return [expected_partial_path]

    subject_name = validate_filename_component(
        subject,
        "subject",
    )
    waveform_file_tag = validate_filename_component(
        file_tag,
        "file_tag",
    )
    annotator_name = validate_filename_component(
        username,
        "annotator username",
    )

    candidates: list[Path] = []

    for candidate in user_path.glob(
        f"{ANNOTATION_FILENAME_PREFIX}_*.csv"
    ):
        if not candidate.is_file():
            continue

        filename = candidate.name

        # Completed files are not partial candidates.
        if filename.endswith(
            f"{COMPLETE_FILENAME_SUFFIX}.csv"
        ):
            continue

        if waveform_file_tag not in filename:
            continue

        if subject_name not in filename:
            continue

        if not filename.endswith(
            f"_{annotator_name}.csv"
        ):
            continue

        candidates.append(
            candidate.resolve(strict=False)
        )

    return sorted(
        candidates,
        key=lambda path: path.name,
    )


def make_source_annotation_file(
    username: str,
    alias: str,
    path: Path,
    *,
    complete: bool,
    readiness_status: InputReadinessStatus,
    readiness_message: str,
) -> SourceAnnotationFile:
    """
    Create source-file metadata for discovery results.

    Parameters
    ----------
    username : str
        Original source annotator username.

    alias : str
        Stable reviewer-facing alias.

    path : pathlib.Path
        Discovered or expected annotation path.

    complete : bool
        Whether the selected path is a completed annotation file.

    readiness_status : InputReadinessStatus
        Discovery readiness classification.

    readiness_message : str
        Human-readable status explanation.

    Returns
    -------
    SourceAnnotationFile
        Structured source-file metadata.

    Notes
    -----
    Missing expected paths receive zero size and an empty modification
    timestamp because no filesystem metadata exists.
    """
    normalized_path = (
        Path(path)
        .expanduser()
        .resolve(strict=False)
    )

    if normalized_path.is_file():
        size_bytes = int(
            normalized_path.stat().st_size
        )
        modified_at = get_file_modified_at_iso(
            normalized_path
        )
    else:
        size_bytes = 0
        modified_at = ""

    return SourceAnnotationFile(
        username=username,
        alias=alias,
        path=normalized_path,
        size_bytes=size_bytes,
        modified_at=modified_at,
        complete=complete,
        readiness_status=readiness_status,
        readiness_message=readiness_message,
    )


def discover_source_annotation_files(
    record_output_path: str | Path,
    subject: Any,
    file_tag: Any,
    *,
    annotators: Optional[list[str]] = None,
) -> list[SourceAnnotationFile]:
    """
    Discover adjudication source files with timing and error diagnostics.

    Parameters
    ----------
    record_output_path : str or pathlib.Path
        Waveform-record output directory containing the configured user
        folders.

    subject : Any
        Subject identifier expected in annotation filenames.

    file_tag : Any
        Waveform record identifier expected in annotation filenames.

    annotators : list[str] or None
        Optional ordered source-user override. The order determines assignment
        to Annotator A and Annotator B.

    Returns
    -------
    list[SourceAnnotationFile]
        One discovery result per configured annotator, including missing,
        incomplete, duplicate, and ready states.

    Raises
    ------
    AdjudicationPathError
        If the record output path or participant configuration is invalid.
    """
    start_time = perf_counter()

    result: list[SourceAnnotationFile] = []

    try:
        result = _discover_source_annotation_files_impl(
            record_output_path=record_output_path,
            subject=subject,
            file_tag=file_tag,
            annotators=annotators,
        )

        return result

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "discover_source_annotation_files failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        status_summary = {
            status.value: sum(
                source.readiness_status == status
                for source in result
            )
            for status in InputReadinessStatus
        }

        _perf_log(
            "discover_source_annotation_files",
            perf_counter() - start_time,
            sources=len(result),
            statuses=status_summary,
            file_tag=clean_string(file_tag),
        )


def _discover_source_annotation_files_impl(
    record_output_path: str | Path,
    subject: Any,
    file_tag: Any,
    *,
    annotators: Optional[list[str]] = None,
) -> list[SourceAnnotationFile]:
    """
    Discover completed source files without UI behavior.

    This private implementation returns a result for every configured
    annotator, even when a source file is missing or incomplete.
    """
    if not clean_string(record_output_path):
        raise AdjudicationPathError(
            "record_output_path cannot be blank."
        )

    record_output = Path(
        record_output_path
    ).expanduser().resolve(strict=False)

    if not record_output.is_dir():
        raise AdjudicationPathError(
            "Waveform record output directory does not exist: "
            f"{record_output}"
        )

    source_users = normalize_source_annotators(
        annotators
    )

    discovered_sources: list[
        SourceAnnotationFile
    ] = []

    for index, username in enumerate(source_users):
        alias = ANNOTATOR_ALIASES[index]

        user_directory = (
            record_output
            / username
        )

        expected_partial_name, expected_complete_name = (
            build_source_annotation_filenames(
                subject=subject,
                file_tag=file_tag,
                username=username,
            )
        )

        expected_complete_path = (
            user_directory
            / expected_complete_name
        )

        expected_partial_path = (
            user_directory
            / expected_partial_name
        )

        # A missing user directory is classified separately from an invalid
        # source file.
        if not user_directory.is_dir():
            discovered_sources.append(
                make_source_annotation_file(
                    username=username,
                    alias=alias,
                    path=expected_complete_path,
                    complete=False,
                    readiness_status=(
                        InputReadinessStatus.MISSING
                    ),
                    readiness_message=(
                        "Configured annotator folder does not exist."
                    ),
                )
            )
            continue

        complete_candidates = (
            find_complete_annotation_candidates(
                user_directory=user_directory,
                subject=subject,
                file_tag=file_tag,
                username=username,
            )
        )

        if len(complete_candidates) > 1:
            discovered_sources.append(
                make_source_annotation_file(
                    username=username,
                    alias=alias,
                    path=complete_candidates[0],
                    complete=True,
                    readiness_status=(
                        InputReadinessStatus.DUPLICATE
                    ),
                    readiness_message=(
                        "Multiple completed annotation files were found: "
                        + ", ".join(
                            candidate.name
                            for candidate in complete_candidates
                        )
                    ),
                )
            )
            continue

        if len(complete_candidates) == 1:
            discovered_sources.append(
                make_source_annotation_file(
                    username=username,
                    alias=alias,
                    path=complete_candidates[0],
                    complete=True,
                    readiness_status=(
                        InputReadinessStatus.READY
                    ),
                    readiness_message=(
                        "Completed annotation input is ready."
                    ),
                )
            )
            continue

        partial_candidates = (
            find_partial_annotation_candidates(
                user_directory=user_directory,
                subject=subject,
                file_tag=file_tag,
                username=username,
            )
        )

        if partial_candidates:
            discovered_sources.append(
                make_source_annotation_file(
                    username=username,
                    alias=alias,
                    path=partial_candidates[0],
                    complete=False,
                    readiness_status=(
                        InputReadinessStatus.INCOMPLETE
                    ),
                    readiness_message=(
                        "A partial annotation exists, but no completed "
                        "annotation file was found."
                    ),
                )
            )
            continue

        # The folder exists, but neither a complete nor partial annotation
        # file exists for this waveform record.
        discovered_sources.append(
            make_source_annotation_file(
                username=username,
                alias=alias,
                path=expected_complete_path,
                complete=False,
                readiness_status=(
                    InputReadinessStatus.MISSING
                ),
                readiness_message=(
                    "No annotation file was found for this waveform."
                ),
            )
        )

    return discovered_sources


def require_ready_source_annotation_files(
    sources: list[SourceAnnotationFile],
) -> tuple[SourceAnnotationFile, SourceAnnotationFile]:
    """
    Require exactly two ready source annotation inputs.

    Parameters
    ----------
    sources : list[SourceAnnotationFile]
        Results returned by ``discover_source_annotation_files``.

    Returns
    -------
    tuple[SourceAnnotationFile, SourceAnnotationFile]
        Ready source files assigned to Annotator A and Annotator B.

    Raises
    ------
    MissingInputError
        If a source is missing or incomplete.

    DuplicateInputError
        If a source has duplicate completed files.

    InvalidAnnotationError
        If a source is marked invalid.

    AdjudicationError
        If the source list has an unexpected size or state.
    """
    start_time = perf_counter()

    try:
        return _require_ready_source_annotation_files_impl(
            sources=sources,
        )

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "require_ready_source_annotation_files failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "require_ready_source_annotation_files",
            perf_counter() - start_time,
            sources=len(sources),
        )


def _require_ready_source_annotation_files_impl(
    sources: list[SourceAnnotationFile],
) -> tuple[SourceAnnotationFile, SourceAnnotationFile]:
    """
    Validate source readiness without UI behavior.
    """
    if len(sources) != REQUIRED_ANNOTATOR_COUNT:
        raise AdjudicationError(
            "Expected exactly "
            f"{REQUIRED_ANNOTATOR_COUNT} source results, "
            f"but received {len(sources)}."
        )

    for source in sources:
        status = source.readiness_status

        if status == InputReadinessStatus.MISSING:
            raise MissingInputError(
                f"{source.alias} ({source.username}) is missing: "
                f"{source.readiness_message} "
                f"Expected path: {source.path}"
            )

        if status == InputReadinessStatus.INCOMPLETE:
            raise MissingInputError(
                f"{source.alias} ({source.username}) is incomplete: "
                f"{source.readiness_message} "
                f"Path: {source.path}"
            )

        if status == InputReadinessStatus.DUPLICATE:
            raise DuplicateInputError(
                f"{source.alias} ({source.username}) has duplicate "
                f"inputs: {source.readiness_message}"
            )

        if status == InputReadinessStatus.INVALID:
            raise InvalidAnnotationError(
                f"{source.alias} ({source.username}) is invalid: "
                f"{source.readiness_message}"
            )

        if status != InputReadinessStatus.READY:
            raise AdjudicationError(
                f"{source.alias} has unsupported readiness status: "
                f"{status.value}"
            )

        if not source.path.is_file():
            raise MissingInputError(
                f"Ready source file no longer exists: {source.path}"
            )

        if not source.complete:
            raise MissingInputError(
                f"Ready source is not marked complete: {source.path}"
            )

    # Preserve the configured ordering and stable A/B alias assignment.
    source_a = sources[0]
    source_b = sources[1]

    if source_a.alias != ANNOTATOR_ALIASES[0]:
        raise AdjudicationError(
            "The first source is not assigned to Annotator A."
        )

    if source_b.alias != ANNOTATOR_ALIASES[1]:
        raise AdjudicationError(
            "The second source is not assigned to Annotator B."
        )

    return source_a, source_b

