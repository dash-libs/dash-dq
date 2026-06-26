"""Tests for checks registry and DQReport — no Spark required."""
import pytest
from dashdq.checks import (
    CHECKS_REGISTRY, CheckResult, DQ_DIMENSIONS,
)
from dashdq.suite import DQReport


# ── CheckResult ───────────────────────────────────────────────────────────────

def test_check_result_to_dict():
    r = CheckResult(
        table_name="t", column_name="col", check_name="expect_column_values_to_not_be_null",
        dq_dimension="Completeness", total_rows=100, passed_rows=95, failed_rows=5,
        passed_pct=95.0, threshold_pct=100.0, status="FAIL",
    )
    d = r.to_dict()
    assert d["passed_pct"] == 95.0
    assert d["status"] == "FAIL"
    assert d["dq_dimension"] == "Completeness"


# ── Registry completeness ─────────────────────────────────────────────────────

def test_all_registry_checks_have_required_keys():
    required = {"dimension", "description", "params", "fn"}
    for name, entry in CHECKS_REGISTRY.items():
        missing = required - entry.keys()
        assert not missing, f"{name} missing keys: {missing}"


def test_all_registry_dimensions_are_valid():
    for name, entry in CHECKS_REGISTRY.items():
        assert entry["dimension"] in DQ_DIMENSIONS, (
            f"{name} has unknown dimension '{entry['dimension']}'"
        )


def test_registry_has_all_four_dimensions():
    dims = {e["dimension"] for e in CHECKS_REGISTRY.values()}
    assert dims == set(DQ_DIMENSIONS)


def test_registry_has_table_level_checks():
    tl = [n for n, e in CHECKS_REGISTRY.items() if e.get("table_level")]
    assert len(tl) >= 2


# ── DQReport ──────────────────────────────────────────────────────────────────

def _make_result(status="PASS", dim="Completeness"):
    return CheckResult(
        table_name="t", column_name="c",
        check_name="expect_column_values_to_not_be_null",
        dq_dimension=dim,
        total_rows=100, passed_rows=100 if status == "PASS" else 80,
        failed_rows=0 if status == "PASS" else 20,
        passed_pct=100.0 if status == "PASS" else 80.0,
        threshold_pct=100.0, status=status,
    )


def test_report_summary_all_pass():
    report = DQReport([_make_result("PASS"), _make_result("PASS")], config={})
    s = report.summary()
    assert s["passed"] == 2
    assert s["failed"] == 0
    assert s["pass_rate_pct"] == 100.0


def test_report_summary_mixed():
    report = DQReport([_make_result("PASS"), _make_result("FAIL")], config={})
    s = report.summary()
    assert s["passed"] == 1
    assert s["failed"] == 1
    assert s["pass_rate_pct"] == 50.0


def test_report_to_dict_shape():
    report = DQReport([_make_result()], config={})
    rows = report.to_dict()
    assert len(rows) == 1
    assert "passed_pct" in rows[0]
    assert "dq_dimension" in rows[0]
    assert "column_coverage_pct" in rows[0]


def test_report_to_pandas():
    report = DQReport([_make_result(), _make_result("FAIL")], config={})
    pdf = report.to_pandas()
    assert len(pdf) == 2
    assert "status" in pdf.columns
    assert list(pdf["status"]) == ["PASS", "FAIL"]


# ── table_summary ─────────────────────────────────────────────────────────────

def _make_result_full(status="PASS", total=100, passed=100, failed=0):
    return CheckResult(
        table_name="cat.sch.tbl", column_name="c",
        check_name="expect_column_values_to_not_be_null",
        dq_dimension="Completeness",
        total_rows=total, passed_rows=passed, failed_rows=failed,
        passed_pct=round(passed / total * 100, 2),
        threshold_pct=100.0, status=status,
        columns_checked=2, total_columns=5, column_coverage_pct=40.0,
        run_timestamp="2026-01-01T00:00:00",
    )


def test_table_summary_all_pass():
    config = {"metadata": {"data_owner": "Alice", "tags": ["finance"]}}
    report = DQReport([_make_result_full("PASS"), _make_result_full("PASS")], config=config)
    s = report.table_summary()
    assert s["overall_status"] == "PASS"
    assert s["passed_checks"] == 2
    assert s["failed_checks"] == 0
    assert s["clean_rows"] == 100
    assert s["clean_pct"] == 100.0
    assert s["data_owner"] == "Alice"
    assert s["tags"] == "finance"


def test_table_summary_with_failures():
    config = {"metadata": {}}
    report = DQReport([
        _make_result_full("PASS", total=100, passed=100, failed=0),
        _make_result_full("FAIL", total=100, passed=80,  failed=20),
    ], config=config)
    s = report.table_summary()
    assert s["overall_status"] == "FAIL"
    assert s["failed_checks"] == 1
    assert s["dirty_rows"] == 20
    assert s["clean_rows"] == 80


def test_table_summary_dirty_rows_capped_at_total():
    # Two checks each failing 70 rows → sum=140 > total=100; cap at 100
    config = {"metadata": {}}
    report = DQReport([
        _make_result_full("FAIL", total=100, passed=30, failed=70),
        _make_result_full("FAIL", total=100, passed=30, failed=70),
    ], config=config)
    s = report.table_summary()
    assert s["dirty_rows"] == 100
    assert s["clean_rows"] == 0


def test_table_summary_pandas_shape():
    config = {"metadata": {}}
    report = DQReport([_make_result_full()], config=config)
    pdf = report.table_summary_pandas()
    assert len(pdf) == 1
    assert "overall_status" in pdf.columns
    assert "clean_rows" in pdf.columns


# ── run_checks config validation ──────────────────────────────────────────────

def test_run_checks_raises_on_empty_config():
    from dashdq.suite import run_checks
    with pytest.raises(ValueError, match="Config is empty"):
        run_checks({})


def test_run_checks_raises_on_missing_file():
    from dashdq.suite import run_checks
    with pytest.raises(FileNotFoundError, match="not found"):
        run_checks("/tmp/does_not_exist_dashdq.json")


def test_run_checks_loads_from_json_file(tmp_path):
    import json
    from dashdq.suite import run_checks
    cfg = {"source": {"table": "a.b.c"}, "checks": []}
    p = tmp_path / "test_config.json"
    p.write_text(json.dumps(cfg))
    # Empty checks → raises because no Spark, but config loads fine
    with pytest.raises(Exception):
        run_checks(str(p))
