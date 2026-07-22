.. _developer-installation:

Installation and Development Setup
==================================

Repository Setup
----------------

Clone the repository and enter the project directory.

Example::

   git clone <repository-url>
   cd ecg-annotation

Repository Layout
-----------------

The expected repository layout is::

   ecg-annotation/
   ├── requirements.txt
   ├── docs/
   │   ├── Makefile
   │   ├── make.bat
   │   └── source/
   │       ├── conf.py
   │       ├── index.rst
   │       ├── user_manual/
   │       └── developer_manual/
   └── software/
       ├── src/
       │   ├── new_app.py
       │   ├── new_callbacks.py
       │   └── processing.py
       ├── assets/
       └── tests/

Python Environment
------------------

Create and activate a Python environment from the repository root.

Example using ``venv`` on macOS/Linux::

   python -m venv .venv
   source .venv/bin/activate

On Windows PowerShell::

   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

Install Dependencies
--------------------

Install project dependencies from the repository root.

.. code-block:: bash

   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt

Core Dependencies
-----------------

The application depends on packages including:

- ``PyQt5``
- ``pyqtgraph``
- ``numpy``
- ``pandas``
- ``h5py``
- ``pytz``
- ``sphinx`` for documentation builds
- ``sphinx-rtd-theme`` for documentation styling
- ``sphinx-autodoc-typehints`` for API documentation

Running the Application
-----------------------

From the repository root, run:

.. code-block:: bash

   python software/src/new_app.py

Alternatively, from inside the ``software`` directory, run:

.. code-block:: bash

   cd software
   python src/new_app.py

Documentation Setup
-------------------

If Sphinx has already been initialized, do not run ``sphinx-quickstart`` again.

The documentation source is located at::

   docs/source/

The Sphinx configuration file is located at::

   docs/source/conf.py

To build documentation from the repository root:

.. code-block:: bash

   cd docs
   make html

On Windows PowerShell:

.. code-block:: powershell

   cd docs
   .\make.bat html

The generated HTML output is located at::

   docs/build/html/index.html

Clean Documentation Build
-------------------------

To clean and rebuild documentation:

.. code-block:: bash

   cd docs
   make clean
   make html

On Windows PowerShell:

.. code-block:: powershell

   cd docs
   .\make.bat clean
   .\make.bat html

Strict Documentation Build
--------------------------

To treat Sphinx warnings as errors, run from the repository root:

.. code-block:: bash

   python -m sphinx -W -b html docs/source docs/build/html

Or from inside the ``docs`` directory:

.. code-block:: bash

   python -m sphinx -W -b html source build/html

Sphinx Path Configuration
-------------------------

If autodoc cannot import project modules, ensure ``docs/source/conf.py`` includes the project source path.

Because the application code is located in ``software/src``, use:

.. code-block:: python

   import os
   import sys

   sys.path.insert(0, os.path.abspath("../../software/src"))

This path is relative to ``docs/source/conf.py``.

Video and Asset Files
---------------------

Walkthrough videos are stored in the Sphinx static directory so they are copied into the generated HTML documentation.

Expected source location::

   docs/source/_static/videos/

Expected built output location::

   docs/build/html/_static/videos/

If videos are stored temporarily in ``software/assets/``, copy them before building the docs.

macOS/Linux example:

.. code-block:: bash

   mkdir -p docs/source/_static/videos
   cp software/assets/*.mp4 docs/source/_static/videos/

Windows PowerShell example:

.. code-block:: powershell

   New-Item -ItemType Directory -Force -Path docs\source\_static\videos
   Copy-Item software\assets\*.mp4 docs\source\_static\videos\

GitHub Actions
--------------

GitHub Actions workflows build:

- Sphinx documentation,
- Windows application artifacts,
- macOS application artifacts.

Artifacts are retained for 30 days and can be rebuilt manually.

If GitHub is a mirror of a GitLab repository, workflow runs start only after the mirror update reaches GitHub. Mirror synchronization may take several minutes.

Downloading GitHub Actions Artifacts
------------------------------------

To download an artifact:

1. Open the GitHub repository.
2. Click the **Actions** tab.
3. Select the workflow run.
4. Scroll to **Artifacts**.
5. Download the desired artifact.

Common artifacts include:

- ``ECGWaveformAnnotationApp-Docs-<branch>``
- ``ECGWaveformAnnotationApp-Windows-<branch>``
- ``ECGWaveformAnnotationApp-macOS-<branch>``

Environment Notes
-----------------

Set HDF5 file locking behavior before importing ``h5py`` when needed:

.. code-block:: python

   os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"

This is already done in ``processing.py``.