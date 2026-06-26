"""Tests for checks registry and DQReport — no Spark required."""
import json
import pytest
from dashdq.checks import (
    CHECKS_REGISTRY, CheckResult, DQ_DIMENSIONS,
    _not_null, _unique, _between, _in_set,
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


# ── run_checks config validation ──────────────────────────────────────────────

def test_run_checks_raises_on_empty_config():
    from dashdq.suite import run_checks
    with pytest.raises(ValueError, match="Config is empty"):
        run_checks({})
