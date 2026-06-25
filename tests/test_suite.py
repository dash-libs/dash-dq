"""Basic unit tests for DQSuite (no Spark needed for rule building)."""
import pytest
from dashdq.suite import DQSuite, DQReport
from dashdq.checks import CheckResult


def test_report_summary_all_passed():
    results = [CheckResult("no_nulls", "col_a", True, "0 nulls")]
    report = DQReport(results)
    assert "PASSED" in report.summary()
    assert report.passed == 1
    assert report.failed == 0


def test_report_summary_with_failure():
    results = [
        CheckResult("no_nulls", "col_a", True, "0 nulls"),
        CheckResult("unique", "col_b", False, "3 duplicates"),
    ]
    report = DQReport(results)
    assert "FAILED" in report.summary()
    assert report.failed == 1


def test_report_to_dict():
    results = [CheckResult("no_nulls", "col_a", True, "0 nulls", 0, 0)]
    report = DQReport(results)
    data = report.to_dict()
    assert len(data) == 1
    assert data[0]["check"] == "no_nulls"
    assert data[0]["passed"] is True


def test_suite_rule_chaining():
    """DQSuite should accumulate rules when chained."""
    class FakeDf:
        pass

    suite = DQSuite.__new__(DQSuite)
    suite._df = FakeDf()
    suite._rules = []
    suite.expect_no_nulls("id").expect_unique("email").expect_min_rows(1)
    assert len(suite._rules) == 3
    assert suite._rules[0]["type"] == "no_nulls"
    assert suite._rules[1]["type"] == "unique"
    assert suite._rules[2]["type"] == "row_count"


def test_suite_from_config():
    suite = DQSuite.__new__(DQSuite)
    suite._df = None
    suite._rules = []
    config = {"rules": [{"type": "no_nulls", "column": "id"}]}
    suite.from_config(config)
    assert suite._rules == config["rules"]
