from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckResult:
    check_name: str
    column: str | None
    passed: bool
    detail: str
    actual_value: Any = None
    threshold: Any = None


def check_no_nulls(df, column: str) -> CheckResult:
    null_count = df.filter(df[column].isNull()).count()
    return CheckResult(
        check_name="no_nulls",
        column=column,
        passed=null_count == 0,
        detail=f"{null_count} nulls found",
        actual_value=null_count,
        threshold=0,
    )


def check_null_rate(df, column: str, max_rate: float) -> CheckResult:
    total = df.count()
    null_count = df.filter(df[column].isNull()).count()
    rate = null_count / total if total > 0 else 0.0
    return CheckResult(
        check_name="null_rate",
        column=column,
        passed=rate <= max_rate,
        detail=f"null rate {rate:.2%} (max {max_rate:.2%})",
        actual_value=round(rate, 4),
        threshold=max_rate,
    )


def check_unique(df, column: str) -> CheckResult:
    total = df.count()
    distinct = df.select(column).distinct().count()
    duplicates = total - distinct
    return CheckResult(
        check_name="unique",
        column=column,
        passed=duplicates == 0,
        detail=f"{duplicates} duplicate values",
        actual_value=duplicates,
        threshold=0,
    )


def check_values_in_set(df, column: str, allowed: list) -> CheckResult:
    invalid = df.filter(~df[column].isin(allowed)).count()
    return CheckResult(
        check_name="values_in_set",
        column=column,
        passed=invalid == 0,
        detail=f"{invalid} rows with values outside allowed set",
        actual_value=invalid,
        threshold=allowed,
    )


def check_column_range(df, column: str, min_val=None, max_val=None) -> CheckResult:
    from pyspark.sql import functions as F
    expr = df
    if min_val is not None:
        expr = expr.filter(F.col(column) < min_val)
    violations = expr
    if max_val is not None:
        violations = df.filter(
            (F.col(column) < (min_val or float("-inf"))) |
            (F.col(column) > max_val)
        )
    count = violations.count()
    return CheckResult(
        check_name="column_range",
        column=column,
        passed=count == 0,
        detail=f"{count} values outside range [{min_val}, {max_val}]",
        actual_value=count,
        threshold=f"[{min_val}, {max_val}]",
    )


def check_regex(df, column: str, pattern: str) -> CheckResult:
    from pyspark.sql import functions as F
    invalid = df.filter(~F.col(column).rlike(pattern)).count()
    return CheckResult(
        check_name="regex",
        column=column,
        passed=invalid == 0,
        detail=f"{invalid} values do not match pattern '{pattern}'",
        actual_value=invalid,
        threshold=pattern,
    )


def check_row_count(df, min_rows: int = 1) -> CheckResult:
    count = df.count()
    return CheckResult(
        check_name="row_count",
        column=None,
        passed=count >= min_rows,
        detail=f"{count} rows (min {min_rows})",
        actual_value=count,
        threshold=min_rows,
    )


def check_freshness(df, timestamp_column: str, max_age_hours: float) -> CheckResult:
    from pyspark.sql import functions as F
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
    stale = df.filter(F.col(timestamp_column) < cutoff).count()
    latest = df.agg(F.max(timestamp_column)).collect()[0][0]
    return CheckResult(
        check_name="freshness",
        column=timestamp_column,
        passed=stale == 0,
        detail=f"Latest record: {latest}. Cutoff: {cutoff}",
        actual_value=str(latest),
        threshold=f"max age {max_age_hours}h",
    )


def check_referential_integrity(df, column: str, ref_df, ref_column: str) -> CheckResult:
    orphans = df.join(ref_df, df[column] == ref_df[ref_column], "left_anti").count()
    return CheckResult(
        check_name="referential_integrity",
        column=column,
        passed=orphans == 0,
        detail=f"{orphans} orphaned rows (no match in reference)",
        actual_value=orphans,
        threshold=0,
    )
