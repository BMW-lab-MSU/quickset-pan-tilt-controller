# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'quickset-pan-tilt-controller'
copyright = '2025, Trevor Vannoy, Wyatt Weller, John Fike'
author = 'Trevor Vannoy, Wyatt Weller, John Fike'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'autoapi.extension',
    'sphinx.ext.napoleon',
    'myst_parser',
    'sphinxcontrib.plantuml',
]

myst_enable_extensions = [
    'colon_fence',
    'attrs_block',
]

autoapi_dirs = ['../src/quickset_pan_tilt']

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
