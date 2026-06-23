.. _getting-started:

Getting Started
===============

Introduction
------------

The ECG Waveform Annotation App enables clinical users to annotate physiological waveforms for research and quality improvement.

The application is designed for sequential waveform review. Users mark intervals, answer clinical annotation questions, save progress, and finalize waveforms when review is complete.

Launching the Application
-------------------------

The application will be distributed as a standalone executable.

To launch:

- On Windows, double-click ``waveform_annotation_app.exe``. (or similar name)
- On Mac/Linux, double-click or run ``waveform_annotation_app``.
- Ensure you have access to the base data folder containing waveform files.

Network Access
--------------

Waveform data can be large. For best performance, annotate while directly connected to the Michigan Network (on-site).

VPN access is supported (and required if off-network), but waveform loading may be slower.

.. note::

   If loading appears slow after selecting a subject, the application may still be reading large waveform files over the network. Please allow time for loading to complete, especially if off-site.

Base Data Folder
----------------

The base data folder contains subject folders, encounter folders, waveform files, metadata, and manifest files.

A typical folder structure may look like this::

   base_data_folder/
   └── MRNNumberPlaceholder/
       └── CSNNumberPlaceholder/
           ├── GEWAVE/
           │   ├── waveform_file_Event01.csv
           │   ├── waveform_file_Event02.mat
           ├── metadata_*.json
           └── waveform_manifest.csv

In the app, select the top-level base folder. For example::

   /nfs/turbo/umms-PI/project/waveforms/

You will likely be provided with the exact base folder path. Keep this path available for future annotation sessions.

Make sure you connect directly to the storage location through you Finder Window or File Explorer.

Setting the Base Folder
-----------------------

1. Paste or browse to the base data folder path.
2. Click **Set Folder** if pasting.
3. Wait for the app to scan for available waveform records and populate the subject dropdown.
4. Select a waveform record from the subject dropdown.

.. warning::

   Do not manually open, edit, move, rename, or delete waveform files using file explorer, terminal, or other tools. Use the annotation app to access waveform data.

Terminology
-----------

The app may display more than one waveform record for a subject.

Common terms:

``Subject``
   The patient or deidentified subject folder, often represented by an MRN-like identifier (or Deidentified UUID).

``Encounter``
   The encounter folder, often represented by a CSN-like identifier (or Deidentified UUID).

``Waveform record``
   A specific waveform file or recording session for an event of interest available for annotation.

``Annotation session``
   One user's saved annotation file for one waveform record.

``Complete annotation``
   A finalized annotation file saved with ``_COMPLETE`` in the filename.