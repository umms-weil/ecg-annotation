.. _completion-finalization:

Completion and Finalization
===========================

Overview
--------

A waveform is complete when annotations cover the waveform through the final data point and the user explicitly finalizes the waveform.

Finalization is a separate step from marking the final interval.

Snap-to-End Logic
-----------------

As you approach the end of the waveform, the app assists with the final interval.

If you place an endpoint within 1 second of the end of the waveform, the endpoint snaps to the exact final data point.

If you click beyond the waveform end, the endpoint also snaps to the final data point.

Marking the Final Segment
-------------------------

When the final interval reaches the end of the waveform:

- The final interval is added to the annotation table.
- The waveform is not finalized automatically.
- The **Finalize Waveform** button becomes enabled.
- A sidebar message prompts you to finalize.

Finalize Waveform
-----------------

Click **Finalize Waveform** after the final interval reaches the waveform end.

The app will ask whether the cardiac arrest/event continues beyond the available waveform.

Choose the appropriate option:

- Cardiac arrest/event does not continue beyond waveform.
- Cardiac arrest/event continues beyond waveform.

You may also enter a final comment. This is an open text field. If the information is time sensitive, please continue to note it, and reach out to the PI and developer :ref:`support`.

After finalization:

- The waveform is marked complete.
- The annotation fields are disabled.
- Additional marking is disabled.
- The annotation file is saved with ``_COMPLETE`` in the filename.
- Any redundant partial annotation file is removed.

Complete Filename
-----------------

Completed files include ``_COMPLETE``.

Example::

   annotations_subject_filetag_jdoe_COMPLETE.csv

Partial sessions do not include ``_COMPLETE``.

Example::

   annotations_subject_filetag_jdoe.csv

Undo After Completion
---------------------

If you need to revise a completed waveform:

1. Click **Remove Last Mark**.
2. The waveform completion state is cleared.
3. Annotation controls are re-enabled.
4. The annotation file reverts to the non-complete filename on save or autosave.
5. Re-mark the final interval.
6. Click **Finalize Waveform** again.

.. caution::

   Only the most recent annotation can be removed. If you need to revise an earlier interval, you must remove later intervals first. This maintains sequential markings keep their timings.

Best Practices
--------------

- Proceed sequentially along the waveform.
- Review intervals carefully before clicking **Mark**.
- Use snap-to-end behavior for the final interval.
- Always click **Finalize Waveform** after the last interval reaches the end.
- Confirm that the completed annotation file includes ``_COMPLETE``.
- Manually save before closing the app.