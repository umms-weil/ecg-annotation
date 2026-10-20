"""
Combined timeline construction, agreement classification, consensus
prefilling, and the primary adjudication comparison API.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Optional

import numpy as np

from .boundaries import extract_and_match_source_boundaries
from .config import (
    ADJUDICATION_BOUNDARY_TOLERANCE_SEC,
    ANNOTATION_USERS,
    ComparisonStatus,
    DisagreementReason,
)
from .discovery import (
    discover_source_annotation_files,
    require_ready_source_annotation_files,
)
from .exceptions import (
    AdjudicationError,
    InvalidAnnotationError,
)
from .models import (
    AdjudicationComparisonResult,
    AdjudicationInterval,
    AnnotationInterval,
    BoundaryMatch,
    ComparisonRegion,
    SourceAnnotationFile,
    ValidationIssue,
)
from .utilities import (
    _perf_log,
    clean_string,
    stable_numbered_id,
    utc_now_iso,
)
from .validation import load_and_validate_source_pair

# =============================================================================
# Combined timeline segmentation
# =============================================================================

# Functions for:
#
# - collecting reconciled and unmatched boundaries
# - splitting the full time range into atomic regions
# - finding active A/B intervals at each region midpoint
# - distinguishing complete, one-sided, and missing coverage


# =============================================================================
# Agreement classification
# =============================================================================

# Functions for:
#
# - comparing CPR values
# - comparing rhythm labels
# - checking adjacent-label compatibility
# - assigning agreement/disagreement/missing status
# - attaching machine-readable disagreement reasons
# - creating stable disagreement IDs


# =============================================================================
# Prefilled final timeline generation
# =============================================================================

# Functions for:
#
# - pre-filling green agreement regions
# - using midpoint-reconciled boundaries
# - leaving red/gray regions unresolved
# - optionally merging adjacent identical green intervals
# - preventing gaps and overlaps introduced by reconciliation
# - generating AdjudicationInterval objects


# =============================================================================
# Main comparison API
# =============================================================================

def build_adjudication_comparison(
    record,
    adjudicator,
    *,
    annotators=None,
    boundary_tolerance_sec=ADJUDICATION_BOUNDARY_TOLERANCE_SEC,
):
    """
    Discover, validate, and compare the two source annotation files.

    Returns an AdjudicationComparisonResult.

    This should be the primary function called by adjudication callbacks.
    """
    raise NotImplementedError

