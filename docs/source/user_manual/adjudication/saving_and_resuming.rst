.. _adjudication-saving-resuming:

Saving and Resuming
===================

Overview
--------

Adjudication work is saved separately from the original annotator files.

A saved session consists of:

- A CSV containing final intervals and labels.
- A companion JSON containing comparison and resolution state.

Both files are required to resume the session.

Saving Options
--------------

Manual Save
~~~~~~~~~~~

Click **Save Draft** to save immediately.

Before saving:

1. Click **Apply Final Label** for pending sidebar changes.
2. Finish or cancel Add Boundary placement.
3. Click **Save Draft**.
4. Confirm the save-status message reports success.

Manual saving is recommended before closing, changing records, or taking
a break.

Automatic Save
~~~~~~~~~~~~~~

The adjudication window checks for changed draft work every two minutes.

Autosave runs when:

- An adjudication is loaded.
- The session is editable rather than completed/read-only.
- Applied changes have not yet been saved.
- No boundary insertion is pending.
- No unapplied sidebar label changes remain.

Autosave does not finalize the adjudication or resolve disagreements.

.. important::

   Sidebar text is not committed to the final timeline until
   **Apply Final Label** is clicked.

   Autosave is deferred while unapplied label changes or pending boundary
   placement exist. The status message explains why saving was deferred.

Autosave After Reopening
~~~~~~~~~~~~~~~~~~~~~~~

A reopened completed adjudication is eligible for draft autosave.

The first successful draft save, whether manual or automatic:

- Archives the previous completed CSV and JSON.
- Writes the editable draft.
- Preserves unresolved review regions.
- Changes the active saved status to Draft.

Clicking Reopen alone does not immediately replace the completed files.
A successful subsequent draft save does.

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
- Source references and verification metadata.
- Comparison regions and reasons.
- Resolved and unresolved states.
- Comparison tolerance.
- Selection information.
- Workflow timestamps.

Caliper measurements are not saved.

Save Confirmation
-----------------

The sidebar displays a compact save confirmation.

Examples include:

- Draft saved successfully.
- Draft autosaved successfully.
- Autosave deferred.
- Autosave failed.

Hover over a successful save message to view the full output path.

Success is reported only after the CSV and JSON have been written and
verified.

An unchanged session does not need another automatic save.

Output Location
---------------

Each waveform record has its own adjudication directory::

   <batch>/<subject>/<encounter>/output/<file_tag>/
   └── ADJUDICATION/
       └── <adjudicator>/

Draft files use::

   adjudication_<subject>_<file_tag>_<adjudicator>.csv
   adjudication_<subject>_<file_tag>_<adjudicator>_state.json

Completed files use::

   adjudication_<subject>_<file_tag>_<adjudicator>_COMPLETE.csv
   adjudication_<subject>_<file_tag>_<adjudicator>_state.json

Source annotator folders remain separate and unchanged.

Resuming Work
-------------

1. Open Adjudication mode.
2. Select the same adjudicator.
3. Set the batch folder using the path available on your computer.
4. Select the waveform record.
5. Click **Resume Adjudication**.

The application restores final labels, boundaries, comparison context,
and explicit resolution state.

Completed sessions load read-only.
Use **Reopen for Editing** to revise them.

Use Resume rather than Load Waveform / Compare when continuing saved work.
A fresh comparison does not restore previous adjudicator edits.

Resuming on Another Operating System
------------------------------------

Windows and macOS may use different paths to the same Turbo files.

For example::

   macOS:
   /Volumes/<share>/...

   Windows:
   \\<server>\<share>\...

Resume locates the source annotations under the currently selected record's
output directory.

A historical Mac path in the saved JSON does not need to be manually changed
to a Windows path.

The saved annotator identities and comparison state remain preserved.

.. important::

   Both completed source annotation files must remain accessible from the
   current computer.

   Selecting the correct batch folder is still required.

Source Verification
-------------------

New saves record content fingerprints for the source annotations.

During resume, the application verifies the currently located source files
against the saved fingerprints.

Older sessions without source fingerprints use their saved file size and
modification metadata.

If verification reports changed or missing inputs:

- Preserve the adjudication files.
- Do not manually edit the JSON.
- Contact support before rebuilding the comparison.

For older sessions, modification-time differences can require investigation
even when files are accessed through another mount protocol.

CSV and JSON Pairing
-------------------

The adjudication CSV has a SHA-256 content fingerprint stored in its JSON.

Resume recalculates that fingerprint to verify that the files belong together.

This detects:

- An interrupted or inconsistent save.
- Manual CSV modification.
- Files copied from different saved versions.

SHA-256 is an integrity check, not encryption or proof of authenticity.

.. warning::

   Do not manually edit, rename, move, or delete either file.

   Keep the CSV and JSON together as a matching pair.

Save Failures
-------------

Possible causes include:

- Turbo is disconnected or unavailable.
- The output directory is not writable.
- A filesystem operation fails.
- CSV/JSON verification fails.
- The session has not been reopened from completed status.

Manual save failures display an error dialog.

Autosave failures display a non-blocking sidebar message and terminal
diagnostics. Unsaved state is retained for a later retry.

If saving fails:

1. Keep the application open.
2. Do not discard changes or load another record.
3. Read the error or status message.
4. Check network and storage access.
5. Apply pending label changes if necessary.
6. Retry Save Draft.
7. Confirm success before leaving the session.

Leaving a Session
-----------------

Before closing or changing records:

- Apply pending sidebar changes.
- Finish or cancel boundary placement.
- Click Save Draft.
- Confirm successful saving.

Autosave reduces the amount of work at risk, but does not replace a verified
manual save before leaving.

If unsaved changes remain, the application asks before discarding them.

Choose Cancel to return and save.
Choose Discard only when intentionally abandoning those changes.

Related Pages
-------------

- :ref:`adjudication-review-workflow`
- :ref:`adjudication-completion-reopening`
- :ref:`adjudication-troubleshooting`