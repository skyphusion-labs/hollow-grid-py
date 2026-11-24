"""Wrangler entrypoint.

The game package is hollow_grid. This file sits at the repo root so the
Worker bundle keeps that package name.
"""

from hollow_grid.worker import Default, VerdigrisWorld

__all__ = ["Default", "VerdigrisWorld"]
