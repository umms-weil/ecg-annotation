# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

from pathlib import Path
import sys

# conf.py is at <repository>/docs/source/conf.py.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRECTORY = REPOSITORY_ROOT / "software" / "src"

sys.path.insert(0, str(SOURCE_DIRECTORY))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'ECG Annotation and Adjudication Tool'
copyright = '2026, Peter Walczyk'
author = 'Peter Walczyk'
# html_title = "UCONN-CPR Waveform Annotation and Adjudication"
html_title = "UCONN-CPR Waveform Tools"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
]

autodoc_mock_imports = ["PyQt5", "pyqtgraph", "numpy", "pandas", "pyqtgraph",]

autodoc_member_order = "bysource"
autodoc_typehints = "description"

napoleon_numpy_docstring = True
napoleon_google_docstring = True

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_theme_options = {
    "collapse_navigation": False,
    "navigation_depth": 5,
    "titles_only": False,
    "sticky_navigation": False,
}
html_static_path = ['_static']
html_static_path = ['_static']
html_css_files = ['custom.css']