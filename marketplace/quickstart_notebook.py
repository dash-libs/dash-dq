# Databricks notebook source
# MAGIC %md
# MAGIC # dash-dq — Data Quality
# MAGIC
# MAGIC Run interactive data quality checks on DataFrames and Unity Catalog tables.
# MAGIC
# MAGIC **Install and launch:**

# COMMAND ----------

# MAGIC %pip install dash-dq

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import dashdq
dashdq.launch()

# COMMAND ----------
# MAGIC %md
# MAGIC ## Python API (optional — for automation)
# MAGIC
# MAGIC ```python
# MAGIC import dashdq
# MAGIC # See docs/api/ for full API reference
# MAGIC ```
