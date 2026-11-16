.. _developer-adjudication-api:

Adjudication API Reference
=========================

This reference is generated from the implemented Python docstrings.

Processing modules are separate from the PyQt reviewer interface.

Main Comparison API
-------------------

.. autofunction:: adjudication.comparison.build_adjudication_comparison

.. autofunction:: adjudication.comparison.summarize_comparison_regions

Configuration and Statuses
--------------------------

.. automodule:: adjudication.config
   :members:
   :undoc-members:
   :no-index:

Data Models
-----------

.. automodule:: adjudication.models
   :members:
   :show-inheritance:
   :no-index:

Exceptions
----------

.. automodule:: adjudication.exceptions
   :members:
   :show-inheritance:
   :no-index:

Paths and Filenames
-------------------

.. automodule:: adjudication.paths
   :members:
   :no-index:

Source Discovery
----------------

.. automodule:: adjudication.discovery
   :members:
   :no-index:

Source Loading
--------------

.. automodule:: adjudication.loading
   :members:
   :no-index:

Source Validation
-----------------

.. automodule:: adjudication.validation
   :members:
   :no-index:

Boundary Matching
-----------------

.. automodule:: adjudication.boundaries
   :members:
   :no-index:

Timeline Segmentation and Agreement
-----------------------------------

.. automodule:: adjudication.comparison
   :members:
   :exclude-members: build_adjudication_comparison, summarize_comparison_regions
   :no-index:

Persistence
-----------

.. automodule:: adjudication.persistence
   :members:
   :no-index:

Utilities
---------

.. automodule:: adjudication.utilities
   :members:
   :no-index:

Reviewer Window
---------------

.. autoclass:: adjudication_app.AdjudicationWindow
   :members:
   :show-inheritance:
   :no-index:

Reviewer Callbacks
------------------

.. autoclass:: adjudication_callbacks.AdjudicationAppCallbacks
   :members:
   :no-index:

Temporary Caliper Controller
----------------------------

.. autoclass:: adjudication_calipers.AdjudicationCalipers
   :members:
   :no-index:

Private Implementations
-----------------------

Private ``_impl`` methods are intentionally omitted from this public reference.

Their source docstrings describe implementation details. Public wrappers
provide the documented entry points and performance instrumentation.

Related Documentation
---------------------

- :ref:`developer-adjudication-contract`
- :ref:`developer-adjudication-implementation`
- :ref:`adjudication-guide`