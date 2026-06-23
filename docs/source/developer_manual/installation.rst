.. _developer-installation:

Installation and Development Setup
==================================

Repository Setup
----------------

Clone the repository and enter the project directory.

Example::

   git clone <repository-url>
   cd ecg-annotation/software

Python Environment
------------------

Create and activate a Python environment.

Example using ``venv``::

   python -m venv .venv
   source .venv/bin/activate

On Windows::

   python -m venv .venv
   .venv\Scripts\activate

Install Dependencies
--------------------

Install project dependencies::

   pip install -r requirements.txt

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

Running the Application
-----------------------

From the project directory, run:

.. code-block:: bash

   python software/src/new_app.py

Documentation Setup
-------------------

If Sphinx has already been initialized, do not run ``sphinx-quickstart`` again.

To build documentation:

.. code-block:: bash

   cd docs
   make html

The generated HTML output is usually located at::

   docs/build/html/index.html

Clean Documentation Build
-------------------------

To clean and rebuild documentation:

.. code-block:: bash

   cd docs
   make clean
   make html

Strict Documentation Build
--------------------------

To treat Sphinx warnings as errors:

.. code-block:: bash

   cd docs
   sphinx-build -W -b html . build/html

Sphinx Path Configuration
-------------------------

If autodoc cannot import project modules, ensure ``docs/conf.py`` includes the project source path.

Example:

.. code-block:: python

   import os
   import sys

   sys.path.insert(0, os.path.abspath(".."))

If the docs are nested more deeply, adjust the path accordingly.

Video and Asset Files
---------------------

Walkthrough videos are stored in the project ``assets`` folder.

Example local path::

   ~/ecg-annotation/docs/source/_static/videos

When building docs, ensure video files are accessible to the generated HTML.

Options include:

- Referencing the relative ``assets`` path from RST files.
- Copying videos into Sphinx ``_static``.
- Configuring Sphinx to copy static assets.
- Hosting videos externally and embedding them with HTML.

Environment Notes
-----------------

Set HDF5 file locking behavior before importing ``h5py`` when needed:

.. code-block:: python

   os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"

This is already done in ``processing.py``.