"""
Check registry — GE-style naming, pure PySpark implementations.
Each entry: dimension, description, params list, fn(df, col, params) -> (total, passed, failed).
"""
from __future__ import annotations
from dataclasses import dataclass


DQ_DIMENSIONS = ["Completeness", "Accuracy", "Integrity", "Consistency"]

DIMENSION_COLORS = {
    "Completeness": "#1565C0",
    "Accuracy":     "#2E7D32",
    "Integrity":    "#6A1B9A",
    "Consistency":  "#E65100",
}


@dataclass
class CheckResult:
    table_name: str
    column_name: str
    check_name: str
    dq_dimension: str
    total_rows: int
    passed_rows: int
    failed_rows: int
    passed_pct: float
    threshold_pct: float
    status: str                    # PASS | FAIL | ERROR
    check_params: str = "{}"       # JSON string
    run_timestamp: str = ""
    data_owner: str = ""
    data_steward: str = ""
    business_domain: str = ""
    table_description: str = ""
    columns_checked: int = 0
    total_columns: int = 0
    column_coverage_pct: float = 0.0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


# ── Row-level check implementations ──────────────────────────────────────────

def _not_null(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    fail = df.filter(F.col(col).isNull()).count()
    return n, n - fail, fail


def _is_null(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col).isNull()).count()
    return n, ok, n - ok


def _unique(df, col, p):
    n = df.count()
    dupes = n - df.select(col).distinct().count()
    return n, n - dupes, dupes


def _between(df, col, p):
    from pyspark.sql import functions as F
    lo, hi = p.get("min_value"), p.get("max_value")
    n = df.count()
    cond = F.col(col).isNotNull()
    if lo is not None:
        cond = cond & (F.col(col) >= lo)
    if hi is not None:
        cond = cond & (F.col(col) <= hi)
    ok = df.filter(cond).count()
    return n, ok, n - ok


def _in_set(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col).isin(p.get("value_set", []))).count()
    return n, ok, n - ok


def _not_in_set(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    fail = df.filter(F.col(col).isin(p.get("value_set", []))).count()
    return n, n - fail, fail


def _regex(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col).rlike(p.get("regex", ".*"))).count()
    return n, ok, n - ok


def _not_regex(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    fail = df.filter(F.col(col).rlike(p.get("regex", ".*"))).count()
    return n, n - fail, fail


def _of_type(df, col, p):
    n = df.count()
    want = p.get("type_", "string").lower()
    actual = dict(df.dtypes).get(col, "").lower()
    ok = n if want in actual else 0
    return n, ok, n - ok


def _strftime(df, col, p):
    from pyspark.sql import functions as F
    fmt = p.get("strftime_format", "%Y-%m-%d")
    spark_fmt = (fmt
                 .replace("%Y", "yyyy").replace("%m", "MM").replace("%d", "dd")
                 .replace("%H", "HH").replace("%M", "mm").replace("%S", "ss"))
    n = df.count()
    ok = (df.filter(F.col(col).isNotNull())
            .filter(F.to_date(F.col(col).cast("string"), spark_fmt).isNotNull())
            .count())
    return n, ok, n - ok


def _increasing(df, col, p):
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window
    n = df.count()
    w = Window.orderBy(F.monotonically_increasing_id())
    fail = (df.withColumn("_prev", F.lag(col).over(w))
              .filter(F.col("_prev").isNotNull() & (F.col(col) < F.col("_prev")))
              .count())
    return n, n - fail, fail


def _decreasing(df, col, p):
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window
    n = df.count()
    w = Window.orderBy(F.monotonically_increasing_id())
    fail = (df.withColumn("_prev", F.lag(col).over(w))
              .filter(F.col("_prev").isNotNull() & (F.col(col) > F.col("_prev")))
              .count())
    return n, n - fail, fail


def _pair_equal(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col) == F.col(p.get("column_b", ""))).count()
    return n, ok, n - ok


def _pair_greater(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col) > F.col(p.get("column_b", ""))).count()
    return n, ok, n - ok


# ── Aggregate helpers (1-row virtual result) ──────────────────────────────────

def _agg_between(val, p):
    lo, hi = p.get("min_value"), p.get("max_value")
    ok = True
    if lo is not None and (val is None or val < lo):
        ok = False
    if hi is not None and (val is None or val > hi):
        ok = False
    return 1, int(ok), int(not ok)


def _mean_between(df, col, p):
    from pyspark.sql import functions as F
    return _agg_between(df.agg(F.mean(col)).collect()[0][0], p)


def _median_between(df, col, p):
    vals = df.approxQuantile(col, [0.5], 0.01)
    return _agg_between(vals[0] if vals else None, p)


def _stdev_between(df, col, p):
    from pyspark.sql import functions as F
    return _agg_between(df.agg(F.stddev(col)).collect()[0][0], p)


def _max_between(df, col, p):
    from pyspark.sql import functions as F
    return _agg_between(df.agg(F.max(col)).collect()[0][0], p)


def _min_between(df, col, p):
    from pyspark.sql import functions as F
    return _agg_between(df.agg(F.min(col)).collect()[0][0], p)


def _sum_between(df, col, p):
    from pyspark.sql import functions as F
    return _agg_between(df.agg(F.sum(col)).collect()[0][0], p)


def _unique_count_between(df, col, p):
    return _agg_between(df.select(col).distinct().count(), p)


