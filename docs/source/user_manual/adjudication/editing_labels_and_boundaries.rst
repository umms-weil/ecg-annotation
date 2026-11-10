.. _adjudication-editing-labels-boundaries:

Editing Labels and Boundaries
=============================

Overview
--------

All reviewer edits apply to the **Final Adjudication** timeline.

Source annotator files and source timelines remain unchanged.

The reviewer may edit green agreement intervals as well as red or gray
review intervals.

Selecting a Final Interval
-------------------------

Select an interval by:

- Clicking its time position in a timeline, or
- Selecting its row in the expanded **Final Interval Table**.

The sidebar displays its final values and comparison context.

.. important::

   Apply pending sidebar changes before selecting another interval.

   Selecting a different interval replaces the displayed sidebar fields
   with that interval's current values.

Changing CPR and Rhythm
----------------------

1. Select the final interval.
2. Choose its final CPR response.
3. Select a rhythm when CPR is **No**.
4. Enter an explanation or comment.
5. Click **Apply Final Label**.

The Apply button is enabled only when required fields are satisfied.

Question Rules
--------------

.. list-table::
   :header-rows: 1
   :widths: 25 30 45

   * - CPR
     - Rhythm
     - Explanation
   * - Yes
     - Not applicable; stored blank.
     - Optional.
   * - No
     - Required.
     - Required for Other or Unable to Determine; otherwise optional.
   * - Unable to Determine
     - Not applicable; stored blank.
     - Required.

Applying Changes
----------------

**Apply Final Label** commits the sidebar values to the selected interval
in memory.

The final timeline, table, and enabled final overlay update accordingly.

Applying a label:

- Does not save the session.
- Does not automatically resolve a disagreement.
- Marks the session as having unsaved changes.
- Invalidates affected previously resolved review regions.

Use **Save Draft** to preserve applied edits.

Dragging an Internal Boundary
-----------------------------

1. Locate the boundary in the **Final Adjudication** row.
2. Hover over its handle.
3. Click and drag left or right.
4. Release to commit the new position.
5. Check the updated table values.

Moving a boundary changes both neighboring intervals:

- The left interval ends at the new position.
- The right interval starts at the same position.

This keeps the final timeline contiguous.

The outer waveform start and end are fixed and cannot be dragged.

Pending sidebar label changes must be applied before dragging a boundary.

Boundary Movement Limits
------------------------

Dragging prevents either neighboring interval from collapsing.

For ordinary intervals, the configured minimum duration limits how far
the boundary can move.

An existing short comparison fragment may remain short during drafting.
It must be adjusted or merged before finalization if it is below the
one-second final minimum.

Adding a Boundary
-----------------

Use Add Boundary to split the selected final interval.

1. Select the interval to split.
2. Apply any pending label changes.
3. Click **Add Boundary**.
4. Click within that interval on a waveform or the final timeline.
5. Review the resulting two intervals.
6. Change either interval's final label if needed.

The new intervals initially inherit the previous final label and comment.

Placement must leave at least one second on both sides.

You do not need to enter a numeric timestamp.
The clicked location is converted to absolute waveform time internally.

Cancelling Placement
~~~~~~~~~~~~~~~~~~~~

While placement is active, the button displays **Cancel Add**.

Click it to leave the timeline unchanged.

While placement is active:

- The selected split target is retained.
- Other timeline clicks do not change that target.
- Existing boundary handles are temporarily unavailable for dragging.

Removing a Boundary
--------------------

Remove merges the selected interval with its following interval.

1. Select the interval immediately before the boundary.
2. Apply pending label changes.
3. Click **Remove**.
4. Review the merged interval.

The last interval has no following interval, so its final endpoint cannot
be removed.

Matching Labels and Comments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If both intervals have identical CPR, rhythm, and explanation values, the
merged interval retains those values.

Different Labels or Comments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If the values differ, the application asks for confirmation.

Confirming the merge:

- Removes the shared boundary.
- Creates one continuous final interval.
- Clears its CPR, rhythm, and explanation.
- Requires the reviewer to assign a new final label.

Neither neighboring decision is silently preferred.

Effects on Resolution
---------------------

An edit affecting a resolved review region returns that region to
unresolved.

This applies to:

- Changed final labels or comments.
- Boundary movement.
- Splitting.
- Merging.

After finishing the change, inspect the affected region and explicitly
click **Mark Resolved** again.

Caliper Interaction
-------------------

Final boundary editing is suspended while caliper **Adjust** or
**Manual Label** is active.

Turn those modes off before:

- Adding a final boundary.
- Removing a final boundary.
- Dragging final boundaries.
- Selecting final intervals through plot clicks.

Caliper lines and peak dots are not final annotation boundaries.

Saving Structural Changes
--------------------------

Boundary changes are retained in memory until **Save Draft** succeeds.

Save before closing, loading another record, or leaving the workstation.

A successful resume restores edited boundaries and final labels.

Related Pages
-------------

- :ref:`adjudication-resolving-disagreements`
- :ref:`adjudication-saving-resuming`
- :ref:`adjudication-completion-reopening`