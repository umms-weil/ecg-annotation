.. _developer-packaging:

Packaging and Distribution
==========================

Overview
--------

The application is packaged with PyInstaller for distribution.

Current distribution targets:

- Windows folder-based application bundle.
- macOS ``.app`` bundle.
- Sphinx HTML documentation zip.

GitHub Actions can build Windows and documentation artifacts automatically. macOS artifacts may be built through GitHub Actions or manually on a trusted Mac, depending on signing and distribution needs.

Repository Paths
----------------

The current source layout is::

   ecg-annotation/
   ├── requirements.txt
   ├── docs/
   └── software/
       └── src/
           ├── new_app.py
           ├── new_callbacks.py
           └── processing.py

The PyInstaller entry point is::

   software/src/new_app.py

Because the app source is inside ``software/src``, PyInstaller should be run with ``src`` on the import path.

Packaging Dependencies
----------------------

Install dependencies from the repository root:

.. code-block:: bash

   python -m pip install --upgrade pip
   python -m pip install "setuptools==70.3.0" wheel
   python -m pip install -r requirements.txt
   python -m pip install "pyinstaller>=6.10" pyinstaller-hooks-contrib
   python -m pip install "setuptools==70.3.0"

``setuptools`` is pinned because newer versions may cause PyInstaller runtime issues involving ``pkg_resources``.

Windows Packaging
-----------------

The Windows build uses PyInstaller folder-based mode, also called ``onedir`` mode.

``--onefile`` is intentionally not used because single-file PyInstaller apps can take much longer to launch while they unpack themselves into a temporary directory.

Run from the repository root:

.. code-block:: powershell

   cd software

   python -m PyInstaller `
     --noconfirm `
     --clean `
     --windowed `
     --paths src `
     --name ECGWaveformAnnotationApp `
     --hidden-import PyQt5 `
     --hidden-import PyQt5.QtCore `
     --hidden-import PyQt5.QtGui `
     --hidden-import PyQt5.QtWidgets `
     --collect-all PyQt5 `
     --collect-all pyqtgraph `
     src\new_app.py

Expected Windows output::

   software/dist/ECGWaveformAnnotationApp/
   ├── ECGWaveformAnnotationApp.exe
   └── _internal/

When distributing the Windows build, zip the entire ``ECGWaveformAnnotationApp`` folder.

.. important::

   Do not distribute only ``ECGWaveformAnnotationApp.exe``.

   The executable depends on the bundled files inside ``_internal``. If users move or copy only the executable, the app may fail with missing module errors such as ``No module named PyQt5``.

Windows Distribution Package
----------------------------

Recommended package structure::

   ECGWaveformAnnotationApp-Windows/
   ├── BUILD_INFO.txt
   ├── README_OPEN_ME_FIRST.txt
   └── ECGWaveformAnnotationApp/
       ├── ECGWaveformAnnotationApp.exe
       └── _internal/

The user should fully extract the zip file and launch::

   ECGWaveformAnnotationApp/ECGWaveformAnnotationApp.exe

macOS Packaging
---------------

The macOS build produces an ``.app`` bundle.

Run from the repository root:

.. code-block:: bash

   cd software

   python -m PyInstaller \
     --noconfirm \
     --clean \
     --windowed \
     --paths src \
     --name ECGWaveformAnnotationApp \
     --hidden-import PyQt5 \
     --hidden-import PyQt5.QtCore \
     --hidden-import PyQt5.QtGui \
     --hidden-import PyQt5.QtWidgets \
     --collect-all PyQt5 \
     --collect-all pyqtgraph \
     src/new_app.py

Expected macOS output::

   software/dist/ECGWaveformAnnotationApp.app

macOS Distribution Package
--------------------------

Recommended package structure::

   ECGWaveformAnnotationApp-macOS/
   ├── BUILD_INFO.txt
   ├── README_OPEN_ME_FIRST.txt
   └── ECGWaveformAnnotationApp.app

Use ``ditto`` to zip macOS app bundles so bundle metadata is preserved:

.. code-block:: bash

   cd release
   ditto -c -k --sequesterRsrc --keepParent ECGWaveformAnnotationApp-macOS ECGWaveformAnnotationApp-macOS.zip

macOS Signing and Gatekeeper
----------------------------

macOS may block downloaded applications that are not Apple Developer ID signed and notarized.

