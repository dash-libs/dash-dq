"""
DashDQ — Data Quality for Databricks.

Workflow::

    # Cell 1: open wizard, configure checks, click Save Config
    config = dashdq.configure()

    # Cell 2: run checks and get a DQReport
    report = dashdq.run_checks(config)

    # Or all-in-one:
    dashdq.launch()
"""
from dashdq.suite import run_checks, DQReport
from dashdq.ui import configure, launch
from dashdq.checks import CHECKS_REGISTRY, CheckResult

__version__ = "0.1.0"
__all__ = ["configure", "run_checks", "launch", "DQReport", "CheckResult", "CHECKS_REGISTRY"]
