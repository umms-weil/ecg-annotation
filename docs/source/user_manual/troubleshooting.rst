.. _troubleshooting:

Troubleshooting
===============

Application Will Not Launch
---------------------------

Possible causes:

- The executable was not fully downloaded.
- Your operating system blocked the application.
- Required network access is unavailable.
- The app is being launched from an unsupported location.

Try:

1. Relaunch the application.
2. Confirm you are using the correct executable for your operating system.
3. Move the executable to a local folder if needed.
4. Contact support if the issue persists.

Base Folder Does Not Load
-------------------------

Possible causes:

- The folder path is incorrect.
- The folder is unavailable over the network.
- VPN is disconnected.
- You do not have permission to access the folder.

Try:

1. Confirm the path is correct.
2. Confirm the Turbo drive or network location is mounted.
3. Connect to the Michigan Network or VPN.
4. Click **Set Folder** again.

No Subjects or Waveform Records Appear
--------------------------------------

Possible causes:

- The wrong base folder was selected.
- The expected folder structure is not present.
- Waveform files are missing.
- The app cannot identify supported waveform files.

Try:

1. Confirm the base folder contains subject folders.
2. Confirm subject folders contain encounter folders.
3. Confirm waveform files are present.
4. Confirm a ``waveform_manifest.csv`` file is present for the encounter when expected.
5. Contact support with the base folder path and a screenshot.

Subject Takes a Long Time to Load
---------------------------------

Waveform files can be large.

Loading may be slower when:

- Using VPN.
- Accessing remote network storage.
- Loading long waveform recordings.
- Loading records with many events.

Try:

- Wait for loading to complete.
- Use the Michigan Network directly if possible.
- Avoid loading multiple large files at the same time.

Waveforms Do Not Appear
-----------------------

Possible causes:

- The selected lead is unavailable.
- The Y-axis scale is too large or too small.
- The waveform window does not overlap the expected data.
- The waveform file could not be read.

Try:

1. Check whether the plot says ``No Data``.
2. Use **Y-IN**, **Y-OUT**, **Y+**, and **Y-** controls.
3. Try another waveform record.
4. Contact support if no leads display data.

Mark Button Is Disabled
-----------------------

The **Mark** button is disabled until all required conditions are met.

Check for:

- Missing user name.
- No marker placed on the waveform.
- Interval shorter than 1 second.
- Missing CPR answer.
- Missing rhythm label.
- Missing explanation.
- Waveform already finalized.

Read the red sidebar warning message and complete the required step.

Previous Annotations Do Not Load
--------------------------------

Possible causes:

- Wrong username selected.
- Wrong waveform record selected.
- No previous annotation file exists.
- Annotation file was moved or renamed.
- Annotation file is in a different output folder.

Try:

1. Confirm your username is correct and lowercase.
2. Confirm you selected the same waveform record.
3. Click **Load Subject** before **Load Annotations**.
4. Contact support if the file should exist but does not load.

Save or Autosave Fails
----------------------

Possible causes:

- Network storage is unavailable.
- You do not have write permission.
- The output folder cannot be created.
- The annotation file is open in another program.

Try:

1. Confirm network/VPN access.
2. Close any manually opened annotation CSV files.
3. Click **Save All Annotations** again.
4. Contact support if saving continues to fail.

App Freezes or Closes Unexpectedly
----------------------------------

Try:

1. Relaunch the app.
2. Select the same username.
3. Select the same waveform record.
4. Click **Load Subject**.
5. Click **Load Annotations**.

Autosave runs every 2 minutes, so most recent work should usually be recoverable.

Reporting an Issue
------------------

When reporting an issue, include:

- Your U-M uniqname.
- Subject or waveform record ID.
- Base folder path.
- What you clicked before the issue occurred.
- Any error message shown.
- Screenshot if available.

See :ref:`support`.