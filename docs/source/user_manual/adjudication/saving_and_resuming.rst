.. _adjudication-saving-resuming:

Saving and Resuming
===================

Overview
--------

Adjudication work is saved separately from the original annotator files.

A saved session consists of:

- A CSV containing the current final intervals and labels.
- A companion JSON containing comparison and resolution state.

Both files are required to resume the session.

.. important::

   The current adjudication baseline uses manual saving.

   The original annotation application's two-minute autosave does not apply
   to the adjudication window.

Saving a Draft
--------------

Use **Save Draft** while review is in progress.

Before saving:

1. Click **Apply Final Label** for pending sidebar changes.
2. Finish or cancel pending Add Boundary placement.
3. Click **Save Draft**.
4. Confirm the save-status message reports success.

Drafts may contain:

- Unresolved disagreements.
- Blank provisional final labels.
- Work that is not yet eligible for finalization.

Saving a draft does not mark unresolved regions resolved.

What a Draft Preserves
----------------------

The CSV preserves:

- Adjudicator identity.
- Waveform-record metadata.
- Final interval start and end times.
- Final CPR responses.
- Final rhythm labels.
- Explanations and comments.

The JSON preserves:

- Annotator A/B mapping.
- Source file references and modification metadata.
- Comparison regions and reasons.
- Resolved and unresolved states.
- Comparison tolerance.
- Current selection information.
- Workflow timestamps.

Caliper measurements are not saved.

Save Confirmation
-----------------

The sidebar displays a compact success or failure message.

Hover over a successful save message to view the full CSV path.

A successful save is reported only after the CSV and JSON have been written
and verified.

Do not interpret an unchanged plot or a button click as proof of saving.

Output Location
---------------

Each waveform record has its own adjudication output directory::

   <batch>/<subject>/<encounter>/output/<file_tag>/
   └── ADJUDICATION/
       └── <adjudicator>/

Draft files use::

   adjudication_<subject>_<file_tag>_<adjudicator>.csv
   adjudication_<subject>_<file_tag>_<adjudicator>_state.json

The original annotator folders remain separate::

   <record_output>/
   ├── <annotator_a>/
   ├── <annotator_b>/
   └── ADJUDICATION/
       └── <adjudicator>/

Resuming a Draft
----------------

1. Open Adjudication mode.
2. Select the same adjudicator.
3. Set the same batch folder.
4. Select the waveform record.
5. Click **Resume Adjudication**.

The application restores:

- Final labels.
- Edited boundaries.
- Explicit resolution state.
- Saved comparison context.
- Selection information where available.

Use Resume rather than Load Waveform / Compare when continuing saved work.

Loading a fresh comparison does not restore previous adjudicator edits.

CSV and JSON Pairing
-------------------

The application records a hash linking the saved CSV to its state JSON.

This detects situations where:

- Only one file was replaced.
- A save was interrupted between file writes.
- Someone manually edited a CSV.
- Files from different sessions were copied together.

.. warning::

   Do not manually edit, rename, move, or delete either file.

   The files must remain together as a matching pair.

If the application reports a mismatch, preserve both files and contact
support. Do not attempt to fix the mismatch by deleting the JSON or changing
its contents.

Source Annotation Changes
-------------------------

The saved state records metadata for the two source annotation files.

On resume, the application checks whether those files are missing or changed.

If a source changed, resume is blocked.

This prevents an existing adjudication from silently continuing against
different source inputs.

Keep the saved adjudication files and contact the project team to determine
whether the comparison should be rebuilt.

Save Failures
-------------

Possible causes include:

- Turbo is disconnected or unavailable.
- The adjudicator output folder is not writable.
- Required parent directories cannot be accessed.
- A file operation failed.
- CSV/JSON verification failed.
- A completed adjudication has not been explicitly reopened.

If saving fails:

1. Keep the application open.
2. Do not load another record or discard edits.
3. Read the error message.
4. Confirm network and storage access.
5. Retry saving after the problem is corrected.
6. Contact support if it continues to fail.

Applied edits remain in memory when a save fails.

If reconnecting Turbo requires restarting the application, seek assistance
before closing an unsaved session.

Leaving a Session
-----------------

Before closing or loading another record:

- Apply pending sidebar changes.
- Finish or cancel boundary placement.
- Save the draft.
- Confirm success.

If unsaved changes exist, the application asks before discarding them.

Choose **Cancel** to return to the session and save.
Choose **Discard** only when intentionally abandoning those changes.

Completed Sessions
------------------

Resume can also load completed adjudications.

Completed sessions open read-only.
Use **Reopen for Editing** to make revisions.

See :ref:`adjudication-completion-reopening`.

Related Pages
-------------

- :ref:`adjudication-review-workflow`
- :ref:`adjudication-completion-reopening`
- :ref:`adjudication-troubleshooting`