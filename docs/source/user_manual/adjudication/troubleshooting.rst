.. _adjudication-troubleshooting:

Troubleshooting
===============

Before Troubleshooting
----------------------

If you have unsaved review work:

1. Keep the application open.
2. Do not load another record or reset the batch folder.
3. Apply any pending sidebar changes.
4. Attempt Save Draft.
5. Confirm saving succeeded before closing.

.. warning::

   Do not manually modify source annotations or adjudication CSV/JSON files
   to work around an application error.

Application Does Not Launch
---------------------------

Check that:

- The application ZIP was fully extracted.
- The application is running from a local folder.
- The build matches your operating system and processor architecture.
- On Windows, the executable remains beside its required support files.

For operating-system launch instructions, see :ref:`getting-started`.

No Records Appear
-----------------

Possible causes:

- The wrong base folder was selected.
- Turbo is not mounted or accessible.
- The selected directory does not contain the expected subject hierarchy.
- Supported waveform files are missing.

Try:

1. Confirm network/VPN connectivity.
2. Confirm the assigned batch is accessible in Finder or File Explorer.
3. Paste the correct batch path.
4. Click Set Folder.
5. Report the discovery error if records still do not appear.

Record Shows Not Ready
----------------------

Normal adjudication requires two configured annotators' completed files.

Check that both inputs:

- Belong to the selected waveform record.
- Are in their respective user folders.
- Have the expected annotation filenames.
- Include ``_COMPLETE.csv``.

An existing partial annotation is not a completed adjudication input.

Do not rename a partial file to COMPLETE to bypass this requirement.

Record Shows Check Files
-----------------------

This status can indicate:

- An adjudication CSV without its companion JSON.
- A JSON referencing a missing CSV.
- Saved identity metadata that do not match the record.
- An unsupported saved status.
- A file-access or JSON-reading error.

Hover over the record for details.

Preserve the files and contact support rather than deleting or rewriting them.

Waveform Loads but Comparison Fails
-----------------------------------

Waveform viewing and comparison loading are separate operations.

A comparison can fail because:

- A completed input is missing.
- Multiple eligible input files exist.
- A CSV lacks required columns.
- Annotation times are invalid.
- Source intervals contain gaps or overlaps.
- User or record identifiers are inconsistent.
- Completion metadata are invalid.

Read the error message and report the affected record.

The application must not silently choose an invalid source timeline.

Labels or Timelines Appear Missing
---------------------------------

Check that:

- Comparison loading completed without an error.
- You are viewing the relevant time range.
- The selected displayed signals contain data.
- Required overlay checkboxes are enabled.
- You are inspecting the final timeline rather than only waveform shading.

Blank final labels in red or gray regions are intentional before adjudication.

The Final waveform overlay is off by default.

If rendering stopped after an error, report the traceback or error message.
Do not assume the source annotations were lost.

Cannot Select or Edit Final Intervals
------------------------------------

Check whether:

- A completed adjudication is loaded read-only.
- Caliper Adjust is active.
- Caliper Manual Label is active.
- Add Boundary placement is active.
- No comparison has been loaded.

Turn caliper interaction modes off to resume ordinary adjudication clicks.

Use Reopen for Editing when revising completed output.

Apply Final Label Is Disabled
----------------------------

Check for:

- No selected final interval.
- Missing CPR response.
- Missing rhythm when CPR is No.
- Missing required explanation.
- Completed read-only state.

Explanations are required for:

- CPR Unable to Determine.
- CPR No with rhythm Other.
- CPR No with rhythm Unable to Determine.

Cannot Add a Boundary
--------------------

Check that:

- A final interval is selected.
- Pending sidebar changes were applied.
- Caliper Adjust and Manual Label are off.
- The interval is long enough to split.

A new boundary must leave at least one second on both sides.

After clicking Add Boundary, click inside the selected interval on a waveform
or the final timeline.

Use Cancel Add to leave placement mode.

