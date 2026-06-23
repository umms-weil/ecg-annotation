.. _developer-testing-validation:

Testing and Validation
======================

Overview
--------

Testing should include both automated tests and manual workflow validation.

Because the app is interactive and data-dependent, manual smoke testing is currently important.

Please see the :ref:`developer-technical-debt` page for un-prioritized To-Do items, including testings.

Automated Tests
---------------

Recommended automated test areas:

- waveform file discovery,
- manifest path discovery,
- signal alias resolution,
- time conversion,
- waveform clipping,
- empty waveform result behavior,
- annotation filename generation,
- annotation save/load behavior,
- completion metadata handling.

Suggested test command:

.. code-block:: bash

   pytest

If type checking is configured:

.. code-block:: bash

   mypy .

Manual Smoke Test
-----------------

Before a release, verify:

1. App launches from source or executable.
2. Base folder can be selected.
3. Waveform records appear in dropdown.
4. A waveform record loads successfully.
5. Plots display expected waveform data.
6. Event markers display when available.
7. Y-axis controls work.
8. Auto-Y toggles work.
9. Collapsible waveform sections work.
10. Clicking a waveform creates a pending interval.
11. Invalid short intervals are rejected.
12. CPR ``Yes`` disables rhythm.
13. CPR ``Unable to Determine`` requires explanation.
14. CPR ``No`` enables rhythm.
15. CPR ``No`` plus rhythm ``Unable to Determine`` requires explanation.
16. CPR ``No`` plus rhythm ``Other`` requires explanation.
17. Valid interval can be marked.
18. Annotation table updates.
19. Colored overlays appear.
20. Manual save writes expected file.
21. Autosave writes expected file.
22. Load annotations resumes correctly.
23. Remove Last Mark works.
24. Final interval reaching waveform end enables finalization.
25. Finalization dialog appears.
26. Complete file is written with ``_COMPLETE``.
27. Undo after completion re-enables marking.
28. Re-saving after undo reverts to partial file.
29. App closes cleanly.

Regression Tests
----------------

Recent or important regressions to test:

- No waveform records found for recursive CSV layouts.
- Subject-specific manifests not discovered.
- Manifest without ``UUID`` column crashes.
- Code window does not overlap waveform due to timezone conversion.
- Explanation disabled for rhythm ``Unable to Determine``.
- Explanation disabled for rhythm ``Other``.
- Final interval automatically finalizes without button click.
- Remove Last Mark after completion does not re-enable marking.
- Complete file does not load terminal metadata.
- Partial and complete files conflict.

Test Data
---------

Maintain a small non-PHI test dataset when possible.

Recommended test cases:

- one subject, one encounter, one CSV waveform file,
- one subject, one encounter, multiple CSV waveform files,
- one subject with subject-specific manifest,
- manifest with ``UUID`` column,
- manifest without ``UUID`` column,
- waveform with missing lead,
- waveform with chest impedance,
- waveform with no events,
- waveform with many events,
- completed annotation file,
- partial annotation file.

Documentation Validation
------------------------

Build docs before release:

.. code-block:: bash

   cd docs
   sphinx-build -W -b html . _build/html

Check for:

- broken references,
- heading underline warnings,
- missing images or videos,
- autodoc import errors,
- stale behavior descriptions.