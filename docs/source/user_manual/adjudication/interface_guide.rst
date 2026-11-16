.. _adjudication-interface-guide:

Interface Guide
===============

Layout
------

The adjudication window contains:

- A scrollable sidebar for reviewer decisions and actions.
- A batch-folder row.
- Overlay and event controls.
- A caliper toolbar.
- Three selectable waveform plots.
- Four synchronized timeline rows.
- A collapsible final interval table.

Drag the horizontal splitter between the waveform and timeline areas to
adjust their relative heights.

Reviewer and Record Controls
---------------------------

``Adjudicator``
   Selects the reviewer whose adjudication files will be loaded or created.

``Waveform Record``
   Selects a discovered waveform record and shows its adjudication status.

``Load Waveform / Compare``
   Loads the selected waveform and generates a fresh comparison from the
   two completed source annotation files.

``Resume Adjudication``
   Restores an existing draft or completed adjudication and its saved
   resolution state.

.. important::

   Selecting another reviewer or record does not automatically replace the
   loaded review.

   Save operations use the reviewer and record associated with the loaded
   session. Load or Resume explicitly to change the session.

Batch Folder Controls
---------------------

``Annotation Batch Folder``
   Accepts the assigned batch path.

``Set Folder``
   Discovers records and refreshes their statuses.

``Browse``
   Opens a folder picker and performs the same discovery operation.

Discovery and status checks may take time over network storage.
They are not repeated during ordinary waveform navigation.

Input Status
------------

The sidebar reports whether Annotator A and Annotator B are loaded.

Their source timelines are read-only.

The application compares configured annotator files rather than arbitrary
files found elsewhere in the batch.

Selected Final Interval
-----------------------

This section displays:

- Final interval number.
- Start and end.
- Duration.
- Source A/B decisions for the selected comparison region.
- Comparison status and reasons.

Start and end values are absolute UTC epoch seconds.
The waveform axis displays relative seconds for easier navigation.

Final Label Controls
--------------------

``Is this CPR?``
   Selects Yes, No, or Unable to Determine for the final interval.

``Rhythm``
   Available when CPR is No.

``Explanation / Comment``
   Allows comments and enforces explanations where required.

``Apply Final Label``
   Applies the sidebar values to the selected final interval in memory.

The Apply button remains disabled when required information is missing.

Applying values does not automatically resolve the comparison region.

Boundary Editing Controls
-------------------------

``Add Boundary``
   Activates click placement within the selected final interval.

``Cancel Add``
   Cancels pending boundary placement without changing the timeline.

``Remove``
   Removes the boundary after the selected interval and merges it with the
   following interval.

Internal final boundaries can also be dragged directly.

Source timeline boundaries cannot be changed.

Review Navigation
-----------------

``Previous``
   Navigates to the previous unresolved comparison region.

``Next``
   Navigates to the next unresolved comparison region.

``Mark Resolved``
   Explicitly confirms that the selected review region has been adjudicated.

``Unresolved count``
   Displays how many review regions remain and, when applicable, the current
   navigation position.

Previous and Next wrap at the ends of the unresolved-region list.
They do not alter labels or resolution state.

Save and Completion Controls
----------------------------

``Save Draft``
   Writes the current final timeline and companion workflow-state JSON.

``Finalize Adjudication``
   Validates the review and writes completed output.

``Reopen for Editing``
   Returns a loaded completed adjudication to an editable session.

The save status appears below these controls.

Hover over a successful save message to view the full output path.

Waveform Rows
-------------

Each displayed waveform row has:

- A signal dropdown.
- Y-IN and Y-OUT.
- Y+ and Y-.
- AUTO-Y.

Changing the displayed signal does not change final annotation boundaries.

The measurement source selected in the caliper toolbar is independent of
the waveform-row dropdowns. For manual peak labeling, at least one displayed
row must show that selected source.

Y-Axis Controls
---------------

``Y-IN``
   Narrows the amplitude range.

``Y-OUT``
   Widens the amplitude range.

``Y+``
   Moves the displayed amplitude range upward.

``Y-``
   Moves the displayed amplitude range downward.

``AUTO-Y``
   Rescales the current visible waveform segment.

In the current adjudication baseline, AUTO-Y is a button-triggered operation.
It is not the same as the annotation window's continuous Auto-Y toggle.

Waveform Overlays
-----------------

The three overlay checkboxes operate independently.

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Overlay
     - Display
   * - Annotator A
     - Upper half of each waveform plot.
   * - Annotator B
     - Lower half of each waveform plot.
   * - Final
     - Full plot height; disabled visually by default until checked.

The upper/lower portions refer to the plot box, not positive or negative
signal amplitude.

Hover over an overlay to inspect its source, label, explanation, and times.

If Final is enabled together with source overlays, shading may overlap.
Disable A/B for a final-only view.

Event Labels
------------

``Hide Event Labels`` and ``Show Event Labels`` change event-text visibility.

Vertical event lines remain visible.

Event metadata come from the selected encounter's manifest.
Events are context only and do not change adjudication boundaries.

Caliper Toolbar
---------------

The toolbar contains:

- Calipers ON/OFF.
- Adjust ON/OFF.
- Source.
- Reset.
- Auto Peaks ON/OFF.
- Manual Label ON/OFF.
- Undo Dot.
- Clear Dots.
- Projection ON/OFF.
- Temporary measurement result.

Caliper Adjust and Manual Label modes temporarily suspend adjudication
click/boundary editing.

Turning these interaction modes off restores ordinary adjudication actions.

See :ref:`adjudication-calipers`.

Timeline Rows
-------------

Annotator A and Annotator B
~~~~~~~~~~~~~~~~~~~~~~~~~~

Display original source intervals.

Their boundaries and labels remain unchanged when final decisions are edited.

Agreement / Review
~~~~~~~~~~~~~~~~~~

Displays comparison status and explicit resolution.

The colors distinguish original agreement from reviewer-resolved
disagreement.

Final Adjudication
~~~~~~~~~~~~~~~~~

Displays the reviewer's editable final timeline.

Select an interval by clicking at its time position.
Drag internal boundary handles to adjust its structure.

All four rows share the waveform X-range.

Final Interval Table
--------------------

Click **Final Interval Table** to expand or collapse the table.

Columns include:

- CPR.
- Rhythm.
- Explanation.
- Start.
- End.

Selecting a row selects the corresponding final interval in the sidebar.

The table is read-only; editing occurs through the sidebar and final timeline.

Completed Read-Only State
-------------------------

After finalization or loading completed output:

- Label editing is disabled.
- Boundary editing is disabled.
- Mark Resolved is disabled.
- Save Draft is disabled.
- Waveform navigation and inspection remain available.
- Reopen for Editing becomes available.

Temporary tools such as overlays and calipers do not modify completed
adjudication data.

Related Pages
-------------

- :ref:`adjudication-review-workflow`
- :ref:`adjudication-comparison-agreement`
- :ref:`adjudication-editing-labels-boundaries`