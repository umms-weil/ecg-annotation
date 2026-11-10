.. _saving-resuming:

Saving and Resuming Work
========================

Autosave
--------

The app automatically saves annotations every 2 minutes.

Autosave helps reduce data loss if:

- The app closes unexpectedly.
- The network connection drops.
- The workstation restarts.
- The user forgets to manually save.

Manual Save
-----------

Click **Save All Annotations** to manually save your work.

Manual saving is recommended before:

- Closing the app.
- Taking a break.
- Switching waveform records.
- Disconnecting from VPN.
- Leaving the workstation.

Loading Previous Annotations
----------------------------

To resume previous work:

1. Launch the app.
2. Select your correct user name.
3. Select the base data folder.
4. Select the same waveform record.
5. Click **Load Subject**.
6. Click **Load Annotations**.

The app will load your saved annotation file and continue from the most recent interval endpoint.

.. important::

   Annotation files are user-specific. If your username is entered incorrectly, the app may not find your previous work.

Partial Annotation Files
------------------------

Partial annotation sessions are saved without ``_COMPLETE`` in the filename.

Example::

   annotations_subject_filetag_jdoe.csv

If no file tag is available, the filename may use this pattern::

   annotations_subject_jdoe.csv

Complete Annotation Files
-------------------------

Finalized annotation sessions are saved with ``_COMPLETE`` in the filename.

Example::

   annotations_subject_filetag_jdoe_COMPLETE.csv

If no file tag is available, the filename may use this pattern::

   annotations_subject_jdoe_COMPLETE.csv

Output Folder
-------------

Annotation files are saved per waveform record and per user.

The output location is typically inside an ``output`` folder associated with the waveform record.

Example structure::

   GEWAVE/
   ├── waveform_file.csv
   └── output/
       └── waveform_file/
           └── jdoe/
               ├── annotations_subject_filetag_jdoe.csv
               └── annotations_subject_filetag_jdoe_COMPLETE.csv

.. warning::

   Do not manually edit, rename, move, or delete annotation files. Use the app's save, load, and undo controls.

Completion Statistics
---------------------

The subject dropdown may show completion information such as::

   subject_or_record_name (1/3 complete)

This means:

- ``1`` complete annotation file exists.
- ``3`` total annotation files exist, including partial and complete files.

Completion statistics may reflect annotations across users for the selected waveform record.

Data Integrity Rules
--------------------

To avoid data corruption:

- Use your own U-M uniqname.
- Do not annotate under another user's name.
- Do not manually modify waveform files.
- Do not manually modify annotation files.
- Use **Load Annotations** to resume work.
- Use **Save All Annotations** before closing the app.