.. _developer-ui-callbacks:

UI and Callback Reference
=========================

Overview
--------

The UI is defined in ``new_app.py`` and the application behavior is defined in ``new_callbacks.py``.

The UI creates widgets and connects their signals to callback methods.

Important UI Components
-----------------------

Sidebar widgets include:

- ``username_input``
- ``subject_dropdown``
- ``load_subject_btn``
- ``load_annotation_btn``
- ``cpr_yes``
- ``cpr_no``
- ``cpr_U2D``
- ``rhythm_dropdown``
- ``rhythm_explanation``
- ``mark_btn``
- ``finalize_waveform_btn``
- ``mark_warning``
- ``remove_last_btn``
- ``save_all_btn``

Main panel widgets include:

- ``folder_input``
- ``browse_folder_btn``
- ``set_folder_btn``
- ``toggle_event_labels_btn``
- ``waveform_plots``
- ``waveform_sections``
- ``ann_table``

Signal Map
----------

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
   * - ``cpr_yes``
     - ``toggled``
     - ``update_sidebar_ui``
   * - ``cpr_no``
     - ``toggled``
     - ``update_sidebar_ui``
   * - ``cpr_U2D``
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

Plot Click Handlers
-------------------

Each waveform plot connects scene clicks to:

.. code-block:: python

   make_plot_click_handler(i)

This creates a closure for each lead index.

The handler converts mouse scene coordinates into waveform time using the plot's ``ViewBox``.

Collapsible Waveform Sections
-----------------------------

Waveforms are wrapped in ``CollapsibleWaveformSection``.

This widget:

- displays a compact toggle button,
- shows or hides the waveform content,
- emits ``toggled`` when expanded/collapsed,
- updates plot axis visibility and layout sizing.

When a waveform section is toggled, the app calls:

.. code-block:: python

   handle_waveform_section_toggled()

This updates:

- visible x-axis placement,
- layout stretches,
- plot geometry.

Auto-Y Controls
---------------

Each plot has an Auto-Y button.

Relevant methods:

``toggle_auto_y_for_plot(plot_idx)``
   Toggles Auto-Y on or off for one plot.

``disable_auto_y_for_plot(plot_idx)``
   Disables Auto-Y after manual Y-axis changes.

``autoscale_visible_y_all()``
   Autoscale all enabled plots using the visible X window.

``autoscale_visible_y_for_plot(plot_idx)``
   Autoscale one plot.

``schedule_visible_y_autoscale()``
   Debounces Auto-Y after X-axis range changes.

Event Label Visibility
----------------------

Event marker labels are toggled by:

.. code-block:: python

   toggle_event_labels_visibility()

This calls:

.. code-block:: python

   set_event_labels_visible(visible)

Only event marker ``TextItem`` objects are shown or hidden. Event marker lines remain visible.

Common UI Maintenance Notes
---------------------------

When adding a new sidebar field:

1. Create the widget in ``new_app.py``.
2. Add it to the appropriate layout.
3. Connect relevant signals to ``update_sidebar_ui()`` or another callback.
4. Update validation logic.
5. Update ``handle_mark_clicked()`` to save the field.
6. Update ``update_table_data()`` if the field should be shown.
7. Update save/load compatibility if needed.
8. Update user and developer documentation.

When adding a new annotation field:

1. Add the key to the annotation dictionary.
2. Add default handling when loading old CSV files.
3. Add the field to the annotation table if user-facing.
4. Add migration or fallback behavior if older files lack the field.