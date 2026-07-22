.. _troubleshooting:

Troubleshooting
===============

Application Will Not Launch
---------------------------

Possible causes:

- The application zip file was not fully extracted.
- The executable was not fully downloaded.
- Your operating system blocked the application.
- Required network access is unavailable.
- The app is being launched from an unsupported location.
- On Windows, the executable was moved away from its required support files.

Try:

1. Fully extract the downloaded zip file before launching the app.
2. Confirm you are using the correct application for your operating system.
3. Move the extracted application folder to a local folder if needed.
4. On Windows, confirm the ``_internal`` folder is still next to the executable.
5. On macOS, try right-clicking the app and selecting **Open**.
6. Contact support if the issue persists.

Windows App Reports a Missing Module
------------------------------------

If Windows reports a missing module, such as ``PyQt5``, the app may have been run outside its extracted folder.

The Windows version is distributed as a folder-based application. The executable depends on files in the same folder.

Correct structure::

   ECGWaveformAnnotationApp/
   ├── ECGWaveformAnnotationApp.exe
   └── _internal/

Incorrect usage::

   Desktop/
   └── ECGWaveformAnnotationApp.exe

Try:

1. Re-extract the full application zip file.
2. Open the extracted folder.
3. Open the ``ECGWaveformAnnotationApp`` folder.
4. Double-click ``ECGWaveformAnnotationApp.exe`` from inside that folder.
5. Do not copy the executable by itself to another location.

macOS Says the App Cannot Be Verified
-------------------------------------

macOS may display a message such as::

   Apple could not verify “ECGWaveformAnnotationApp” is free of malware.

This can happen when the app is not Apple Developer ID signed and notarized.

Try:

1. Make sure the zip file is fully extracted.
2. Right-click or Control-click ``ECGWaveformAnnotationApp.app``.
3. Select **Open**.
4. Confirm **Open** if prompted.

If the app is still blocked, open Terminal and run::

   xattr -dr com.apple.quarantine /path/to/ECGWaveformAnnotationApp.app

Example::

   xattr -dr com.apple.quarantine ~/Downloads/ECGWaveformAnnotationApp-macOS/ECGWaveformAnnotationApp.app

macOS App Does Not Open and Shows No Warning
--------------------------------------------

If the macOS app does not open and no warning appears, run it from Terminal to see the error.

Example::

   /path/to/ECGWaveformAnnotationApp.app/Contents/MacOS/ECGWaveformAnnotationApp

If the app is in your Downloads folder, the command may look like::

   ~/Downloads/ECGWaveformAnnotationApp-macOS/ECGWaveformAnnotationApp.app/Contents/MacOS/ECGWaveformAnnotationApp

Copy any error output and include it when contacting support.

Documentation Looks Broken on Windows
-------------------------------------

If the HTML documentation opens from a path containing ``AppData`` or ``Temp``, it was probably opened directly from inside the zip file.

To fix:

1. Right-click the documentation zip file.
2. Select **Extract All...**.
3. Open the extracted folder.
4. Double-click ``index.html``.

Do not open ``index.html`` directly from inside the zip file.

If the documentation is opened from inside the zip, the browser may not be able to find:

- ``_static`` files,
- CSS styling,
- JavaScript,
- linked pages,
- videos,
- images.

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
- Operating system, Windows or macOS.
- Whether you fully extracted the application zip file.
- What you clicked before the issue occurred.
- Any error message shown.
- Screenshot if available.

For macOS launch issues, include Terminal output if available.

See :ref:`support`.