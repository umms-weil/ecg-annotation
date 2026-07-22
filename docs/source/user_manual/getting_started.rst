.. _getting-started:

Getting Started
===============

Introduction
------------

The ECG Waveform Annotation App enables clinical users to annotate physiological waveforms for research and quality improvement.

The application is designed for sequential waveform review. Users mark intervals, answer clinical annotation questions, save progress, and finalize waveforms when review is complete.

Downloading and Extracting the Application
------------------------------------------

The application may be distributed as a compressed ``.zip`` file.

Before launching the application, fully extract the zip file.

.. warning::

   Do not run the application directly from inside the zip file.

   On Windows, running from inside the zip can cause the app to open from a temporary ``AppData`` folder. This may prevent required files and folders from loading correctly.

Launching the Application
-------------------------

Windows
~~~~~~~

The Windows version is distributed as a folder-based application so that it opens faster than a single-file executable.

After extracting the zip file, the folder may look similar to this::

   ECGWaveformAnnotationApp-Windows/
   ├── BUILD_INFO.txt
   ├── README_OPEN_ME_FIRST.txt
   └── ECGWaveformAnnotationApp/
       ├── ECGWaveformAnnotationApp.exe
       └── _internal/

To launch on Windows:

1. Right-click the downloaded zip file.
2. Select **Extract All...**.
3. Open the extracted folder.
4. Open the ``ECGWaveformAnnotationApp`` folder.
5. Double-click ``ECGWaveformAnnotationApp.exe``.

.. important::

   Do not move ``ECGWaveformAnnotationApp.exe`` out of its folder.

   The ``_internal`` folder is required. If the executable is copied elsewhere by itself, the app may fail to open or report missing modules.

macOS
~~~~~

After extracting the zip file, double-click ``ECGWaveformAnnotationApp.app``.

If macOS blocks the app with a message such as:

``Apple could not verify “ECGWaveformAnnotationApp” is free of malware...``

try:

1. Right-click or Control-click ``ECGWaveformAnnotationApp.app``.
2. Select **Open**.
3. Confirm **Open** if prompted.

If the app is still blocked, open Terminal and run::

   xattr -dr com.apple.quarantine /path/to/ECGWaveformAnnotationApp.app

Example::

   xattr -dr com.apple.quarantine ~/Downloads/ECGWaveformAnnotationApp-macOS/ECGWaveformAnnotationApp.app

.. note::

   Some macOS builds may not be Apple Developer ID signed or notarized. This can trigger Gatekeeper warnings even when the app was built correctly.

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
           │   └── waveform_file_Event02.mat
           ├── metadata_*.json
           └── waveform_manifest.csv

In the app, select the top-level base folder. For example::

   /nfs/turbo/umms-PI/project/waveforms/

You will likely be provided with the exact base folder path. Keep this path available for future annotation sessions.

Make sure you connect directly to the storage location through your Finder window or File Explorer before loading data in the app.

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
   The patient or deidentified subject folder, often represented by an MRN-like identifier or deidentified UUID.

``Encounter``
   The encounter folder, often represented by a CSN-like identifier or deidentified UUID.

``Waveform record``
   A specific waveform file or recording session for an event of interest available for annotation.

``Annotation session``
   One user's saved annotation file for one waveform record.

``Complete annotation``
   A finalized annotation file saved with ``_COMPLETE`` in the filename.