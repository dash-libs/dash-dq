## DashDQ v0.1.9

**Released:** 2026-06-26
**Previous:** v0.1.8

### Notes
Fix cascade dropdowns: schema list was reading comment column instead of schema name

### What's included
- All tests passing across Python 3.9, 3.10, 3.11, 3.12
- API documentation regenerated (see `docs/api/`)
- Published to PyPI and Databricks Marketplace

### Install
```bash
pip install dash-dq==0.1.9
```

### Quick Start (Databricks notebook)
```python
%pip install dash-dq==0.1.9
import dashdq
dashdq.launch()
```
