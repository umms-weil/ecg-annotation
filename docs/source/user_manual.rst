User Manual: Overview and Instructions
======================================

.. contents::
   :local:
   :depth: 2

Introduction
------------

Welcome to the ECG Waveform Annotation App!

This tool enables clinical users to efficiently annotate physiological waveforms for research and quality improvement. 
This manual will guide you step-by-step through setup, annotation tasks, saving, troubleshooting, and data management.

Launching the Application
-------------------------

The application will be distributed as a standalone executable. To launch:

- Double-click the application icon (e.g., `waveform_annotation_app.exe` on Windows or `waveform_annotation_app` on Mac/Linux).

- Ensure you have access to the base data folder containing patient waveform files. The waveform and event data will be stored in Turbo.

- It is encouraged to be directly on the Michigan Network when annotating. This will allow the most efficient access to the data. The VPN is still possible, but will be much slower in load times. Waveform data is quite large, so there will be a load discrepancy. 

- If you encounter any issues launching the app, or any other issues, please reference the :ref:`troubleshooting` section. If you still have issues, please contact the developer, Peter Walczyk, at pwalczyk@med.umich.edu

Annotating Waveforms
--------------------

1. **Start the program** and select the base data folder.
    The base data folder should contain subfolders for each patient/subject with waveform files. For example: `/nfs/turbo/umms-user/project/waveforms/` where waveforms contains all the subjects. 
    
    You will very likely be provided with the full path to where the waveform data is stored. Please keep this path on hand for reference each time you open the application.
    
    Please place the path and click **Set Folder**. The application will take a moment to parse the folder structure and list available subjects in the dropdown menu in the sidebar.

    .. warning::
        Please do not access the waveform files directly via file explorer or terminal. We would like to avoid any potential file alterations, corruption, or deletions.
        This may cause file access conflicts and lead to errors in loading or saving annotations.

2. **Enter your User Name** in the sidebar.
    Your uniqname will be used to label your annotations. please use your U-M uniqname (e.g., `jdoe` | all lowercase).

3. **Choose a Patient/Subject** from the dropdown and click "Load Subject."
    The dropdown lists all available subjects found in the base data folder. The subjects are listed by their unique identifier (e.g., `subject_DEID1`, `subject_DEID2`, etc.).
    
    The dropdown will also show the number of annotations that have been completed for each subject (e.g., `subject_DEID1 (1/3 annotations)`). This is across users, not just your own annotations.
    
    Select the desired patient and click "Load Subject" to load their waveform data.

4. Optionally, click "Load Annotations" to resume previous work.
    If you began annotating a subject previously and did not complete annotating, click "Load Annotations" after you load the patient waveforms to load your existing annotations and continue where you left off.
    
    It may take a moment to load your previous annotations depending on how many you have completed as it will populate the table as well as the waveform display.

    If you partially annotated a subject, please note the subject you left off on for your records to ensure you can resume correctly. There will be no indication of incomplete annotations in the subject dropdown.

5. **Annotate intervals** using the Mark button and follow on-screen instructions.
    The sidebar will guide you through the annotation process. Place markers on the waveform, answer CPR and rhythm questions, and provide explanations as needed.
    
    **A mouse** is highly recommended for annotation as opposed to a trackpad. You may click through the waveform and increase the x-axis scale to view more data using the scroll wheel on your mouse.
    
    There are buttons on the left side of waveform display to zoom in/out and shift the y-axis up/down as needed. Some waveforms may not be centered properly, so you may need to adjust the y-axis to view the waveform clearly.
    
    .. note::
        The plot will show "No Data" if there is no waveform data in that lead. You can ignore these leads. If you do not see "No Data" and no waveform is visible, try adjusting the y-axis using the buttons on the left side of the plot area.
    
    Blue text will walk you through each step on what to select next. 
    
    Red warnings will indicate if any required steps are missing before you can mark an interval.

