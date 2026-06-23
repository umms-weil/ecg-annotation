.. _developer-annotation-lifecycle:

Annotation Lifecycle
====================

Overview
--------

The annotation lifecycle is managed primarily in ``new_callbacks.py``.

Annotations are stored in memory as a list of dictionaries:

.. code-block:: python

   self.annotations = []

Each dictionary represents one interval.

Annotation State Variables
--------------------------

``last_mark``
   Start time for the next interval.

``current_marker``
   Pending endpoint selected by a plot click.

``annotations``
   List of confirmed annotation dictionaries.

``waveform_complete``
   Indicates whether the waveform has been finalized.

``terminal_event_status``
   Final completion status selected during finalization.

``terminal_event_comment``
   Optional final completion comment.

Plot Click Flow
---------------

Plot clicks are handled by:

.. code-block:: python

   make_plot_click_handler(lead_idx)

Click behavior:

1. Ignore non-left-click events.
2. If the waveform is complete, prevent marking.
3. Convert scene position to waveform time.
4. Snap to waveform end if needed.
5. If no ``last_mark`` exists, initialize it.
6. If the click is after ``last_mark``, set ``current_marker``.
7. Update sidebar validation and waveform overlays.

Mark Flow
---------

Marking is handled by:

.. code-block:: python

   handle_mark_clicked()

The method:

1. Verifies waveform is not already complete.
2. Verifies ``current_marker`` and ``last_mark`` define a valid interval.
3. Builds an annotation dictionary.
4. Appends it to ``self.annotations``.
5. Updates ``last_mark`` to the interval end.
6. Clears ``current_marker``.
7. Resets sidebar inputs.
8. Updates plot overlays.
9. Updates the annotation table.
10. Enables finalization if the waveform end was reached.

Annotation Dictionary
---------------------

Common annotation fields include:

``user``
   User name or uniqname.

``subject``
   Subject identifier.

``encounter``
   Encounter identifier.

``namespace``
   Waveform namespace.

``file_tag``
   Source waveform file tag.

``source_path``
   Source waveform file path.

``cpr``
   CPR response.

``rhythm_label``
   Rhythm label, when applicable.

``rhythm_expl``
   Rhythm or signal explanation.

``start``
   Interval start time.

``end``
   Interval end time.

``waveform_complete``
   Completion flag for final row.

``terminal_event_status``
   Final completion status.

``terminal_event_comment``
   Final completion comment.

Sidebar Validation
------------------

Sidebar validation is handled by:

.. code-block:: python

   update_sidebar_ui()

This method controls:

- CPR button availability.
- Rhythm dropdown availability.
- Explanation field availability.
- Mark button state.
- Finalize button state.
- Warning messages.
- Remove Last Mark button state.

Validation requirements include:

- user name selected.
- CPR answer selected.
- valid marker interval.
- rhythm selected when CPR is ``No``.
- explanation entered when required.
- interval length at least 1 second.

CPR and Rhythm Logic
--------------------

Expected logic:

.. list-table::
   :header-rows: 1
   :widths: 25 25 30

   * - CPR Answer
     - Rhythm Dropdown
     - Explanation Required
   * - ``Yes``
     - Disabled
     - No
   * - ``No``
     - Enabled
     - If rhythm is ``Unable to Determine`` or ``Other``
   * - ``Unable to Determine``
     - Disabled
     - Yes

Undo Flow
---------

Undo is handled by:

.. code-block:: python

   handle_remove_last_mark()

The method:

1. Removes the last annotation from ``self.annotations``.
2. Clears waveform completion state.
3. Resets terminal completion fields.
4. Sets ``last_mark`` to the previous annotation end, if one exists.
5. Clears ``current_marker``.
6. Updates the table.
7. Updates waveform overlays.
8. Updates sidebar state.
9. Saves remaining annotations or deletes annotation files if none remain.

Finalize Button Logic
---------------------

The finalization button state is controlled by:

.. code-block:: python

   update_finalize_button_state()

The button should be enabled only when:

- at least one annotation exists,
- the last annotation reaches the waveform end,
- ``waveform_complete`` is ``False``.

Finalization Flow
-----------------

Finalization is handled by:

.. code-block:: python

   handle_finalize_waveform_clicked()

The method:

1. Confirms the last annotation reaches the waveform end.
2. Opens the final completion dialog.
3. Stores terminal completion status and comment.
4. Sets ``waveform_complete`` to ``True``.
5. Applies completion metadata to the final annotation row.
6. Updates the table and waveform overlays.
7. Saves immediately using complete filename logic.
8. Disables further marking.

Terminal Completion Metadata
----------------------------

Completion metadata is applied by:

.. code-block:: python

   apply_terminal_completion_to_annotations(status, comment)

Expected behavior:

- earlier annotations have completion fields cleared,
- final annotation has ``waveform_complete`` set to ``True``,
- final annotation stores ``terminal_event_status``,
- final annotation stores ``terminal_event_comment``.

Clearing Completion State
-------------------------

Completion state is cleared by:

.. code-block:: python

   clear_terminal_completion_fields()

This is used when undoing after completion.

Expected behavior:

- ``waveform_complete`` becomes ``False``.
- ``terminal_event_status`` is cleared.
- ``terminal_event_comment`` is cleared.
- all annotations have completion fields reset.

Save and Load Behavior
----------------------

Partial files use:

.. code-block:: text

   annotations_{subject}_{file_tag}_{user}.csv

Complete files use:

.. code-block:: text

   annotations_{subject}_{file_tag}_{user}_COMPLETE.csv

If no file tag exists, fallback names may omit ``file_tag``.

Complete-file behavior:

- saving complete annotations writes the ``_COMPLETE`` file,
- redundant partial files are removed,
- loading prefers the complete file if present.

Partial-file behavior:

- saving partial annotations writes the non-complete file,
- redundant complete files are removed when reverting to partial.

Regression Checks
-----------------

Important behaviors to test after annotation workflow changes:

- CPR ``No`` plus rhythm ``Unable to Determine`` enables explanation.
- CPR ``No`` plus rhythm ``Other`` enables explanation.
- Final interval does not automatically finalize.
- Finalize button enables after waveform end is reached.
- Finalization dialog is required for completion.
- Completed waveform disables further marking.
- Removing last mark after completion re-enables marking.
- Undo after completion reverts save state to partial.
- Loading a complete file restores completion state.
- Loading a partial file allows continued marking.