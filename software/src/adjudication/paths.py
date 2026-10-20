"""
Adjudication output-folder and filename construction with source-file
protection.
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, Optional

from .config import (
    ADJUDICATION_FILENAME_PREFIX,
    ADJUDICATION_FOLDER_NAME,
    ADJUDICATION_STATE_FILENAME_SUFFIX,
    ADJUDICATORS,
    COMPLETE_FILENAME_SUFFIX,
)
from .exceptions import AdjudicationPathError
from .models import AdjudicationPaths
from .utilities import (
    _perf_log,
    clean_string,
)

# =============================================================================
# Adjudication paths and filenames
# =============================================================================

def validate_filename_component(
    value: Any,
    field_name: str,
) -> str:
    """
    Validate a value used as one component of an adjudication filename.

    Parameters
    ----------
    value : Any
        Subject identifier, waveform file tag, or adjudicator username.

    field_name : str
        Human-readable field name included in validation errors.

    Returns
    -------
    str
        Stripped filename component.

    Raises
    ------
    AdjudicationPathError
        If the value is blank, contains a path separator, contains a null
        character, or represents a relative directory component.

    Notes
    -----
    Values are validated rather than silently rewritten. This preserves the
    subject and waveform identifiers used by existing annotation files.
    """
    component = clean_string(value)

    if not component:
        raise AdjudicationPathError(
            f"{field_name} cannot be blank."
        )

    if "\x00" in component:
        raise AdjudicationPathError(
            f"{field_name} contains a null character."
        )

    if component in {".", ".."}:
        raise AdjudicationPathError(
            f"{field_name} cannot be {component!r}."
        )

    # Reject both POSIX and Windows separators so generated names remain safe
    # on every supported operating system.
    if "/" in component or "\\" in component:
        raise AdjudicationPathError(
            f"{field_name} contains a path separator: "
            f"{component!r}"
        )

    return component


def validate_adjudicator(
    adjudicator: Any,
    allowed_adjudicators: Optional[list[str]] = None,
) -> str:
    """
    Validate an adjudicator against the configured allowlist.

    Parameters
    ----------
    adjudicator : Any
        Candidate adjudicator username.

    allowed_adjudicators : list[str] or None
        Optional allowlist override. When omitted, ``ADJUDICATORS`` is used.

    Returns
    -------
    str
        Validated adjudicator username.

    Raises
    ------
    AdjudicationPathError
        If the adjudicator is blank or is not configured.
    """
    adjudicator_name = validate_filename_component(
        adjudicator,
        "adjudicator",
    )

    configured_adjudicators = (
        ADJUDICATORS
        if allowed_adjudicators is None
        else allowed_adjudicators
    )

    normalized_allowlist = {
        clean_string(username)
        for username in configured_adjudicators
        if clean_string(username)
    }

    if adjudicator_name not in normalized_allowlist:
        raise AdjudicationPathError(
            f"Adjudicator {adjudicator_name!r} is not configured. "
            f"Allowed adjudicators: "
            f"{sorted(normalized_allowlist)}"
        )

    return adjudicator_name


def build_adjudication_filename_base(
    subject: Any,
    file_tag: Any,
    adjudicator: Any,
    *,
    allowed_adjudicators: Optional[list[str]] = None,
) -> str:
    """
    Build the common filename stem for one adjudication.

    Parameters
    ----------
    subject : Any
        Subject identifier used by the source annotation files.

    file_tag : Any
        Waveform record identifier.

    adjudicator : Any
        Reviewer username.

    allowed_adjudicators : list[str] or None
        Optional adjudicator allowlist override.

    Returns
    -------
    str
        Filename stem without extension or completion suffix.

    Examples
    --------
    ``adjudication_001234567_waveform_tag_pwalczyk``
    """
    subject_name = validate_filename_component(
        subject,
        "subject",
    )
    waveform_file_tag = validate_filename_component(
        file_tag,
        "file_tag",
    )
    adjudicator_name = validate_adjudicator(
        adjudicator,
        allowed_adjudicators=allowed_adjudicators,
    )

    return (
        f"{ADJUDICATION_FILENAME_PREFIX}_"
        f"{subject_name}_"
        f"{waveform_file_tag}_"
        f"{adjudicator_name}"
    )


def _path_is_relative_to(
    candidate: Path,
    parent: Path,
) -> bool:
    """
    Return whether one normalized path is inside another path.

    Parameters
    ----------
    candidate : pathlib.Path
        Potential child path.

    parent : pathlib.Path
        Potential parent directory.

    Returns
    -------
    bool
        True when ``candidate`` is equal to or contained by ``parent``.

    Notes
    -----
    This helper avoids requiring callers to handle ``ValueError`` from
    ``Path.relative_to``.
    """
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_adjudication_paths(
    paths: AdjudicationPaths,
    record_output_path: str | Path,
    source_paths: Optional[list[str | Path]] = None,
) -> None:
    """
    Validate that adjudication output is isolated from source annotations.

    Parameters
    ----------
    paths : AdjudicationPaths
        Generated adjudication paths.

    record_output_path : str or pathlib.Path
        Waveform-record output directory containing annotator folders.

    source_paths : list[str or Path] or None
        Optional source annotation CSV paths to protect explicitly.

    Raises
    ------
    AdjudicationPathError
        If generated output is outside the expected record output directory,
        is not inside the ``ADJUDICATION`` folder, overlaps a source file, or
        uses a source annotator folder as its output location.
    """
    normalized_record_output = Path(
        record_output_path
    ).expanduser().resolve(strict=False)

    normalized_output_directory = (
        paths.output_directory
        .expanduser()
        .resolve(strict=False)
    )

    expected_adjudication_root = (
        normalized_record_output
        / ADJUDICATION_FOLDER_NAME
    ).resolve(strict=False)

    # Every adjudication output must remain below the waveform record's
    # dedicated ADJUDICATION directory.
    if not _path_is_relative_to(
        normalized_output_directory,
        expected_adjudication_root,
    ):
        raise AdjudicationPathError(
            "Adjudication output directory is outside the expected "
            f"ADJUDICATION folder: {normalized_output_directory}"
        )

    generated_files = {
        paths.draft_csv.expanduser().resolve(strict=False),
        paths.complete_csv.expanduser().resolve(strict=False),
        paths.state_json.expanduser().resolve(strict=False),
    }

    for generated_file in generated_files:
        if generated_file.parent != normalized_output_directory:
            raise AdjudicationPathError(
                "Generated adjudication file is not directly inside the "
                f"adjudicator output directory: {generated_file}"
            )

    if not source_paths:
        return

    for source_path_value in source_paths:
        source_path = Path(
            source_path_value
        ).expanduser().resolve(strict=False)

        # Generated adjudication files must never be the same files as source
        # annotations.
        if source_path in generated_files:
            raise AdjudicationPathError(
                "Adjudication output overlaps a source annotation file: "
                f"{source_path}"
            )

        # The adjudicator output directory must not be an annotator's source
        # folder.
        if normalized_output_directory == source_path.parent:
            raise AdjudicationPathError(
                "Adjudication output directory overlaps a source "
                f"annotator folder: {source_path.parent}"
            )

        # Source annotation files should never be located beneath the generated
        # adjudicator directory.
        if _path_is_relative_to(
            source_path,
            normalized_output_directory,
        ):
            raise AdjudicationPathError(
                "A source annotation file is inside the adjudication "
                f"output directory: {source_path}"
            )


def get_adjudication_paths(
    record_output_path: str | Path,
    subject: Any,
    file_tag: Any,
    adjudicator: Any,
    *,
    source_paths: Optional[list[str | Path]] = None,
    allowed_adjudicators: Optional[list[str]] = None,
) -> AdjudicationPaths:
    """
    Build and validate all adjudication output paths.

    Parameters
    ----------
    record_output_path : str or pathlib.Path
        Waveform-record output directory. This is the directory containing the
        source annotator folders.

    subject : Any
        Subject identifier included in output filenames.

    file_tag : Any
        Waveform record identifier included in output filenames.

    adjudicator : Any
        Reviewer username used for the output folder and filenames.

    source_paths : list[str or Path] or None
        Optional source annotation paths protected from output overlap.

    allowed_adjudicators : list[str] or None
        Optional adjudicator allowlist override.

    Returns
    -------
    AdjudicationPaths
        Validated draft CSV, complete CSV, state JSON, and output-directory
        paths.

    Raises
    ------
    AdjudicationPathError
        If the input path or generated paths violate the file contract.
    """
    start_time = perf_counter()

    try:
        return _get_adjudication_paths_impl(
            record_output_path=record_output_path,
            subject=subject,
            file_tag=file_tag,
            adjudicator=adjudicator,
            source_paths=source_paths,
            allowed_adjudicators=allowed_adjudicators,
        )

    except Exception as exc:
        print(
            "[ADJUDICATION] get_adjudication_paths failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "get_adjudication_paths",
            perf_counter() - start_time,
            adjudicator=clean_string(adjudicator),
            file_tag=clean_string(file_tag),
        )


def _get_adjudication_paths_impl(
    record_output_path: str | Path,
    subject: Any,
    file_tag: Any,
    adjudicator: Any,
    *,
    source_paths: Optional[list[str | Path]] = None,
    allowed_adjudicators: Optional[list[str]] = None,
) -> AdjudicationPaths:
    """
    Construct adjudication output paths without UI behavior.

    This private implementation is called by the timed public wrapper.
    """
    record_output = Path(
        record_output_path
    ).expanduser().resolve(strict=False)

    if not clean_string(record_output_path):
        raise AdjudicationPathError(
            "record_output_path cannot be blank."
        )

    adjudicator_name = validate_adjudicator(
        adjudicator,
        allowed_adjudicators=allowed_adjudicators,
    )

    filename_base = build_adjudication_filename_base(
        subject=subject,
        file_tag=file_tag,
        adjudicator=adjudicator_name,
        allowed_adjudicators=allowed_adjudicators,
    )

    # Store adjudications separately from all source-user folders.
    output_directory = (
        record_output
        / ADJUDICATION_FOLDER_NAME
        / adjudicator_name
    )

    draft_csv = (
        output_directory
        / f"{filename_base}.csv"
    )

    complete_csv = (
        output_directory
        / (
            f"{filename_base}"
            f"{COMPLETE_FILENAME_SUFFIX}.csv"
        )
    )

    state_json = (
        output_directory
        / (
            f"{filename_base}"
            f"{ADJUDICATION_STATE_FILENAME_SUFFIX}"
        )
    )

    paths = AdjudicationPaths(
        output_directory=output_directory,
        draft_csv=draft_csv,
        complete_csv=complete_csv,
        state_json=state_json,
    )

    validate_adjudication_paths(
        paths=paths,
        record_output_path=record_output,
        source_paths=source_paths,
    )

    return paths


def ensure_adjudication_output_directory(
    paths: AdjudicationPaths,
) -> Path:
    """
    Create the adjudicator output directory when it does not exist.

    Parameters
    ----------
    paths : AdjudicationPaths
        Previously validated adjudication output paths.

    Returns
    -------
    pathlib.Path
        Created or existing adjudicator output directory.

    Raises
    ------
    OSError
        If the directory cannot be created because of permissions, network
        storage availability, or another filesystem error.

    Notes
    -----
    This function creates directories only. It does not create, modify, or
    delete annotation or adjudication files.
    """
    start_time = perf_counter()

    try:
        return _ensure_adjudication_output_directory_impl(
            paths=paths,
        )

    except Exception as exc:
        print(
            "[ADJUDICATION] "
            "ensure_adjudication_output_directory failed:",
            type(exc).__name__,
            exc,
        )
        raise

    finally:
        _perf_log(
            "ensure_adjudication_output_directory",
            perf_counter() - start_time,
            output_directory=paths.output_directory,
        )


def _ensure_adjudication_output_directory_impl(
    paths: AdjudicationPaths,
) -> Path:
    """
    Create the adjudicator directory without timing or UI behavior.
    """
    output_directory = (
        paths.output_directory
        .expanduser()
        .resolve(strict=False)
    )

    # parents=True creates ADJUDICATION and the adjudicator folder as needed.
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not output_directory.is_dir():
        raise AdjudicationPathError(
            "Adjudication output path was not created as a directory: "
            f"{output_directory}"
        )

    return output_directory

