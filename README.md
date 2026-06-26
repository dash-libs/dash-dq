# DashDQ — Data Quality for Databricks

[![CI](https://github.com/dash-libs/dash-dq/actions/workflows/ci.yml/badge.svg)](https://github.com/dash-libs/dash-dq/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dash-dq)](https://pypi.org/project/dash-dq/)
[![Python](https://img.shields.io/pypi/pyversions/dash-dq)](https://pypi.org/project/dash-dq/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

**DashDQ** is a Databricks-native data quality library. It provides an interactive notebook wizard and a Python API to run **60+ production-ready checks** on Unity Catalog tables — built entirely on PySpark and the Databricks SDK. No Great Expectations or external DQ frameworks required.

> Part of the [Dashlibs](https://github.com/dash-libs) suite for Databricks.

---

## Features

- **60+ native checks** — completeness, accuracy, integrity, consistency — pure PySpark, zero external DQ library
- **Interactive wizard** (`configure()`) — 3-tab notebook UI powered by ipywidgets
- **GE-compatible naming** — check names follow Great Expectations conventions
- **DQX-inspired checks** — freshness, email/URL/IPv4/UUID validation, custom SQL filter
- **Cross-table checks** — foreign key validation, referential integrity, row count comparison across tables
- **Composite key checks** — multi-column PK and uniqueness validation
- **Custom SQL filter** — write a SQL WHERE clause; rows matching it are marked FAILED
- **Flexible output** — Delta table, Databricks Volume (JSON/CSV), or DataFrame
- **Summary output** — 1 row per check × column with pass/fail counts, %, column coverage, and metadata headers

---

## Install

```python
# Inside a Databricks notebook
%pip install dash-dq
dbutils.library.restartPython()
```

```bash
# Locally (Python 3.9+)
pip install dash-dq
```

---

## Quickstart

### Option 1 — 2-cell wizard

```python
# Cell 1: open the configuration wizard
import dashdq
config = dashdq.configure()
```

> The wizard opens below the cell. Enter your table name → **Load Columns** → add checks → choose output → **Save Config**.

```python
# Cell 2: run checks (after clicking Save Config above)
report = dashdq.run_checks(config)
```

### Option 2 — all-in-one

```python
import dashdq
dashdq.launch()
```

### Option 3 — pure Python API (no UI)

```python
import dashdq

config = {
    "source": {"table": "catalog.schema.dim_customer"},
    "metadata": {
        "data_owner":      "Jane Smith",
        "data_steward":    "John Doe",
        "business_domain": "Finance",
        "description":     "Customer master data quality run",
    },
    "checks": [
        # Completeness
        {"check_name": "expect_column_values_to_not_be_null",
         "column": "customer_id", "threshold_pct": 100.0, "params": {}},

        # Accuracy — range
        {"check_name": "expect_column_values_to_be_between",
         "column": "age", "threshold_pct": 99.0,
         "params": {"min_value": 18, "max_value": 120}},

        # Accuracy — format
        {"check_name": "expect_column_values_to_be_valid_email",
         "column": "email_address", "threshold_pct": 98.0, "params": {}},

        # Accuracy — freshness
        {"check_name": "expect_column_values_to_be_not_older_than_n_days",
         "column": "last_updated", "threshold_pct": 100.0,
         "params": {"n_days": 7}},

        # Accuracy — custom SQL filter
        {"check_name": "expect_column_values_to_pass_custom_sql_filter",
         "column": "annual_income_aed", "threshold_pct": 100.0,
         "params": {"sql_filter": "annual_income_aed < 0 OR annual_income_aed > 100000000"}},

        # Integrity — primary key
        {"check_name": "expect_primary_key_to_be_valid",
         "column": "_COMPOUND_", "threshold_pct": 100.0,
         "params": {"columns": ["customer_id"]}},

        # Integrity — foreign key
        {"check_name": "expect_column_values_to_exist_in_reference_table",
         "column": "branch_id", "threshold_pct": 100.0,
         "params": {
             "reference_table": "catalog.schema.dim_branch",
             "reference_column": "branch_id",
         }},

        # Consistency — table level
        {"check_name": "expect_table_row_count_to_be_between",
         "column": "_TABLE_LEVEL_", "threshold_pct": 100.0,
         "params": {"min_value": 10000, "max_value": 100000}},
    ],
    "output": {
        "type": "delta",
        "delta_table": "catalog.schema.dq_results",
    },
}

report = dashdq.run_checks(config)
report.display()
print(report.summary())
# {'total_checks': 8, 'passed': 8, 'failed': 0, 'pass_rate_pct': 100.0}
```

---

## Screenshots

> **Note:** Replace these placeholders with screenshots from your Databricks workspace.

### Tab 1 — Source & Metadata
![Tab 1 — Source and Metadata](docs/screenshots/tab1_source.png)

Enter a fully-qualified table name (e.g. `ai_innovation_gold_dev.sdh.dim_customer`), click **Load Columns** to pull the column list from Spark, and optionally fill in Data Owner, Data Steward, Business Domain, and Description fields.

### Tab 2 — Checks Builder
![Tab 2 — Checks builder](docs/screenshots/tab2_checks.png)

Select a column, pick a check from the dropdown (grouped by DQ dimension), set a pass threshold %, fill in parameters (fields appear dynamically), and click **＋ Add Check**. A live table shows all configured checks with coloured dimension badges.

### Tab 3 — Output
![Tab 3 — Output](docs/screenshots/tab3_output.png)

Choose between **DataFrame only**, **Delta Table**, **Volume — JSON**, or **Volume — CSV**. The filename is auto-suggested as `dq_{table}_{date}`.

### Results
![Results](docs/screenshots/results.png)

One row per check × column combination, with a summary banner showing total pass/fail counts and pass rate %.

> To add screenshots: run `dashdq.configure()` in your Databricks workspace, take screenshots of each tab, and save them to `docs/screenshots/`.

---

## Output schema

| Column | Type | Description |
|---|---|---|
| `table_name` | string | Fully qualified source table |
| `column_name` | string | Column checked (`_TABLE_LEVEL_` or `_COMPOUND_` for multi-column checks) |
| `check_name` | string | GE-style check name |
| `dq_dimension` | string | Completeness / Accuracy / Integrity / Consistency |
| `total_rows` | int | Total rows evaluated |
| `passed_rows` | int | Rows that passed |
| `failed_rows` | int | Rows that failed |
| `passed_pct` | float | `passed_rows / total_rows × 100` |
| `threshold_pct` | float | Minimum pass % required (FAIL if below) |
| `status` | string | `PASS` or `FAIL` |
| `check_params` | string | JSON string of check parameters used |
| `run_timestamp` | string | ISO timestamp of the run |
| `data_owner` | string | Optional metadata header |
| `data_steward` | string | Optional metadata header |
| `business_domain` | string | Optional metadata header |
| `table_description` | string | Optional metadata header |
| `columns_checked` | int | Distinct columns covered by checks in this run |
| `total_columns` | int | Total columns in the source table |
| `column_coverage_pct` | float | `columns_checked / total_columns × 100` |

---

## Check catalog (60+)

### Completeness (5)

| Check | Params | Description |
|---|---|---|
| `expect_column_values_to_not_be_null` | — | Values must not be null |
| `expect_column_values_to_be_null` | — | Values must be null |
| `expect_column_values_to_not_be_null_or_empty` | — | Not null AND not empty/whitespace |
| `expect_column_null_count_to_be_between` | min_value, max_value | Null count in range |
| `expect_column_null_proportion_to_be_between` | min_value, max_value | Null proportion (0–1) in range |

### Accuracy — value (13)

| Check | Params | Description |
|---|---|---|
| `expect_column_values_to_be_between` | min_value, max_value | Values in numeric range |
| `expect_column_values_to_not_be_between` | min_value, max_value | Values outside numeric range |
| `expect_column_values_to_be_in_set` | value_set | Values in allowed list |
| `expect_column_values_to_not_be_in_set` | value_set | Values not in forbidden list |
| `expect_column_values_to_equal` | value | All values == constant |
| `expect_column_values_to_not_equal` | value | No values == constant |
| `expect_column_values_to_be_not_less_than` | min_value | Values >= min |
| `expect_column_values_to_be_not_greater_than` | max_value | Values <= max |
| `expect_column_values_to_be_positive` | — | Values > 0 |
| `expect_column_values_to_be_negative` | — | Values < 0 |
| `expect_column_values_to_be_non_negative` | — | Values >= 0 |
| `expect_column_values_to_be_increasing` | — | Non-decreasing order |
| `expect_column_values_to_be_decreasing` | — | Non-increasing order |

### Accuracy — string & pattern (13)

| Check | Params | Description |
|---|---|---|
| `expect_column_values_to_not_be_empty_string` | — | Not blank/whitespace |
| `expect_column_values_to_match_regex` | regex | Matches regex |
| `expect_column_values_to_not_match_regex` | regex | Does not match regex |
| `expect_column_values_to_match_regex_list` | regex_list | Matches any regex in list |
| `expect_column_values_to_match_like_pattern` | like_pattern | SQL LIKE pattern (%, _) |
| `expect_column_values_to_not_match_like_pattern` | like_pattern | Does not match LIKE pattern |
| `expect_column_value_lengths_to_be_between` | min_value, max_value | String length in range |
| `expect_column_value_lengths_to_equal` | value | Exact string length |
| `expect_column_values_to_be_of_type` | type_ | dtype contains type string |
| `expect_column_values_to_be_in_type_list` | type_list | dtype in list |
| `expect_column_values_to_be_valid_email` | — | Valid email address |
| `expect_column_values_to_be_valid_url` | — | Valid HTTP/HTTPS URL |
| `expect_column_values_to_be_valid_ipv4` | — | Valid IPv4 address |
| `expect_column_values_to_be_valid_uuid` | — | Valid UUID |
| `expect_column_values_to_be_json_parseable` | — | Valid JSON string |

### Accuracy — date & time (7)

| Check | Params | Description |
|---|---|---|
| `expect_column_values_to_match_strftime_format` | strftime_format | Date format match |
| `expect_column_values_to_be_dateutil_parseable` | — | Parseable as a date (multiple formats) |
| `expect_column_values_to_not_be_in_future` | — | Date is not in the future |
| `expect_column_values_to_be_not_older_than_n_days` | n_days | Date within last N days |
| `expect_column_values_to_not_be_in_near_future` | n_days | Not within next N days |
| `expect_column_data_to_be_fresh` | n_minutes | Latest value within N minutes of now |
| `expect_column_values_to_pass_custom_sql_filter` | sql_filter | Rows matching WHERE clause = FAILED |

### Accuracy — aggregate (11)

| Check | Params | Description |
|---|---|---|
| `expect_column_mean_to_be_between` | min_value, max_value | Mean in range |
| `expect_column_median_to_be_between` | min_value, max_value | Median in range |
| `expect_column_stdev_to_be_between` | min_value, max_value | Std deviation in range |
| `expect_column_max_to_be_between` | min_value, max_value | Max in range |
| `expect_column_min_to_be_between` | min_value, max_value | Min in range |
| `expect_column_sum_to_be_between` | min_value, max_value | Sum in range |
| `expect_column_most_common_value_to_be_in_set` | value_set | Mode in allowed set |
| `expect_column_quantile_value_to_be_between` | quantile, min_value, max_value | Quantile in range |
| `expect_column_distinct_values_to_be_in_set` | value_set | All distinct values in set |
| `expect_column_distinct_values_to_contain_set` | value_set | Distinct values include all of set |
| `expect_column_distinct_values_to_equal_set` | value_set | Distinct values == set exactly |

### Integrity (10)

| Check | Params | Description |
|---|---|---|
| `expect_column_values_to_be_unique` | — | No duplicates |
| `expect_column_unique_value_count_to_be_between` | min_value, max_value | Distinct count in range |
| `expect_column_proportion_of_unique_values_to_be_between` | min_value, max_value | Uniqueness ratio in range |
| `expect_column_pair_values_to_be_equal` | column_b | colA == colB row-wise |
| `expect_column_pair_values_a_to_be_greater_than_b` | column_b | colA > colB row-wise |
| `expect_column_pair_values_to_be_in_set` | column_b, valid_pairs | (colA, colB) pairs in allowed set |
| `expect_compound_columns_to_be_unique` | columns | Multi-column combination unique |
| `expect_primary_key_to_be_valid` | columns | PK: not null + unique (single or composite) |
| `expect_column_values_to_exist_in_reference_table` | reference_table, reference_column | Foreign key check |
| `expect_referential_integrity` | reference_table, reference_column, check_orphans | Full RI, optionally bidirectional |

### Consistency — table level (10)

| Check | Params | Description |
|---|---|---|
| `expect_table_row_count_to_be_between` | min_value, max_value | Row count in range |
| `expect_table_row_count_to_equal` | value | Exact row count |
| `expect_table_column_count_to_be_between` | min_value, max_value | Column count in range |
| `expect_table_column_count_to_equal` | value | Exact column count |
| `expect_column_to_exist` | — | Column exists in table |
| `expect_table_columns_to_match_set` | column_set | Column names == expected set |
| `expect_table_columns_to_match_ordered_list` | column_list | Columns in exact order |
| `expect_multicolumn_sum_to_equal` | columns, sum_value | Sum across columns == value |
| `expect_table_row_count_to_equal_other_table` | reference_table | Row count == other table's count |
| `expect_table_schema_to_match` | expected_schema | Schema (names + types) match |

---

## DQ Dimensions

| Dimension | Focus |
|---|---|
| **Completeness** | Are all required values present? |
| **Accuracy** | Are values correct, valid, and within expected ranges? |
| **Integrity** | Are relationships and constraints maintained? |
| **Consistency** | Is data consistent across columns, tables, and time? |

---

## Contributing

PRs require review — direct pushes to `main` are blocked on all Dashlibs repos.

```bash
git clone https://github.com/dash-libs/dash-dq
cd dash-dq
pip install -e ".[dev]"
pytest tests/ -v
```

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
