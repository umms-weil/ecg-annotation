.. _adjudication-comparison-agreement:

Comparison and Agreement
========================

Purpose
-------

The comparison timeline helps the reviewer identify where two annotators
agree and where focused review is required.

It is a review-prioritization tool, not a clinical correctness assessment.

.. important::

   Both annotators can agree on an incorrect label.

   Green regions remain editable and under the adjudicator's oversight.

What Is Compared
----------------

The application compares:

- CPR responses.
- Rhythm labels.
- Interval boundaries.
- Coverage from both annotators.
- Labels immediately before and after corresponding boundaries.

Explanations are available as reviewer context. Identical explanation text
is not required for agreement.

However, required explanations must be present for a valid final timeline.

Time Alignment
--------------

Both source timelines are compared using their original absolute UTC epoch
timestamps.

The application does not independently shift each annotator's first
annotation to zero for comparison.

Relative seconds displayed on the plots are an axis-label convenience.
They do not change the underlying time alignment.

Boundary Tolerance
------------------

The default boundary tolerance is one second.

Two corresponding boundaries within tolerance may be reconciled only when
the CPR and rhythm labels on their applicable sides agree.

Example::

   Annotator A: 60.0 seconds
   Annotator B: 60.8 seconds
   Difference:   0.8 seconds
   Reconciled:  60.4 seconds

The reconciled position is the midpoint.

A difference exactly equal to the configured tolerance is eligible for
matching.

.. note::

   The tolerance is configurable by the development team. The reviewer
   should interpret comparisons using the tolerance selected for the study.

Adjacent Labels Matter
----------------------

Close boundary positions alone do not establish agreement.

The labels before and after the boundary must also be compatible.

For example, if both annotators mark nearly the same transition time but
disagree on the rhythm after it, that transition requires review.

An extra boundary from one annotator may also create a review region.

Comparison Colors
-----------------

Green: Agreement
~~~~~~~~~~~~~~~~

Green indicates that both sources provide coverage and meet the comparison
rules for labels and boundaries.

Green regions are initially prefilled into the final timeline.

They are not locked and do not require a Mark Resolved action.

Red: Unresolved Disagreement
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Red indicates a comparison conflict requiring explicit adjudication.

Possible reasons include:

- Different CPR responses.
- Different rhythm labels.
- Boundaries outside tolerance.
- Incompatible labels around a boundary.
- An extra or unmatched boundary.

A region may have multiple reasons.

Gray: Missing Coverage
~~~~~~~~~~~~~~~~~~~~~

Gray indicates that one or both annotators do not provide valid coverage
for the comparison region.

Examples include one source starting later or ending earlier than the other.

Missing or structurally invalid source files may prevent comparison loading
altogether rather than producing a complete timeline.

Blue: Resolved Review Region
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Blue indicates that the reviewer explicitly selected **Mark Resolved**.

It is distinct from original green agreement.

If a subsequent final edit affects a resolved region, it returns to an
unresolved state.

Prefilled Final Intervals
------------------------

Green regions receive the agreed CPR and rhythm labels.

Adjacent green regions may become one final interval when their final
labels and explanations are identical.

Red and gray regions initially remain unlabeled.
The reviewer must assign final decisions.

If both source explanations are identical, that text can be prefilled.
If they differ, no explanation is silently selected from one annotator.

.. important::

   A green interval may still need a final explanation when the source
   explanation texts differ and the selected CPR/rhythm requires one.

Source and Final Boundaries
--------------------------

The source A/B timelines and waveform overlays show original annotation
boundaries.

The final timeline may show:

- Midpoint-reconciled boundaries.
- Reviewer-adjusted boundaries.
- New boundaries added during review.
- Merged intervals after a boundary is removed.

Editing the final timeline does not move source boundaries.

Review Regions Versus Final Intervals
-------------------------------------

A comparison region is not necessarily the same as a final interval.

After editing:

- One review region may contain several final intervals.
- One final interval may span several comparison regions.

The original comparison provides review context.
The final timeline contains the decisions used for downstream analysis.

When resolving a region, the application checks all final intervals
covering that region.

Related Pages
-------------

- :ref:`adjudication-review-workflow`
- :ref:`adjudication-editing-labels-boundaries`
- :ref:`adjudication-resolving-disagreements`