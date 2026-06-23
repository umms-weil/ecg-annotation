.. _developer-architecture:

Architecture
============

Overview
--------

The ECG Waveform Annotation App is a PyQt5 desktop application for loading physiological waveform data, displaying synchronized waveform plots, and collecting interval-based annotations.

The application is organized around three primary modules:

``new_app.py``
   Defines the main PyQt5 user interface, window layout, widgets, plot containers, and signal wiring.

``new_callbacks.py``
   Defines application behavior, callback methods, annotation workflow logic, plotting updates, save/load behavior, finalization, autosave, and UI state transitions.

``processing.py``
   Defines waveform discovery, waveform loading, manifest parsing, time conversion, event loading, signal alias handling, and data utility functions.

Main Application Class
----------------------

The main application class uses multiple inheritance:

.. code-block:: python

   class MainApp(QMainWindow, AnnotationAppCallbacks):
       ...

``QMainWindow``
   Provides the PyQt5 main window behavior.

``AnnotationAppCallbacks``
   Provides callback methods and application logic used by the UI.

High-Level Flow
---------------

The typical user workflow maps to the following internal flow::

   User selects base folder
       -> set_base_folder()
       -> processing.list_subjects()
       -> update_subject_dropdown()

   User loads waveform record
       -> load_subject_data()
       -> processing.get_code_time_bounds()
       -> processing.load_waveforms_for_subject()
       -> plot_all_leads()
       -> plot_event_markers()

   User clicks waveform
       -> make_plot_click_handler()
       -> current_marker is set
       -> update_sidebar_ui()
       -> update_waveform_and_mark()

   User clicks Mark
       -> handle_mark_clicked()
       -> annotation dict appended to self.annotations
       -> table updated
       -> plot overlays updated
       -> autosave/manual save available

   User reaches waveform end
       -> update_finalize_button_state()
       -> Finalize Waveform button enabled

   User finalizes waveform
       -> handle_finalize_waveform_clicked()
       -> terminal completion metadata saved
       -> complete annotation file written

UI Layer
--------

The UI layer is responsible for:

- Creating widgets.
- Laying out the sidebar and waveform plots.
- Creating collapsible waveform sections.
- Creating PyQtGraph plot widgets.
- Connecting widget signals to callback methods.
- Maintaining visible UI controls.

Most UI construction occurs in ``MainApp.__init__()``.

Callback Layer
--------------

The callback layer is responsible for:

- Folder selection behavior.
- Subject/waveform record loading.
- Annotation workflow validation.
- Plot click handling.
- Marking intervals.
- Removing the last mark.
- Saving and autosaving annotations.
- Loading existing annotations.
- Finalizing waveforms.
- Updating UI enable/disable state.
- Drawing annotation overlays and event markers.
- Auto-Y scaling behavior.

Processing Layer
----------------

The processing layer is responsible for:

- Discovering supported waveform records.
- Reading waveform files.
- Normalizing signal names.
- Resolving aliases.
- Loading H5, CSV, and MAT waveform data.
- Normalizing epoch timestamps.
- Reading manifest files.
- Determining code and recording time bounds.
- Loading event rows for display.

Shared State
------------

The app uses shared instance attributes across the UI and callback layers.

Important state variables include:

``base_folder``
   Path to the selected base data folder.

``current_subject_record``
   Record dictionary for the selected waveform record.

``current_subject``
   Current subject identifier.

``current_encounter``
   Current encounter identifier.

``current_namespace``
   Current waveform namespace.

``current_file_tag``
   File tag for the selected waveform file.

``current_manifest_path``
   Path to the waveform manifest used for the selected record.

``data_store``
   Dictionary containing loaded waveform data and metadata.

``time_axis``
   Loaded waveform time vector.

``leads_ds``
   Loaded and downsampled lead arrays.

``lead_names``
   Display names for loaded leads.

``manifest_events``
   DataFrame of clinical events loaded from the waveform manifest.

``recording_start_sec``
   Recording start time in epoch seconds.

``recording_end_sec``
   Recording end time in epoch seconds.

``code_start_sec``
   Code/event window start time in epoch seconds.

``code_stop_sec``
   Code/event window end time in epoch seconds.

``annotations``
   List of annotation dictionaries.

``last_mark``
   Start time for the next annotation interval.

``current_marker``
   Pending endpoint selected by the user.

``waveform_complete``
   Boolean indicating whether the current waveform record has been finalized.

``terminal_event_status``
   Final completion status selected during waveform finalization.

``terminal_event_comment``
   Optional final completion comment.

Signal and Slot Overview
------------------------

Key UI signal connections include:

.. list-table::
   :header-rows: 1
   :widths: 30 25 45

   * - Widget
     - Signal
     - Callback
   * - ``set_folder_btn``
     - ``clicked``
     - ``set_base_folder``
   * - ``browse_folder_btn``
     - ``clicked``
     - ``browse_base_folder``
   * - ``toggle_event_labels_btn``
     - ``clicked``
     - ``toggle_event_labels_visibility``
   * - ``load_subject_btn``
     - ``clicked``
     - ``load_subject_data``
   * - ``load_annotation_btn``
     - ``clicked``
     - ``handle_load_annotation``
   * - ``save_all_btn``
     - ``clicked``
     - ``save_all_to_file``
   * - ``mark_btn``
     - ``clicked``
     - ``handle_mark_clicked``
   * - ``finalize_waveform_btn``
     - ``clicked``
     - ``handle_finalize_waveform_clicked``
   * - ``remove_last_btn``
     - ``clicked``
     - ``handle_remove_last_mark``
   * - ``cpr_yes``, ``cpr_no``, ``cpr_U2D``
     - ``toggled``
     - ``update_sidebar_ui``
   * - ``rhythm_dropdown``
     - ``currentTextChanged``
     - ``update_sidebar_ui``
   * - ``rhythm_explanation``
     - ``textChanged``
     - ``update_sidebar_ui``
   * - ``username_input``
     - ``currentTextChanged``
     - ``update_sidebar_ui``