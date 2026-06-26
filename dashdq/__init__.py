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
from dashdq.checks import CHECKS_REGISTRY, CheckResult

__version__ = "0.1.6"
__author__ = "Darshan Shah"
__email__ = "darshan.innovation@gmail.com"
__license__ = "Apache-2.0"
__url__ = "https://github.com/dash-libs/dash-dq"

__all__ = ["configure", "run_checks", "launch", "DQReport", "CheckResult", "CHECKS_REGISTRY"]


def configure(spark=None) -> dict:
    """Open the DashDQ wizard. Returns a config dict filled on Save Configuration."""
    from dashdq.ui import configure as _configure
    return _configure(spark=spark)


def launch(spark=None) -> None:
    """All-in-one: open wizard + Run Checks button."""
    from dashdq.ui import launch as _launch
    return _launch(spark=spark)
