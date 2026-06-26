"""
DashDQ check registry — 60+ native PySpark implementations.
No external dependencies (no great_expectations, no databricks-dqx).

fn signature:
  row-level / aggregate:   fn(df, col, params)            → (total, passed, failed)
  cross-table:             fn(df, col, params, spark)     → (total, passed, failed)
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import re as _re


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
    check_params: str = "{}"
    run_timestamp: str = ""
    data_owner: str = ""
    data_steward: str = ""
    business_domain: str = ""
    table_description: str = ""
    columns_checked: int = 0
    total_columns: int = 0
    column_coverage_pct: float = 0.0
    tags: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _agg_between(val, p) -> tuple:
    lo, hi = p.get("min_value"), p.get("max_value")
    ok = True
    if lo is not None and (val is None or val < lo):
        ok = False
    if hi is not None and (val is None or val > hi):
        ok = False
    return 1, int(ok), int(not ok)


def _get_cols(p, default_col: str) -> list:
    """Parse params['columns'] into a list, falling back to default_col."""
    cols = p.get("columns", default_col)
    if isinstance(cols, str):
        return [c.strip() for c in cols.split(",") if c.strip()]
    return list(cols)


# ═══════════════════════════════════════════════════════════════════════════════
# COMPLETENESS
# ═══════════════════════════════════════════════════════════════════════════════

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


def _not_null_or_empty(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    fail = df.filter(F.col(col).isNull() | (F.trim(F.col(col)) == "")).count()
    return n, n - fail, fail


def _null_count_between(df, col, p):
    from pyspark.sql import functions as F
    null_count = df.filter(F.col(col).isNull()).count()
    return _agg_between(null_count, p)


def _null_proportion_between(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    null_count = df.filter(F.col(col).isNull()).count()
    proportion = null_count / n if n > 0 else 0
    return _agg_between(proportion, p)


# ═══════════════════════════════════════════════════════════════════════════════
# ACCURACY — value checks (row-level)
# ═══════════════════════════════════════════════════════════════════════════════

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


def _not_between(df, col, p):
    from pyspark.sql import functions as F
    lo, hi = p.get("min_value"), p.get("max_value")
    n = df.count()
    cond = F.col(col).isNotNull()
    if lo is not None and hi is not None:
        cond = cond & ((F.col(col) < lo) | (F.col(col) > hi))
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


def _equal_to(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col) == p.get("value")).count()
    return n, ok, n - ok


def _not_equal_to(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col) != p.get("value")).count()
    return n, ok, n - ok


def _not_less_than(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col).isNotNull() & (F.col(col) >= p.get("min_value", 0))).count()
    return n, ok, n - ok


def _not_greater_than(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col).isNotNull() & (F.col(col) <= p.get("max_value", 0))).count()
    return n, ok, n - ok


def _positive(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col).isNotNull() & (F.col(col) > 0)).count()
    return n, ok, n - ok


def _negative(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col).isNotNull() & (F.col(col) < 0)).count()
    return n, ok, n - ok


def _non_negative(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col).isNotNull() & (F.col(col) >= 0)).count()
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


# ── ACCURACY — string / pattern (row-level) ───────────────────────────────────

def _not_empty_string(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    fail = df.filter(F.col(col).isNotNull() & (F.trim(F.col(col)) == "")).count()
    return n, n - fail, fail


def _regex(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col).rlike(p.get("regex", ".*"))).count()
    return n, ok, n - ok


def _not_regex(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    fail = df.filter(F.col(col).isNotNull() & F.col(col).rlike(p.get("regex", "(?!x)x"))).count()
    return n, n - fail, fail


def _regex_list(df, col, p):
    """Values must match at least one regex in the list."""
    from pyspark.sql import functions as F
    patterns = p.get("regex_list", [])
    n = df.count()
    if not patterns:
        return n, n, 0
    combined = "|".join(f"(?:{r})" for r in patterns)
    ok = df.filter(F.col(col).rlike(combined)).count()
    return n, ok, n - ok


def _like_pattern(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col).like(p.get("like_pattern", "%"))).count()
    return n, ok, n - ok


def _not_like_pattern(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    fail = df.filter(F.col(col).isNotNull() & F.col(col).like(p.get("like_pattern", ""))).count()
    return n, n - fail, fail


def _length_between(df, col, p):
    from pyspark.sql import functions as F
    lo, hi = p.get("min_value"), p.get("max_value")
    n = df.count()
    cond = F.col(col).isNotNull()
    if lo is not None:
        cond = cond & (F.length(F.col(col)) >= int(lo))
    if hi is not None:
        cond = cond & (F.length(F.col(col)) <= int(hi))
    ok = df.filter(cond).count()
    return n, ok, n - ok


def _length_equal(df, col, p):
    from pyspark.sql import functions as F
    target = int(p.get("value", 0))
    n = df.count()
    ok = df.filter(F.col(col).isNotNull() & (F.length(F.col(col)) == target)).count()
    return n, ok, n - ok


def _valid_email(df, col, p):
    from pyspark.sql import functions as F
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    n = df.count()
    ok = df.filter(F.col(col).isNotNull() & F.col(col).rlike(pattern)).count()
    return n, ok, n - ok


def _valid_url(df, col, p):
    from pyspark.sql import functions as F
    pattern = r'^https?://[^\s/$.?#].[^\s]*$'
    n = df.count()
    ok = df.filter(F.col(col).isNotNull() & F.col(col).rlike(pattern)).count()
    return n, ok, n - ok


def _valid_ipv4(df, col, p):
    from pyspark.sql import functions as F
    pattern = r'^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$'
    n = df.count()
    ok = df.filter(F.col(col).isNotNull() & F.col(col).rlike(pattern)).count()
    return n, ok, n - ok


def _valid_uuid(df, col, p):
    from pyspark.sql import functions as F
    pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    n = df.count()
    ok = df.filter(F.col(col).isNotNull() & F.col(col).rlike(pattern)).count()
    return n, ok, n - ok


def _json_parseable(df, col, p):
    """Valid JSON: get_json_object returns non-null for valid JSON."""
    from pyspark.sql import functions as F
    n = df.count()
    ok = (df.filter(F.col(col).isNotNull())
            .filter(F.get_json_object(F.col(col), "$").isNotNull())
            .count())
    fail = df.filter(F.col(col).isNotNull()).count() - ok
    return n, n - fail, fail


def _of_type(df, col, p):
    n = df.count()
    want = p.get("type_", "string").lower()
    actual = dict(df.dtypes).get(col, "").lower()
    ok = n if want in actual else 0
    return n, ok, n - ok


def _in_type_list(df, col, p):
    n = df.count()
    type_list = [t.lower() for t in p.get("type_list", [])]
    actual = dict(df.dtypes).get(col, "").lower()
    ok = n if any(t in actual for t in type_list) else 0
    return n, ok, n - ok


# ── ACCURACY — date / time (row-level) ────────────────────────────────────────

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


def _date_parseable(df, col, p):
    """Try multiple common date formats; pass if any succeeds."""
    from pyspark.sql import functions as F
    n = df.count()
    ok = (df.filter(F.col(col).isNotNull())
            .filter(
                F.coalesce(
                    F.to_date(F.col(col).cast("string"), "yyyy-MM-dd"),
                    F.to_date(F.col(col).cast("string"), "MM/dd/yyyy"),
                    F.to_date(F.col(col).cast("string"), "dd-MM-yyyy"),
                    F.to_date(F.col(col).cast("string"), "dd/MM/yyyy"),
                    F.to_date(F.col(col).cast("string"), "yyyyMMdd"),
                ).isNotNull()
            ).count())
    return n, ok, n - ok


def _not_in_future(df, col, p):
    from pyspark.sql import functions as F
    n = df.count()
    ok = df.filter(F.col(col).isNotNull() & (F.col(col).cast("date") <= F.current_date())).count()
    return n, ok, n - ok


def _not_older_than_n_days(df, col, p):
    from pyspark.sql import functions as F
    days = int(p.get("n_days", 30))
    n = df.count()
    cutoff = F.date_sub(F.current_date(), days)
    ok = df.filter(F.col(col).isNotNull() & (F.col(col).cast("date") >= cutoff)).count()
    return n, ok, n - ok


def _data_fresh(df, col, p):
    """Most recent value in col must be within n_minutes of now."""
    from pyspark.sql import functions as F
    minutes = int(p.get("n_minutes", 60))
    latest = df.agg(F.max(col)).collect()[0][0]
    if latest is None:
        return 1, 0, 1
    from datetime import datetime, timezone
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        diff = (cutoff - latest).total_seconds() / 60
        ok = diff <= minutes
    except Exception:
        ok = False
    return 1, int(ok), int(not ok)


def _not_near_future(df, col, p):
    """Values must not be within the next n_days."""
    from pyspark.sql import functions as F
    days = int(p.get("n_days", 1))
    n = df.count()
    upper = F.date_add(F.current_date(), days)
    fail = df.filter(
        F.col(col).isNotNull() &
        (F.col(col).cast("date") > F.current_date()) &
        (F.col(col).cast("date") <= upper)
    ).count()
    return n, n - fail, fail


# ── ACCURACY — custom SQL ─────────────────────────────────────────────────────

def _custom_sql_filter(df, col, p):
    """
    Rows matching sql_filter are FAILED rows.
    Example: sql_filter = "age < 0 OR salary IS NULL"
    """
    from pyspark.sql import functions as F
    sql_filter = p.get("sql_filter", "1=0")
    n = df.count()
    fail = df.filter(sql_filter).count()
    return n, n - fail, fail


# ── ACCURACY — aggregate ──────────────────────────────────────────────────────

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


def _most_common_in_set(df, col, p):
    from pyspark.sql import functions as F
    value_set = p.get("value_set", [])
    rows = df.groupBy(col).count().orderBy(F.col("count").desc()).limit(1).collect()
    ok = len(rows) > 0 and rows[0][0] in value_set
    return 1, int(ok), int(not ok)


def _quantile_between(df, col, p):
    q = float(p.get("quantile", 0.5))
    vals = df.approxQuantile(col, [q], 0.01)
    return _agg_between(vals[0] if vals else None, p)


def _unique_count_between(df, col, p):
    return _agg_between(df.select(col).distinct().count(), p)


def _unique_proportion_between(df, col, p):
    n = df.count()
    val = df.select(col).distinct().count() / n if n > 0 else 0
    return _agg_between(val, p)


def _distinct_in_set(df, col, p):
    """All distinct values must be in value_set."""
    from pyspark.sql import functions as F
    value_set = set(p.get("value_set", []))
    distinct_vals = {r[0] for r in df.select(col).distinct().collect() if r[0] is not None}
    outliers = distinct_vals - value_set
    ok = len(outliers) == 0
    return 1, int(ok), int(not ok)


def _distinct_contains_set(df, col, p):
    """Distinct values must contain all items in value_set."""
    from pyspark.sql import functions as F
    required = set(p.get("value_set", []))
    distinct_vals = {r[0] for r in df.select(col).distinct().collect() if r[0] is not None}
    ok = required.issubset(distinct_vals)
    return 1, int(ok), int(not ok)


def _distinct_equal_set(df, col, p):
    """Distinct values must exactly equal value_set (no more, no less)."""
    from pyspark.sql import functions as F
    expected = set(p.get("value_set", []))
    distinct_vals = {r[0] for r in df.select(col).distinct().collect() if r[0] is not None}
    ok = expected == distinct_vals
    return 1, int(ok), int(not ok)


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════════

def _unique(df, col, p):
    n = df.count()
    dupes = n - df.select(col).distinct().count()
    return n, n - dupes, dupes


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


def _pair_in_set(df, col, p):
    """(colA, colB) tuples must be in valid_pairs list of [a, b] pairs."""
    from pyspark.sql import functions as F
    valid_pairs = [tuple(pair) for pair in p.get("valid_pairs", [])]
    col_b = p.get("column_b", "")
    n = df.count()
    actual_pairs = {tuple(r) for r in df.select(col, col_b).distinct().collect()}
    invalid_pair_vals = actual_pairs - set(valid_pairs)
    if not invalid_pair_vals:
        return n, n, 0
    fail_cond = F.lit(False)
    for a, b in invalid_pair_vals:
        fail_cond = fail_cond | ((F.col(col) == a) & (F.col(col_b) == b))
    fail = df.filter(fail_cond).count()
    return n, n - fail, fail


def _compound_unique(df, col, p):
    """Composite columns must be unique together (no duplicate key combinations)."""
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window
    cols = _get_cols(p, col)
    n = df.count()
    w = Window.partitionBy(cols)
    fail = (df.withColumn("_cnt", F.count("*").over(w))
              .filter(F.col("_cnt") > 1)
              .count())
    return n, n - fail, fail


def _primary_key_valid(df, col, p):
    """
    Composite PK: every column must be NOT NULL and the combination must be unique.
    Fails rows that are null in any PK column OR are part of a duplicate key.
    """
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window
    cols = _get_cols(p, col)
    n = df.count()
    null_cond = F.lit(False)
    for c in cols:
        null_cond = null_cond | F.col(c).isNull()
    w = Window.partitionBy(cols)
    fail = (df.withColumn("_null", null_cond)
              .withColumn("_cnt", F.count("*").over(w))
              .filter(F.col("_null") | (F.col("_cnt") > 1))
              .count())
    return n, n - fail, fail


def _foreign_key(df, col, p, spark):
    """Values in col must exist in reference_table.reference_column (FK check)."""
    from pyspark.sql import functions as F
    ref_table = p.get("reference_table", "")
    ref_col   = p.get("reference_column", col)
    ref_df    = spark.table(ref_table).select(F.col(ref_col).alias("_ref")).distinct()
    n         = df.count()
    # Anti-join: rows in source that have no match in reference (and are not null)
    fail = (df.select(F.col(col).alias("_src"))
              .filter(F.col("_src").isNotNull())
              .join(ref_df, F.col("_src") == F.col("_ref"), "left_anti")
              .count())
    return n, n - fail, fail


def _referential_integrity(df, col, p, spark):
    """
    Bidirectional referential integrity between two tables.
    Checks both that col values exist in reference_table.reference_column
    AND optionally that all reference values are used (no orphans).
    Reports as a single pass/fail.
    """
    from pyspark.sql import functions as F
    ref_table  = p.get("reference_table", "")
    ref_col    = p.get("reference_column", col)
    check_orphans = p.get("check_orphans", False)
    ref_df     = spark.table(ref_table).select(F.col(ref_col).alias("_ref")).distinct()
    n          = df.count()
    fk_fail    = (df.select(F.col(col).alias("_src"))
                    .filter(F.col("_src").isNotNull())
                    .join(ref_df, F.col("_src") == F.col("_ref"), "left_anti")
                    .count())
    orphan_fail = 0
    if check_orphans:
        src_vals = df.select(F.col(col).alias("_src")).distinct()
        orphan_fail = (ref_df.join(src_vals, F.col("_ref") == F.col("_src"), "left_anti")
                             .count())
    fail = fk_fail + orphan_fail
    return n, n - min(fail, n), min(fail, n)


# ═══════════════════════════════════════════════════════════════════════════════
# CONSISTENCY — table-level
# ═══════════════════════════════════════════════════════════════════════════════

def _row_count_between(df, col, p):
    return _agg_between(df.count(), p)


def _row_count_equal(df, col, p):
    return _agg_between(df.count(), {"min_value": p.get("value"), "max_value": p.get("value")})


def _col_count_between(df, col, p):
    return _agg_between(len(df.columns), p)


def _col_count_equal(df, col, p):
    return _agg_between(len(df.columns), {"min_value": p.get("value"), "max_value": p.get("value")})


def _col_to_exist(df, col, p):
    ok = col in df.columns
    return 1, int(ok), int(not ok)


def _columns_match_set(df, col, p):
    expected = set(c.strip() for c in p.get("column_set", "").split(",") if c.strip())
    actual   = set(df.columns)
    ok = expected == actual
    return 1, int(ok), int(not ok)


def _columns_match_ordered_list(df, col, p):
    expected = [c.strip() for c in p.get("column_list", "").split(",") if c.strip()]
    ok = df.columns == expected
    return 1, int(ok), int(not ok)


def _multicolumn_sum_equal(df, col, p):
    from pyspark.sql import functions as F
    cols      = _get_cols(p, col)
    target    = float(p.get("sum_value", 0))
    total_sum = df.agg(F.sum(F.col(cols[0]))).collect()[0][0] or 0
    for c in cols[1:]:
        total_sum += df.agg(F.sum(F.col(c))).collect()[0][0] or 0
    ok = abs(total_sum - target) < 1e-9
    return 1, int(ok), int(not ok)


def _row_count_equal_other_table(df, col, p, spark):
    other_table = p.get("reference_table", "")
    n1 = df.count()
    n2 = spark.table(other_table).count()
    ok = n1 == n2
    return 1, int(ok), int(not ok)


def _schema_valid(df, col, p):
    """Schema (column names and types) must match expected_schema dict."""
    expected = p.get("expected_schema", {})   # {"col_name": "dtype_string"}
    actual   = dict(df.dtypes)
    ok = all(
        col_name in actual and expected[col_name].lower() in actual[col_name].lower()
        for col_name in expected
    )
    return 1, int(ok), int(not ok)


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

CHECKS_REGISTRY: dict[str, dict] = {

    # ── Completeness ─────────────────────────────────────────────────────────
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
    "expect_column_values_to_not_be_null_or_empty": {
        "dimension": "Completeness",
        "description": "Values must not be null and must not be an empty/whitespace string",
        "params": [],
        "fn": _not_null_or_empty,
    },
    "expect_column_null_count_to_be_between": {
        "dimension": "Completeness",
        "description": "Number of null values must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _null_count_between,
        "aggregate": True,
    },
    "expect_column_null_proportion_to_be_between": {
        "dimension": "Completeness",
        "description": "Proportion of null values (0–1) must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _null_proportion_between,
        "aggregate": True,
    },

    # ── Accuracy — numeric / value ────────────────────────────────────────────
    "expect_column_values_to_be_between": {
        "dimension": "Accuracy",
        "description": "Values must fall within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _between,
    },
    "expect_column_values_to_not_be_between": {
        "dimension": "Accuracy",
        "description": "Values must fall outside [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _not_between,
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
    "expect_column_values_to_equal": {
        "dimension": "Accuracy",
        "description": "All values must equal the specified constant",
        "params": ["value"],
        "fn": _equal_to,
    },
    "expect_column_values_to_not_equal": {
        "dimension": "Accuracy",
        "description": "No values may equal the specified constant",
        "params": ["value"],
        "fn": _not_equal_to,
    },
    "expect_column_values_to_be_not_less_than": {
        "dimension": "Accuracy",
        "description": "Values must be >= min_value",
        "params": ["min_value"],
        "fn": _not_less_than,
    },
    "expect_column_values_to_be_not_greater_than": {
        "dimension": "Accuracy",
        "description": "Values must be <= max_value",
        "params": ["max_value"],
        "fn": _not_greater_than,
    },
    "expect_column_values_to_be_positive": {
        "dimension": "Accuracy",
        "description": "Values must be strictly positive (> 0)",
        "params": [],
        "fn": _positive,
    },
    "expect_column_values_to_be_negative": {
        "dimension": "Accuracy",
        "description": "Values must be strictly negative (< 0)",
        "params": [],
        "fn": _negative,
    },
    "expect_column_values_to_be_non_negative": {
        "dimension": "Accuracy",
        "description": "Values must be zero or positive (>= 0)",
        "params": [],
        "fn": _non_negative,
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

    # ── Accuracy — string / pattern ───────────────────────────────────────────
    "expect_column_values_to_not_be_empty_string": {
        "dimension": "Accuracy",
        "description": "Non-null values must not be empty or whitespace-only",
        "params": [],
        "fn": _not_empty_string,
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
    "expect_column_values_to_match_regex_list": {
        "dimension": "Accuracy",
        "description": "Values must match at least one regex in the list",
        "params": ["regex_list"],
        "fn": _regex_list,
    },
    "expect_column_values_to_match_like_pattern": {
        "dimension": "Accuracy",
        "description": "Values must match the SQL LIKE pattern (% and _ wildcards)",
        "params": ["like_pattern"],
        "fn": _like_pattern,
    },
    "expect_column_values_to_not_match_like_pattern": {
        "dimension": "Accuracy",
        "description": "Values must not match the SQL LIKE pattern",
        "params": ["like_pattern"],
        "fn": _not_like_pattern,
    },
    "expect_column_value_lengths_to_be_between": {
        "dimension": "Accuracy",
        "description": "String length must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _length_between,
    },
    "expect_column_value_lengths_to_equal": {
        "dimension": "Accuracy",
        "description": "String length must equal the specified value",
        "params": ["value"],
        "fn": _length_equal,
    },
    "expect_column_values_to_be_of_type": {
        "dimension": "Accuracy",
        "description": "Column dtype must contain the specified type string (e.g. 'int', 'string')",
        "params": ["type_"],
        "fn": _of_type,
    },
    "expect_column_values_to_be_in_type_list": {
        "dimension": "Accuracy",
        "description": "Column dtype must match one of the types in type_list",
        "params": ["type_list"],
        "fn": _in_type_list,
    },
    "expect_column_values_to_be_valid_email": {
        "dimension": "Accuracy",
        "description": "Values must be valid email addresses",
        "params": [],
        "fn": _valid_email,
    },
    "expect_column_values_to_be_valid_url": {
        "dimension": "Accuracy",
        "description": "Values must be valid HTTP/HTTPS URLs",
        "params": [],
        "fn": _valid_url,
    },
    "expect_column_values_to_be_valid_ipv4": {
        "dimension": "Accuracy",
        "description": "Values must be valid IPv4 addresses (e.g. 192.168.1.1)",
        "params": [],
        "fn": _valid_ipv4,
    },
    "expect_column_values_to_be_valid_uuid": {
        "dimension": "Accuracy",
        "description": "Values must be valid UUIDs (8-4-4-4-12 hex format)",
        "params": [],
        "fn": _valid_uuid,
    },
    "expect_column_values_to_be_json_parseable": {
        "dimension": "Accuracy",
        "description": "Values must be valid JSON strings",
        "params": [],
        "fn": _json_parseable,
    },

    # ── Accuracy — date / time ────────────────────────────────────────────────
    "expect_column_values_to_match_strftime_format": {
        "dimension": "Accuracy",
        "description": "Values must match the strftime date format (e.g. %Y-%m-%d)",
        "params": ["strftime_format"],
        "fn": _strftime,
    },
    "expect_column_values_to_be_dateutil_parseable": {
        "dimension": "Accuracy",
        "description": "Values must be parseable as a date in any common format",
        "params": [],
        "fn": _date_parseable,
    },
    "expect_column_values_to_not_be_in_future": {
        "dimension": "Accuracy",
        "description": "Date/timestamp values must not be in the future",
        "params": [],
        "fn": _not_in_future,
    },
    "expect_column_values_to_be_not_older_than_n_days": {
        "dimension": "Accuracy",
        "description": "Date values must be within the last n_days",
        "params": ["n_days"],
        "fn": _not_older_than_n_days,
    },
    "expect_column_values_to_not_be_in_near_future": {
        "dimension": "Accuracy",
        "description": "Values must not fall within the next n_days",
        "params": ["n_days"],
        "fn": _not_near_future,
    },
    "expect_column_data_to_be_fresh": {
        "dimension": "Accuracy",
        "description": "Most recent value in column must be within n_minutes of now",
        "params": ["n_minutes"],
        "fn": _data_fresh,
        "aggregate": True,
    },

    # ── Accuracy — custom SQL ─────────────────────────────────────────────────
    "expect_column_values_to_pass_custom_sql_filter": {
        "dimension": "Accuracy",
        "description": "Rows matching sql_filter are FAILED rows (write a WHERE clause for bad data)",
        "params": ["sql_filter"],
        "fn": _custom_sql_filter,
    },

    # ── Accuracy — aggregate ──────────────────────────────────────────────────
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
    "expect_column_quantile_value_to_be_between": {
        "dimension": "Accuracy",
        "description": "Column quantile (0–1) must be within [min_value, max_value]",
        "params": ["quantile", "min_value", "max_value"],
        "fn": _quantile_between,
        "aggregate": True,
    },
    "expect_column_distinct_values_to_be_in_set": {
        "dimension": "Accuracy",
        "description": "All distinct values must be in value_set (no unlisted values allowed)",
        "params": ["value_set"],
        "fn": _distinct_in_set,
        "aggregate": True,
    },
    "expect_column_distinct_values_to_contain_set": {
        "dimension": "Accuracy",
        "description": "Distinct values must include all items in value_set",
        "params": ["value_set"],
        "fn": _distinct_contains_set,
        "aggregate": True,
    },
    "expect_column_distinct_values_to_equal_set": {
        "dimension": "Accuracy",
        "description": "Distinct values must exactly match value_set (no extras, no missing)",
        "params": ["value_set"],
        "fn": _distinct_equal_set,
        "aggregate": True,
    },

    # ── Integrity ─────────────────────────────────────────────────────────────
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
    "expect_column_pair_values_to_be_in_set": {
        "dimension": "Integrity",
        "description": "Row-wise (colA, colB) value pairs must be in valid_pairs",
        "params": ["column_b", "valid_pairs"],
        "fn": _pair_in_set,
    },
    "expect_compound_columns_to_be_unique": {
        "dimension": "Integrity",
        "description": "Combination of columns must be unique across all rows",
        "params": ["columns"],
        "fn": _compound_unique,
        "compound": True,
    },
    "expect_primary_key_to_be_valid": {
        "dimension": "Integrity",
        "description": "PK columns must all be non-null AND the combination must be unique",
        "params": ["columns"],
        "fn": _primary_key_valid,
        "compound": True,
    },
    "expect_column_values_to_exist_in_reference_table": {
        "dimension": "Integrity",
        "description": "Values must exist in reference_table.reference_column (foreign key check)",
        "params": ["reference_table", "reference_column"],
        "fn": _foreign_key,
        "cross_table": True,
    },
    "expect_referential_integrity": {
        "dimension": "Integrity",
        "description": "Full referential integrity check between tables; optionally checks orphans too",
        "params": ["reference_table", "reference_column", "check_orphans"],
        "fn": _referential_integrity,
        "cross_table": True,
    },

    # ── Consistency — table-level ─────────────────────────────────────────────
    "expect_table_row_count_to_be_between": {
        "dimension": "Consistency",
        "description": "Table row count must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _row_count_between,
        "table_level": True,
        "aggregate": True,
    },
    "expect_table_row_count_to_equal": {
        "dimension": "Consistency",
        "description": "Table row count must equal value exactly",
        "params": ["value"],
        "fn": _row_count_equal,
        "table_level": True,
        "aggregate": True,
    },
    "expect_table_column_count_to_be_between": {
        "dimension": "Consistency",
        "description": "Number of columns must be within [min_value, max_value]",
        "params": ["min_value", "max_value"],
        "fn": _col_count_between,
        "table_level": True,
        "aggregate": True,
    },
    "expect_table_column_count_to_equal": {
        "dimension": "Consistency",
        "description": "Number of columns must equal value exactly",
        "params": ["value"],
        "fn": _col_count_equal,
        "table_level": True,
        "aggregate": True,
    },
    "expect_column_to_exist": {
        "dimension": "Consistency",
        "description": "The specified column must exist in the table",
        "params": [],
        "fn": _col_to_exist,
        "table_level": True,
        "aggregate": True,
    },
    "expect_table_columns_to_match_set": {
        "dimension": "Consistency",
        "description": "Table column names must exactly match column_set (order-independent)",
        "params": ["column_set"],
        "fn": _columns_match_set,
        "table_level": True,
        "aggregate": True,
    },
    "expect_table_columns_to_match_ordered_list": {
        "dimension": "Consistency",
        "description": "Table columns must match column_list in exact order",
        "params": ["column_list"],
        "fn": _columns_match_ordered_list,
        "table_level": True,
        "aggregate": True,
    },
    "expect_multicolumn_sum_to_equal": {
        "dimension": "Consistency",
        "description": "Sum of all values across columns must equal sum_value",
        "params": ["columns", "sum_value"],
        "fn": _multicolumn_sum_equal,
        "compound": True,
        "aggregate": True,
    },
    "expect_table_row_count_to_equal_other_table": {
        "dimension": "Consistency",
        "description": "This table's row count must equal reference_table's row count",
        "params": ["reference_table"],
        "fn": _row_count_equal_other_table,
        "table_level": True,
        "cross_table": True,
        "aggregate": True,
    },
    "expect_table_schema_to_match": {
        "dimension": "Consistency",
        "description": "Table schema must match expected_schema dict {col_name: dtype_string}",
        "params": ["expected_schema"],
        "fn": _schema_valid,
        "table_level": True,
        "aggregate": True,
    },
}
