.. _developer-packaging:

Packaging and Distribution
==========================

Overview
--------

The application is intended to be distributed as a standalone executable.

Packaging instructions may vary by operating system and packaging tool.

.. note::

   This page should be updated with the final packaging workflow once the build process is finalized.

Recommended Packaging Checklist
-------------------------------

Before packaging:

- Confirm the application runs from source.
- Confirm dependencies are pinned or documented.
- Confirm sample waveform data loads.
- Confirm annotation save/load works.
- Confirm walkthrough documentation is current.
- Confirm Sphinx docs build without warnings.
- Confirm version number is updated.

Potential Packaging Tool
------------------------

A common option is ``PyInstaller``.

Example placeholder command:

.. code-block:: bash

   pyinstaller --onefile --windowed new_app.py

If using PyInstaller, confirm required hidden imports and data files are included.

Files to Include
----------------

Packaging may need to include:

- Python source files.
- Required package dependencies.
- Icons.
- Configuration files.
- Documentation links.
- Static assets if bundled.
- Any required templates.

Files Not to Include
--------------------

Do not package:

- Raw waveform data.
- Annotation output files.
- Patient identifiers.
- Local developer environment files.
- Temporary build artifacts.
- Unapproved PHI/ePHI data.

Post-Build Smoke Test
---------------------

After creating the executable, test:

1. App launches.
2. Base folder can be selected.
3. Waveform records appear.
4. Subject/waveform loads.
5. Event markers appear when available.
6. Marker placement works.
7. CPR/rhythm UI logic works.
8. Annotation can be marked.
9. Manual save works.
10. Autosave works.
11. Load annotations works.
12. Finalize waveform works.
13. Remove Last Mark works after completion.
14. App closes cleanly.

Platform Notes
--------------

Windows
~~~~~~~

Confirm:

- executable launches by double-click,
- network paths are accessible,
- file dialogs work,
- PyQt plugins are bundled.

macOS
~~~~~

Confirm:

- app permissions are handled,
- quarantine/signing behavior is understood,
- file dialogs work,
- network mounts are accessible.

Linux
~~~~~

Confirm:

- Qt platform plugins are available,
- executable permissions are set,
- network mounts are accessible.

Versioning
----------

Each packaged release should have:

- release version,
- build date,
- source commit hash,
- known issues,
- change log entry.

Consider adding a visible app version label or an **About** dialog.