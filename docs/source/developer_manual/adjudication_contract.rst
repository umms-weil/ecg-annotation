.. _developer-adjudication-contract:

Adjudication Data Model and File Contract
=========================================

.. important::

   This document is the canonical **North Star contract** for the waveform
   adjudication implementation.

   Adjudication discovery, comparison, editing, saving, resuming, finalization,
   testing, and user-interface behavior must conform to this contract unless a
   change is explicitly approved and documented through a new schema version.

Contract Status
---------------

``Contract version``
   1

``Schema version``
   1

``Status``
   Active development contract

``Primary implementation target``
   Integrated PyQt waveform annotation application

``Authoritative interval output``
   Adjudication CSV

``Authoritative workflow state``
   Companion adjudication state JSON

Core Principles
---------------

The adjudication subsystem must follow these principles:

1. Original annotator files are immutable.
2. Adjudication output is stored separately from user annotations.
3. Exactly two configured annotators are compared in the current workflow.
4. One configured adjudicator produces the final timeline.
5. Agreement is a review-prioritization aid, not proof of clinical correctness.
6. The adjudicator retains authority over every final interval, including green
   agreement regions.
7. Editing does not automatically resolve a disagreement.
8. Disagreements require explicit resolution.
9. The final CSV is the authoritative adjudicated annotation timeline.
10. The JSON file stores workflow and resolution state.
11. Waveform timestamps retain their original precision.
12. Adjudication must never overwrite, rename, move, or delete source annotation
    files.

Configurable Participants
-------------------------

Annotators and adjudicators are defined through configurable lists.

Conceptual configuration:

.. code-block:: python

   ANNOTATION_USERS = [
       "annotator_1",
       "annotator_2",
   ]

   ADJUDICATORS = [
       "adjudicator_1",
   ]

The current workflow requires exactly two completed annotation inputs.

The implementation should remain flexible enough to change participant names
without rewriting discovery or comparison logic.

Annotator Identity in the Interface
-----------------------------------

Source annotators are displayed consistently as:

- ``Annotator A``
- ``Annotator B``

The A/B assignment must remain stable for one waveform record and must be stored
in the companion state JSON.

The adjudication interface should not depend on source usernames for display
logic.

Input Directory Structure
-------------------------

The expected waveform-record output structure is:

.. code-block:: text

   <BATCH>/
   └── <MRN>/
       └── <CSN>/
           └── output/
               └── <file_tag>/
                   ├── <annotator_1>/
                   │   └── annotations_<subject>_<file_tag>_<annotator_1>_COMPLETE.csv
                   └── <annotator_2>/
                       └── annotations_<subject>_<file_tag>_<annotator_2>_COMPLETE.csv

Example:

.. code-block:: text

   BATCH_1/
   └── MRN/
       └── CSN/
           └── output/
               └── waveform_file_name/
                   ├── user_a/
                   │   └── annotations_MRN_waveform_file_name_user_a_COMPLETE.csv
                   └── user_b/
                       └── annotations_MRN_waveform_file_name_user_b_COMPLETE.csv

Input File Requirements
-----------------------

Normal adjudication requires:

- One ``_COMPLETE.csv`` file from each configured annotator.
- Both files associated with the same waveform record.
- Valid numeric ``start`` and ``end`` values.
- Sequential, non-overlapping intervals within each source file.
- Required annotation columns.
- At least one annotation row in each file.

Missing or incomplete inputs must be visibly flagged.

The application may support opening incomplete inputs for investigation, but
must not silently treat incomplete files as ready for standard adjudication.

Source File Protection
----------------------

Source annotation files are read-only inputs.

The adjudication subsystem must never:

- Modify source annotation rows.
- Rewrite source annotation CSVs.
- Rename source annotation files.
- Move source annotation files.
- Delete source annotation files.
- Replace source annotation files with adjudication output.
- Store adjudication state inside an annotator's folder.

All adjudication writes must target the dedicated adjudication output location.

Adjudication Output Directory
-----------------------------

Adjudication output is stored under the waveform record's existing output
directory:

.. code-block:: text

   <BATCH>/
   └── <MRN>/
       └── <CSN>/
           └── output/
               └── <file_tag>/
                   └── ADJUDICATION/
                       └── <adjudicator>/

Example:

.. code-block:: text

   BATCH_1/
   └── MRN/
       └── CSN/
           └── output/
               └── waveform_file_name/
                   └── ADJUDICATION/
                       └── reviewer_uniqname/

The application may create the ``ADJUDICATION`` and adjudicator folders when
saving, provided the user has write permission.

Draft Output Files
------------------

A draft adjudication uses:

.. code-block:: text

   adjudication_<subject>_<file_tag>_<adjudicator>.csv

The companion workflow-state file uses:

.. code-block:: text

   adjudication_<subject>_<file_tag>_<adjudicator>_state.json

