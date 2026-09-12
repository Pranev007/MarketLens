"""Dashboard page renderers.

Deliberately not Streamlit's magic ``pages/`` directory: the filters in the
sidebar apply across every page, which needs a single script controlling
navigation and passing the filtered dataset down.
"""
