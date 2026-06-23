.. _developer-technical-debt:

Maintenance Notes and Technical Debt
====================================

Overview
--------

This page tracks known maintenance considerations and future refactoring opportunities.

These notes are intended to help future developers understand areas that may deserve attention.

Large Callback Class
--------------------

``AnnotationAppCallbacks`` currently contains many responsibilities:

- waveform loading,
- plotting,
- UI validation,
- annotation lifecycle,
- save/load behavior,
- event markers,
- finalization,
- Auto-Y scaling.

Future refactor opportunity:

- split annotation state logic into a model,
- split plotting helpers into a plot controller,
- split file save/load into an annotation storage module,
- split waveform/event loading into a data service layer.

Shared Mutable State
--------------------

The app uses many shared instance attributes across UI and callback methods.

This is practical for PyQt development, but can make bugs harder to trace.

Future refactor opportunity:

- create a formal annotation session state object,
- define explicit state transitions,
- reduce implicit dependencies between methods.

Synchronous Loading
-------------------

Large waveform files are loaded synchronously on the UI thread.

This can make the app appear frozen during large loads, especially over VPN.

Future refactor opportunity:

- load waveform data in a worker thread,
- show progress indicators,
- allow cancellation,
- prevent UI interaction during loading.

Debug Print Statements
----------------------

The code currently uses ``print`` statements for debugging.

Future refactor opportunity:

- use Python's ``logging`` module,
- define log levels,
- write logs to a local troubleshooting file,
- include log excerpts in support workflows.

Duplicate or Overlapping Methods
--------------------------------

Some helper methods may exist in both the UI class and callback class.

Future refactor opportunity:

- centralize duplicate methods,
- keep UI-only helpers in ``new_app.py``,
- keep behavior/state helpers in ``new_callbacks.py``.

Documentation Synchronization
-----------------------------

User-facing behavior changes should be reflected in:

- user manual,
- developer manual,
- walkthrough videos,
- troubleshooting guide.

Recent areas that need careful synchronization:

- finalization behavior,
- undo after completion,
- subject-specific manifest discovery,
- recursive CSV waveform discovery,
- annotation filename conventions.

Packaging Process
-----------------

Packaging and distribution instructions are currently placeholders.

Future work:

- finalize packaging tool,
- document build commands,
- document platform-specific issues,
- include versioning and release notes,
- define executable smoke-test checklist.

Testing Coverage
----------------

Automated test coverage should be expanded.

Priority test areas:

- waveform discovery,
- subject-specific manifest discovery,
- timestamp conversion,
- signal alias matching,
- save/load annotation lifecycle,
- finalization and undo behavior,
- UI validation logic where feasible.