Example:

.. code-block:: text

   ADJUDICATION/
   └── reviewer_uniqname/
       ├── adjudication_MRN_waveform_file_name_reviewer_uniqname.csv
       └── adjudication_MRN_waveform_file_name_reviewer_uniqname_state.json

Completed Output Files
----------------------

A finalized adjudication uses:

.. code-block:: text

   adjudication_<subject>_<file_tag>_<adjudicator>_COMPLETE.csv

The companion state JSON remains:

.. code-block:: text

   adjudication_<subject>_<file_tag>_<adjudicator>_state.json

Example:

.. code-block:: text

   ADJUDICATION/
   └── reviewer_uniqname/
       ├── adjudication_MRN_waveform_file_name_reviewer_uniqname_COMPLETE.csv
       └── adjudication_MRN_waveform_file_name_reviewer_uniqname_state.json

The completed CSV represents the authoritative finalized timeline.

CSV and JSON Responsibilities
-----------------------------

CSV Responsibility
~~~~~~~~~~~~~~~~~~

The adjudication CSV is authoritative for:

- Final interval boundaries.
- Final CPR values.
- Final rhythm labels.
- Required explanations.
- Final waveform-completion metadata.
- Adjudicator identity.
- Waveform-record identity.

Downstream analysis should primarily consume the CSV.

JSON Responsibility
~~~~~~~~~~~~~~~~~~~

The companion JSON is authoritative for:

- Workflow state.
- Input file references.
- Annotator A/B mapping.
- Input modification metadata.
- Boundary tolerance used.
- Disagreement definitions.
- Disagreement reasons.
- Explicit resolved/unresolved status.
- Resolution timestamps.
- Current disagreement navigation position.
- Draft or complete status.
- Workflow timestamps.

The JSON supplements the CSV and does not replace it.

Required Adjudication CSV Columns
---------------------------------

The adjudication CSV must retain, at minimum, all fields used by the original
annotation format:

.. code-block:: text

   user
   subject
   encounter
   namespace
   file_tag
   source_path
   cpr
   rhythm_label
   rhythm_expl
   start
   end
   waveform_complete
   terminal_event_status
   terminal_event_comment

For compatibility:

.. code-block:: text

   user = adjudicator uniqname

Recommended additional adjudication fields:

.. code-block:: text

   record_type
   adjudication_created_at
   adjudication_updated_at

Recommended value:

.. code-block:: text

   record_type = adjudication

The CSV may gain additional tracking fields later, but existing required fields
must remain available for compatibility.

Time Representation
-------------------

Waveform and annotation boundaries use absolute UTC epoch seconds stored as
floating-point values.

Example:

.. code-block:: text

   1685030534.512845

The implementation must not intentionally convert these values to integer epoch
milliseconds.

The implementation must not deliberately round boundaries during:

- Input loading.
- Boundary comparison.
- Boundary matching.
- Midpoint calculation.
- Timeline editing.
- Dragging.
- Draft saving.
- Final saving.
- Reopening completed adjudications.

At 240 Hz, adjacent samples are approximately:

.. code-block:: text

   1 / 240 = 0.0041666667 seconds

Floating-point epoch seconds preserve the precision required for waveform
boundary placement.

Human-readable workflow timestamps should use ISO-8601 UTC.

Example:

.. code-block:: text

   2026-10-19T14:32:10.123456Z

These human-readable timestamps are metadata and do not replace numeric waveform
boundary timestamps.

Boundary Tolerance
------------------

The default boundary matching tolerance is:

.. code-block:: python

   ADJUDICATION_BOUNDARY_TOLERANCE_SEC = 1.0

This value must be defined in a clear configuration location and remain easy to
change during testing.

Two corresponding boundaries may be reconciled only when their absolute
difference is within tolerance:

.. code-block:: text

   absolute(boundary_a - boundary_b) <= tolerance

Reconciled Boundary Calculation
-------------------------------

When two boundaries satisfy the agreement requirements, the adjudicated
prefilled boundary is their midpoint:

.. code-block:: text

   reconciled_boundary =
       (boundary_a + boundary_b) / 2

The midpoint remains a floating-point UTC epoch timestamp.

Boundary Agreement Requirements
-------------------------------

Boundary proximity alone is insufficient.

A matched boundary is considered compatible only when:

- The boundary difference is within tolerance.
- The CPR values before the boundary agree.
- The rhythm labels before the boundary agree.
- The CPR values after the boundary agree.
- The rhythm labels after the boundary agree.
- Both annotators provide valid coverage around the boundary.

If adjacent labels are incompatible, the surrounding region must be flagged for
review even when the boundary positions are close.

Region Agreement Requirements
-----------------------------

A region is considered complete annotator agreement only when:

