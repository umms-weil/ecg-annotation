.. _adjudication-faq:

Frequently Asked Questions
==========================

Does adjudication change the original annotations?
--------------------------------------------------

No. Reviewer edits are stored under the separate ADJUDICATION directory.

Source annotator CSVs and timelines remain unchanged.

How many annotators are compared?
--------------------------------

The current implementation compares exactly two configured annotators.

They are displayed as Annotator A and Annotator B.

Does green mean the label is correct?
------------------------------------

No. Green indicates agreement under the configured comparison rules.

The reviewer may change any green interval.

See :ref:`adjudication-comparison-agreement`.

Why is a final interval blank?
------------------------------

Red and gray regions initially remain unlabeled to avoid favoring one
annotator.

Assign the final CPR, rhythm, and required explanation.

Why do source and final boundaries differ?
-----------------------------------------

Compatible source boundaries within tolerance are prefilled at their
midpoint.

The reviewer can also drag, add, or remove final boundaries.

Source timelines retain their original positions.

Are comments required to explain a disagreement?
------------------------------------------------

No separate dispute comment is required.

The existing question rules still require explanations for CPR Unable to
Determine and rhythm Other or Unable to Determine.

Optional comments are available for other final intervals.

Does Apply Final Label resolve the disagreement?
-----------------------------------------------

No. Apply commits the final label in memory.

Click Mark Resolved separately after completing the review.

Why did my resolved region become red again?
-------------------------------------------

An edit affected a previously resolved region.

Review the changed final timeline and explicitly mark the region resolved
again.

Can I change several final intervals within one review region?
-------------------------------------------------------------

Yes. A review region can overlap several final intervals.

All final intervals covering that region must have valid labels and coverage
before it can be resolved.

Can I add a boundary by clicking?
--------------------------------

Yes. Select an interval, click Add Boundary, then click the waveform or final
timeline at the desired time.

No numeric time entry is required.

New splits must leave at least one second on each side.

What happens when I merge different labels?
------------------------------------------

The application requests confirmation.

After confirmation, the merged final interval becomes unlabeled so you can
assign the new final decision.

Are my edits automatically saved?
---------------------------------

Not in the current adjudication baseline.

Click Save Draft regularly and before leaving the session.

The annotation application's two-minute autosave does not apply here.

What is the difference between Load and Resume?
----------------------------------------------

Load Waveform / Compare generates a fresh comparison from the source inputs.

Resume Adjudication restores your saved final labels, boundaries, and
resolution state.

Use Resume to continue existing reviewer work.

Why are both CSV and JSON required?
----------------------------------

The CSV contains the final interval timeline.

The JSON contains the comparison context, resolution flags, source references,
and workflow state.

They form a verified pair and must remain together.

Can I save before all disagreements are resolved?
------------------------------------------------

Yes. Save Draft supports partial work, including unresolved regions.

Finalize Adjudication requires all review regions to be resolved.

Can I reopen completed adjudication?
-----------------------------------

Yes. Resume the completed record, then select Reopen for Editing.

The previous completion is preserved until the first successful reopened draft
save and then retained under history.

See :ref:`adjudication-completion-reopening`.

Why is the Final waveform overlay off initially?
-----------------------------------------------

The source A/B overlays are shown separately in the upper and lower portions
of the waveform plots.

Final covers the entire plot and may overlap that shading.
Enable it when reviewing final output or disable A/B for a final-only view.

Are caliper measurements saved?
------------------------------

No. Automatic dots, manual dots, rates, caliper positions, and projection
markers are temporary.

They do not change final labels or resolution state.

Can I place caliper dots manually?
---------------------------------

Yes. Enable Manual Label and click inside the calipers on a displayed row
showing the selected source signal.

Turn Manual Label off to resume normal adjudication clicks.

Does projection repeat the detected beat interval?
-------------------------------------------------

No. Projection repeats the complete selected start-to-stop caliper duration.

See :ref:`adjudication-calipers`.

Why can I not edit boundaries while using calipers?
--------------------------------------------------

Caliper Adjust and Manual Label modes temporarily suspend final-boundary
editing to prevent conflicting interactions.

Turn those modes off before editing the final timeline.

Why does a record status appear outdated?
----------------------------------------

Statuses are cached during the session.

Save, finalization, and reopening update the loaded record.
Click Set Folder to refresh external changes across the batch.

Why is resume blocked after an annotator changes a file?
-------------------------------------------------------

The saved adjudication refers to the inputs reviewed previously.

Resume detects source changes to prevent silently using a different source
timeline.

Contact the project team before rebuilding the comparison.

Where can I get help?
--------------------

See :ref:`adjudication-troubleshooting` and :ref:`support`.