## DashDQ v0.1.2

**Released:** 2026-06-26
**Previous:** v0.1.1

### Notes
Major UI redesign: Databricks theme, 5-tab wizard, Unity Catalog dropdowns, multi-check per column, complex-check wizard, multi-output destinations

### What's included
- All tests passing across Python 3.9, 3.10, 3.11, 3.12
- API documentation regenerated (see `docs/api/`)
- Published to PyPI and Databricks Marketplace

### Install
```bash
pip install dash-dq==0.1.2
```

### Quick Start (Databricks notebook)
```python
%pip install dash-dq==0.1.2
import dashdq
dashdq.launch()
```
