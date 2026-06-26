"""run_checks(config) → DQReport.  One result row per check × column."""
from __future__ import annotations
import json
from datetime import datetime
from dashdq.checks import CHECKS_REGISTRY, CheckResult


class DQReport:
    def __init__(self, results: list[CheckResult], config: dict):
        self.results = results
        self.config = config

    # ── Row-level outputs (one row per check × column) ────────────────────────

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

    # ── Table-level summary (one row per table run) ───────────────────────────

    def table_summary(self) -> dict:
        """Single-row summary at table level.

        clean_records = rows that passed every column check applied to them.
        overall_status = PASS only if all checks passed.
        """
        if not self.results:
            return {}

        r0 = self.results[0]
        metadata = self.config.get("metadata", {})
        total_rows = r0.total_rows
        total_checks = len(self.results)
        passed_checks = sum(1 for r in self.results if r.status == "PASS")
        failed_checks = total_checks - passed_checks
        overall_status = "PASS" if failed_checks == 0 else "FAIL"

        # Clean records: rows not flagged as failed by ANY check.
        # Each check reports failed_rows independently; we sum them as a
        # conservative lower-bound on dirty rows (exact intersection needs a join).
        total_failed_rows = sum(r.failed_rows for r in self.results)
        # Cap at total_rows to avoid negative clean counts when checks overlap
        dirty_rows = min(total_failed_rows, total_rows) if total_rows else 0
        clean_rows = max(0, total_rows - dirty_rows)
        clean_pct = round(clean_rows / total_rows * 100, 2) if total_rows else 0.0

        return {
            "table_name":          r0.table_name,
            "overall_status":      overall_status,
            "total_rows":          total_rows,
            "clean_rows":          clean_rows,
            "dirty_rows":          dirty_rows,
            "clean_pct":           clean_pct,
            "total_checks":        total_checks,
            "passed_checks":       passed_checks,
            "failed_checks":       failed_checks,
            "columns_checked":     r0.columns_checked,
            "total_columns":       r0.total_columns,
            "column_coverage_pct": r0.column_coverage_pct,
            "run_timestamp":       r0.run_timestamp,
            "data_owner":          metadata.get("data_owner", ""),
            "data_steward":        metadata.get("data_steward", ""),
            "business_domain":     metadata.get("business_domain", ""),
            "description":         metadata.get("description", ""),
            "tags":                ",".join(metadata.get("tags", [])),
        }

    def to_table_summary_df(self, spark=None):
        """Spark DataFrame with one row summarising this table run."""
        if spark is None:
            from pyspark.sql import SparkSession
            spark = SparkSession.getActiveSession()
        return spark.createDataFrame([self.table_summary()])

    def table_summary_pandas(self):
        import pandas as pd
        return pd.DataFrame([self.table_summary()])

    def save_table_summary(self, output_cfg: dict, spark=None):
        """Persist the table-level summary row to configured destinations."""
        import os

        types = output_cfg.get("types") or (
            [output_cfg["type"]] if "type" in output_cfg else ["dataframe"]
        )
        summary = self.table_summary()
        if not summary:
            return

        for otype in types:
            if otype == "delta":
                if spark is None:
                    from pyspark.sql import SparkSession
                    spark = SparkSession.getActiveSession()
                table = output_cfg.get("delta_table", "")
                if not table:
                    print("⚠️  delta_table not set — skipping Delta summary output")
                    continue
                (self.to_table_summary_df(spark)
                    .write.format("delta")
                    .mode("append")
                    .option("mergeSchema", "true")
                    .saveAsTable(table))
                print(f"✅ Saved table summary to Delta: {table}")

            elif otype in ("volume_json", "volume_csv"):
                vol_path = output_cfg.get("volume_path", "").rstrip("/")
                table_name = self.config.get("source", {}).get("table", "")
                tbl = table_name.split(".")[-1] if table_name else "table"
                filename = (
                    output_cfg.get("filename")
                    or f"dq_{tbl}_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )
                ext = "json" if otype == "volume_json" else "csv"
                os.makedirs(vol_path, exist_ok=True)
                full = f"{vol_path}/{filename}.{ext}"
                import pandas as pd
                spdf = pd.DataFrame([summary])
                if ext == "json":
                    spdf.to_json(full, orient="records", indent=2)
                else:
                    spdf.to_csv(full, index=False)
                print(f"✅ Saved table summary to: {full}")

    def save(self, output_cfg: dict, spark=None):
        """Persist results to one or more destinations defined in output_cfg."""
        import os

        # Support both old single-type ("type") and new multi-type ("types") format
        types = output_cfg.get("types") or ([output_cfg["type"]] if "type" in output_cfg else ["dataframe"])

        results = {}
        sdf = None

        for otype in types:
            if otype == "dataframe":
                if sdf is None:
                    sdf = self.to_spark_df(spark)
                results["dataframe"] = sdf

            elif otype == "delta":
                if sdf is None:
                    sdf = self.to_spark_df(spark)
                table = output_cfg.get("delta_table", "")
                if not table:
                    print("⚠️  delta_table not set — skipping Delta output")
                    continue
                (sdf.write.format("delta")
                    .mode("append")
                    .option("mergeSchema", "true")
                    .saveAsTable(table))
                print(f"✅ Saved to Delta table: {table}")
                # Also write table-level summary to <table>_summary if configured
                summary_table = output_cfg.get("summary_delta_table", "")
                if summary_table:
                    (self.to_table_summary_df(spark)
                        .write.format("delta")
                        .mode("append")
                        .option("mergeSchema", "true")
                        .saveAsTable(summary_table))
                    print(f"✅ Saved table summary to: {summary_table}")
                results["delta"] = sdf

            elif otype in ("volume_json", "volume_csv"):
                # vol_path already contains catalog/schema from the wizard
                vol_path = output_cfg.get("volume_path", "").rstrip("/")
                table_name = self.config.get("source", {}).get("table", "")
                tbl = table_name.split(".")[-1] if table_name else "table"
                filename = (output_cfg.get("filename")
                            or f"dq_{tbl}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                ext = "json" if otype == "volume_json" else "csv"
                os.makedirs(vol_path, exist_ok=True)
                full = f"{vol_path}/{filename}.{ext}"
                pdf = self.to_pandas()
                if ext == "json":
                    pdf.to_json(full, orient="records", indent=2)
                else:
                    pdf.to_csv(full, index=False)
                print(f"✅ Saved to: {full}")
                # Summary file alongside: same dir, _summary suffix
                summary_file = f"{vol_path}/{filename}_summary.{ext}"
                spdf = self.table_summary_pandas()
                if ext == "json":
                    spdf.to_json(summary_file, orient="records", indent=2)
                else:
                    spdf.to_csv(summary_file, index=False)
                print(f"✅ Saved table summary to: {summary_file}")
                results[otype] = full

        return results.get("dataframe") or (sdf if sdf is not None else None)


def run_checks(config, spark=None) -> DQReport:
    """
    Execute all checks defined in config and return a DQReport.

    ``config`` can be:
    - a **dict** returned by ``dashdq.configure()``
    - a **file path** (str) to a JSON config saved by the wizard

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
            "output":   {"types": ["delta"], "delta_table": "..."}    # optional
        }
    """
    import os
    if isinstance(config, (str, os.PathLike)):
        path = str(config)
        if not os.path.exists(path):
            raise FileNotFoundError(f"DashDQ config file not found: {path}")
        with open(path) as f:
            config = json.load(f)

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
    tags_str = ",".join(metadata.get("tags", []))

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
            if entry.get("cross_table"):
                total, passed, failed = entry["fn"](df, col, params, spark)
            else:
                total, passed, failed = entry["fn"](df, col, params)
            passed_pct = round(passed / total * 100, 2) if total > 0 else 0.0
            status = "PASS" if passed_pct >= threshold else "FAIL"
            if not entry.get("table_level") and not entry.get("compound"):
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
            tags=tags_str,
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

    # Auto-save check-level output if configured
    output_cfg = config.get("output", {})
    types = output_cfg.get("types") or ([output_cfg.get("type", "dataframe")])
    if output_cfg and types != ["dataframe"]:
        report.save(output_cfg, spark)

    # Auto-save table-level summary output if configured (new separate key)
    tbl_output_cfg = config.get("table_output", {})
    tbl_types = tbl_output_cfg.get("types") or ([tbl_output_cfg.get("type", "dataframe")])
    if tbl_output_cfg and tbl_types != ["dataframe"]:
        report.save_table_summary(tbl_output_cfg, spark)

    return report


def table_quality_ok(config, spark=None) -> bool:
    """Run all configured checks and return True if every check passes.

    Useful as a gate before consuming a table::

        if dashdq.table_quality_ok(config, spark=spark):
            df = spark.table(config["source"]["table"])
            # safe to use
        else:
            raise RuntimeError("Table failed quality checks — aborting pipeline.")
    """
    report = run_checks(config, spark=spark)
    return report.table_summary().get("overall_status") == "PASS"
