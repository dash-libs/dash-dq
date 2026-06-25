# DashDQ — Data Quality for Databricks

[![CI](https://github.com/darshan-innovation/dash-dq/actions/workflows/ci.yml/badge.svg)](https://github.com/darshan-innovation/dash-dq/actions)
[![PyPI](https://img.shields.io/pypi/v/dash-dq)](https://pypi.org/project/dash-dq/)
[![Python](https://img.shields.io/pypi/pyversions/dash-dq)](https://pypi.org/project/dash-dq/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

**DashDQ** makes data quality checks effortless for business users on Databricks.  
Launch an interactive widget UI directly in your notebook — no code required.

---

## Installation

```bash
%pip install dash-dq
```

---

## Quick Start

### Option A — Interactive UI (recommended for business users)

```python
import dashdq
dashdq.launch()
```

This opens a step-by-step widget where you:
1. Choose your data source (DataFrame / UC table / SQL)
2. Add quality checks with dropdowns and text fields
3. Click **Run** — results display inline and optionally save to a Delta table

### Option B — Python API

```python
from dashdq import DQSuite

suite = DQSuite(table="catalog.schema.customers")
suite.expect_no_nulls("customer_id") \
     .expect_unique("email") \
     .expect_values_in_set("status", ["ACTIVE", "INACTIVE"]) \
     .expect_column_range("age", min_val=0, max_val=120) \
     .expect_freshness("updated_at", max_age_hours=24)

report = suite.run(save_to="catalog.schema.dq_results")
report.display()
```

---

## Available Checks

| Check | Method | Description |
|---|---|---|
| No nulls | `expect_no_nulls(column)` | Column must have zero nulls |
| Null rate | `expect_null_rate(column, max_rate)` | Null % must be ≤ threshold |
| Uniqueness | `expect_unique(column)` | No duplicate values |
| Allowed values | `expect_values_in_set(column, list)` | All values must be in the set |
| Range | `expect_column_range(column, min, max)` | Numeric values within bounds |
| Regex | `expect_regex(column, pattern)` | Values must match pattern |
| Row count | `expect_min_rows(n)` | Table must have ≥ n rows |
| Freshness | `expect_freshness(ts_col, hours)` | Latest record within N hours |

---

## Data Sources

```python
# From a DataFrame already in memory
DQSuite(df=my_df)

# From a Unity Catalog table
DQSuite(table="catalog.schema.table")

# From a SQL query
DQSuite(query="SELECT * FROM catalog.schema.table WHERE region = 'EMEA'")
```

---

## Saving Results

```python
report = suite.run(save_to="catalog.dq.results")
```

Results are appended to the Delta table with a `run_ts` timestamp column — ready for dashboarding.

---

## Part of the Dashlibs Suite

DashDQ is part of **[Dashlibs](https://github.com/darshan-innovation)** — a collection of Databricks-native Python libraries built for business users.

| Library | Purpose |
|---|---|
| **dash-dq** | Data Quality |
| dash-synthetic | Synthetic Data Generation |
| dash-ml | ML Model Monitoring |
| dash-ingest | Data Ingestion |
| dash-gov | Data Governance |
| dash-relate | Ontology & Lineage for AI |

---

## Contributing

PRs welcome. Please run `pytest tests/` before submitting.

## License

Apache 2.0
