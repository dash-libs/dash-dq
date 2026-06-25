# CLAUDE.md — dash-dq

Part of the **Dashlibs** suite. See ~/dashlibs for the full context.

## Purpose
Data quality checks on Databricks — DataFrames, UC tables, SQL queries.  
Business users use `dashdq.launch()` for a widget UI. Engineers use `DQSuite` directly.

## Structure
- `dashdq/ui.py` — ipywidgets UI, `launch()` entrypoint
- `dashdq/checks.py` — individual check functions, each returns `CheckResult`
- `dashdq/suite.py` — `DQSuite` (fluent API) and `DQReport`
- `tests/` — pytest, no Spark dependency for unit tests

## Key Design Rules
- New checks go in `checks.py` as standalone functions returning `CheckResult`
- `DQSuite` maps rule dicts → check functions; the UI builds those dicts
- `DQReport.save()` appends to a Delta table — always use `mode("append")`
- Never import Spark at module level — always inside functions

## CI
- `ci.yml` — runs on every PR: lint (ruff) → test (py3.9–3.12) → build
- `daily.yml` — runs at 06:00 UTC daily: tests + appends to `.health/log.txt`
- `release.yml` — runs Monday 09:00 UTC: bumps patch version, tags, releases

## Adding a New Check
1. Add function to `checks.py` returning `CheckResult`
2. Add `expect_<name>` method to `DQSuite`
3. Add rule type handling in `DQSuite.run()`
4. Add dropdown option to `ui.py` and `_build_rule()`
5. Add test in `tests/test_suite.py`
