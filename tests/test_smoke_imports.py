"""
tests/test_smoke_imports.py — Verify every core module can be imported cleanly.
"""
import importlib
import pytest


def test_core_modules_import():
    modules = (
        "worker",
        "main",
        "db",
        "pool",
        "human",
        "fingerprint",
        "autopublish_daemon",
        "autopublish_engine",
        "seo_pipeline",
        "topic_intelligence",
    )
    for m in modules:
        mod = importlib.import_module(m)
        assert mod is not None, f"Module {m} could not be imported"