6. **Save your annotations** as needed using "Save All Annotations." Autosave runs every 2 minutes.
    Annotations are automatically saved every 2 minutes to prevent data loss. However, it is recommended to manually save your annotations periodically by clicking "Save All Annotations."
    
    This ensures that your work is securely stored and minimizes the risk of losing data due to unexpected issues.


Resuming and Saving Work
------------------------

- Load previous annotations with "Load Annotations."

- Finished annotations will show in the annotation table.

- **Autosave** will regularly update your annotation file.

- Manually save with "Save All Annotations" to ensure data integrity.

Annotation Completion Statistics in Subject Dropdown
---------------------------------------------------

When you select a patient/subject in the sidebar dropdown, you will see a completion ratio next to each subject. For example:

  ``subject_DEID1 (1/3 complete)``

This means:

- **1** completed annotation (waveforms fully marked and saved with `_COMPLETE`)
- **3** total annotation files present (including both completed and partial sessions)

Use this information to identify subjects who still require annotation and track your progress.


Error Messages
--------------

- **Missing User Name:** Enter your name before marking or loading.

- **No Subject Selected:** Choose a patient before proceeding.

- **No annotation file found:** Be sure you've saved at least one annotation.

- **Interval too short:** Segments must be ≥1 second.

- **Cannot mark:** Review sidebar warnings for missing steps.

Output & Data Storage
---------------------

- Annotation files are saved as `annotations_{subject}_{user}.csv` in the patient’s `output/` folder.

- You can load and continue annotating from these files at any time.

    .. warning::
        Do not manually edit or move annotation files to avoid data corruption.

Sequential Annotation and Undo Workflow
--------------------------------------

Annotations are **sequential**—you can only remove (undo) the most recent marking.  

Use the **Remove Last Mark** button in the sidebar to undo the last annotation interval. 

    .. caution::
        Editing or deleting older marks (other than the most recent mark) is not supported, ensuring data traceability.
        Additionally, there is not automated process to resolving sequential annotations via removing non-end annotations.

Sidebar Question Logic: CPR & Rhythm
------------------------------------

Your answers to CPR and Rhythm questions determine which additional fields are enabled.

.. list-table::
   :header-rows: 1

   * - CPR Answer
     - Rhythm Dropdown
     - Explanation Required
   * - Yes
     - Disabled
     - No
   * - No
     - Enabled
     - If Rhythm is "Unable to Determine" or "Other"
   * - Unable to Determine
     - Disabled
     - Yes

Red sidebar warnings will guide you step by step and indicate any required fields that are missing before you can mark an interval.

Event Markers & Plot Navigation
------------------------------

Vertical dashed lines in green, red, and purple on the plots represent:

- **Green:** Clinical events from the patient flowsheet events.

- **Red:** Code Blue start and code end markers. (if available)

- **Purple/Yellow:** Recording start and end.

Use these cues to orient yourself while annotating—intervals can be marked anywhere, but you may reference clinical events as part of your workflow.

.. note::
    Not all patients will have event markers. Some may have many. This is exclusively dependent on the EHR data available for that patient.

Zoom, Shift, and Y-Scaling
--------------------------

- Use the Y-IN/Y-OUT and SHIFT UP/DOWN buttons on the plot sidebar to adjust waveform amplitude and view.

- If a lead displays "No Data", The waveform for that lead is not available.

- If a lead has very small or large waveform, use the zoom/shift controls to make the annotation process easier. 

Annotation Table & Colored Overlays
-----------------------------------

- The annotation table lists each interval with user, subject, CPR response, rhythm, explanation, start, and end time.
    .. tip::
        The times in the table are in EPIC time, which is seconds since January 1, 1970 (Unix epoch time). This will be the most accurate way to reference the exact time of your annotations.
        The plot x-axis is in seconds relative to the start of the recording (0 seconds = recording start time) for ease of navigation.

