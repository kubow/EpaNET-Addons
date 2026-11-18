"""Reusable local EPANET, MSX, and MIKE URBAN add-on library."""

__all__ = ["EpanetWrapper"]


def __getattr__(name):
    """Avoid loading the EPANET runtime for conversion-only commands."""
    if name == "EpanetWrapper":
        from .engine import EpanetWrapper
        return EpanetWrapper
    raise AttributeError(name)
