# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'GCS-UmemotoLab'
copyright = '2026, KeitaTK & Team'
author = 'KeitaTK, Hirata, Taitai'
release = '1.0.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx_rtd_theme',  # ReadTheDocs テーマ（見やすい）
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# 言語設定（日本語）
language = 'ja'

# Napoleon拡張の設定（docstring形式の統一）
napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_include_init_docstring = True
napoleon_include_private_with_doc = False
napoleon_attr_annotations = True

# autodoc拡張の設定
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': False,
    'show-inheritance': True,
}

# ソースコードへのリンク表示
viewcode_follow_imported_members = True

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../app')))

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# Read the Docsテーマを使用（見やすく、モバイル対応）
html_theme = 'sphinx_rtd_theme'

html_theme_options = {
    'collapse_navigation': False,
    'sticky_navigation': True,
    'navigation_depth': 4,
    'includehidden': True,
    'titles_only': False,
    'logo_only': False,
    'prev_next_buttons_location': 'bottom',
}

html_static_path = ['_static']
html_favicon = None

# サイドバーのカスタマイズ
html_sidebars = {
    '**': ['localtoc.html', 'relations.html', 'sourcelink.html', 'searchbox.html']
}

