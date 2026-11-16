.. _adjudication-review-workflow:

Review Workflow
===============

Overview
--------

The reviewer works on the **Final Adjudication** timeline.

Annotator A and Annotator B provide read-only references. The comparison row
identifies areas of agreement, disagreement, or missing coverage.

.. important::

   Green regions are prefilled to assist review. They remain editable and
   should not be interpreted as automatically correct.

Step 1: Load the Review
----------------------

1. Open Adjudication mode.
2. Select your adjudicator username.
3. Set the assigned batch folder.
4. Select a waveform record.
5. Choose the appropriate action:

   - **Load Waveform / Compare** for a new comparison.
   - **Resume Adjudication** for previously saved work.

See :ref:`adjudication-getting-started` for setup details.

Step 2: Orient Yourself
----------------------

Review the four timeline rows:

1. **Annotator A**
2. **Annotator B**
3. **Agreement / Review**
4. **Final Adjudication**

Select useful signals using the waveform-row dropdowns.

The waveform plots and timelines share a synchronized time axis. Pan or zoom
to inspect the same time interval across all rows.

Step 3: Review the Comparison
----------------------------

Use the comparison colors to prioritize attention:

- **Green:** source annotator agreement.
- **Red:** unresolved disagreement.
- **Gray:** missing or one-sided coverage.
- **Blue:** explicitly resolved review region.

Use **Previous** and **Next** to visit unresolved regions.

Navigation highlights the selected review region and displays its source
decisions and disagreement reasons in the sidebar.

See :ref:`adjudication-comparison-agreement`.

Step 4: Inspect Source Decisions
-------------------------------

For the selected region, compare:

- Annotator A's CPR response.
- Annotator B's CPR response.
- Rhythm labels.
- Explanations.
- Boundary positions.
- The underlying physiological waveform.

Enable or disable source waveform overlays as needed:

- Annotator A occupies the upper plot portion.
- Annotator B occupies the lower plot portion.
- Final occupies the full plot height when enabled.

The Final waveform overlay starts off by default.

Step 5: Select a Final Interval
------------------------------

Click a timeline at the desired time or select a row in the
**Final Interval Table**.

The sidebar displays the selected final interval and its current values.

A review region and a final interval are not necessarily identical.
After splitting or merging, one review region may overlap several final
intervals.

Step 6: Apply the Final Label
----------------------------

1. Select the final CPR response.
2. Select the rhythm when CPR is **No**.
3. Enter a required explanation or optional comment.
4. Click **Apply Final Label**.

Required explanations follow the annotation question rules:

- CPR **Unable to Determine** requires an explanation.
- CPR **No** with rhythm **Other** requires an explanation.
- CPR **No** with rhythm **Unable to Determine** requires an explanation.

.. important::

   Apply sidebar changes before selecting another interval.

   Editing fields in the sidebar does not itself update the final timeline.
   **Apply Final Label** commits those values in memory.

Step 7: Adjust Boundaries if Necessary
-------------------------------------

Use the final timeline to correct interval structure:

- Drag an internal boundary.
- Add a boundary by clicking **Add Boundary**, then clicking the waveform
  or final timeline.
- Remove the boundary after the selected interval to merge it with the
  following interval.

New splits must leave at least one second on each side.

If merged intervals have different labels or comments, confirmation is
required and the merged interval becomes unlabeled.

See :ref:`adjudication-editing-labels-boundaries`.

Step 8: Explicitly Resolve the Region
------------------------------------

When satisfied with all final intervals covering the selected review region:

1. Apply any pending label changes.
2. Click **Mark Resolved**.
3. Confirm the comparison row changes to the resolved state.
4. Continue to the next unresolved region.

Applying labels or moving boundaries does not automatically resolve the
region.

Editing an affected resolved region later returns it to unresolved.

See :ref:`adjudication-resolving-disagreements`.

Step 9: Review Agreement Regions
-------------------------------

Inspect green regions as part of the final review.

The reviewer may change their labels or boundaries, even though the source
annotators agreed.

Green regions do not require Mark Resolved, but they still require valid final
labels and explanations before finalization.

For example, differing source explanation text may not be prefilled.
The reviewer must provide a final explanation where the question logic
requires one.

Step 10: Save Progress
---------------------

Click **Save Draft** periodically and before leaving the session.

A draft preserves:

- Final labels and interval boundaries.
- Resolved and unresolved regions.
- Comparison context.
- Selection information.

.. warning::

   The current adjudication baseline requires manual saving.

   Do not assume the annotation application's two-minute autosave also runs
   for adjudication.

Check the save confirmation before closing or loading another record.

See :ref:`adjudication-saving-resuming`.

Step 11: Finalize
-----------------

When review is complete:

1. Ensure all red and gray regions are resolved.
2. Check final coverage, labels, explanations, and interval lengths.
3. Click **Finalize Adjudication**.
4. Select the terminal-event decision.
5. Enter an optional final comment.
6. Confirm successful completed saving.

Finalization rejects invalid coverage, gaps, overlaps, missing required
fields, and final intervals shorter than one second.

See :ref:`adjudication-completion-reopening`.

Using Calipers During Review
----------------------------

Calipers can support waveform timing measurements.

Automatic and manual peak dots, calculated rates, and projection markers are
temporary. They are not final adjudication labels.

Turn **Adjust** or **Manual Label** off before returning to adjudication
click and boundary-editing actions.

See :ref:`adjudication-calipers`.

Session Checklist
-----------------

Before leaving a partial review:

- Apply pending sidebar changes.
- Finish or cancel pending boundary placement.
- Click **Save Draft**.
- Confirm the save succeeded.

Before finalization:

- Review the source comparison and final timeline.
- Resolve every red and gray review region.
- Check required explanations.
- Check complete waveform coverage.
- Check final interval lengths.
- Confirm the terminal-event decision.