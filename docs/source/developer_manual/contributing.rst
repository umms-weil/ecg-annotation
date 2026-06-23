.. _developer-contributing:

Contributing
============

Overview
--------

Contributions should preserve clinical annotation traceability, data integrity, and user workflow clarity.

General Guidelines
------------------

When making changes:

- Keep user-facing behavior documented.
- Update the user manual when workflow changes.
- Update the developer manual when architecture or data behavior changes.
- Test with representative non-PHI data.
- Avoid manual edits to generated annotation files.
- Preserve backward compatibility with existing annotation CSVs when possible.

Code Style
----------

Recommended practices:

- Use descriptive function and variable names.
- Add type hints where practical.
- Use docstrings for public functions.
- Keep UI construction and business logic separated where possible.
- Prefer small helper functions over large monolithic methods.
- Replace long-term debug ``print`` statements with structured logging when feasible.

Docstrings
----------

Use clear docstrings for functions that:

- load waveform data,
- parse manifests,
- convert timestamps,
- modify annotation state,
- save or load files,
- update complex UI state.

Example style:

.. code-block:: python

   def function_name(arg1: str) -> bool:
       """
       Short summary.

       Parameters
       ----------
       arg1 : str
           Description.

       Returns
       -------
       bool
           Description.
       """

Adding a New Sidebar Question
-----------------------------

To add a new question:

1. Add the widget in ``new_app.py``.
2. Add labels and layout placement.
3. Connect relevant signals.
4. Update ``update_sidebar_ui()`` validation.
5. Add the value to the annotation dictionary in ``handle_mark_clicked()``.
6. Add the column to ``update_table_data()`` if it should be visible.
7. Add default values when loading older annotation files.
8. Update save/load tests.
9. Update user documentation.
10. Update developer documentation.

Adding a New Waveform Signal
----------------------------

To add a new waveform signal:

1. Add the desired display name to ``WAVEFORM_PLOT_ORDER``.
2. Add aliases to ``SIGNAL_ALIASES``.
3. Confirm H5, CSV, or MAT files contain the signal.
4. Test signal discovery.
5. Test plotting.
6. Update user documentation if the signal is clinically relevant.

Changing Annotation CSV Columns
-------------------------------

When changing annotation output:

- Preserve existing columns when possible.
- Add new columns with default values when loading old files.
- Avoid renaming columns unless migration logic is added.
- Update ``handle_mark_clicked()``.
- Update ``handle_load_annotation()`` normalization.
- Update ``update_table_data()``.
- Update tests.
- Update documentation.

Branching and Review
--------------------

Recommended workflow:

1. Create a feature branch.
2. Make code changes.
3. Run tests.
4. Build documentation.
5. Perform manual smoke test.
6. Open a pull request or request review.
7. Document behavior changes.

Support Contact
---------------

For questions, contact:

``pwalczyk@med.umich.edu``