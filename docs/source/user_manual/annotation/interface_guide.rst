.. _interface-guide:

Interface Guide
===============

Sidebar
-------

The sidebar contains the primary annotation controls:

- User Name dropdown.
- Subject or waveform record dropdown.
- **Load Subject** button.
- **Load Annotations** button.
- CPR question.
- Rhythm label dropdown.
- Explanation text box.
- **Mark** button.
- **Finalize Waveform** button.
- Warning and status messages.
- **Remove Last Mark** button.
- **Save All Annotations** button.

CPR and Rhythm Logic
--------------------

Your CPR answer determines which rhythm fields are enabled.

.. list-table::
   :header-rows: 1
   :widths: 25 25 30

   * - CPR Answer
     - Rhythm Dropdown
     - Explanation Required
   * - Yes
     - Disabled
     - No
   * - No
     - Enabled
     - Only if rhythm is ``Unable to Determine`` or ``Other``
   * - Unable to Determine
     - Disabled
     - Yes

Explanation Field
-----------------

The explanation field is required when:

- CPR is ``Unable to Determine``.
- CPR is ``No`` and rhythm is ``Unable to Determine``.
- CPR is ``No`` and rhythm is ``Other``.

The **Mark** button remains disabled until required explanations are entered.

Mark Button
-----------

The **Mark** button is enabled only when:

- A valid interval endpoint has been selected.
- The interval is at least 1 second long.
- A user name is selected.
- CPR question is answered.
- Rhythm label is selected when required.
- Explanation text is entered when required.
- The waveform has not already been finalized.

Remove Last Mark
----------------

Use **Remove Last Mark** to undo the most recent annotation interval.

.. caution::

   Only the most recent annotation can be removed at a time. Earlier annotations cannot be edited or deleted through the app.

Finalize Waveform Button
------------------------

The **Finalize Waveform** button becomes available after the latest annotation reaches the end of the waveform.

Use this button to confirm final waveform completion and save the annotation as complete.

Waveform Plots
--------------

The main panel displays waveform plots.

Features include:

- Synchronized x-axis navigation.
- Collapsible waveform sections.
- Y-axis zoom controls.
- Y-axis shift controls.
- Auto-Y scaling controls.
- Event markers.
- Annotation overlays.

Y-Axis Controls
---------------

Each waveform plot has Y-axis controls:

``Y-IN``
   Zoom in vertically on y-axis.

``Y-OUT``
   Zoom out vertically on y-axis.

``Y+``
   Shift waveform display upward on y-axis.

``Y-``
   Shift waveform display downward on y-axis.

``AUTO ON``
   Automatically rescales the Y-axis when the visible time window changes. Will pause if x-axis is too large.

``OFF``
   Manual Y-axis mode.

``PAUSED``
   Auto-Y is temporarily paused because the visible time window is too large.

Event Markers
-------------

Vertical dashed lines represent clinical or recording events.

.. list-table::
   :header-rows: 1
   :widths: 20 60

   * - Color
     - Meaning
   * - Green
     - Clinical events from flowsheet/event data
   * - Red
     - Code start and code end markers, when available
   * - Purple/Yellow
     - Recording start and recording end markers

.. note::

   Not all waveform records will have event markers. Some may have many, and others may have none.

Annotation Table
----------------

The annotation table lists saved intervals.

Common columns include:

- User.
- Subject.
- CPR response.
- Rhythm label.
- Explanation.
- Start time.
- End time.

.. tip::

   Table times will be stored as epoch seconds. The plot x-axis will display time relative to the start of the recording for easier navigation.

Colored Overlays
----------------

After an interval is marked, a colored overlay appears on the waveform.

The overlay provides visual feedback for the annotated interval and rhythm category.