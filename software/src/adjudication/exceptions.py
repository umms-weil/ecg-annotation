"""
Custom exception types raised by the adjudication subsystem.
"""

from __future__ import annotations

# =============================================================================
# Public exception types
# =============================================================================

class AdjudicationError(Exception):
    """
    Base exception for adjudication processing failures.

    Callers may catch this exception when they want to handle all expected
    adjudication errors through one code path.
    """


class MissingInputError(AdjudicationError):
    """
    Raised when a required source annotation file cannot be found.
    """


class DuplicateInputError(AdjudicationError):
    """
    Raised when multiple eligible source files are found for one annotator.
    """


class InvalidAnnotationError(AdjudicationError):
    """
    Raised when a source or final annotation timeline is structurally invalid.
    """


class UnsupportedSchemaError(AdjudicationError):
    """
    Raised when a state file uses an unsupported adjudication schema version.
    """


class SourceFilesChangedError(AdjudicationError):
    """
    Raised when source annotation files changed after adjudication began.
    """


class AdjudicationPathError(AdjudicationError):
    """
    Raised when an output path is invalid or could overlap source annotations.
    """

