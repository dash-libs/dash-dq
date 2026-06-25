"""
DashDQ — Data Quality for Databricks.
Launch the UI with dashdq.launch() inside a Databricks notebook.
"""
from dashdq.suite import DQSuite
from dashdq.ui import launch

__version__ = "0.1.0"
__all__ = ["DQSuite", "launch"]