def _unique_proportion_between(df, col, p):
    n = df.count()
    val = df.select(col).distinct().count() / n if n > 0 else 0
    return _agg_between(val, p)


def _most_common_in_set(df, col, p):
    from pyspark.sql import functions as F
    value_set = p.get("value_set", [])
    rows = df.groupBy(col).count().orderBy(F.col("count").desc()).limit(1).collect()
    ok = len(rows) > 0 and rows[0][0] in value_set
    return 1, int(ok), int(not ok)


def _row_count_between(df, col, p):
    return _agg_between(df.count(), p)


def _col_count_between(df, col, p):
    return _agg_between(len(df.columns), p)


# ── Registry ──────────────────────────────────────────────────────────────────

CHECKS_REGISTRY: dict[str, dict] = {
    # Completeness
    "expect_column_values_to_not_be_null": {
        "dimension": "Completeness",
        "description": "Values must not be null",
        "params": [],
        "fn": _not_null,
    },
    "expect_column_values_to_be_null": {
        "dimension": "Completeness",
        "description": "Values must be null",
        "params": [],
        "fn": _is_null,
    },
    # Accuracy — value checks
    "expect_column_values_to_be_between": {
        "dimension": "Accuracy",
        "description": "Values must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _between,
    },
    "expect_column_values_to_be_in_set": {
        "dimension": "Accuracy",
        "description": "Values must belong to the allowed set",
        "params": ["value_set"],
        "fn": _in_set,
    },
    "expect_column_values_to_not_be_in_set": {
        "dimension": "Accuracy",
        "description": "Values must not belong to the disallowed set",
        "params": ["value_set"],
        "fn": _not_in_set,
    },
    "expect_column_values_to_match_regex": {
        "dimension": "Accuracy",
        "description": "Values must match the regular expression",
        "params": ["regex"],
        "fn": _regex,
    },
    "expect_column_values_to_not_match_regex": {
        "dimension": "Accuracy",
        "description": "Values must not match the regular expression",
        "params": ["regex"],
        "fn": _not_regex,
    },
    "expect_column_values_to_be_of_type": {
        "dimension": "Accuracy",
        "description": "Column dtype must contain the specified type string",
        "params": ["type_"],
        "fn": _of_type,
    },
    "expect_column_values_to_match_strftime_format": {
        "dimension": "Accuracy",
        "description": "Values must match the strftime format (e.g. %Y-%m-%d)",
        "params": ["strftime_format"],
        "fn": _strftime,
    },
    "expect_column_values_to_be_increasing": {
        "dimension": "Accuracy",
        "description": "Values must be non-decreasing in row order",
        "params": [],
        "fn": _increasing,
    },
    "expect_column_values_to_be_decreasing": {
        "dimension": "Accuracy",
        "description": "Values must be non-increasing in row order",
        "params": [],
        "fn": _decreasing,
    },
    # Accuracy — aggregate checks
    "expect_column_mean_to_be_between": {
        "dimension": "Accuracy",
        "description": "Column mean must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _mean_between,
        "aggregate": True,
    },
    "expect_column_median_to_be_between": {
        "dimension": "Accuracy",
        "description": "Column median must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _median_between,
        "aggregate": True,
    },
    "expect_column_stdev_to_be_between": {
        "dimension": "Accuracy",
        "description": "Standard deviation must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _stdev_between,
        "aggregate": True,
    },
    "expect_column_max_to_be_between": {
        "dimension": "Accuracy",
        "description": "Column maximum must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _max_between,
        "aggregate": True,
    },
    "expect_column_min_to_be_between": {
        "dimension": "Accuracy",
        "description": "Column minimum must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _min_between,
        "aggregate": True,
    },
    "expect_column_sum_to_be_between": {
        "dimension": "Accuracy",
        "description": "Column sum must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _sum_between,
        "aggregate": True,
    },
    "expect_column_most_common_value_to_be_in_set": {
        "dimension": "Accuracy",
        "description": "Most frequent value must be in the allowed set",
        "params": ["value_set"],
        "fn": _most_common_in_set,
        "aggregate": True,
    },
    # Integrity
    "expect_column_values_to_be_unique": {
        "dimension": "Integrity",
        "description": "All values must be unique — no duplicates",
        "params": [],
        "fn": _unique,
    },
    "expect_column_unique_value_count_to_be_between": {
        "dimension": "Integrity",
        "description": "Distinct value count must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _unique_count_between,
        "aggregate": True,
    },
    "expect_column_proportion_of_unique_values_to_be_between": {
        "dimension": "Integrity",
        "description": "Proportion of unique values (0–1) must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _unique_proportion_between,
        "aggregate": True,
    },
    "expect_column_pair_values_to_be_equal": {
        "dimension": "Integrity",
        "description": "Values in this column must equal values in column_b (row-wise)",
        "params": ["column_b"],
        "fn": _pair_equal,
    },
    "expect_column_pair_values_a_to_be_greater_than_b": {
        "dimension": "Integrity",
        "description": "Values in this column must be greater than values in column_b",
        "params": ["column_b"],
        "fn": _pair_greater,
    },
    # Consistency — table-level
    "expect_table_row_count_to_be_between": {
        "dimension": "Consistency",
        "description": "Table row count must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _row_count_between,
        "table_level": True,
        "aggregate": True,
    },
    "expect_table_column_count_to_be_between": {
        "dimension": "Consistency",
        "description": "Number of table columns must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _col_count_between,
        "table_level": True,
        "aggregate": True,
    },
}