Cannot Remove a Boundary
------------------------

Remove deletes the boundary after the selected final interval.

The final interval has no following interval, so its endpoint cannot be
removed.

Apply pending sidebar changes first.

If neighboring labels or comments differ, confirm the merge and then assign
a new final label to the merged interval.

Mark Resolved Is Rejected
------------------------

Possible causes:

- No unresolved comparison region is selected.
- Sidebar edits have not been applied.
- Final labels do not cover the entire review region.
- Required fields are missing.
- Final coverage has a gap or overlap.

One review region can overlap several final intervals.
Check all of them before marking the region resolved.

A Resolved Region Became Unresolved
-----------------------------------

This is expected when an applied edit changes a final interval affecting that
region.

Label changes, comments, boundary movement, splitting, and merging can require
another explicit review confirmation.

Finish the revision and click Mark Resolved again.

Save Draft Fails
---------------

Possible causes:

- Turbo/network connection is unavailable.
- The adjudicator folder lacks write permission.
- Required directories cannot be created.
- A filesystem operation fails.
- CSV/JSON verification fails.
- A completed session has not been reopened.
- Sidebar changes or boundary placement are pending.

Try:

1. Apply pending labels.
2. Finish or cancel boundary placement.
3. Confirm Turbo access and write permission.
4. Retry Save Draft.
5. Confirm the success message.

Keep the application open while resolving the problem.

For an unstable connection, reconnecting storage may help. If that requires
closing the application, seek assistance before discarding unsaved work.

Resume Reports Changed Source Files
-----------------------------------

The saved session records source-file size and modification metadata.

Resume is blocked when a source file is missing or changed.

Do not overwrite existing review work with a fresh comparison until the
project team determines how to handle the changed inputs.

Resume Reports CSV/JSON Mismatch
-------------------------------

The CSV and JSON are linked through a content hash.

A mismatch may result from:

- An interrupted save.
- Manual editing.
- Copying only one file.
- Combining files from different versions.

Preserve both files and report the error.

Do not manually change the hash or delete the state JSON.

Cannot Finalize
---------------

Finalization requires:

- Complete loaded-waveform coverage.
- No gaps or overlaps.
- Final intervals at least one second long.
- Valid CPR and rhythm fields.
- Required explanations.
- No unresolved review regions.

Correct the reported errors, then retry.

If the outer timeline bounds differ from the waveform and cannot be corrected
through available controls, contact support. Do not bypass validation.

Caliper Dots Do Not Appear
-------------------------

For automatic detection:

- Confirm Auto Peaks is on.
- Release the caliper marker to trigger calculation.
- Select a sufficiently long interval with usable data.
- Check for data gaps or the automatic processing limit.

For manual labeling:

- Turn Manual Label on.
- Display the selected source signal in a waveform row.
- Click inside the calipers.
- Use at least two dots for a rate.

See :ref:`adjudication-calipers`.

Caliper Projection Disappears
----------------------------

A wide view can require too many projection markers.

If the button requests Zoom In, narrow the visible time range.
Projection should return when the marker count is manageable.

Projection spacing is the full selected caliper duration, not the detected
beat interval.

Event Markers Are Missing
------------------------

Check whether:

- The encounter has a ``waveform_manifest.csv``.
- The manifest contains usable event timestamps.
- Event times overlap the current view.
- Text labels have been hidden.

Events may exist outside the loaded waveform interval.

Missing labels do not necessarily mean missing event lines or missing
waveform data.

Reporting an Issue
------------------

Include:

- Application version or build commit, if available.
- Operating system.
- Selected adjudicator.
- Batch and waveform-record reference using approved sharing practices.
- The action immediately preceding the problem.
- Exact error text.
- Relevant diagnostic output.
- Whether saving succeeded.
- Whether the session was draft, complete, or reopened.

Avoid including patient identifiers or clinical screenshots in an unapproved
support channel.

See :ref:`support`.