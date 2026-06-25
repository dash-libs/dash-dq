from __future__ import annotations
from typing import Optional
import json
from dashdq import checks as C
from dashdq.checks import CheckResult


class DQSuite:
    """
    Programmatic API for data quality checks.

    Usage::
        suite = DQSuite(df)
        suite.expect_no_nulls("customer_id")
        suite.expect_unique("account_number")
        report = suite.run()
    """

    def __init__(self, df=None, table: str = None, query: str = None):
        self._df = self._resolve_input(df, table, query)
        self._rules: list[dict] = []

    def _resolve_input(self, df, table, query):
        if df is not None:
            return df
        try:
            from pyspark.sql import SparkSession
            spark = SparkSession.getActiveSession()
            if table:
                return spark.table(table)
            if query:
                return spark.sql(query)
        except Exception as e:
            raise ValueError(f"Could not load data: {e}")
        raise ValueError("Provide df, table, or query")

    def expect_no_nulls(self, column: str):
        self._rules.append({"type": "no_nulls", "column": column})
        return self

    def expect_null_rate(self, column: str, max_rate: float):
        self._rules.append({"type": "null_rate", "column": column, "max_rate": max_rate})
        return self

    def expect_unique(self, column: str):
        self._rules.append({"type": "unique", "column": column})
        return self

    def expect_values_in_set(self, column: str, allowed: list):
        self._rules.append({"type": "values_in_set", "column": column, "allowed": allowed})
        return self

    def expect_column_range(self, column: str, min_val=None, max_val=None):
        self._rules.append({"type": "column_range", "column": column, "min_val": min_val, "max_val": max_val})
        return self

    def expect_regex(self, column: str, pattern: str):
        self._rules.append({"type": "regex", "column": column, "pattern": pattern})
        return self

    def expect_min_rows(self, min_rows: int):
        self._rules.append({"type": "row_count", "min_rows": min_rows})
        return self

    def expect_freshness(self, timestamp_column: str, max_age_hours: float):
        self._rules.append({"type": "freshness", "column": timestamp_column, "max_age_hours": max_age_hours})
        return self

    def from_config(self, config: dict):
        """Load rules from a dict (used by the UI)."""
        self._rules = config.get("rules", [])
        return self

    def run(self, save_to: Optional[str] = None) -> "DQReport":
        results = []
        for rule in self._rules:
            rtype = rule["type"]
            col = rule.get("column")
            if rtype == "no_nulls":
                results.append(C.check_no_nulls(self._df, col))
            elif rtype == "null_rate":
                results.append(C.check_null_rate(self._df, col, rule["max_rate"]))
            elif rtype == "unique":
                results.append(C.check_unique(self._df, col))
            elif rtype == "values_in_set":
                results.append(C.check_values_in_set(self._df, col, rule["allowed"]))
            elif rtype == "column_range":
                results.append(C.check_column_range(self._df, col, rule.get("min_val"), rule.get("max_val")))
            elif rtype == "regex":
                results.append(C.check_regex(self._df, col, rule["pattern"]))
            elif rtype == "row_count":
                results.append(C.check_row_count(self._df, rule["min_rows"]))
            elif rtype == "freshness":
                results.append(C.check_freshness(self._df, col, rule["max_age_hours"]))

        report = DQReport(results)
        if save_to:
            report.save(save_to)
        return report


class DQReport:
    def __init__(self, results: list[CheckResult]):
        self.results = results
        self.passed = sum(1 for r in results if r.passed)
        self.failed = sum(1 for r in results if not r.passed)
        self.total = len(results)

    def summary(self) -> str:
        status = "✅ PASSED" if self.failed == 0 else "❌ FAILED"
        return f"{status} — {self.passed}/{self.total} checks passed"

    def to_dict(self) -> list[dict]:
        return [
            {
                "check": r.check_name,
                "column": r.column,
                "passed": r.passed,
                "detail": r.detail,
                "actual": str(r.actual_value),
                "threshold": str(r.threshold),
            }
            for r in self.results
        ]

    def to_spark_df(self):
        from pyspark.sql import SparkSession
        spark = SparkSession.getActiveSession()
        return spark.createDataFrame(self.to_dict())

    def save(self, delta_table: str):
        from pyspark.sql import functions as F
        df = self.to_spark_df().withColumn("run_ts", F.current_timestamp())
        df.write.format("delta").mode("append").saveAsTable(delta_table)
        print(f"Results saved to {delta_table}")

    def display(self):
        try:
            from IPython.display import display as ipy_display
            import pandas as pd
            df = pd.DataFrame(self.to_dict())
            df["status"] = df["passed"].map({True: "✅", False: "❌"})
            ipy_display(df[["status", "check", "column", "detail"]])
        except Exception:
            print(self.summary())
            for r in self.results:
                icon = "✅" if r.passed else "❌"
                print(f"  {icon} {r.check_name} [{r.column}]: {r.detail}")

    def __repr__(self):
        return self.summary()