1. Both annotators cover the region.
2. CPR values match.
3. Rhythm labels match.
4. Relevant required explanations are structurally valid.
5. Corresponding boundaries are within the configured tolerance.
6. Adjacent labels support valid boundary reconciliation.
7. Neither source contains an invalid gap or overlap affecting the region.

Agreement is used to prioritize review. It is not a clinical correctness
determination.

Comparison States
-----------------

The adjudication comparison uses the following conceptual states.

Green: Annotator Agreement
~~~~~~~~~~~~~~~~~~~~~~~~~~

Green indicates:

- Both annotators provide coverage.
- CPR values agree.
- Rhythm labels agree.
- Boundaries satisfy tolerance and adjacency rules.

Green means:

.. code-block:: text

   The two annotators agree in this region.

Green does not mean:

- Clinically correct.
- Automatically accepted.
- Locked.
- Uneditable.
- Exempt from adjudicator review.

The adjudicator retains full editing authority over green regions.

Red: Unresolved Disagreement
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Red indicates one or more of:

- CPR mismatch.
- Rhythm mismatch.
- Boundary outside tolerance.
- Extra boundary from one annotator.
- Incompatible labels across a boundary.
- Structurally conflicting interval coverage.
- Another comparison conflict requiring explicit review.

Red remains unresolved until the adjudicator explicitly marks it resolved.

Gray: Missing or Incomplete Coverage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Gray indicates one or more of:

- Missing annotator file.
- Incomplete annotator input.
- Coverage from only one annotator.
- A gap in annotation coverage.
- Invalid source structure preventing normal comparison.

Gray requires reviewer attention before finalization.

Resolved Disagreement
~~~~~~~~~~~~~~~~~~~~~

Resolved disagreements must use a visual state distinct from original green
agreement.

Recommended representation:

- Blue.
- Blue with checkmark.
- Another clearly separate resolved style.

This distinction preserves the difference between:

- Original annotator agreement.
- A disagreement explicitly resolved by the adjudicator.

Disagreement Reasons
--------------------

Each disagreement should include one or more machine-readable reasons.

Initial reason vocabulary:

.. code-block:: text

   boundary_outside_tolerance
   cpr_mismatch
   rhythm_mismatch
   adjacent_label_mismatch
   annotator_a_only
   annotator_b_only
   missing_coverage
   incomplete_input
   invalid_gap
   invalid_overlap

Additional reasons may be added in future schema versions.

Disagreement Identity
---------------------

Each disagreement receives a stable identifier within the adjudication state.

Recommended format:

.. code-block:: text

   disagreement_0001
   disagreement_0002
   disagreement_0003

Each disagreement state includes:

.. code-block:: text

   disagreement_id
   start
   end
   comparison_status
   reasons
   resolved
   resolved_at

Disagreement IDs must remain stable when saving and reopening the same draft.

Prefilled Final Timeline
------------------------

The initial final adjudication timeline is generated from the comparison result.

Green regions:

- Are prefilled.
- Use reconciled midpoint boundaries where applicable.
- Use the agreed CPR and rhythm labels.
- Remain editable.

Red regions:

- Remain unresolved.
- Must not be silently treated as accepted consensus.
- Should initially remain unlabeled unless an explicitly approved provisional
  strategy is adopted later.

Gray regions:

- Remain unresolved.
- Require reviewer action.

The adjudicator may change any prefilled interval, including green regions.

Adjudicator Authority
---------------------

The adjudicator has final authority over the adjudicated timeline.

The adjudicator may:

- Change CPR values.
- Change rhythm labels.
- Add required explanations.
- Drag boundaries.
- Add boundaries.
- Remove boundaries.
- Split intervals.
- Merge intervals.
- Correct gaps.
- Correct overlaps.
- Change prefilled green regions.
- Resolve red or gray regions.

The existing CPR/rhythm question logic should apply to final adjudication
intervals.

Explicit Resolution
-------------------

A disagreement becomes resolved only when the adjudicator explicitly chooses:

.. code-block:: text

   Mark Resolved

Editing alone must not resolve a disagreement.

This rule prevents intermediate or exploratory edits from being treated as a
completed decision.

If a resolved region is edited later, its state must return to unresolved.

Finalization requires no unresolved red or gray regions.

Draft Saving
------------

Draft saving must preserve:

- Current final intervals.
- Current interval labels.
- Current boundary positions.
- Current explanations.
- Disagreement definitions.
- Resolved/unresolved states.
- Current disagreement index.
- Adjudicator identity.
- Input source metadata.
- Configuration values used for comparison.

The draft CSV stores the current final timeline.

The companion JSON stores workflow state.

Resume Behavior
---------------

When reopening a draft:

