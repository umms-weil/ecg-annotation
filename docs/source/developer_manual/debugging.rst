.. _developer-debugging:

Debugging Guide
===============

Overview
--------

This page lists common developer debugging scenarios and values to inspect.

No Waveform Records Found
-------------------------

Check:

- selected base folder,
- actual folder tree,
- whether files are inside nested encounter/namespace folders,
- whether ``list_subjects()`` scans the relevant extension,
- whether CSV files are being incorrectly ignored,
- whether files are inside an ignored ``output`` folder.

Useful debug print:

.. code-block:: python

   print("base_folder:", base_folder)
   print("records:", list_subjects(base_folder))

For recursive CSV layouts, confirm that CSV waveform files are detected and non-waveform CSV files are skipped.

Waveform Record Appears but Loads Empty
---------------------------------------

Check:

- selected record dictionary,
- waveform file path,
- manifest path,
- code start and stop times,
- waveform file start and stop times,
- whether the requested window overlaps the file,
- lead names and aliases.

Useful debug prints:

.. code-block:: python

   print("Selected record:", record)
   print("manifest_path:", record.get("manifest_path"))
   print("csv_path:", record.get("csv_path"))
   print("h5_path:", record.get("h5_path"))
   print("code_start_sec:", code_start_sec)
   print("code_stop_sec:", code_stop_sec)

Inside a loader:

.. code-block:: python

   print("file_start:", file_start)
   print("file_stop:", file_stop)
   print("window_start:", window_start)
   print("window_stop:", window_stop)
   print("i0:", i0)
   print("i1:", i1)

Manifest Errors
---------------

Check:

- whether ``waveform_manifest.csv`` exists,
- whether the record has ``manifest_path``,
- whether the manifest has ``UUID``,
- whether the manifest is subject-specific,
- whether expected columns are present.

Expected columns may include:

- ``UUID``
- ``signal_start``
- ``signal_end``
- ``CODE_START``
- ``CODE_END``
- ``RECORDED_TIME``
- ``FLO_MEAS_NAME``
- ``FLOWSHEET_VALUE``

If a subject-specific manifest lacks ``UUID``, processing should treat it as already filtered.

Timezone or Window Mismatch
---------------------------

Symptoms:

- waveform file loads empty,
- code window is outside file bounds,
- event markers appear shifted,
- recording bounds do not align.

Compare:

- raw manifest timestamps,
- converted epoch seconds,
- waveform ``time_axis`` start/end,
- ``code_start_sec`` and ``code_stop_sec``.

Useful debug prints:

.. code-block:: python

   print("Recording start Sec:", recording_start_sec)
   print("Recording end Sec:", recording_end_sec)
   print("Code start Sec:", code_start_sec)
   print("Code stop Sec:", code_stop_sec)
   print("Waveform start:", time_axis[0])
   print("Waveform end:", time_axis[-1])

Signal Alias Problems
---------------------

Symptoms:

- plots show no data for expected leads,
- only some leads load,
- chest impedance missing.

Check:

- CSV column names or H5 signal IDs,
- ``SIGNAL_ALIASES``,
- normalized lookup keys,
- requested waveform names.

Useful debug print:

.. code-block:: python

   print("desired_waveforms:", desired_waveforms)
   print("signal_lookup:", signal_lookup)

UI State Bugs
-------------

For Mark button or sidebar issues, inspect:

- ``get_cpr_val()``,
- ``rhythm_dropdown.currentText()``,
- ``rhythm_dropdown.isEnabled()``,
- ``rhythm_explanation.isEnabled()``,
- ``current_marker``,
- ``last_mark``,
- ``waveform_complete``,
- warnings generated inside ``update_sidebar_ui()``.

Useful debug print:

.. code-block:: python

   print("cpr:", self.get_cpr_val())
   print("rhythm:", self.rhythm_dropdown.currentText())
   print("rhythm enabled:", self.rhythm_dropdown.isEnabled())
   print("explanation enabled:", self.rhythm_explanation.isEnabled())
   print("marker:", self.current_marker)
   print("last_mark:", self.last_mark)
   print("waveform_complete:", self.waveform_complete)

Save and Load Bugs
------------------

Check:

- selected username,
- selected subject record,
- output folder,
- partial filename,
- complete filename,
- whether both partial and complete files exist,
- whether load precedence is correct.

Useful debug print:

.. code-block:: python

   print("user:", self.get_user_name())
   print("subject:", self.get_selected_subject_name())
   print("record:", self.get_selected_subject_record())
   print("output_folder:", self.get_annotation_output_folder())
   print("filenames:", self.get_annotation_filenames())

Sphinx Autodoc Import Errors
----------------------------

Check:

- ``docs/conf.py`` source path,
- missing dependencies,
- module names,
- whether PyQt imports work in the docs build environment.

Try:

.. code-block:: bash

   python -c "import new_app"
   python -c "import new_callbacks"
   python -c "import processing"

If imports fail during docs build, adjust ``sys.path`` in ``conf.py`` or mock heavy GUI dependencies.