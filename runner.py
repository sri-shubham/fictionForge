"""Thin entrypoint for the FictionForge workflow runner."""

from __future__ import annotations

from fictionforge.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
