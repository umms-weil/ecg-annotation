.. _developer-data-layout:

Data Layout
===========

Overview
--------

The app discovers waveform records from a base data folder.

The currently supported structure is recursive and may include one or more subjects, encounters, namespaces, and waveform files.

Example Folder Tree
-------------------

Example::

   base_data_folder/
   └── MRNNumberPlaceholder/
       └── CSNNumberPlaceholder/
           ├── GEWAVE/
           │   ├── 20240415T135229050Z__20240413T092000_20240417T095000.h5
           │   ├── 20240417T040004912Z__20240413T092000_20240417T095000.h5
           ├── metadata_20240413T092000_20240417T095000.json
           └── waveform_manifest.csv

Expected Components
-------------------

``base_data_folder``
   Top-level folder selected by the user.

``MRNNumberPlaceholder``
   Subject folder.

``CSNNumberPlaceholder``
   Encounter folder.

``GEWAVE`` or ``GEVITAL``
   Namespace folder containing waveform files. GEWAVE is high-frequency recordings, GEVITAL is lower-frequency recordings.

``waveform_manifest.csv``
   Encounter-level manifest file used for recording bounds, code bounds, and event markers.

``metadata_*.json``
   Encounter metadata file.

``*.csv``
   CSV waveform bundle files when they contain signal columns.

``*.h5``
   H5 waveform bundle files when available.

``*.mat``
   MAT waveform files for backward compatibility.

``output``
   Annotation output folder created by the app.

Supported Waveform Sources
--------------------------

The processing layer supports:

- H5 bundle records.
- CSV waveform bundle records.
- MAT waveform files for legacy fallback.

Unsupported or Ignored Files
----------------------------

The app should ignore non-waveform files or non-manifest files.

Discovered Record Dictionary
----------------------------

``processing.list_subjects()`` returns a list of dictionaries.

Common keys include:

``name``
   Display label for the dropdown.

``subject``
   Subject folder identifier.

``encounter``
   Encounter identifier.

``namespace``
   Waveform namespace, such as ``GEWAVE`` or ``GEVITAL``.

``window_tag``
   Optional window tag from metadata or H5 attributes.

``file_tag``
   File stem or waveform file identifier.

``kind``
   Source type, such as ``h5``, ``csv``, or ``mat``.

``h5_path``
   Path to an H5 waveform file, when applicable.

``csv_path``
   Path to a CSV waveform file, when applicable.

``subject_path``
   Path to the subject folder.

``encounter_path``
   Path to the encounter folder.

``namespace_path``
   Path to the waveform namespace folder.

``manifest_path``
   Path to the nearest applicable ``waveform_manifest.csv``.

``output_path``
   Output folder for annotations associated with this waveform record.

``n_annotations``
   Total annotation files found for the record.

``n_complete_annotations``
   Completed annotation files found for the record.

``has_annotations``
   Boolean indicating whether annotation files were found.

Output Folder Structure
-----------------------

Annotation files are saved per waveform record and per user.

Example::

   GEWAVE/
   ├── waveform_file.csv
   └── output/
       └── waveform_file/
           └── uniqname/
               ├── annotations_subject_filetag_uniqname1.csv
               └── annotations_subject_filetag_uniqname2_COMPLETE.csv

Manifest Discovery
------------------

For waveform files stored inside a namespace folder, the app should search upward for the nearest manifest.

Example::

   base/MRN/CSN/GEWAVE/waveform_file.csv

Expected manifest::

   base/MRN/CSN/waveform_manifest.csv

If no subject-specific manifest is found, older fallback behavior may check for a base-level manifest.