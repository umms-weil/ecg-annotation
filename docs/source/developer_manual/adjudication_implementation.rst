.. _developer-adjudication-implementation:

Adjudication Implementation
==========================

Overview
--------

Adjudication is an independent reviewer workflow within the waveform
application.

The startup chooser opens either:

- The existing annotation window.
- The independent adjudication window.

Annotation callbacks are not inherited by the adjudication window.
This separates reviewer state, file operations, and interaction handling from
the original annotation workflow.

The canonical requirements are documented in
:ref:`developer-adjudication-contract`.

Module Structure
----------------

.. code-block:: text

   software/src/
   ├── app.py
   ├── callbacks.py
   ├── adjudication_app.py
   ├── adjudication_callbacks.py
   ├── adjudication_calipers.py
   └── adjudication/
       ├── __init__.py
       ├── config.py
       ├── exceptions.py
       ├── models.py
       ├── utilities.py
       ├── paths.py
       ├── discovery.py
       ├── loading.py
       ├── validation.py
       ├── boundaries.py
       ├── comparison.py
       └── persistence.py

Responsibilities
---------------

``app.py``
   Owns the startup mode chooser and existing annotation window.

``adjudication_app.py``
   Constructs the reviewer window, sidebar, plots, timelines, table, and signal
   connections.

``adjudication_callbacks.py``
   Handles loading, selection, final editing, resolution, saving, resuming,
   status indicators, overlays, and events.

``adjudication_calipers.py``
   Owns temporary caliper state, peak measurements, manual dots, and projection
   graphics.

``adjudication/``
   Contains non-UI models, comparison processing, validation, and persistence.

Processing modules must remain importable without importing the GUI modules.

Configuration
-------------

Project configuration resides in ``adjudication/config.py``.

Important settings include:

- ``ANNOTATION_USERS``
- ``ADJUDICATORS``
- ``REQUIRED_ANNOTATOR_COUNT``
- ``ANNOTATOR_ALIASES``
- ``ADJUDICATION_BOUNDARY_TOLERANCE_SEC``
- ``MINIMUM_VALID_INTERVAL_SEC``
- ``SOURCE_CONTINUITY_TOLERANCE_SEC``
- CSV column definitions.
- Schema version.

The current implementation supports exactly two source annotators.

Their configured order determines the stable Annotator A/B mapping.

The minimum final interval duration is currently one second.

Comparison Pipeline
-------------------

The main processing entry point is:

.. code-block:: python

   build_adjudication_comparison(
       record,
       adjudicator,
       annotators=None,
       allowed_adjudicators=None,
       boundary_tolerance_sec=1.0,
       merge_adjacent_agreement=True,
   )

The pipeline is:

.. code-block:: text

   Selected waveform record
       -> Discover configured COMPLETE inputs
       -> Require two ready source files
       -> Load and normalize CSV rows
       -> Validate source timelines and record identity
       -> Extract boundaries
       -> Match compatible boundaries
       -> Build reconciled atomic segments
       -> Classify comparison regions
       -> Generate provisional final intervals

Source Loading and Validation
-----------------------------

Discovery checks configured user folders under the selected record's
``output_path``.

Completed files are preferred. Partial files are identified as incomplete
rather than accepted as normal comparison inputs.

Source validation checks:

- Required columns.
- Source username.
- Finite boundaries.
- Minimum interval duration.
- Sequential coverage.
- Gaps and overlaps.
- CPR/rhythm/explanation rules.
- Completion metadata.
- Consistent record identity.

Missing or invalid inputs can block comparison construction.
The current engine does not construct a full comparison from an absent source.

Boundary Matching
-----------------

Boundary extraction records:

- Source start.
- Internal transitions.
- Source end.
- Labels immediately before and after each boundary.

Matching uses ordered one-to-one alignment.

The algorithm maximizes compatible matches and then minimizes their total
time offset.

A match requires:

- Corresponding boundary types.
- Absolute difference within tolerance.
- Compatible CPR and rhythm on both applicable sides.

Accepted matches use their midpoint.

Unmatched boundaries retain their original coordinates for comparison.

.. note::

   Midpoint reconciliation must not collapse or reverse intervals.

   Finalization also checks actual loaded-waveform bounds. Reconciled outer
   boundaries that do not match those bounds can therefore require investigation.

Comparison and Prefilling
-------------------------

Atomic segments are classified as:

``agreement``
   Both sources cover the segment without detected label or boundary conflict.

``unresolved_disagreement``
   Both sources cover the segment but a conflict exists.

``missing_coverage``
   One or both sources lack coverage.

``resolved_disagreement``
   A review region was explicitly resolved in the UI.

Green regions receive agreed final labels.

Red and gray regions remain unlabeled.

Adjacent green regions may merge when their final label and explanation
values match.

Different source explanation text is not silently selected. A required final
explanation may still need reviewer input.

Time Representation
-------------------

Waveform, source, and final boundaries use floating-point UTC epoch seconds.

Relative plot labels do not change the underlying coordinates.

No deliberate rounding or conversion to integer milliseconds should occur.

Saved CSV loading uses round-trip floating-point parsing where implemented.

Workflow State
--------------

The reviewer window maintains separate state for:

- Loaded record.
- Loaded adjudicator.
- Comparison result.
- Selected final interval.
- Selected comparison region.
- Pending boundary placement.
- Dirty state.
- Completed/read-only state.
- Reopened-from-complete state.

