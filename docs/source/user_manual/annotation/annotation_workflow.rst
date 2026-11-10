.. _annotation-workflow:

Annotation Workflow
===================

Overview
--------

Annotations are created sequentially from the beginning of the loaded waveform toward the end.

Each interval begins where the previous interval ended. You can only remove the most recent annotation.

Step 1: Select the Base Data Folder
-----------------------------------

1. Launch the application.
2. Enter or browse to the base data folder.
3. Click **Set Folder**.
4. Wait for available waveform records to appear in the dropdown.

Step 2: Select Your User Name
-----------------------------

Select your U-M uniqname in the sidebar.

Use your uniqname in lowercase. For example::

   jdoe

Your username is used to:

- Attribute your annotations.
- Save your annotation file separately from other users.
- Resume your previous work.

If your username is not available in the drop-down, contact :ref:`support`.

Step 3: Choose a Waveform Record
--------------------------------

Select a waveform record from the dropdown.

The dropdown may display information such as:

- Subject identifier.
- Encounter identifier.
- Waveform namespace.
- File tag.
- Completion statistics.

Click **Load Subject** to load the waveform data.

.. note::

   Loading can take time because some waveform files are large, especially over VPN.

Step 4: Resume Previous Work, If Needed
---------------------------------------

If you previously annotated this waveform record:

1. Select the same user name.
2. Select the same waveform record.
3. Click **Load Subject**.
4. Click **Load Annotations**.

The app will load your saved intervals and continue from the last marked endpoint.

.. important::

   Previous annotations are user-specific. If you enter the wrong username, the app may not find your saved annotations.

Step 5: Navigate the Waveform
-----------------------------

Use the waveform plots to review the signal.

Recommended navigation:

- Use a mouse scroll wheel for horizontal zooming.
- Use plot controls for Y-axis adjustment.
- Collapse waveform sections that are not useful.
- Click and drag to peruse the waveform quickly.
- Ignore leads marked as unavailable or showing no data.

Step 6: Place an Interval Endpoint
----------------------------------

Click on the waveform to place the next endpoint.

The interval to be annotated is from the previous endpoint to the point you clicked.

Rules:

- The endpoint must be after the previous mark.
- The interval must be at least 1 second long.
- If the endpoint is within 1 second of the waveform end, it snaps to the final point.
- If the endpoint is beyond the waveform end, it snaps to the final point.

Step 7: Answer Sidebar Questions
--------------------------------

Before clicking **Mark**, answer the required sidebar questions.

You must provide:

- CPR Yes/No answer.
- Rhythm label when required.
- Explanation when required.

The sidebar displays red warning messages when required information is missing.

Step 8: Click Mark
------------------

When all required information is complete, the **Mark** button becomes enabled.

Click **Mark** to save the interval into the annotation table.

After marking:

- The interval appears as a colored overlay on the waveform.
- The interval is added to the annotation table.
- The next interval begins where the previous one ended.
- The sidebar resets for the next annotation.

Step 9: Save Your Work
----------------------

Autosave runs every 2 minutes.

You should also manually save by clicking **Save All Annotations**, especially before:

- Taking a break.
- Closing the app.
- Switching subjects.
- Disconnecting from VPN or network storage.

Step 10: Finalize the Waveform
------------------------------

When the final annotation reaches the end of the waveform, the **Finalize Waveform** button becomes available.

Click **Finalize Waveform** and answer the final completion question.

You **MUST** Finalize Waveform to complete the annotation. 

After finalization, the annotation file is saved with ``_COMPLETE`` in the filename.

See :ref:`completion-finalization` for details.