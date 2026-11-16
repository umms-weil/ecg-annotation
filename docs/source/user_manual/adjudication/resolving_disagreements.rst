.. _adjudication-resolving-disagreements:

Resolving Disagreements
=======================

Purpose
-------

Explicit resolution records that the adjudicator has finished reviewing
a comparison region.

Changing a label or moving a boundary is not sufficient to mark review
complete.

.. important::

   Only **Mark Resolved** resolves a red or gray review region.

   This prevents exploratory or intermediate edits from being treated as
   a completed adjudication decision.

Navigating Unresolved Regions
------------------------------

Use the sidebar controls:

``Next``
   Moves to the next unresolved region.

``Previous``
   Moves to the previous unresolved region.

The controls wrap at the beginning and end of the list.

Navigation:

- Moves the waveform view to the region with surrounding context.
- Highlights the selected time range.
- Displays Annotator A and B's decisions.
- Displays comparison reasons.
- Selects a final interval within the region.

Navigation does not modify labels or resolution state.

Reviewing a Region
------------------

For each unresolved region:

1. Inspect the source A/B decisions.
2. Inspect the relevant waveform leads.
3. Consider event markers as available context.
4. Adjust final boundaries when needed.
5. Assign valid final labels.
6. Apply pending sidebar changes.
7. Confirm all final intervals covering the region are satisfactory.
8. Click **Mark Resolved**.

Calipers may be used for temporary measurements.
Turn their interactive modes off before continuing adjudication editing.

Multiple Final Intervals
------------------------

A review region may overlap multiple final intervals after boundary edits.

Resolving that region requires valid labels throughout its entire range.

The application checks for:

- Complete final coverage.
- No gaps in the reviewed range.
- No overlapping final intervals.
- Required CPR responses.
- Required rhythm labels.
- Required explanations.

Editing only one overlapping final interval may not satisfy the whole
review region.

When Mark Resolved Is Rejected
-----------------------------

Possible causes include:

- No unresolved region is selected.
- Sidebar changes have not been applied.
- One or more final labels are missing.
- A required explanation is missing.
- Final coverage has a gap.
- Final coverage overlaps.

Read the displayed error, correct the final timeline, and try again.

Resolved Appearance
-------------------

An explicitly resolved region changes to the resolved color, normally blue.

This is intentionally distinct from green source agreement.

- **Green:** the annotators agreed.
- **Blue:** the adjudicator explicitly resolved a review region.
- **Red:** disagreement still requires review.
- **Gray:** missing coverage still requires review.

Remaining Unresolved Count
--------------------------

The sidebar count decreases as regions are resolved.

Previous and Next navigate only the remaining unresolved regions.

Resolving a region does not automatically save it.
Click **Save Draft** to preserve resolution state.

Editing After Resolution
------------------------

If a later edit affects a resolved region, it returns to unresolved.

Examples include:

- Changing a final rhythm.
- Changing CPR.
- Changing an explanation.
- Moving a neighboring boundary.
- Adding or removing a boundary.

Review the changed region and use **Mark Resolved** again.

Green Agreement Regions
-----------------------

Green regions do not require explicit Mark Resolved because they are not
comparison disagreements.

They remain fully editable and must have valid final labels before
finalization.

Reviewer changes to green regions do not alter the original source
comparison. The final timeline records the reviewer's decision.

Finalization
------------

Finalization requires no unresolved review regions.

A valid final label alone does not bypass the explicit resolution requirement.

Before finalizing:

- Inspect the unresolved count.
- Resolve remaining red or gray regions.
- Save or finalize only after pending sidebar changes are applied.
- Check final waveform coverage and interval lengths.

Related Pages
-------------

- :ref:`adjudication-comparison-agreement`
- :ref:`adjudication-editing-labels-boundaries`
- :ref:`adjudication-saving-resuming`
- :ref:`adjudication-completion-reopening`