Saving uses the loaded session identity, not merely the current dropdown
selection.

Changing a dropdown does not automatically replace the loaded session.

UI Editing
----------

Final labels are edited in the sidebar and committed through
``Apply Final Label``.

Boundary operations include:

- Dragging an internal final boundary.
- Click-to-place splitting.
- Removing a boundary to merge neighboring intervals.

Dragging updates both adjacent interval endpoints together.

New splits leave at least the minimum duration on each side.

Merging different labels or comments requires confirmation and clears the
merged final label.

Source timelines and source overlays remain unchanged.

Resolution
----------

Only ``Mark Resolved`` resolves a review region.

Before resolution, callbacks check valid final coverage and required labels
throughout that region.

A later applied edit affecting a resolved region invalidates its resolution.

Original green agreement remains comparison context and is not a clinical
approval flag.

Persistence
-----------

Output is stored under:

.. code-block:: text

   <record_output_path>/ADJUDICATION/<adjudicator>/

Draft:

.. code-block:: text

   adjudication_<subject>_<file_tag>_<adjudicator>.csv
   adjudication_<subject>_<file_tag>_<adjudicator>_state.json

Completed:

.. code-block:: text

   adjudication_<subject>_<file_tag>_<adjudicator>_COMPLETE.csv
   adjudication_<subject>_<file_tag>_<adjudicator>_state.json

The CSV is authoritative for final interval output.

The JSON stores comparison context, resolution flags, source signatures,
navigation state, and workflow metadata.

Individual files are written through temporary files and replacement.
The CSV/JSON pair is not one filesystem transaction.

A stored CSV hash detects mismatched pairs.

.. important::

   Interrupted saves can leave a mismatched pair. Resume must report this
   rather than silently loading inconsistent versions.

   Source annotator files must never be overwritten by persistence operations.

Source-Change Detection
-----------------------

Saved source signatures contain file size and modification time.

Resume checks these signatures before restoring the session.

The current implementation blocks resume when a source changed or is missing.
It does not yet offer an override/rebuild choice in the resume dialog.

Finalization
------------

Finalization checks:

- Loaded-waveform coverage.
- Contiguous final intervals.
- Minimum interval duration.
- Required labels and explanations.
- No unresolved review regions.
- Valid terminal-event status.

Completion metadata are stored on the last final interval.

The UI becomes read-only only after completed output is successfully written
and verified.

Reopening and History
---------------------

Reopening changes in-memory state first.

The previous completed files remain on disk until the first reopened draft
save.

That save:

1. Archives the completed CSV and JSON under ``history/<version_id>/``.
2. Verifies the archive.
3. Writes the new draft pair.
4. Removes the active completed CSV after draft verification.

The state JSON identifies the authoritative active CSV.

This matters if a cleanup failure leaves an old COMPLETE file beside a valid
draft.

Record Status Indicators
-----------------------

Status checks inspect known source/output paths rather than rediscovering
waveform files.

Reviewer-specific statuses are cached.

Saving, finalization, and reopening update only the loaded record.

Set Folder explicitly refreshes the batch.

Indicators describe file/workflow state, not clinical validity.

Overlays and Events
-------------------

Annotator A overlays occupy the upper waveform portion.
Annotator B overlays occupy the lower portion.
Final overlays cover the full plot height and start off by default.

Encounter events use the shared processing parser.

Timestamp priority is:

1. ``event_time``
2. ``original_event_time``
3. ``recorded_time``

Naive manifest timestamps are interpreted as America/New_York local time
and converted to UTC epoch seconds.

Out-of-waveform events are retained as metadata without expanding annotation
coverage.

Calipers
--------

The independent caliper controller provides:

- Synchronized start/stop lines.
- Automatic peak detection.
- Manual peak selection.
- Temporary rate calculation.
- Full-selected-range projection.

Interactive caliper modes suspend adjudication click/boundary editing.

Projection uses the full caliper duration, not the detected beat interval.

Panning refreshes projection graphics without rerunning detection.

All caliper state is temporary and excluded from persistence.

.. warning::

   Automatic detection is not clinically validated for peri-arrest signals.
   Timing regularity or plausible rate does not prove correct beat detection.

Timing and Error Handling
-------------------------

Substantive functions use timed public wrappers and private implementations.

Prefixes include:

- ``[PERF][ADJ]`` for processing.
- ``[PERF][ADJ-UI]`` for UI actions.
- ``[PERF][ADJ-CAL]`` for calipers.

Processing failures propagate to UI callbacks.

Save failures must retain dirty state and display a readable error.
Do not report success before persistence verification completes.

Testing
-------

Processing tests reside in:

.. code-block:: text

   software/tests/adjudication/

GUI tests reside in:

.. code-block:: text

   software/tests/adjudication_gui/

Run from the repository root:

.. code-block:: bash

   python -m pytest software/tests/adjudication software/tests/adjudication_gui -v

For headless GUI testing:

.. code-block:: bash

   QT_QPA_PLATFORM=offscreen python -m pytest software/tests/adjudication_gui -v

Current tests cover comparison, persistence, editing, explicit resolution,
read-only/reopen state, failure paths, events, and caliper isolation.

These tests establish software behavior, not clinical validity.

Related Documentation
---------------------

- :ref:`developer-adjudication-contract`
- :ref:`developer-adjudication-api`
- :ref:`adjudication-guide`