- Colored overlays, corresponding to the rhythm type, will appear above the relevant interval in the plot for visual feedback.

File Storage and Autosave Details
---------------------------------

- All annotations are saved per subject and per user: ``annotations_{subject}_{user}.csv`` stored in the subject's `output/` folder.

- Autosave occurs every 2 minutes. However, it is best practice to click "Save All Annotations" before closing the app or taking a break.

- Loading annotations always resumes **your** annotation session for that subject and displays a confirmation with the last save time.
    .. hint::
        To load your previous annotations, ensure you enter your User Name correctly (uniqname, all lowercase) and select the correct subject before clicking "Load Annotations."

- Do **not** manually move, edit, or rename annotation files or waveform data. All data should only be accessed via the application to prevent corruption or data loss.

Annotation Completion & Snap-to-End Logic
-----------------------------------------

As you approach the end of the waveform, the app assists in marking the final interval:

- If you place the end marker within **one second of the end of the waveform**, the application will automatically snap the interval to the exact last point of data.
- If you try to mark past the last data point, it will also snap to the end automatically.

When you mark the final segment:

- You will see a **green completion message** in the sidebar:

  .. raw:: html

     <span style="color: #199E40; font-weight: bold;">Waveform annotation complete! No further marking needed.</span>

- Once complete, you cannot add more marks (unless you undo the last one to adjust your last mark).
- The annotation will be **autosaved** immediately, ensuring your work is preserved.

Filename for Completed Annotations
----------------------------------

- When you finish annotating a waveform, the app saves your annotation file with **_COMPLETE** appended:
  ``annotations_{subject}_{user}_COMPLETE.csv``