1. Load the adjudication CSV.
2. Load the state JSON.
3. Restore final intervals.
4. Restore disagreement states.
5. Restore Annotator A/B mapping.
6. Restore comparison tolerance.
7. Restore navigation position.
8. Validate source input metadata.
9. Warn if source files changed.

Input Change Protection
-----------------------

The state JSON should store, for each input file:

- Full path.
- File size.
- Last modification timestamp.
- Annotator alias.
- Source username.

When resuming, the application should detect source changes.

If an input changed, the application must not silently overwrite existing
adjudication work.

The reviewer should be offered explicit choices:

- Continue with the saved comparison state.
- Rebuild adjudication from the changed source files.
- Cancel.

Finalization Requirements
-------------------------

Final adjudication may be completed only when:

1. Final intervals cover the required waveform range.
2. Final intervals are sequential.
3. Final intervals do not overlap.
4. No invalid gaps remain.
5. Every interval has valid CPR information.
6. Every required rhythm label is present.
7. Required explanations are present.
8. No red disagreement remains unresolved.
9. No gray missing-coverage region remains unresolved.
10. Required terminal waveform-completion fields are complete.

Finalization writes the ``_COMPLETE.csv`` output.

Original annotator files remain unchanged.

Reopening Completed Adjudications
---------------------------------

Completed adjudications may be reopened.

Recommended behavior:

1. Load the completed CSV in read-only mode.
2. Require an explicit **Reopen for Editing** action.
3. Return adjudication status to draft/editable.
4. Preserve the completed file until the first successful draft save.
5. Save subsequent work as the draft CSV.
6. Re-finalization creates a new completed CSV.

The implementation must avoid losing a previously completed adjudication before
a new draft has been written successfully.

Recommended State JSON Structure
--------------------------------

Conceptual schema:

.. code-block:: json

   {
     "schema_version": 1,
     "record_type": "adjudication_state",
     "status": "draft",
     "adjudicator": "reviewer_uniqname",
     "subject": "subject_identifier",
     "encounter": "encounter_identifier",
     "file_tag": "waveform_file_tag",
     "boundary_tolerance_sec": 1.0,
     "annotator_mapping": {
       "Annotator A": {
         "username": "source_user_1",
         "path": "/path/to/source_a_COMPLETE.csv",
         "size_bytes": 12345,
         "modified_at": "2026-10-19T14:00:00Z"
       },
       "Annotator B": {
         "username": "source_user_2",
         "path": "/path/to/source_b_COMPLETE.csv",
         "size_bytes": 12345,
         "modified_at": "2026-10-19T14:01:00Z"
       }
     },
     "disagreements": [
       {
         "disagreement_id": "disagreement_0001",
         "start": 1685030534.512845,
         "end": 1685030540.729512,
         "comparison_status": "unresolved",
         "reasons": [
           "rhythm_mismatch"
         ],
         "resolved": false,
         "resolved_at": null
       }
     ],
     "current_disagreement_index": 0,
     "created_at": "2026-10-19T14:32:10.123456Z",
     "updated_at": "2026-10-19T15:10:22.654321Z"
   }

Testing Contract
----------------

Automated tests must verify at minimum:

- Exactly two configured complete input files are discovered.
- Source files are never modified.
- Invalid source intervals are rejected or flagged.
- Exact agreement is identified.
- Boundaries within tolerance are matched.
- Boundary midpoint is calculated correctly.
- Boundaries outside tolerance create disagreements.
- CPR mismatches create disagreements.
- Rhythm mismatches create disagreements.
- Adjacent-label mismatches prevent boundary reconciliation.
- Missing coverage creates gray review regions.
- Editing does not resolve disagreements.
- Mark Resolved changes only the intended disagreement.
- Editing a resolved region returns it to unresolved.
- Draft CSV and state JSON resume correctly.
- Input file changes produce a warning.
- Finalization rejects unresolved regions.
- Finalization rejects gaps and overlaps.
- Final output retains floating-point epoch precision.
- Completed adjudication can be reopened safely.
- Original annotation files remain unchanged.

Change Control
--------------

Changes to this contract must be explicit.

A contract change should include:

1. The proposed behavior change.
2. The reason for the change.
3. Impact on existing draft files.
4. Impact on completed files.
5. Required migration behavior.
6. Test updates.
7. Documentation updates.
8. A schema-version decision.

If the change breaks compatibility with existing state JSON or CSV expectations,
increment the schema version.

Implementation Reference
------------------------

Future adjudication modules should reference this contract directly.

Recommended modules:

.. code-block:: text

   software/src/adjudication.py
   software/src/adjudication_callbacks.py

The main application may integrate callbacks through:

.. code-block:: python

   class MainApp(
       QMainWindow,
       AnnotationAppCallbacks,
       AdjudicationAppCallbacks,
   ):
       ...

Shared waveform functionality should be reused.

Adjudication-specific state and callbacks should remain clearly separated from
standard annotation state.