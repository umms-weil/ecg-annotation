.. _adjudication-guide:

Adjudication Guide
==================

This guide is for designated reviewers producing final waveform labels from
two annotators' completed annotation sessions.

Adjudication is a separate workflow from creating the original annotations.

The reviewer can:

- Compare the two source timelines.
- Inspect agreement and disagreement.
- Change final labels and interval boundaries.
- Explicitly resolve review regions.
- Save and resume partially completed work.
- Finalize and reopen completed adjudications.
- Use waveforms, event markers, and temporary caliper measurements.

.. important::

   Original annotator files are **never modified**.

   Green agreement indicates that the two annotators agree under the
   comparison rules. It does not establish clinical correctness or remove
   the reviewer's authority to change the final labels.

Recommended Adjudication Reading Order
-------------------------------------

For your first adjudication session:

1. To connect to the network, review :ref:`connect-to-network`.
2. Read :ref:`adjudication-getting-started`.
3. Follow :ref:`adjudication-review-workflow`.
4. Review :ref:`adjudication-comparison-agreement` to understand the timeline colors.
5. Use :ref:`adjudication-editing-labels-boundaries` when making final decisions.
6. Follow :ref:`adjudication-resolving-disagreements` for explicit review confirmation.
7. Read :ref:`adjudication-saving-resuming` before leaving the application.
8. Follow :ref:`adjudication-completion-reopening` when review is finished.

Guide Contents
--------------

.. toctree::
   :maxdepth: 1

   Getting Started <getting_started>
   Review Workflow <review_workflow>
   Interface Guide <interface_guide>
   Comparison and Agreement <comparison_and_agreement>
   Editing Labels and Boundaries <editing_labels_and_boundaries>
   Resolving Disagreements <resolving_disagreements>
   Saving and Resuming <saving_and_resuming>
   Completion and Reopening <completion_and_reopening>
   Calipers and Temporary Measurements <calipers>
   Walkthrough Videos <walkthrough_videos>
   Troubleshooting <troubleshooting>
   Frequently Asked Questions <faq>

Core Review Principles
----------------------

Source Timelines Are Read-Only
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Annotator A and Annotator B retain their original boundaries and labels.
All reviewer changes are made to the separate final adjudication timeline.

Final Labels Remain Under Reviewer Control
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Both prefilled agreement intervals and unresolved intervals may be changed.

Applying a Label Is Not Resolution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Clicking **Apply Final Label** commits the final interval values in memory.
A disagreement remains unresolved until **Mark Resolved** is explicitly
selected.

Draft Saving Is Required
~~~~~~~~~~~~~~~~~~~~~~~

Use **Save Draft** before closing or loading another record.

The current baseline requires manual adjudication saving. Do not assume that
the annotation workflow's two-minute autosave also applies to adjudication.

Caliper Measurements Are Temporary
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Peak dots, estimated rates, and projection markers support visual review.
They are not saved as adjudication labels.

Shared Resources
----------------

For VPN and Turbo connection instructions:

- :ref:`connect-to-network`

For assistance:

- :ref:`support`

If you are creating original annotations rather than reviewing them, see
:ref:`annotation-guide`.