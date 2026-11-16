.. _adjudication-getting-started:

Getting Started
===============

Purpose
-------

Adjudication is the review of two completed annotation sessions for the same
waveform record.

The reviewer creates a separate final timeline by:

- Inspecting the source annotations.
- Reviewing discrepancies.
- Adjusting final labels and boundaries.
- Explicitly resolving review regions.
- Saving and finalizing the adjudication.

The application does not change either annotator's original files.

Before You Begin
----------------

Make sure you have:

- The application extracted into a local folder.
- Access to the assigned annotation batch on Turbo.
- The required network or VPN connection.
- Your configured adjudicator username.
- Two completed annotator inputs for the waveform you intend to review.
- Permission to write to the adjudication output location.

.. important::

   Run the application locally, not directly from inside a ZIP file or from
   Turbo.

   Keep the entire extracted Windows application folder together, including
   its ``_internal`` directory.

For network and storage setup, see :ref:`connect-to-network`.

Opening the Reviewer Interface
-------------------------------

1. Launch the application.
2. Select **Adjudication** in the startup mode chooser.
3. The independent adjudication window opens.

Choosing **Annotation** opens the original annotator workflow instead.

There is no live workflow switch inside the window. Close and relaunch the
application to select another mode.

Selecting the Adjudicator
-------------------------

Select your username from the **Adjudicator** dropdown.

The list contains the reviewers configured for the project.

Your selection determines whose adjudication files are loaded or created.
It does not change the network credentials used to access Turbo.

.. note::

   Filesystem access uses the account associated with your Turbo connection.
   Selecting a username in the application does not grant storage permission.

Selecting the Batch Folder
--------------------------

Use either method:

Paste a Path
~~~~~~~~~~~~

1. Paste the assigned batch path into **Annotation Batch Folder**.
2. Click **Set Folder**, or press **Enter**.
3. Wait for waveform discovery and status checks to finish.

Browse
~~~~~~

1. Click **Browse**.
2. Select the assigned batch directory.
3. Wait for the waveform dropdown to populate.

Select the batch directory containing the subject folders, not an individual
annotator output folder.

Example::

   BATCH_1/
   └── subject/
       └── encounter/
           ├── GEWAVE/
           ├── GEVITAL/
           ├── waveform_manifest.csv
           └── output/
               └── waveform_file_tag/
                   ├── annotator_a/
                   ├── annotator_b/
                   └── ADJUDICATION/

Record Status
-------------

The record dropdown shows the selected adjudicator's saved workflow status.

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Status
     - Meaning
   * - Not Ready
     - One or more required completed annotator files are missing.
   * - Ready
     - Completed annotator inputs exist and no adjudication is saved.
   * - Draft
     - A saved draft is available.
   * - Complete
     - A completed adjudication is available.
   * - Check Files
     - Saved files are inaccessible, inconsistent, or require investigation.

Hover over a record to view additional status information.

These indicators check expected file availability and saved state.
Full input validation occurs during loading.

.. note::

   A saved Draft or Complete status does not guarantee that its source files
   are still available or unchanged. Loading may report an input problem.

Starting or Resuming
-------------------

Starting a New Review
~~~~~~~~~~~~~~~~~~~~~

1. Select the waveform record.
2. Click **Load Waveform / Compare**.
3. Review the newly generated comparison and prefilled final timeline.

Resuming Existing Work
~~~~~~~~~~~~~~~~~~~~~~

1. Select the same batch, waveform record, and adjudicator.
2. Click **Resume Adjudication**.

Use Resume for a saved Draft or Complete record. Loading a fresh comparison
does not restore your previous reviewer edits.

Completed adjudications load read-only. Select **Reopen for Editing** if a
revision is necessary.

Refreshing Record Information
-----------------------------

Click **Set Folder** to rediscover the batch and refresh externally changed
file statuses.

The application caches record information during a session. Changes made
outside the application may not appear immediately.

Save current work before changing batches or loading another record.

Next Steps
----------

Continue with:

- :ref:`adjudication-review-workflow`
- :ref:`adjudication-interface-guide`