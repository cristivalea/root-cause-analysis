"""Checks that the project environment is installed correctly."""

import importlib

import pytest

REQUIRED_PACKAGES = ["chromadb", "requests", "groq", "langgraph", "pydantic", "streamlit", "dotenv"]


def test_rca_package_is_importable():
    import rca
    import rca.agents

    assert rca.__doc__
    assert rca.agents.__doc__


@pytest.mark.parametrize("package", REQUIRED_PACKAGES)
def test_required_package_is_installed(package):
    importlib.import_module(package)
