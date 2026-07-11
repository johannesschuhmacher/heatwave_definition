"""Compatibility entry point for the full publication workflow.

The reproducible manuscript workflow is implemented in
`scripts/run_complete_climate_workflow.py`. This wrapper keeps the older command
name available while avoiding the previous legacy-metrics path.
"""

from __future__ import annotations

from scripts.run_complete_climate_workflow import main


if __name__ == "__main__":
    main()