Users may see a message such as::

   Apple could not verify “ECGWaveformAnnotationApp” is free of malware.

For broad distribution, the proper solution is Apple Developer ID signing and notarization.

This requires:

- Apple Developer Program access,
- Developer ID Application certificate,
- notarization credentials,
- signing/notarization workflow.

If Apple signing and notarization are not available, macOS builds may be distributed for internal use with instructions for opening unsigned apps.

Internal-use instructions:

1. Fully extract the zip file.
2. Right-click or Control-click ``ECGWaveformAnnotationApp.app``.
3. Select **Open**.
4. Confirm **Open** if prompted.

If needed, remove the quarantine attribute:

.. code-block:: bash

   xattr -dr com.apple.quarantine /path/to/ECGWaveformAnnotationApp.app

Ad-Hoc macOS Signing
--------------------

Ad-hoc signing is not equivalent to Apple Developer ID signing or notarization, but it can help with some local execution issues.

Example:

.. code-block:: bash

   codesign --force --deep --sign - software/dist/ECGWaveformAnnotationApp.app
   codesign --verify --deep --strict --verbose=4 software/dist/ECGWaveformAnnotationApp.app

Gatekeeper may still reject ad-hoc signed apps downloaded from the internet.

GitHub Actions Artifacts
------------------------

GitHub Actions builds and uploads compressed artifacts.

Artifacts are retained for 30 days.

Common artifacts:

``ECGWaveformAnnotationApp-Docs-<branch>``
   Sphinx HTML documentation zip.

``ECGWaveformAnnotationApp-Windows-<branch>``
   Windows folder-based application zip.

``ECGWaveformAnnotationApp-macOS-<branch>``
   macOS application bundle zip.

To download artifacts:

1. Open the GitHub repository.
2. Click **Actions**.
3. Select the workflow run.
4. Scroll to **Artifacts**.
5. Download the desired zip file.

Documentation Packaging
-----------------------

The documentation is built with Sphinx.

Expected source directory::

   docs/source/

Expected build output::

   docs/build/html/

Recommended documentation package structure::

   ECGWaveformAnnotationApp-Docs/
   ├── README_OPEN_ME_FIRST.txt
   ├── index.html
   ├── _static/
   ├── user_manual/
   ├── developer_manual/
   ├── search.html
   └── genindex.html

.. warning::

   Users must fully extract the documentation zip before opening ``index.html``.

   On Windows, opening ``index.html`` directly from inside the zip may cause the browser to load it from an ``AppData`` or temporary folder. This can break styling, navigation, links, images, and videos.

Files to Include
----------------

Packaging may need to include:

- Python source files bundled by PyInstaller.
- Required package dependencies.
- PyQt5 and PyQtGraph runtime files.
- Icons, if configured.
- Configuration files, if added later.
- Documentation links or README files.
- Static assets, if required at runtime.

Files Not to Include
--------------------

Do not package:

- Raw waveform data.
- Annotation output files.
- Patient identifiers.
- Local developer environment files.
- Temporary build artifacts.
- Unapproved PHI/ePHI data.

Pre-Build Checklist
-------------------

Before packaging:

- Confirm the application runs from source.
- Confirm dependencies are pinned or documented.
- Confirm ``requirements.txt`` is current.
- Confirm sample non-PHI waveform data loads.
- Confirm annotation save/load works.
- Confirm walkthrough documentation is current.
- Confirm Sphinx docs build without warnings.
- Confirm version number or build metadata is updated.

Post-Build Smoke Test
---------------------

After creating the application package, test:

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

- the zip is fully extracted before launching,
- the executable launches by double-click,
- the ``_internal`` folder remains next to the executable,
- network paths are accessible,
- file dialogs work,
- PyQt plugins are bundled.

macOS
~~~~~

Confirm:

- the zip is fully extracted before launching,
- app permissions and Gatekeeper behavior are understood,
- quarantine/signing behavior is documented,
- file dialogs work,
- network mounts are accessible.

Linux
~~~~~

Linux packaging is not currently the primary distribution target.

If Linux distribution is added later, confirm:

- Qt platform plugins are available,
- executable permissions are set,
- network mounts are accessible,
- PyInstaller output works on the target Linux distribution.

Versioning
----------

Each packaged release should have:

- release version,
- build date,
- source commit hash,
- known issues,
- change log entry.

Consider adding a visible app version label or an **About** dialog.