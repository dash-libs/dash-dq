"""run_checks(config) → DQReport.  One result row per check × column."""
from __future__ import annotations
import json
from datetime import datetime
from dashdq.checks import CHECKS_REGISTRY, CheckResult


class DQReport:
    def __init__(self, results: list[CheckResult], config: dict):
        self.results = results
        self.config = config

    # ── Outputs ───────────────────────────────────────────────────────────────

    def to_dict(self) -> list[dict]:
        return [r.to_dict() for r in self.results]

    def to_spark_df(self, spark=None):
        if spark is None:
            from pyspark.sql import SparkSession
            spark = SparkSession.getActiveSession()
        return spark.createDataFrame([r.to_dict() for r in self.results])

    def to_pandas(self):
        import pandas as pd
        return pd.DataFrame(self.to_dict())

    def display(self):
        try:
            from IPython.display import display as ipy_display
            ipy_display(self.to_pandas())
        except Exception:
            for r in self.results:
                print(r)

    def summary(self) -> dict:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "PASS")
        return {
            "total_checks": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate_pct": round(passed / total * 100, 1) if total else 0,
        }

    def save(self, output_cfg: dict, spark=None):
        """Persist results according to output_cfg (from configure())."""
        otype = output_cfg.get("type", "dataframe")

        if otype == "dataframe":
            return self.to_spark_df(spark)

        if otype == "delta":
            sdf = self.to_spark_df(spark)
            table = output_cfg["delta_table"]
            (sdf.write.format("delta")
                .mode("append")
                .option("mergeSchema", "true")
                .saveAsTable(table))
            print(f"✅ Saved to Delta table: {table}")
            return sdf

        if otype in ("volume_json", "volume_csv"):
            import os
            path = output_cfg.get("volume_path", "").rstrip("/")
            filename = output_cfg.get("filename", f"dq_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            ext = "json" if otype == "volume_json" else "csv"
            full = f"{path}/{filename}.{ext}"
            pdf = self.to_pandas()
            os.makedirs(path, exist_ok=True)
            if ext == "json":
                pdf.to_json(full, orient="records", indent=2)
            else:
                pdf.to_csv(full, index=False)
            print(f"✅ Saved to: {full}")
            return full

        return self.to_spark_df(spark)


def run_checks(config: dict, spark=None) -> DQReport:
    """
    Execute all checks defined in config and return a DQReport.

    config shape::

        {
            "source":   {"table": "catalog.schema.table"},
            "metadata": {"data_owner": "", "data_steward": "", ...},  # optional
            "checks": [
                {"check_name": "expect_column_values_to_not_be_null",
                 "column": "customer_id",
                 "threshold_pct": 100.0,
                 "params": {}},
                ...
            ],
            "output":   {"type": "delta", "delta_table": "..."}       # optional
        }
    """
    if not config:
        raise ValueError("Config is empty — run dashdq.configure() first and click 'Save Config'.")

    if spark is None:
        from pyspark.sql import SparkSession
        spark = SparkSession.getActiveSession()

    table = config["source"]["table"]
    df = spark.table(table)
    total_cols = len(df.columns)
    metadata = config.get("metadata", {})
    run_ts = datetime.now().isoformat(timespec="seconds")

    checked_cols: set[str] = set()
    results: list[CheckResult] = []

    for chk in config.get("checks", []):
        name = chk["check_name"]
        col = chk.get("column", "_TABLE_LEVEL_")
        threshold = float(chk.get("threshold_pct", 100.0))
        params = chk.get("params", {})

        entry = CHECKS_REGISTRY.get(name)
        if not entry:
            continue

        try:
            total, passed, failed = entry["fn"](df, col, params)
            passed_pct = round(passed / total * 100, 2) if total > 0 else 0.0
            status = "PASS" if passed_pct >= threshold else "FAIL"
            if not entry.get("table_level"):
                checked_cols.add(col)
        except Exception as exc:
            total = passed = failed = 0
            passed_pct = 0.0
            status = f"ERROR: {exc}"

        results.append(CheckResult(
            table_name=table,
            column_name=col,
            check_name=name,
            dq_dimension=entry["dimension"],
            total_rows=total,
            passed_rows=passed,
            failed_rows=failed,
            passed_pct=passed_pct,
            threshold_pct=threshold,
            status=status,
            check_params=json.dumps(params),
            run_timestamp=run_ts,
            data_owner=metadata.get("data_owner", ""),
            data_steward=metadata.get("data_steward", ""),
            business_domain=metadata.get("business_domain", ""),
            table_description=metadata.get("description", ""),
            columns_checked=0,       # back-filled below
            total_columns=total_cols,
            column_coverage_pct=0.0,
        ))

    # Back-fill coverage (same value for all rows — table-level metric)
    n_covered = len(checked_cols)
    coverage = round(n_covered / total_cols * 100, 2) if total_cols else 0.0
    for r in results:
        r.columns_checked = n_covered
        r.column_coverage_pct = coverage

    report = DQReport(results, config)

    # Auto-save if output block present and not dataframe-only
    output_cfg = config.get("output", {})
    if output_cfg and output_cfg.get("type", "dataframe") != "dataframe":
        report.save(output_cfg, spark)

    return report