- Partial annotation sessions (if you haven't fully covered the waveform) are still saved as
  ``annotations_{subject}_{user}.csv``

- You can resume or edit unfinished annotations via the usual loading workflow. Completed files help you and your team distinguish **fully reviewed waveforms** from partial annotation sessions.

Undo After Completion
---------------------
If you undo the final mark after completion:

- The app re-enables marking for the remaining segment(s).
- The annotation file reverts to the non-`_COMPLETE` name on autosave.
- You may re-mark the end or extend/edit the last interval as needed.

Best Practices for Completing Annotation
----------------------------------------

- Proceed sequentially along the waveform—place intervals with care.
- At the end, allow the app to snap your last marking for accuracy and traceability.
- Confirm the green completion message and check for the `_COMPLETE` file after saving.


.. _troubleshooting:

Troubleshooting and FAQ
-----------------------

Frequently Asked Questions (FAQ)
-------------------------------

- *Can I undo or delete past marks?*  
    Only the most recent annotation can be removed using the **Remove Last Mark** button. Older annotations cannot be undone. This helps ensure the traceability and clinical validity of the annotation process.

- *Can I edit previous annotations?*  
    No—annotations are designed to be sequential and immutable. Edits and deletes are not permitted except for the latest interval you just marked.
    Please be intentional and careful when annotating to minimize the need for undoing many marks.


- *Where are annotation files stored?*  
    Annotation files are saved per subject and per user in the subject’s `output/` folder, named as ``annotations_{subject}_{user}.csv``. For example, if your uniqname is `jdoe` and you annotate `patient123`, the file will be named `annotations_patient123_jdoe.csv`.

- *Can I annotate the same subject in multiple sessions?*  
    Yes. After saving your work, you may close the app and resume later by reloading the subject's waveforms and clicking **Load Annotations**. Make sure you enter your User Name correctly and select the correct subject. The app will continue from your last marked interval.

- *Why do I need to enter my User Name?*  
    Your U-M uniqname ensures your annotations are correctly attributed and enables you to resume your session. Each user’s annotation file is kept separate for data integrity.

- *I don't see my previous annotations after loading—what did I miss?*  
    Make sure you entered your User Name correctly (uniqname all lowercase, e.g., `jdoe`) and selected the right subject. If you still do not see your annotations, verify the annotation file exists in the `output/` folder or utilize :ref:`support`.

- *How often should I save my work?*  
    Autosave occurs every 2 minutes, but it is best practice to manually save your annotations regularly—especially before closing the app or stepping away.

- *What should I do if a warning appears in red in the sidebar?*  
    Red warnings indicate that required information is missing (e.g., User Name, required question, invalid interval). Correct the highlighted items and try again.

- *What does the annotation table show?*  
    Each row displays the details of your marked intervals—including CPR status, rhythm, explanation, start and end time.

- *What are the colored overlays and vertical lines on the waveform plots?*  
    Colored overlays indicate annotated intervals with the type of rhythm you selected. Vertical dashed lines indicate clinical events, code start/end (red), and recording bounds (purple/yellow).

- *Can I annotate if there is missing waveform data in some leads?*  
    Yes. Leads marked "No Data" can be skipped. Only annotate from available leads.

- *How do I zoom, shift, or adjust the amplitude of waveforms?*  
    Use the Y-IN/Y-OUT buttons on the plot sidebar to zoom in and out vertically. Use Y+/Y- to move the waveform display for better visibility.

- *What happens if the interval I marked is too short?*  
    The app will display a warning. Make sure the interval between your start and end markers is at least 1 second. Annotations smaller than 1 second are not allowed.

- *Why is the Mark button disabled?*  
    The Mark button is only enabled when all required information is entered and a valid interval is selected. Check the sidebar for red warning messages.

- *Is there a limit to the number of annotations I can make?*
    There is no fixed limit—annotate as needed for your session. You are limited to one annotation file per subject per user. The entire waveform must be annotated. 

- *Can I manually edit or move annotation files or waveform data?*  
    No. Do not move, rename, or manually change annotation files or waveform data. Use the app’s save and load functions to ensure proper data handling and avoid corruption.

- *What if the app crashes or closes unexpectedly?*  
    Due to regular autosave, little progress should be lost. Re-launch the app, reload your subject and annotations, and continue from the latest saved interval.
    It is also possible that the application is loading slowly due to network issues. If you selected a subject's waveforms to load, please be patient as waveform data is quite large. If this is an issue, please conduct annotaitons on the Michigan Network directly.

- *Do I need an internet connection or VPN?*  
    It is recommended to be directly on the Michigan Network for fastest performance. VPN is supported if needed, but data loading may be slower. You will need to mount the Turbo drive onto your device to access waveform data via VPN.

- *How can I get help with an issue not listed here?*  
    Refer to the :ref:`troubleshooting` section for further guidance or utilize :ref:`support`.

- *Can I annotate from home or off-site?*  
    Yes—the application may be used off-site with VPN. Be mindful of slower data access speeds.

- *Is my annotation data shared with others?*  
    No. Your annotations are user-specific and stored separately from other users unless you explicitly share an annotation file.
    Your annotations will be visible to others during a later adjudication phase. You may or may not be involved in adjudication depending on your role.

Best Practices & Checklist
--------------------------

- Always use your correct U-M uniqname as User Name before marking or loading.

- Periodically save your annotations (don't rely solely on autosave).

- Review all red warnings before marking intervals.

- Only remove marks using the Remove Last Mark button (no manual edits).

- Annotate with reference to clinical events when relevant.

- Never alter or move waveform/annotation files outside the app.

.. _support:

Contact & Support
-----------------

For help, contact the developer at **pwalczyk@med.umich.edu** or refer to the :ref:`troubleshooting` sections above.

.. important::
    **When emailing for support**, please include the following details:
        
        - Subject line: "ECG Annotation App Support"
        
        - Your U-M uniqname
        
        - Subject ID you are annotating
        
        - Description of the issue or error message


.. raw:: html

   <span style="color: #FFCB05; background-color: #00274C; font-weight: bold; font-size: 100px; text-align: center;">~~Go Blue!~~</span>