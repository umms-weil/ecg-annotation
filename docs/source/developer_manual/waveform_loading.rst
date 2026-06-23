.. _developer-waveform-loading:

Waveform Loading
================

Overview
--------

Waveform loading is handled by ``processing.py``.

The main public loader is:

.. code-block:: python

   load_waveforms_for_subject(
       base_folder,
       subject,
       recording_start_sec=None,
       code_start_sec=None,
       code_stop_sec=None,
       desired_waveforms=WAVEFORM_PLOT_ORDER,
   )

This function dispatches to source-specific loaders based on the selected record type.

Subject Discovery
-----------------

Waveform records are discovered with:

.. code-block:: python

   list_subjects(base_folder)

This function recursively scans the base folder and returns record dictionaries for supported waveform files.

Supported record types:

``h5``
   H5 waveform bundle.

``csv``
   CSV waveform bundle.

``mat``
   Legacy MAT waveform source.

Signal Order
------------

The default waveform display order is defined by ``WAVEFORM_PLOT_ORDER``.

Current order:

.. code-block:: python

   WAVEFORM_PLOT_ORDER = [
       "I",
       "II",
       "III",
       "V",
       "AVF",
       "AVL",
       "CHEST_IMPEDANCE",
   ]

Signal Alias Resolution
-----------------------

Signal names are normalized before matching.

The helper:

.. code-block:: python

   normalize_signal_key(value)

removes non-alphanumeric characters and uppercases the value.

Aliases are defined in ``SIGNAL_ALIASES``.

Example aliases:

- ``I``
- ``LEAD I``
- ``ECG I``
- ``GE ECG I``
- ``GE_ECG_I``

H5 Loading
----------

H5 bundle loading is handled by:

.. code-block:: python

   load_waveforms_from_h5(...)

Expected H5 structure::

   /time_epoch_s
   /signals/<signal_id>/values

Important constants:

``H5_TIME_DATASET``
   Name of the H5 time dataset. Current value: ``time_epoch_s``.

``H5_SIGNALS_GROUP``
   Name of the signal group. Current value: ``signals``.

The H5 loader:

1. Reads and normalizes epoch timestamps.
2. Sorts data if the time vector is not sorted.
3. Clips the waveform to the requested code window.
4. Estimates sampling frequency.
5. Downsamples to the desired frequency.
6. Resolves desired lead names against available signal IDs.
7. Returns loaded lead arrays and metadata.

CSV Loading
-----------

CSV loading is handled by:

.. code-block:: python

   load_waveforms_from_csv(...)

Expected CSV structure::

   time,I,II,III,V,AVF,AVL,...

If no ``time`` column exists, the numeric index is used.

The CSV loader:

1. Reads the CSV into a DataFrame.
2. Extracts the time axis.
3. Normalizes epoch timestamps.
4. Sorts rows if the time vector is not sorted.
5. Clips to the requested code window.
6. Estimates sampling frequency.
7. Downsamples to the desired frequency.
8. Resolves signal columns.
9. Returns loaded lead arrays and metadata.

MAT Loading
-----------

MAT loading is handled by:

.. code-block:: python

   load_waveforms_from_mat_subject(...)

This supports older per-lead MAT layouts.

The MAT loader:

1. Finds MAT files for requested leads.
2. Loads data using HDF5-compatible MAT handling.
3. Builds time arrays from sampling frequency and start time.
4. Intersects available lead ranges with requested code bounds.
5. Downsamples signals.
6. Returns lead arrays and metadata.

Time Normalization
------------------

The helper:

.. code-block:: python

   normalize_epoch_seconds(time_values)

detects epoch milliseconds and converts them to epoch seconds.

Detection logic:

- epoch seconds are usually around ``1.7e9``.
- epoch milliseconds are usually around ``1.7e12``.

Downsampling
------------

The default desired display sampling frequency is:

.. code-block:: python

   DESIRED_FS_DEFAULT = 120.0

The loader estimates the source sampling rate from the time vector and computes a downsample factor.

Empty Waveform Result
---------------------

If no valid waveform data is available, the loader returns:

.. code-block:: python

   _empty_waveform_result(desired_waveforms)

This returns:

- empty ``times_ds``.
- empty arrays for requested leads.
- requested lead names.
- blank units.
- ``Fs`` set to ``None``.

Common causes:

- No supported waveform files found.
- Requested code window does not overlap waveform file bounds.
- Missing signal columns.
- Unrecognized signal names.
- Empty waveform file.
- Incorrect timestamp conversion.

Manifest and Event Handling
---------------------------

Manifest parsing is handled by:

.. code-block:: python

   get_code_time_bounds(...)
   get_events_for_window(...)

The manifest is used for:

- recording start and end markers.
- code start and end markers.
- event markers.
- waveform clipping window.

Subject-specific manifests may not include a ``UUID`` column (rare case possible). In that case, the manifest should be treated as already subject-specific.

Debugging Empty Loads
---------------------

When waveform loading returns empty data, inspect:

- selected record dictionary.
- ``manifest_path``.
- waveform source path.
- ``time_axis[0]`` and ``time_axis[-1]``.
- ``code_start_sec`` and ``code_stop_sec``.
- source file start and stop timestamps.
- signal lookup keys.
- requested waveform names.
- lengths of returned lead arrays.

Useful debug prints inside loaders include:

.. code-block:: python

   print("file_start:", file_start)
   print("file_stop:", file_stop)
   print("window_start:", window_start)
   print("window_stop:", window_stop)
   print("desired_waveforms:", desired_waveforms)
   print("signal_lookup:", signal_lookup)