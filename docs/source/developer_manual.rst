Developer Manual
================

.. contents::
   :local:
   :depth: 2

Overview
--------
This manual provides technical details for installing, extending, and maintaining the Waveform Annotation App, targeted at developers and data operations staff.

Code Structure
--------------
- `src/app.py` - User interface and PyQt widgets/layout.
- `src/callbacks.py` - Application logic, annotation workflow, waveform processing.
- `src/processing.py` - Data loading, timebounds, event fetching, utility functions.

Installation & Setup
--------------------
.. code-block:: bash

   pip install -r requirements.txt

- Set up Sphinx docs via `sphinx-quickstart` in the `docs/` directory.
- Build documentation with `make html` inside `docs/`.

Annotation File Workflow
------------------------
- Annotation CSVs are stored per subject and user (`output/annotations_{subject}_{user}.csv`).
- Loading, saving, undo, autosave logic are managed in `callbacks.py`.

Extending the App
-----------------
- To add a new question to the sidebar, modify `UI.py` and integrate logic in `callbacks.py`.
- Add new output columns by updating the annotation dict in `handle_mark_clicked` and `update_table_data`.
- For plotting changes, see the `plot_all_leads` and `update_waveform_and_mark` methods.

API Reference
-------------
**Callbacks Module**
.. automodule:: callbacks
   :members:
   :undoc-members:
   :show-inheritance:

**Processing Module**
.. automodule:: processing
   :members:
   :undoc-members:
   :show-inheritance:

Tests & Validation
------------------
- Test all annotation workflows with simulated data before clinical use.
- Run automated type and docstring validation using `pytest` and `mypy`.

Troubleshooting and Maintenance
------------------------------
- For performance issues, check array processing bottlenecks in `processing.py`.
- For UI bugs, review signal/slot connections in `UI.py`.
- For annotation data errors, inspect annotation dict consistency and saving/loading code in `callbacks.py`.

Contributing & Support
----------------------
- Please document new functions and classes using reStructuredText docstrings and type hints.
- For questions or contribution guidelines, contact [your dev email].