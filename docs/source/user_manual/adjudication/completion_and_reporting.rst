.. _adjudication-completion-reopening:

Completion and Reopening
========================

Overview
--------

Finalization marks the adjudicated timeline as complete.

It is separate from:

- Applying a final label.
- Marking a review region resolved.
- Saving a draft.

A completed adjudication may later be reopened for revision.

Before Finalizing
-----------------

Check that:

- All required waveform time is covered.
- Final intervals are sequential and contiguous.
- There are no invalid overlaps.
- Every final interval is at least one second long.
- CPR and rhythm values are valid.
- Required explanations are present.
- All red and gray review regions are explicitly resolved.
- Pending sidebar changes have been applied.
- Pending Add Boundary placement is finished or cancelled.

.. important::

   Green source agreement does not guarantee correct final labels.

   The adjudicator should inspect the final timeline before completing review.

Finalizing
----------

1. Click **Finalize Adjudication**.
2. Address any reported validation errors.
3. Select whether the cardiac arrest/event continues beyond the available
   waveform.
4. Enter an optional final comment.
5. Confirm that completed output was saved successfully.

Cancelling either finalization dialog leaves the session unfinalized.

Terminal-Event Decision
----------------------

Choose one of:

- Cardiac arrest/event does NOT continue beyond waveform.
- Cardiac arrest/event CONTINUES beyond waveform.

This records the reviewer's final interpretation of the available waveform
boundary.

The final comment is optional.

Completion metadata are stored on the last final interval.

Completed Filename
------------------

The completed CSV includes ``_COMPLETE``::

   adjudication_<subject>_<file_tag>_<adjudicator>_COMPLETE.csv

The companion state JSON remains::

   adjudication_<subject>_<file_tag>_<adjudicator>_state.json

The CSV contains the final interval output.
The JSON records that the workflow is complete.

After Finalization
------------------

The application becomes read-only for adjudication edits.

Disabled actions include:

- Applying final labels.
- Adding or removing boundaries.
- Dragging final boundaries.
- Marking regions resolved.
- Saving a draft.

Inspection remains available:

- Waveform navigation.
- Lead selection.
- Overlay visibility.
- Event-label visibility.
- Temporary caliper measurements.
- Final interval table selection.

The record status changes to **Complete**.

Validation Errors
-----------------

Unresolved Regions
~~~~~~~~~~~~~~~~~~

Use Previous/Next to locate remaining review regions.
Apply valid final decisions and click Mark Resolved.

Missing Fields
~~~~~~~~~~~~~~

Select the affected interval and complete the required CPR, rhythm, or
explanation fields.

Short Intervals
~~~~~~~~~~~~~~~

Comparison and editing can create short draft fragments.

Adjust or merge intervals shorter than one second before finalization.

Coverage Errors
~~~~~~~~~~~~~~~

The final timeline must match the loaded waveform's start and end.

If outer coverage is incorrect and cannot be corrected through available
editing controls, contact support.

Do not bypass coverage validation or manually change the CSV.

Loading Completed Work
-----------------------

1. Select the batch, record, and adjudicator.
2. Click **Resume Adjudication**.
3. The completed timeline loads read-only.

This restores the final labels and saved review state.

Reopening for Editing
---------------------

1. Load the completed adjudication.
2. Click **Reopen for Editing**.
3. Make the required revisions.
4. Save a draft or finalize again when appropriate.

Reopening:

- Enables final editing.
- Returns the session to an editable state.
- Clears completion metadata in the in-memory draft.
- Does not immediately delete or overwrite the completed files.

The previous completed version stays on disk until the first successful
reopened draft save.

Saving the First Reopened Draft
-------------------------------

The first successful Save Draft after reopening:

1. Preserves the previous completed CSV and JSON under ``history/``.
2. Writes the revised draft CSV.
3. Writes matching draft state JSON.
4. Removes the previous active completed CSV after verification.

Example::

   ADJUDICATION/<adjudicator>/
   ├── adjudication_...csv
   ├── adjudication_..._state.json
   └── history/
       └── <version_id>/
           ├── adjudication_..._COMPLETE.csv
           └── adjudication_..._state.json

Do not manually modify the history files.

Resolution After Revision
-------------------------

Changing final labels, comments, or boundaries can invalidate affected
previously resolved regions.

Those regions must be explicitly resolved again.

Saving a reopened draft with unresolved regions is allowed.
Finalization with unresolved regions is not allowed.

Refinalizing
------------

After revisions:

1. Apply pending label changes.
2. Resolve all affected review regions.
3. Check complete coverage and interval lengths.
4. Click Finalize Adjudication.
5. Complete the terminal-event decision and optional comment.

A revised completed CSV is produced.
The prior completed version remains in history.

Related Pages
-------------

- :ref:`adjudication-saving-resuming`
- :ref:`adjudication-resolving-disagreements`
- :ref:`adjudication-troubleshooting`