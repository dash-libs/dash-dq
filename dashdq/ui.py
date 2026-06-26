"""DashDQ UI — Sequential 5-step wizard.

Steps:
  1  📊 Source          — Unity Catalog cascade: catalog → schema → table
  2  ✅ Column Checks   — per-column inline check builder (table rows)
  3  🔗 Additional      — table-level & compound checks
  4  📤 Output          — check-level output + table summary output (separate)
  5  🏷️ Metadata        — owner, steward, domain, tags, description

  ⚙️ Settings panel (collapsible, top-right) — workspace paths and defaults
"""
from __future__ import annotations
import json
import os
from datetime import datetime

try:
    import ipywidgets as w
    from IPython.display import display, HTML
except ImportError as _e:
    raise ImportError(
        "ipywidgets is required for the DashDQ UI.\n"
        "Your Databricks cluster should already include it — if not, run:\n"
        "  %pip install 'ipywidgets>=7.6'\n"
        "Do NOT pip-install ipywidgets separately if your cluster already has it,\n"
        "as a Python/JS version mismatch causes 'Error displaying widget: undefined'."
    ) from _e

from dashdq.checks import CHECKS_REGISTRY, DQ_DIMENSIONS

_active_wizard: "DashDQWizard | None" = None

# ─── Theme ────────────────────────────────────────────────────────────────────

_COMPLEX_KEYS = {
    "reference_table", "reference_column", "column_b", "columns",
    "valid_pairs", "expected_schema", "check_orphans",
}

_ENV_PATH = os.environ.get("DASHDQ_ENV_PATH", os.path.expanduser("~/dashdq_env.json"))

_DEFAULT_ENV: dict = {
    "config_dir":           "",
    "default_catalog":      "",
    "default_schema":       "",
    "default_volume_path":  "/Volumes/",
    "library_paths":        [],
}

# ─── CSS ─────────────────────────────────────────────────────────────────────

_CSS = """
<style>
.dq-root { font-family: -apple-system,'Segoe UI',Roboto,Oxygen,sans-serif; }

/* ── Section header ── */
.dq-sec {
    background: linear-gradient(90deg,#1B3A4B 0%,#2D5A7B 100%);
    color: #fff; padding: 7px 14px; border-radius: 5px;
    font-size: 12px; font-weight: 700; letter-spacing: .3px;
    margin-bottom: 10px;
}

/* ── Dimension badges ── */
.dq-badge { padding: 2px 9px; border-radius: 12px; font-size: 11px; font-weight: 600; white-space:nowrap; }
.dq-Completeness { background:#DBEAFE; color:#1E40AF; }
.dq-Accuracy     { background:#DCFCE7; color:#166534; }
.dq-Integrity    { background:#FEF3C7; color:#92400E; }
.dq-Consistency  { background:#F3E8FF; color:#6B21A8; }

/* ── Alerts ── */
.dq-info  { background:#EFF6FF; border-left:3px solid #1890FF; padding:8px 12px; border-radius:0 4px 4px 0; font-size:12px; margin:4px 0 10px 0; }
.dq-ok    { background:#F0FDF4; border-left:3px solid #43A047; padding:8px 12px; border-radius:0 4px 4px 0; font-size:12px; margin:4px 0 10px 0; }
.dq-warn  { background:#FFFBEB; border-left:3px solid #FFA000; padding:8px 12px; border-radius:0 4px 4px 0; font-size:12px; margin:4px 0 10px 0; }
.dq-error { background:#FEF2F2; border-left:3px solid #C62828; padding:8px 12px; border-radius:0 4px 4px 0; font-size:12px; margin:4px 0 10px 0; }

/* ── Buttons via wrapping div class ── */
.dq-primary   .widget-button { background:#FF3621!important; color:#fff!important; border:none!important; border-radius:4px!important; font-weight:600!important; }
.dq-primary   .widget-button:hover { background:#D92B1A!important; }
.dq-secondary .widget-button { background:#fff!important; color:#1B3A4B!important; border:1px solid #1B3A4B!important; border-radius:4px!important; }
.dq-outline   .widget-button { background:transparent!important; color:#1890FF!important; border:1px solid #1890FF!important; border-radius:4px!important; }
.dq-danger    .widget-button { background:transparent!important; color:#C62828!important; border:1px solid #C62828!important; border-radius:4px!important; font-size:11px!important; }
.dq-success   .widget-button { background:#43A047!important; color:#fff!important; border:none!important; border-radius:4px!important; font-weight:600!important; }
.dq-nav       .widget-button { background:#1B3A4B!important; color:#fff!important; border:none!important; border-radius:4px!important; font-weight:600!important; font-size:13px!important; }
.dq-nav       .widget-button:hover { background:#2D5A7B!important; }

/* ── Complex wizard panel ── */
.dq-wizard {
    background:#FFFBEB; border:1.5px solid #FDE68A;
    border-radius:6px; padding:14px; margin-top:10px;
}

/* ── Summary banner ── */
.dq-summary { background:linear-gradient(90deg,#1B3A4B,#2D5A7B); color:#fff; border-radius:6px; padding:12px 20px; font-size:13px; font-weight:600; margin-top:12px; }
.dq-pass { color:#86EFAC; }
.dq-fail { color:#FCA5A5; }

/* ── Panels (ipywidgets-7-safe: borders via add_class not Layout) ── */
.dq-form-box  { border:1px solid #E8EBF0!important; border-radius:6px!important; background:#FAFBFC!important; }
.dq-check-row { border:1px solid #E8EBF0!important; border-radius:4px!important; background:#fff!important; }
.dq-out-opts  { border:1px solid #E8EBF0!important; border-radius:6px!important; }
.dq-sub-panel { border:1px solid #E8EBF0!important; border-radius:4px!important; }
.dq-col-header { background:#F7F8FA!important; border:1px solid #E8EBF0!important; border-radius:5px 5px 0 0!important; }
.dq-col-row-alt { background:#FAFBFC!important; }

/* ── HBox gap shim ── */
.dq-gap-8 > .p-Panel > *,  .dq-gap-8 > .lm-Panel > *,
.dq-gap-8 > .widget-hbox > * { margin-right:8px!important; }
.dq-gap-8 > .p-Panel > *:last-child,  .dq-gap-8 > .lm-Panel > *:last-child,
.dq-gap-8 > .widget-hbox > *:last-child { margin-right:0!important; }
</style>
"""

# ─── Spark helpers ────────────────────────────────────────────────────────────

def _get_spark():
    try:
        from pyspark.sql import SparkSession
        return SparkSession.getActiveSession()
    except Exception:
        return None


def _list_catalogs(spark) -> list[str]:
    try:
        return sorted(r[0] for r in spark.sql("SHOW CATALOGS").collect())
    except Exception:
        return []


def _list_schemas(spark, catalog: str) -> list[str]:
    try:
        rows = spark.sql(f"SHOW SCHEMAS IN `{catalog}`").collect()
        return sorted(r[0] for r in rows if r[0])
    except Exception:
        return []


def _list_tables(spark, catalog: str, schema: str) -> list[str]:
    try:
        rows = spark.sql(f"SHOW TABLES IN `{catalog}`.`{schema}`").collect()
        return sorted(r[1] for r in rows if not r[2])
    except Exception:
        return []


def _table_info(spark, full_table: str) -> tuple[list[tuple[str, str]], int]:
    try:
        df = spark.table(full_table)
        cols = [(f.name, f.dataType.simpleString()) for f in df.schema.fields]
        count = df.count()
        return cols, count
    except Exception:
        return [], -1


# ─── Config file helpers ──────────────────────────────────────────────────────

def _load_env() -> dict:
    if os.path.exists(_ENV_PATH):
        try:
            with open(_ENV_PATH) as f:
                return {**_DEFAULT_ENV, **json.load(f)}
        except Exception:
            pass
    return dict(_DEFAULT_ENV)


def _save_env(cfg: dict) -> str:
    with open(_ENV_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    return _ENV_PATH


def _load_existing_config(config_dir: str, table: str) -> dict:
    """Load full config from config_dir/catalog/schema/table.json."""
    if not config_dir or not os.path.isdir(config_dir):
        return {}
    parts = table.split(".")
    if len(parts) == 3:
        cat, sch, tbl = parts
        direct = os.path.join(config_dir, cat, sch, f"{tbl}.json")
        if os.path.exists(direct):
            try:
                with open(direct) as f:
                    return json.load(f)
            except Exception:
                pass
    for fname in sorted(os.listdir(config_dir)):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(config_dir, fname)) as f:
                cfg = json.load(f)
            if cfg.get("source", {}).get("table") == table:
                return cfg
        except Exception:
            pass
    return {}


# ─── Widget helpers ───────────────────────────────────────────────────────────

def _h(html: str) -> w.HTML:
    return w.HTML(html)


def _sec(title: str) -> w.HTML:
    return _h(f"<div class='dq-sec'>{title}</div>")


def _label(text: str) -> w.HTML:
    return _h(
        f"<div style='font-size:11px;color:#5C6673;font-weight:600;margin-bottom:3px;"
        f"text-transform:uppercase;letter-spacing:.4px'>{text}</div>"
    )


def _info(text: str, kind: str = "info") -> w.HTML:
    return _h(f"<div class='dq-{kind}'>{text}</div>")


def _field(label: str, widget, width: str = "100%") -> w.VBox:
    widget.layout.width = width
    return w.VBox([_label(label), widget], layout=w.Layout(margin="0 0 10px 0"))


def _styled_btn(label: str, kind: str = "primary") -> tuple[w.HBox, w.Button]:
    btn = w.Button(description=label)
    box = w.HBox([btn])
    box.add_class(f"dq-{kind}")
    return box, btn


# ─── Check grouping ───────────────────────────────────────────────────────────

_GROUPED: dict[str, list[str]] = {}
for _k, _v in CHECKS_REGISTRY.items():
    _GROUPED.setdefault(_v["dimension"], []).append(_k)


_SHORT: dict[str, str] = {
    # column pair
    "expect_column_pair_values_a_to_be_greater_than_b":        "pair: A > B",
    "expect_column_pair_values_to_be_equal":                   "pair: equal",
    "expect_column_pair_values_to_be_in_set":                  "pair: in set",
    # column stats
    "expect_column_max_to_be_between":                         "max between",
    "expect_column_mean_to_be_between":                        "mean between",
    "expect_column_median_to_be_between":                      "median between",
    "expect_column_min_to_be_between":                         "min between",
    "expect_column_stdev_to_be_between":                       "stdev between",
    "expect_column_sum_to_be_between":                         "sum between",
    "expect_column_quantile_value_to_be_between":              "quantile between",
    "expect_column_null_count_to_be_between":                  "null count between",
    "expect_column_null_proportion_to_be_between":             "null % between",
    "expect_column_most_common_value_to_be_in_set":            "mode in set",
    "expect_column_proportion_of_unique_values_to_be_between": "unique % between",
    "expect_column_unique_value_count_to_be_between":          "unique count between",
    "expect_column_value_lengths_to_be_between":               "length between",
    "expect_column_value_lengths_to_equal":                    "length =",
    "expect_column_data_to_be_fresh":                          "fresh",
    "expect_column_to_exist":                                  "col exists",
    # distinct
    "expect_column_distinct_values_to_be_in_set":              "distinct in set",
    "expect_column_distinct_values_to_contain_set":            "distinct contains",
    "expect_column_distinct_values_to_equal_set":              "distinct = set",
    # not-null / null
    "expect_column_values_to_not_be_null":                     "not null",
    "expect_column_values_to_not_be_null_or_empty":            "not null or empty",
    "expect_column_values_to_not_be_empty_string":             "not empty",
    "expect_column_values_to_be_null":                         "is null",
    # set membership
    "expect_column_values_to_be_in_set":                       "in set",
    "expect_column_values_to_not_be_in_set":                   "not in set",
    "expect_column_values_to_exist_in_reference_table":        "in ref table",
    # equality
    "expect_column_values_to_equal":                           "equal",
    "expect_column_values_to_not_equal":                       "not equal",
    # range
    "expect_column_values_to_be_between":                      "between",
    "expect_column_values_to_not_be_between":                  "not between",
    "expect_column_values_to_be_not_greater_than":             "≤ max",
    "expect_column_values_to_be_not_less_than":                "≥ min",
    # uniqueness
    "expect_column_values_to_be_unique":                       "unique",
    # type
    "expect_column_values_to_be_of_type":                      "of type",
    "expect_column_values_to_be_in_type_list":                 "in type list",
    # numeric sign
    "expect_column_values_to_be_positive":                     "positive",
    "expect_column_values_to_be_negative":                     "negative",
    "expect_column_values_to_be_non_negative":                 "≥ 0",
    # ordering
    "expect_column_values_to_be_increasing":                   "increasing",
    "expect_column_values_to_be_decreasing":                   "decreasing",
    # date / time
    "expect_column_values_to_be_dateutil_parseable":           "parseable date",
    "expect_column_values_to_be_not_older_than_n_days":        "not older than N days",
    "expect_column_values_to_not_be_in_future":                "not in future",
    "expect_column_values_to_not_be_in_near_future":           "not near future",
    # format / pattern
    "expect_column_values_to_match_regex":                     "match regex",
    "expect_column_values_to_not_match_regex":                 "not match regex",
    "expect_column_values_to_match_regex_list":                "match regex list",
    "expect_column_values_to_match_like_pattern":              "like pattern",
    "expect_column_values_to_not_match_like_pattern":          "not like pattern",
    "expect_column_values_to_match_strftime_format":           "strftime format",
    "expect_column_values_to_pass_custom_sql_filter":          "sql filter",
    "expect_column_values_to_be_json_parseable":               "parseable JSON",
    # internet
    "expect_column_values_to_be_valid_email":                  "valid email",
    "expect_column_values_to_be_valid_ipv4":                   "valid IPv4",
    "expect_column_values_to_be_valid_url":                    "valid URL",
    "expect_column_values_to_be_valid_uuid":                   "valid UUID",
    # compound / table-level
    "expect_compound_columns_to_be_unique":                    "compound unique",
    "expect_multicolumn_sum_to_equal":                         "multi-col sum =",
    "expect_primary_key_to_be_valid":                          "pk valid",
    "expect_referential_integrity":                            "fk integrity",
    "expect_table_column_count_to_be_between":                 "col count between",
    "expect_table_column_count_to_equal":                      "col count =",
    "expect_table_columns_to_match_ordered_list":              "cols ordered",
    "expect_table_columns_to_match_set":                       "cols match set",
    "expect_table_row_count_to_be_between":                    "rows between",
    "expect_table_row_count_to_equal":                         "rows =",
    "expect_table_row_count_to_equal_other_table":             "rows = other table",
    "expect_table_schema_to_match":                            "schema matches",
}


def _short_name(name: str) -> str:
    return _SHORT.get(name, name.replace("_", " "))


def _col_check_options() -> list[tuple[str, str]]:
    """Column-level checks only (not table_level, not compound)."""
    opts = []
    for dim in DQ_DIMENSIONS:
        for name in _GROUPED.get(dim, []):
            entry = CHECKS_REGISTRY[name]
            if not entry.get("table_level") and not entry.get("compound"):
                opts.append((f"[{dim[:4]}] {_short_name(name)}", name))
    return opts


def _extra_check_options() -> list[tuple[str, str]]:
    """Table-level and compound checks for the Additional Checks step."""
    opts = []
    for dim in DQ_DIMENSIONS:
        for name in _GROUPED.get(dim, []):
            entry = CHECKS_REGISTRY[name]
            if entry.get("table_level") or entry.get("compound"):
                opts.append((f"[{dim[:4]}] {_short_name(name)}", name))
    return opts


# ═════════════════════════════════════════════════════════════════════════════
# DashDQWizard — sequential 5-step wizard
# ═════════════════════════════════════════════════════════════════════════════

class DashDQWizard:
    """Sequential 5-step DQ configuration wizard."""

    STEPS = [
        ("📊", "Source"),
        ("✅", "Column Checks"),
        ("🔗", "Additional"),
        ("📤", "Output"),
        ("🏷️", "Metadata"),
    ]

    def __init__(self, spark=None, config_target: dict | None = None):
        self.spark = spark or _get_spark()
        self.env   = _load_env()

        # Source state
        self._catalog = self.env.get("default_catalog", "")
        self._schema  = self.env.get("default_schema", "")
        self._table   = ""
        self._full    = ""
        self._columns: list[tuple[str, str]] = []

        # Check state
        self._col_checks: dict[str, list[dict]]  = {}   # col_name → [check_dict, …]
        self._extra_checks: list[dict]            = []   # table-level / compound
        self._col_step_mode: str                  = "column"  # "column" | "check"

        # Output state — pre-create as attributes so _make_output_step always has refs
        self._check_o_df:       w.Checkbox | None = None
        self._check_o_delta:    w.Checkbox | None = None
        self._check_o_vol_json: w.Checkbox | None = None
        self._check_o_vol_csv:  w.Checkbox | None = None
        self._check_o_delta_tbl: w.Text | None    = None
        self._check_o_vol_path:  w.Text | None    = None
        self._check_o_filename:  w.Text | None    = None
        self._tbl_o_df:          w.Checkbox | None = None
        self._tbl_o_delta:       w.Checkbox | None = None
        self._tbl_o_vol_json:    w.Checkbox | None = None
        self._tbl_o_vol_csv:     w.Checkbox | None = None
        self._tbl_o_delta_tbl:   w.Text | None    = None
        self._tbl_o_vol_path:    w.Text | None    = None
        self._tbl_o_filename:    w.Text | None    = None

        # Metadata state — pre-create so save works even if step not visited
        self._m_owner   = w.Text(placeholder="e.g. Jane Smith",    layout=w.Layout(width="100%"))
        self._m_steward = w.Text(placeholder="e.g. John Doe",      layout=w.Layout(width="100%"))
        self._m_domain  = w.Text(placeholder="e.g. Finance, Risk", layout=w.Layout(width="100%"))
        self._m_tags    = w.Text(placeholder="tag1, tag2, tag3",    layout=w.Layout(width="100%"))
        self._m_desc    = w.Textarea(
            placeholder="Describe the purpose of this data quality run…",
            layout=w.Layout(width="100%", height="80px"),
        )

        self._config: dict = config_target if config_target is not None else {}
        self._step: int    = 0

        display(HTML(_CSS))
        self._build()

    # ── Root layout ───────────────────────────────────────────────────────────

    def _build(self):
        header = w.HBox([
            _h("<div style='font-size:15px;font-weight:700;color:#1B3A4B;"
               "letter-spacing:.2px'>DashDQ — Data Quality Wizard</div>"),
            _h("<div style='font-size:11px;color:#9CA3AF'>"
               "Run <code>dashdq.env_setup()</code> to configure paths &amp; defaults</div>"),
        ], layout=w.Layout(justify_content="space-between", align_items="center",
                           margin="0 0 8px 0"))

        self._progress = w.VBox([])
        self._content  = w.VBox([])
        self._nav_msg  = w.VBox([])

        self._back_box, self._back_btn = _styled_btn("← Back", "secondary")
        self._next_box, self._next_btn = _styled_btn("Next →", "nav")
        self._back_btn.layout = w.Layout(height="36px", min_width="100px")
        self._next_btn.layout = w.Layout(height="36px", min_width="160px")
        self._back_btn.on_click(lambda _: self._go_to(self._step - 1))
        self._next_btn.on_click(self._on_next)

        nav = w.HBox(
            [self._back_box, self._next_box, self._nav_msg],
            layout=w.Layout(align_items="center", margin="14px 0 0 0"),
        )
        nav.add_class("dq-gap-8")

        root = w.VBox([
            header, self._progress, self._content, nav,
        ], layout=w.Layout(max_width="1160px", padding="12px"))
        root.add_class("dq-root")
        display(root)

        self._go_to(0)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _update_progress(self):
        n = len(self.STEPS)
        parts = []
        for i, (icon, label) in enumerate(self.STEPS):
            if i < self._step:
                dot = "background:#43A047;color:#fff;border:2px solid #43A047"
                lbl = "color:#43A047;font-weight:500"
                num = "✓"
            elif i == self._step:
                dot = "background:#FF3621;color:#fff;border:2px solid #FF3621"
                lbl = "color:#1B3A4B;font-weight:700"
                num = str(i + 1)
            else:
                dot = "background:#fff;color:#9CA3AF;border:2px solid #E5E7EB"
                lbl = "color:#9CA3AF;font-weight:400"
                num = str(i + 1)

            parts.append(
                f"<div style='display:flex;align-items:center;gap:6px'>"
                f"<div style='{dot};border-radius:50%;width:26px;height:26px;"
                f"display:flex;align-items:center;justify-content:center;"
                f"font-size:11px;font-weight:700;flex-shrink:0'>{num}</div>"
                f"<span style='font-size:12px;{lbl}'>{icon} {label}</span>"
                f"</div>"
            )
            if i < n - 1:
                line = "#43A047" if i < self._step else "#E5E7EB"
                parts.append(
                    f"<div style='flex:1;height:2px;background:{line};margin:0 6px'></div>"
                )

        self._progress.children = (_h(
            f"<div style='display:flex;align-items:center;padding:12px 0 14px 0'>"
            f"{''.join(parts)}</div>"
        ),)

    def _go_to(self, step: int):
        self._step = max(0, min(step, len(self.STEPS) - 1))
        self._update_progress()
        self._nav_msg.children = ()

        builders = [
            self._make_source_step,
            self._make_col_checks_step,
            self._make_extra_checks_step,
            self._make_output_step,
            self._make_metadata_step,
        ]
        self._content.children = (builders[self._step](),)

        self._back_btn.disabled = (self._step == 0)
        is_last = (self._step == len(self.STEPS) - 1)
        self._next_btn.description = "💾  Save Config" if is_last else "Next →"

    def _on_next(self, _=None):
        if self._step == len(self.STEPS) - 1:
            self._do_save()
            return
        if self._step == 0:
            # Validate a table is selected
            table = getattr(self, "_table", "")
            if not table or str(table).startswith("—"):
                self._nav_msg.children = (
                    _info("⚠️ Select a catalog, schema, and table first.", "warn"),
                )
                return
            new_full = f"{self._catalog}.{self._schema}.{self._table}"
            if new_full != self._full or not self._columns:
                # Load columns on the way to step 2
                self._nav_msg.children = (
                    _info(f"⏳ Loading columns from <code>{new_full}</code>…", "info"),
                )
                self._full = new_full
                cols, _count = _table_info(self.spark, self._full) if self.spark else ([], -1)
                self._columns = cols
                if not cols and self.spark:
                    self._nav_msg.children = (
                        _info(f"❌ Could not load <code>{new_full}</code> — check permissions.", "error"),
                    )
                    return
                cfg_dir = self.env.get("config_dir", "")
                existing = _load_existing_config(cfg_dir, self._full)
                if existing.get("checks"):
                    self._col_checks = {}
                    self._extra_checks = []
                    for chk in existing["checks"]:
                        col = chk.get("column", "")
                        if col in ("_TABLE_LEVEL_", "_COMPOUND_"):
                            self._extra_checks.append(chk)
                        else:
                            self._col_checks.setdefault(col, []).append(chk)
        self._go_to(self._step + 1)

    # ── Step 1: Source ────────────────────────────────────────────────────────

    def _make_source_step(self) -> w.VBox:
        self._cat_dd = w.Dropdown(options=["— loading… —"],
                                  layout=w.Layout(width="100%"))
        self._sch_dd = w.Dropdown(options=["— select schema —"], disabled=True,
                                  layout=w.Layout(width="100%"))
        self._tbl_dd = w.Dropdown(options=["— select table —"], disabled=True,
                                  layout=w.Layout(width="100%"))
        self._source_info = w.VBox([])

        self._cat_dd.observe(self._on_catalog_change, names="value")
        self._sch_dd.observe(self._on_schema_change,  names="value")
        self._tbl_dd.observe(self._on_table_change,   names="value")

        if self._full and self._columns:
            self._source_info.children = (
                _info(f"✅ <b>{self._full}</b> — {len(self._columns)} columns loaded. "
                      "Click <b>Next →</b> to review checks.", "ok"),
            )

        self._do_load_catalogs()

        return w.VBox([
            _sec("📊  Step 1 of 5 — Select Source Table"),
            _info("Select catalog → schema → table, then click <b>Next →</b> to load columns.", "info"),
            w.VBox([_label("Catalog"), self._cat_dd], layout=w.Layout(margin="0 0 10px 0")),
            w.VBox([_label("Schema"),  self._sch_dd], layout=w.Layout(margin="0 0 10px 0")),
            w.VBox([_label("Table"),   self._tbl_dd], layout=w.Layout(margin="0 0 12px 0")),
            self._source_info,
        ], layout=w.Layout(padding="18px"))

    def _do_load_catalogs(self):
        catalogs = _list_catalogs(self.spark) if self.spark else []
        opts = (["— select catalog —"] + catalogs) if catalogs else ["— no catalogs found —"]
        self._cat_dd.options  = opts
        self._cat_dd.disabled = not bool(catalogs)
        default = self.env.get("default_catalog", "")
        if default and default in catalogs:
            self._cat_dd.value = default

    def _on_catalog_change(self, change):
        val = change["new"]
        if val.startswith("—"):
            return
        self._catalog = val
        schemas = _list_schemas(self.spark, val) if self.spark else []
        self._sch_dd.options  = ["— select schema —"] + schemas
        self._sch_dd.disabled = not bool(schemas)
        self._tbl_dd.options  = ["— select table —"]
        self._tbl_dd.disabled = True
        self._source_info.children = ()
        default = self.env.get("default_schema", "")
        if default and default in schemas:
            self._sch_dd.value = default

    def _on_schema_change(self, change):
        val = change["new"]
        if val.startswith("—"):
            return
        self._schema = val
        tables = _list_tables(self.spark, self._catalog, val) if self.spark else []
        self._tbl_dd.options  = ["— select table —"] + tables
        self._tbl_dd.disabled = not bool(tables)
        self._source_info.children = ()

    def _on_table_change(self, change):
        val = change["new"]
        if not val.startswith("—"):
            self._table = val
            self._source_info.children = (
                _info(f"📊 <b>{self._catalog}.{self._schema}.{val}</b> "
                      "— click <b>Next →</b> to load columns", "info"),
            )
        else:
            self._source_info.children = ()

    def _source_loaded_widgets(self, count: int = -1, existing: dict | None = None) -> tuple:
        rc = f"{count:,}" if count >= 0 else "—"
        schema_rows = "".join(
            f"<tr><td style='padding:3px 10px;font-family:monospace;border:1px solid #E8EBF0'>{n}</td>"
            f"<td style='padding:3px 10px;color:#888;border:1px solid #E8EBF0'>{dt}</td></tr>"
            for n, dt in self._columns
        )
        widgets = [_h(
            f"<div style='background:#F0F9FF;border:1px solid #BAE6FD;border-radius:5px;"
            f"padding:10px 14px;margin:10px 0;font-size:12px'>"
            f"✅ <b>{self._full}</b> &nbsp;·&nbsp; "
            f"<b>{len(self._columns)}</b> columns &nbsp;·&nbsp; <b>{rc}</b> rows &nbsp;—&nbsp; "
            f"click <b>Next →</b> to configure checks</div>"
            f"<div style='max-height:200px;overflow-y:auto;border-radius:4px'>"
            f"<table style='border-collapse:collapse;width:100%;font-size:12px'>"
            f"<tr style='background:#F7F8FA'>"
            f"<th style='padding:4px 10px;text-align:left;border:1px solid #E8EBF0'>Column</th>"
            f"<th style='padding:4px 10px;text-align:left;border:1px solid #E8EBF0'>Type</th></tr>"
            f"{schema_rows}</table></div>"
        )]
        if existing and existing.get("checks"):
            n = len(existing["checks"])
            widgets.append(_info(f"✅ Loaded <b>{n} existing check(s)</b> from config directory.", "ok"))
        return tuple(widgets)

    # ── Step 2: Column Checks ─────────────────────────────────────────────────

    def _make_col_checks_step(self) -> w.VBox:
        if not self._columns:
            return w.VBox([
                _sec("✅  Step 2 of 5 — Column Checks"),
                _info("⚠️ No table loaded. Go back to step 1 and select a table.", "warn"),
            ], layout=w.Layout(padding="18px"))

        body = w.VBox([])

        # ── Mode toggle ────────────────────────────────────────────────────────
        col_btn_box, col_btn = _styled_btn("📋 By Column", "nav")
        chk_btn_box, chk_btn = _styled_btn("🔍 By Check", "secondary")
        col_btn.layout = w.Layout(height="30px")
        chk_btn.layout = w.Layout(height="30px")

        def _render_body():
            n_cfg = sum(1 for c in self._col_checks if self._col_checks[c])
            n_total = len(self._columns)
            summary = (f"<span style='font-size:12px;color:#666'>{n_total} columns · "
                       f"<b style='color:#1B3A4B'>{n_cfg}</b> with checks</span>")
            if self._col_step_mode == "column":
                col_btn.style.button_color = "#FF3621"
                col_btn.style.text_color   = "#fff"
                chk_btn.style.button_color = None
                chk_btn.style.text_color   = None
                body.children = (self._build_col_view(summary),)
            else:
                chk_btn.style.button_color = "#FF3621"
                chk_btn.style.text_color   = "#fff"
                col_btn.style.button_color = None
                col_btn.style.text_color   = None
                body.children = (self._build_chk_view(summary),)

        def _to_col(_):
            self._col_step_mode = "column"
            _render_body()

        def _to_chk(_):
            self._col_step_mode = "check"
            _render_body()

        col_btn.on_click(_to_col)
        chk_btn.on_click(_to_chk)

        toggle = w.HBox(
            [col_btn_box, chk_btn_box],
            layout=w.Layout(margin="0 0 10px 0"),
        )
        toggle.add_class("dq-gap-8")

        _render_body()

        return w.VBox([
            _sec("✅  Step 2 of 5 — Column Checks"),
            toggle,
            body,
        ], layout=w.Layout(padding="18px"))

    def _build_col_view(self, summary_html: str) -> w.VBox:
        """Per-column table rows with inline +Add form (original layout)."""
        header_row = _h(
            "<div style='display:grid;grid-template-columns:220px 110px 1fr 120px;"
            "padding:8px 14px;font-size:11px;font-weight:700;color:#5C6673;"
            "text-transform:uppercase;letter-spacing:.4px'>"
            "<div>Column</div><div>Type</div><div>Checks</div><div></div></div>"
        )
        header_box = w.VBox([header_row])
        header_box.add_class("dq-col-header")

        rows = [header_box]
        for i, (col_name, dtype) in enumerate(self._columns):
            row = self._build_col_row(col_name, dtype)
            if i % 2 == 1:
                row.add_class("dq-col-row-alt")
            rows.append(row)

        return w.VBox([
            _info(
                "Click <b>＋ Add</b> on any column row to attach one or more checks. "
                f"<span style='float:right'>{summary_html}</span>", "info"
            ),
            w.VBox(rows, layout=w.Layout(margin="4px 0 0 0")),
        ])

    def _build_chk_view(self, summary_html: str) -> w.VBox:
        """Check-first view: pick a check + multi-select columns."""
        list_box = w.VBox([])

        def _refresh_list():
            rows = []
            for col_name, checks in self._col_checks.items():
                for idx, chk in enumerate(checks):
                    sn = _short_name(chk["check_name"])
                    dim = CHECKS_REGISTRY.get(chk["check_name"], {}).get("dimension", "")
                    rm_box2, rm_btn2 = _styled_btn("✕", "danger")
                    rm_btn2.layout = w.Layout(height="22px", width="26px")

                    def _make_rm(c, i):
                        def _rm(_):
                            self._col_checks[c].pop(i)
                            _refresh_list()
                        return _rm

                    rm_btn2.on_click(_make_rm(col_name, idx))
                    rows.append(w.HBox([
                        _h(f"<span class='dq-badge dq-{dim}' style='font-size:10px;"
                           f"min-width:140px;display:inline-block'>{sn}</span>"),
                        _h(f"<span style='font-family:monospace;font-size:12px;"
                           f"color:#1B3A4B;min-width:160px;padding:0 8px'>{col_name}</span>"),
                        _h(f"<span style='font-size:11px;color:#888;min-width:60px'>"
                           f"{chk['threshold_pct']}%</span>"),
                        rm_box2,
                    ], layout=w.Layout(align_items="center", padding="5px 8px",
                                       margin="0 0 2px 0")))
            if rows:
                hdr = _h(
                    "<div style='display:flex;gap:0;padding:4px 8px;font-size:11px;"
                    "font-weight:700;color:#5C6673;text-transform:uppercase;letter-spacing:.4px'>"
                    "<span style='min-width:156px'>Check</span>"
                    "<span style='min-width:168px'>Column</span>"
                    "<span style='min-width:68px'>Threshold</span></div>"
                )
                hdr_box = w.VBox([hdr])
                hdr_box.add_class("dq-col-header")
                list_box.children = (hdr_box, w.VBox(rows))
            else:
                list_box.children = (
                    _info("No column checks added yet. Use the form above to add checks.", "info"),
                )

        # ── Add form ──────────────────────────────────────────────────────────
        col_opts  = _col_check_options()
        check_dd  = w.Dropdown(options=col_opts, layout=w.Layout(width="260px"))
        threshold = w.BoundedFloatText(value=100.0, min=0.0, max=100.0, step=0.5,
                                       layout=w.Layout(width="85px"))

        col_names = [n for n, _ in self._columns]
        col_multi = w.SelectMultiple(
            options=[(f"{n}  ({dt})", n) for n, dt in self._columns],
            value=[],
            rows=min(10, len(col_names)),
            layout=w.Layout(width="320px", min_height="140px"),
        )
        select_all_box, select_all_btn = _styled_btn("Select All", "outline")
        clear_box,      clear_btn      = _styled_btn("Clear", "outline")
        select_all_btn.layout = w.Layout(height="26px")
        clear_btn.layout      = w.Layout(height="26px")

        def _sel_all(_): col_multi.value = tuple(col_names)
        def _clear(_):   col_multi.value = ()
        select_all_btn.on_click(_sel_all)
        clear_btn.on_click(_clear)

        simple_out  = w.VBox([])
        complex_out = w.VBox([])
        simple_store: dict = {}
        complex_store: dict = {}

        def _on_dd(change):
            name  = change["new"]
            entry = CHECKS_REGISTRY.get(name, {})
            raw   = entry.get("params", [])
            all_p = raw if isinstance(raw, dict) else {k: None for k in raw}
            simple_store.clear()
            complex_store.clear()
            simple = {k: v for k, v in all_p.items() if k not in _COMPLEX_KEYS}
            pw = []
            for pname, default in simple.items():
                wgt = self._make_simple_widget(pname, default)
                if wgt:
                    simple_store[pname] = wgt
                    pw.append(w.HBox([
                        _h(f"<div style='font-size:11px;color:#5C6673;font-weight:600;"
                           f"min-width:100px'>{pname.replace('_',' ').title()}</div>"),
                        wgt,
                    ], layout=w.Layout(align_items="center", margin="0 0 4px 0")))
            simple_out.children = tuple(pw)
            cplx = {k: v for k, v in all_p.items() if k in _COMPLEX_KEYS}
            if cplx:
                complex_out.children = (self._make_complex_wizard(name, cplx, col_names, complex_store),)
            else:
                complex_out.children = ()

        check_dd.observe(_on_dd, names="value")
        _on_dd({"new": check_dd.value})

        add_box2, add_btn2 = _styled_btn("✓ Add to selected columns", "primary")
        add_btn2.layout = w.Layout(height="32px")
        status2 = w.VBox([])

        def _do_add_chk(_):
            selected = list(col_multi.value)
            if not selected:
                status2.children = (_info("⚠️ Select at least one column first.", "warn"),)
                return
            params: dict = {}
            for k, wgt in simple_store.items():
                val = wgt.value
                if k in ("value_set", "regex_list", "type_list"):
                    val = [x.strip() for x in str(val).split(",") if x.strip()]
                elif k in ("min_value", "max_value", "sum_value", "quantile"):
                    try:
                        val = float(val)
                    except Exception:
                        val = None
                elif k in ("n_days", "n_minutes"):
                    try:
                        val = int(val)
                    except Exception:
                        val = 1
                params[k] = val
            for k, wgt in complex_store.items():
                val = wgt.value
                if k in ("valid_pairs", "expected_schema"):
                    try:
                        val = json.loads(val) if val else ([] if k == "valid_pairs" else {})
                    except Exception:
                        val = [] if k == "valid_pairs" else {}
                elif k == "columns":
                    val = list(val)
                elif k == "check_orphans":
                    val = bool(val)
                params[k] = val
            chk_name = check_dd.value
            thr = round(float(threshold.value), 1)
            for col in selected:
                self._col_checks.setdefault(col, []).append({
                    "check_name":    chk_name,
                    "column":        col,
                    "threshold_pct": thr,
                    "params":        params,
                })
            sn = _short_name(chk_name)
            status2.children = (
                _info(f"✅ Added <b>{sn}</b> to {len(selected)} column(s).", "ok"),
            )
            col_multi.value = ()
            _refresh_list()

        add_btn2.on_click(_do_add_chk)

        form = w.VBox([
            w.HBox([
                w.VBox([_label("Check"), check_dd]),
                w.HTML("&nbsp;&nbsp;&nbsp;"),
                w.VBox([_label("Pass Threshold %"), threshold]),
            ], layout=w.Layout(align_items="flex-end", margin="0 0 8px 0")),
            simple_out, complex_out,
            w.VBox([
                _label("Columns (select one or more)"),
                col_multi,
                w.HBox([select_all_box, clear_box],
                       layout=w.Layout(margin="4px 0 0 0")),
            ], layout=w.Layout(margin="6px 0 8px 0")),
            w.HBox([add_box2]),
            status2,
        ], layout=w.Layout(padding="12px 14px 10px 14px", margin="0 0 10px 0"))
        form.add_class("dq-form-box")

        _refresh_list()

        return w.VBox([
            _info(
                "Select a check + one or more columns, then click <b>✓ Add</b>. "
                f"<span style='float:right'>{summary_html}</span>", "info"
            ),
            form,
            list_box,
        ])

    def _build_col_row(self, col_name: str, dtype: str) -> w.VBox:
        """One column row: header with tags + collapsible add-check form."""
        tags_box = w.VBox([])
        self._refresh_col_tags(col_name, tags_box)

        # ── Add form (hidden until ＋ Add is clicked) ─────────────────────────
        col_opts = _col_check_options()
        check_dd   = w.Dropdown(options=col_opts, layout=w.Layout(width="300px"))
        threshold  = w.BoundedFloatText(value=100.0, min=0.0, max=100.0, step=0.5,
                                        layout=w.Layout(width="90px"))
        simple_out = w.VBox([])
        complex_out = w.VBox([])
        simple_store: dict = {}
        complex_store: dict = {}

        def _on_dd(change, _s_out=simple_out, _c_out=complex_out,
                   _ss=simple_store, _cs=complex_store):
            name  = change["new"]
            entry = CHECKS_REGISTRY.get(name, {})
            raw   = entry.get("params", [])
            all_p = raw if isinstance(raw, dict) else {k: None for k in raw}

            _ss.clear()
            _cs.clear()
            simple = {k: v for k, v in all_p.items() if k not in _COMPLEX_KEYS}
            pw = []
            for pname, default in simple.items():
                wgt = self._make_simple_widget(pname, default)
                if wgt:
                    _ss[pname] = wgt
                    pw.append(w.HBox([
                        _h(f"<div style='font-size:11px;color:#5C6673;font-weight:600;"
                           f"min-width:100px'>{pname.replace('_',' ').title()}</div>"),
                        wgt,
                    ], layout=w.Layout(align_items="center", margin="0 0 4px 0")))
            _s_out.children = tuple(pw)

            cplx = {k: v for k, v in all_p.items() if k in _COMPLEX_KEYS}
            if cplx:
                col_names = [n for n, _ in self._columns]
                _c_out.children = (self._make_complex_wizard(name, cplx, col_names, _cs),)
            else:
                _c_out.children = ()

        check_dd.observe(_on_dd, names="value")
        _on_dd({"new": check_dd.value})   # populate params immediately

        add_box, add_btn       = _styled_btn("✓ Add", "primary")
        cancel_box, cancel_btn = _styled_btn("✕ Cancel", "outline")
        add_btn.layout    = w.Layout(height="30px")
        cancel_btn.layout = w.Layout(height="30px")

        form = w.VBox([
            w.HBox([
                w.VBox([_label("Check"), check_dd]),
                w.HTML("&nbsp;&nbsp;"),
                w.VBox([_label("Pass Threshold %"), threshold]),
            ], layout=w.Layout(align_items="flex-end", margin="6px 0 8px 0")),
            simple_out, complex_out,
            w.HBox([add_box, cancel_box],
                   layout=w.Layout(margin="6px 0 0 0")),
        ], layout=w.Layout(padding="12px 14px 10px 14px", margin="0 0 2px 0"))
        form.add_class("dq-form-box")
        form.layout.display = "none"

        add_chk_box, add_chk_btn = _styled_btn("＋ Add", "outline")
        add_chk_btn.layout = w.Layout(height="28px")

        def _toggle(_):
            form.layout.display = "" if form.layout.display == "none" else "none"

        def _do_add(_, _col=col_name, _tb=tags_box, _form=form,
                    _dd=check_dd, _thr=threshold,
                    _ss=simple_store, _cs=complex_store):
            params: dict = {}
            for k, wgt in _ss.items():
                val = wgt.value
                if k in ("value_set", "regex_list", "type_list"):
                    val = [x.strip() for x in str(val).split(",") if x.strip()]
                elif k in ("min_value", "max_value", "sum_value", "quantile"):
                    try:
                        val = float(val)
                    except Exception:
                        val = None
                elif k in ("n_days", "n_minutes"):
                    try:
                        val = int(val)
                    except Exception:
                        val = 1
                params[k] = val
            for k, wgt in _cs.items():
                val = wgt.value
                if k in ("valid_pairs", "expected_schema"):
                    try:
                        val = json.loads(val) if val else ([] if k == "valid_pairs" else {})
                    except Exception:
                        val = [] if k == "valid_pairs" else {}
                elif k == "columns":
                    val = list(val)
                elif k == "check_orphans":
                    val = bool(val)
                params[k] = val

            self._col_checks.setdefault(_col, []).append({
                "check_name":    _dd.value,
                "column":        _col,
                "threshold_pct": round(float(_thr.value), 1),
                "params":        params,
            })
            self._refresh_col_tags(_col, _tb)
            _form.layout.display = "none"
            _thr.value = 100.0

        def _cancel(_): form.layout.display = "none"

        add_chk_btn.on_click(_toggle)
        add_btn.on_click(_do_add)
        cancel_btn.on_click(_cancel)

        header = w.HBox([
            _h(f"<div style='font-family:monospace;font-size:13px;font-weight:700;"
               f"color:#1B3A4B;min-width:220px;max-width:220px;"
               f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{col_name}</div>"),
            _h(f"<div style='font-size:11px;color:#888;min-width:110px'>{dtype}</div>"),
            tags_box,
            add_chk_box,
        ], layout=w.Layout(align_items="center", padding="8px 14px",
                           justify_content="space-between"))
        header.add_class("dq-check-row")

        return w.VBox([header, form])

    def _refresh_col_tags(self, col: str, box: w.VBox):
        checks = self._col_checks.get(col, [])
        if not checks:
            box.children = (
                _h("<span style='color:#9CA3AF;font-size:11px;font-style:italic'>no checks</span>"),
            )
            return

        tags = []
        for i, chk in enumerate(checks):
            dim = CHECKS_REGISTRY.get(chk["check_name"], {}).get("dimension", "")
            rm_box, rm_btn = _styled_btn("✕", "danger")
            rm_btn.layout = w.Layout(height="22px", width="26px")

            def _make_rm(idx, c, b):
                def _rm(_):
                    self._col_checks[c].pop(idx)
                    self._refresh_col_tags(c, b)
                return _rm

            rm_btn.on_click(_make_rm(i, col, box))
            tags.append(w.HBox([
                _h(f"<span class='dq-badge dq-{dim}' style='font-size:10px'>"
                   f"{_short_name(chk['check_name'])}</span>"),
                rm_box,
            ], layout=w.Layout(align_items="center", margin="0 4px 2px 0")))

        box.children = tuple(tags)

    # ── Step 3: Additional Checks ─────────────────────────────────────────────

    def _make_extra_checks_step(self) -> w.VBox:
        extra_opts = _extra_check_options()

        self._extra_list_box = w.VBox([])
        self._refresh_extra_list()

        if not extra_opts:
            return w.VBox([
                _sec("🔗  Step 3 of 5 — Additional Checks"),
                _info("No table-level or compound checks are defined in the registry. "
                      "Click Next to continue.", "info"),
                self._extra_list_box,
            ], layout=w.Layout(padding="18px"))

        # Add form
        check_dd  = w.Dropdown(options=extra_opts, layout=w.Layout(width="320px"))
        threshold = w.BoundedFloatText(value=100.0, min=0.0, max=100.0, step=0.5,
                                       layout=w.Layout(width="90px"))
        simple_out  = w.VBox([])
        complex_out = w.VBox([])
        simple_store: dict = {}
        complex_store: dict = {}

        def _on_dd(change, _s=simple_out, _c=complex_out,
                   _ss=simple_store, _cs=complex_store):
            name  = change["new"]
            entry = CHECKS_REGISTRY.get(name, {})
            raw   = entry.get("params", [])
            all_p = raw if isinstance(raw, dict) else {k: None for k in raw}

            _ss.clear()
            _cs.clear()
            simple = {k: v for k, v in all_p.items() if k not in _COMPLEX_KEYS}
            pw = []
            for pname, default in simple.items():
                wgt = self._make_simple_widget(pname, default)
                if wgt:
                    _ss[pname] = wgt
                    pw.append(w.HBox([
                        _h(f"<div style='font-size:11px;color:#5C6673;font-weight:600;"
                           f"min-width:110px'>{pname.replace('_',' ').title()}</div>"),
                        wgt,
                    ], layout=w.Layout(align_items="center", margin="0 0 4px 0")))
            _s.children = tuple(pw) if pw else (
                _h("<span style='color:#AAA;font-size:12px;font-style:italic'>"
                   "No extra parameters.</span>"),
            )

            cplx = {k: v for k, v in all_p.items() if k in _COMPLEX_KEYS}
            if cplx:
                col_names = [n for n, _ in self._columns]
                _c.children = (self._make_complex_wizard(name, cplx, col_names, _cs),)
            else:
                _c.children = ()

        check_dd.observe(_on_dd, names="value")
        _on_dd({"new": check_dd.value})

        add_box, add_btn = _styled_btn("＋ Add Check", "primary")
        add_btn.layout   = w.Layout(height="34px")

        def _add(_, _dd=check_dd, _thr=threshold,
                 _ss=simple_store, _cs=complex_store):
            params: dict = {}
            for k, wgt in _ss.items():
                val = wgt.value
                if k in ("value_set", "regex_list", "type_list"):
                    val = [x.strip() for x in str(val).split(",") if x.strip()]
                elif k in ("min_value", "max_value", "sum_value", "quantile"):
                    try:
                        val = float(val)
                    except Exception:
                        val = None
                elif k in ("n_days", "n_minutes"):
                    try:
                        val = int(val)
                    except Exception:
                        val = 1
                params[k] = val
            for k, wgt in _cs.items():
                val = wgt.value
                if k in ("valid_pairs", "expected_schema"):
                    try:
                        val = json.loads(val) if val else ([] if k == "valid_pairs" else {})
                    except Exception:
                        val = [] if k == "valid_pairs" else {}
                elif k == "columns":
                    val = list(val)
                elif k == "check_orphans":
                    val = bool(val)
                params[k] = val

            name  = _dd.value
            entry = CHECKS_REGISTRY.get(name, {})
            col   = "_TABLE_LEVEL_" if entry.get("table_level") else "_COMPOUND_"
            self._extra_checks.append({
                "check_name":    name,
                "column":        col,
                "threshold_pct": round(float(_thr.value), 1),
                "params":        params,
            })
            self._refresh_extra_list()
            _thr.value = 100.0

        add_btn.on_click(_add)

        add_form = w.VBox([
            _h("<div style='font-size:13px;font-weight:700;color:#1B3A4B;margin-bottom:8px'>"
               "Add Additional Check</div>"),
            w.HBox([
                w.VBox([_label("Check"), check_dd]),
                w.HTML("&nbsp;&nbsp;"),
                w.VBox([_label("Pass Threshold %"), threshold]),
            ], layout=w.Layout(align_items="flex-end", margin="0 0 8px 0")),
            simple_out, complex_out,
            w.HBox([add_box], layout=w.Layout(margin="8px 0 0 0")),
        ], layout=w.Layout(padding="14px", margin="12px 0 0 0"))
        add_form.add_class("dq-form-box")

        return w.VBox([
            _sec("🔗  Step 3 of 5 — Additional Checks"),
            _info("Add table-level checks (row count, schema, no-duplicates) and "
                  "multi-column checks (composite key, referential integrity). "
                  "Skip this step if not needed.", "info"),
            self._extra_list_box,
            add_form,
        ], layout=w.Layout(padding="18px"))

    def _refresh_extra_list(self):
        if not self._extra_checks:
            self._extra_list_box.children = (
                _info("No additional checks configured yet.", "info"),
            )
            return
        rows = []
        for i, chk in enumerate(self._extra_checks):
            dim = CHECKS_REGISTRY.get(chk["check_name"], {}).get("dimension", "")
            rm_box, rm_btn = _styled_btn("✕ Remove", "danger")
            rm_btn.layout  = w.Layout(height="28px")

            def _make_rm(idx):
                def _rm(_):
                    self._extra_checks.pop(idx)
                    self._refresh_extra_list()
                return _rm

            rm_btn.on_click(_make_rm(i))
            kind_tag = (
                "<span style='background:#F3F4F6;color:#374151;padding:1px 6px;"
                "border-radius:3px;font-size:10px;font-family:monospace'>"
                + ("table-level" if chk.get("column") == "_TABLE_LEVEL_" else "compound") +
                "</span>"
            )
            row = w.HBox([
                _h(
                    f"<span class='dq-badge dq-{dim}' style='font-size:10px'>{dim}</span>&nbsp;"
                    f"<code style='font-size:12px'>{chk['check_name']}</code>"
                    f"&nbsp;{kind_tag}&nbsp;"
                    f"<span style='color:#888;font-size:11px'>"
                    f"threshold: {chk.get('threshold_pct', 100)}%</span>"
                ),
                rm_box,
            ], layout=w.Layout(justify_content="space-between", align_items="center",
                               padding="8px 12px", margin="0 0 4px 0"))
            row.add_class("dq-check-row")
            rows.append(row)
        self._extra_list_box.children = tuple(rows)

    # ── Step 4: Output ────────────────────────────────────────────────────────

    def _make_output_step(self) -> w.VBox:
        check_section = self._build_output_section(
            "Check-Level Output", "check",
            "One row per check × column. Detailed results for every configured check. "
            "Use for debugging and per-column analysis."
        )
        tbl_section = self._build_output_section(
            "Table Summary Output", "tbl",
            "One aggregated row per run. Overall PASS/FAIL, clean record count, "
            "check coverage. Use for pipeline gates and dashboards."
        )
        return w.VBox([
            _sec("📤  Step 4 of 5 — Output Configuration"),
            _info("Configure where results are written. The two sections are independent — "
                  "each can go to a different destination.", "info"),
            check_section,
            _h("<div style='margin:14px 0 6px 0'></div>"),
            tbl_section,
        ], layout=w.Layout(padding="18px"))

    def _build_output_section(self, title: str, prefix: str, description: str) -> w.VBox:
        df_cb    = w.Checkbox(value=(prefix == "check"), description="In-memory DataFrame",
                              style={"description_width": "initial"})
        delta_cb = w.Checkbox(value=False, description="Delta Table",
                              style={"description_width": "initial"})
        json_cb  = w.Checkbox(value=False, description="Volume — JSON",
                              style={"description_width": "initial"})
        csv_cb   = w.Checkbox(value=False, description="Volume — CSV",
                              style={"description_width": "initial"})

        delta_tbl_wgt = w.Text(placeholder="catalog.schema.dq_results",
                               layout=w.Layout(width="100%"))
        vol_path_wgt  = w.Text(value=self.env.get("default_volume_path", "/Volumes/"),
                               layout=w.Layout(width="100%"))
        filename_wgt  = w.Text(layout=w.Layout(width="100%"))

        # Store refs for _do_save
        setattr(self, f"_{prefix}_o_df",        df_cb)
        setattr(self, f"_{prefix}_o_delta",      delta_cb)
        setattr(self, f"_{prefix}_o_vol_json",   json_cb)
        setattr(self, f"_{prefix}_o_vol_csv",    csv_cb)
        setattr(self, f"_{prefix}_o_delta_tbl",  delta_tbl_wgt)
        setattr(self, f"_{prefix}_o_vol_path",   vol_path_wgt)
        setattr(self, f"_{prefix}_o_filename",   filename_wgt)

        delta_panel = w.VBox([
            _field("Delta Table Name", delta_tbl_wgt),
        ], layout=w.Layout(padding="10px 14px", margin="0 0 6px 0", display="none"))
        delta_panel.add_class("dq-sub-panel")

        vol_panel = w.VBox([
            _field("Volume Path", vol_path_wgt),
            _field("Filename (no extension)", filename_wgt),
        ], layout=w.Layout(padding="10px 14px", margin="0 0 6px 0", display="none"))
        vol_panel.add_class("dq-sub-panel")

        def _toggle_delta(change):
            delta_panel.layout.display = "" if change["new"] else "none"
            if change["new"] and not delta_tbl_wgt.value.strip():
                cat = self.env.get("default_catalog", "")
                sch = self.env.get("default_schema", "")
                tbl = self._full.split(".")[-1] if self._full else "results"
                sfx = "" if prefix == "check" else "_summary"
                if cat and sch:
                    delta_tbl_wgt.value = f"{cat}.{sch}.dq_{tbl}{sfx}"

        def _toggle_vol(change):
            show = json_cb.value or csv_cb.value
            vol_panel.layout.display = "" if show else "none"
            if show:
                if not vol_path_wgt.value.strip():
                    base = self.env.get("default_volume_path", "/Volumes/").rstrip("/")
                    if self._full:
                        parts = self._full.split(".")
                        cat, sch = (parts + ["", ""])[:2]
                        vol_path_wgt.value = f"{base}/{cat}/{sch}"
                    else:
                        vol_path_wgt.value = base
                if not filename_wgt.value.strip():
                    tbl = self._full.split(".")[-1] if self._full else "table"
                    sfx = "" if prefix == "check" else "_summary"
                    filename_wgt.value = f"dq_{tbl}{sfx}_{datetime.now().strftime('%Y%m%d')}"

        delta_cb.observe(_toggle_delta, names="value")
        json_cb.observe(_toggle_vol,   names="value")
        csv_cb.observe(_toggle_vol,    names="value")

        # Pre-fill filename
        if self._full:
            tbl = self._full.split(".")[-1]
            sfx = "" if prefix == "check" else "_summary"
            filename_wgt.value = f"dq_{tbl}{sfx}_{datetime.now().strftime('%Y%m%d')}"

        opts_box = w.VBox([
            _h(
                f"<div style='font-size:13px;font-weight:700;color:#1B3A4B;"
                f"margin-bottom:4px'>{title}</div>"
                f"<div style='font-size:11px;color:#666;margin-bottom:10px'>{description}</div>"
            ),
            df_cb, delta_cb, json_cb, csv_cb,
        ], layout=w.Layout(padding="14px", margin="0 0 6px 0"))
        opts_box.add_class("dq-out-opts")

        return w.VBox([opts_box, delta_panel, vol_panel])

    # ── Step 5: Metadata ──────────────────────────────────────────────────────

    def _make_metadata_step(self) -> w.VBox:
        return w.VBox([
            _sec("🏷️  Step 5 of 5 — Metadata"),
            _info("Metadata fields are stored in every output row for traceability. "
                  "All optional. When ready, click <b>💾 Save Config</b>.", "info"),
            w.HBox([
                _field("Data Owner",   self._m_owner),
                w.HTML("&nbsp;&nbsp;"),
                _field("Data Steward", self._m_steward),
            ]),
            w.HBox([
                _field("Business Domain", self._m_domain),
                w.HTML("&nbsp;&nbsp;"),
                _field("Tags (comma-separated)", self._m_tags),
            ]),
            _field("Description", self._m_desc),
        ], layout=w.Layout(padding="18px"))

    # ── Widget helpers ────────────────────────────────────────────────────────

    def _make_simple_widget(self, pname: str, default):
        W = w.Layout(width="280px")
        if pname in ("min_value", "max_value", "sum_value"):
            return w.FloatText(value=float(default) if default is not None else 0.0, layout=W)
        if pname == "value":
            return w.Text(value=str(default) if default is not None else "", layout=W)
        if pname in ("n_days", "n_minutes"):
            return w.IntText(value=int(default) if default else 7, layout=W)
        if pname == "quantile":
            return w.BoundedFloatText(value=0.5, min=0.0, max=1.0, step=0.01, layout=W)
        if pname in ("regex", "like_pattern", "strftime_format"):
            return w.Text(value=str(default) if default else "", layout=w.Layout(width="340px"))
        if pname in ("value_set", "regex_list", "type_list"):
            return w.Text(placeholder="A, B, C  (comma-separated)", layout=w.Layout(width="340px"))
        if pname == "sql_filter":
            return w.Textarea(
                placeholder="SQL WHERE clause — matching rows are FAILED\ne.g. amount < 0",
                layout=w.Layout(width="100%", height="60px"),
            )
        if pname == "type_":
            return w.Dropdown(
                options=["string","int","long","double","float",
                         "boolean","date","timestamp","decimal"],
                layout=W,
            )
        return None

    def _make_complex_wizard(
        self, check_name: str, params: dict,
        col_names: list[str], widget_store: dict
    ) -> w.VBox:
        rows: list = [
            _h(
                f"<div style='font-size:12px;font-weight:700;color:#92400E;margin-bottom:10px'>"
                f"⚙️ Advanced Parameters — <code style='font-size:11px'>{check_name}</code></div>"
            ),
        ]

        if "columns" in params:
            wgt = w.SelectMultiple(
                options=col_names,
                rows=min(6, max(3, len(col_names))),
                layout=w.Layout(width="100%"),
            )
            widget_store["columns"] = wgt
            rows.append(w.VBox([
                _h("<div style='font-size:11px;color:#5C6673;font-weight:600;margin-bottom:3px'>"
                   "COLUMNS <span style='color:#AAA;font-weight:400'>"
                   "(hold Ctrl/⌘ for multi-select)</span></div>"),
                wgt,
            ], layout=w.Layout(margin="0 0 10px 0")))

        if "reference_table" in params:
            wgt = w.Text(placeholder="catalog.schema.reference_table",
                         layout=w.Layout(width="100%"))
            widget_store["reference_table"] = wgt
            rows.append(w.VBox([_label("Reference Table"), wgt],
                               layout=w.Layout(margin="0 0 8px 0")))

        if "reference_column" in params:
            wgt = w.Text(placeholder="column name in reference table",
                         layout=w.Layout(width="100%"))
            widget_store["reference_column"] = wgt
            rows.append(w.VBox([_label("Reference Column"), wgt],
                               layout=w.Layout(margin="0 0 8px 0")))

        if "column_b" in params:
            wgt = w.Dropdown(options=col_names or ["—"], layout=w.Layout(width="100%"))
            widget_store["column_b"] = wgt
            rows.append(w.VBox([_label("Column B"), wgt],
                               layout=w.Layout(margin="0 0 8px 0")))

        if "valid_pairs" in params:
            wgt = w.Textarea(
                placeholder='[["val_a","val_b"],["val_c","val_d"]]  (JSON array)',
                layout=w.Layout(width="100%", height="60px"),
            )
            widget_store["valid_pairs"] = wgt
            rows.append(w.VBox([_label("Valid Pairs (JSON)"), wgt],
                               layout=w.Layout(margin="0 0 8px 0")))

        if "expected_schema" in params:
            wgt = w.Textarea(
                placeholder='[["col1","string"],["col2","int"]]  (JSON list of [name, type])',
                layout=w.Layout(width="100%", height="60px"),
            )
            widget_store["expected_schema"] = wgt
            rows.append(w.VBox([_label("Expected Schema (JSON)"), wgt],
                               layout=w.Layout(margin="0 0 8px 0")))

        if "check_orphans" in params:
            wgt = w.Checkbox(value=False, description="Check orphans (bidirectional RI)",
                             style={"description_width": "initial"})
            widget_store["check_orphans"] = wgt
            rows.append(wgt)

        box = w.VBox(rows)
        box.add_class("dq-wizard")
        return box

    # ── Save Config ───────────────────────────────────────────────────────────

    def _do_save(self, _=None):
        # Flatten checks
        all_checks: list[dict] = []
        for checks in self._col_checks.values():
            all_checks.extend(checks)
        all_checks.extend(self._extra_checks)

        def _out_cfg(prefix: str) -> dict:
            types = []
            if getattr(self, f"_{prefix}_o_df") is not None and getattr(self, f"_{prefix}_o_df").value:
                types.append("dataframe")
            if getattr(self, f"_{prefix}_o_delta") is not None and getattr(self, f"_{prefix}_o_delta").value:
                types.append("delta")
            if getattr(self, f"_{prefix}_o_vol_json") is not None and getattr(self, f"_{prefix}_o_vol_json").value:
                types.append("volume_json")
            if getattr(self, f"_{prefix}_o_vol_csv") is not None and getattr(self, f"_{prefix}_o_vol_csv").value:
                types.append("volume_csv")
            if not types:
                types = ["dataframe"]
            return {
                "types":       types,
                "delta_table": (getattr(self, f"_{prefix}_o_delta_tbl").value.strip()
                                if getattr(self, f"_{prefix}_o_delta_tbl") else ""),
                "volume_path": (getattr(self, f"_{prefix}_o_vol_path").value.strip()
                                if getattr(self, f"_{prefix}_o_vol_path") else ""),
                "filename":    (getattr(self, f"_{prefix}_o_filename").value.strip()
                                if getattr(self, f"_{prefix}_o_filename") else ""),
            }

        self._config.clear()
        self._config.update({
            "source": {"table": self._full},
            "metadata": {
                "data_owner":      self._m_owner.value.strip(),
                "data_steward":    self._m_steward.value.strip(),
                "business_domain": self._m_domain.value.strip(),
                "description":     self._m_desc.value.strip(),
                "tags":            [t.strip() for t in self._m_tags.value.split(",") if t.strip()],
            },
            "checks":       all_checks,
            "output":       _out_cfg("check"),    # check-level (backward-compat key)
            "table_output": _out_cfg("tbl"),      # table summary
        })

        # Persist to config_dir/catalog/schema/table.json
        config_dir = self.env.get("config_dir", "").strip()
        saved_path = ""
        write_error = ""
        if config_dir and self._full:
            parts = self._full.split(".")
            cat, sch, tbl = (parts + ["", "", ""])[:3]
            target_dir = os.path.join(config_dir, cat, sch)
            attempt_path = os.path.join(target_dir, f"{tbl}.json")
            try:
                os.makedirs(target_dir, exist_ok=True)
            except Exception as exc:
                write_error = f"Could not create directory <code>{target_dir}</code>: {exc}"
            if not write_error:
                try:
                    with open(attempt_path, "w") as f:
                        json.dump(self._config, f, indent=2)
                    saved_path = attempt_path
                except Exception as exc:
                    write_error = f"Could not write <code>{attempt_path}</code>: {exc}"

        n = len(all_checks)
        col_n = sum(
            1 for c in self._col_checks if self._col_checks[c]
        )

        path_repr = repr(saved_path) if saved_path else "config  # (dict returned by configure())"
        cmd = (
            f"import dashdq\n\n"
            f"config_path = {path_repr}\n\n"
            f"# Run checks (returns DQReport)\n"
            f"report = dashdq.run_checks(config_path, spark=spark)\n\n"
            f"# Check-level detail — one row per check × column\n"
            f"report.display()\n\n"
            f"# Table-level summary — overall PASS/FAIL, clean record count\n"
            f"summary = report.table_summary()\n\n"
            f"# Pipeline gate — raises nothing, returns bool\n"
            f"ok = dashdq.table_quality_ok(config_path, spark=spark)"
        )

        if saved_path:
            path_line = f"✅ Saved to <code>{saved_path}</code>"
        elif write_error:
            path_line = (
                f"⚠️ Write failed — {write_error}<br>"
                f"Config is in-memory only. Run <code>dashdq.env_setup()</code> "
                f"to fix the Config Directory."
            )
        else:
            path_line = (
                "⚠️ No Config Directory set — config is in-memory only. "
                "Run <code>dashdq.env_setup()</code> to set a path."
            )

        self._nav_msg.children = (_h(
            f"<div style='background:#F0FDF4;border:1px solid #BBF7D0;"
            f"border-radius:6px;padding:14px 16px;margin:4px 0;max-width:920px'>"
            f"<div style='font-size:13px;font-weight:700;color:#166534;margin-bottom:6px'>"
            f"✅ Config saved — {n} check{'s' if n != 1 else ''} across "
            f"{col_n} column{'s' if col_n != 1 else ''} on "
            f"<code>{self._full or '(no table)'}</code></div>"
            f"<div style='font-size:11px;color:#555;margin-bottom:10px'>{path_line}</div>"
            f"<div style='font-size:11px;font-weight:700;color:#1B3A4B;margin-bottom:6px'>"
            f"Run in a notebook cell:</div>"
            f"<pre style='background:#1B3A4B;color:#E2E8F0;padding:12px 14px;"
            f"border-radius:5px;font-size:11px;overflow-x:auto;margin:0;line-height:1.6'>"
            f"{cmd}</pre>"
            f"</div>"
        ),)


# ═════════════════════════════════════════════════════════════════════════════
# DashDQEnvSetup — standalone environment configuration panel
# ═════════════════════════════════════════════════════════════════════════════

class DashDQEnvSetup:
    """Standalone panel to configure DashDQ environment defaults."""

    def __init__(self):
        self.env = _load_env()
        display(HTML(_CSS))
        self._build()

    def _build(self):
        e = self.env

        config_dir_wgt = w.Text(
            value=e.get("config_dir", ""),
            placeholder="/Workspace/Shared/dashdq_configs",
            layout=w.Layout(width="100%"),
        )
        default_cat_wgt = w.Text(
            value=e.get("default_catalog", ""),
            placeholder="e.g. ai_innovation_gold_dev",
            layout=w.Layout(width="100%"),
        )
        default_sch_wgt = w.Text(
            value=e.get("default_schema", ""),
            placeholder="e.g. sdh",
            layout=w.Layout(width="100%"),
        )
        vol_path_wgt = w.Text(
            value=e.get("default_volume_path", "/Volumes/"),
            placeholder="/Volumes/catalog/schema/volume",
            layout=w.Layout(width="100%"),
        )

        status = w.VBox([])
        save_box,   save_btn   = _styled_btn("💾  Save Settings", "primary")
        reload_box, reload_btn = _styled_btn("↺  Reload from disk", "secondary")
        test_box,   test_btn   = _styled_btn("🔍  Test config path", "outline")
        save_btn.layout   = w.Layout(height="34px")
        reload_btn.layout = w.Layout(height="34px")
        test_btn.layout   = w.Layout(height="34px")

        def _save(_):
            self.env.update({
                "config_dir":          config_dir_wgt.value.strip(),
                "default_catalog":     default_cat_wgt.value.strip(),
                "default_schema":      default_sch_wgt.value.strip(),
                "default_volume_path": vol_path_wgt.value.strip(),
            })
            try:
                path = _save_env(self.env)
                status.children = (_info(
                    f"✅ Settings saved to <code>{path}</code>. "
                    "Reload the wizard for defaults to take effect.", "ok"
                ),)
            except Exception as exc:
                status.children = (_info(f"❌ Could not save settings: {exc}", "error"),)

        def _reload(_):
            self.env = _load_env()
            config_dir_wgt.value  = self.env.get("config_dir", "")
            default_cat_wgt.value = self.env.get("default_catalog", "")
            default_sch_wgt.value = self.env.get("default_schema", "")
            vol_path_wgt.value    = self.env.get("default_volume_path", "/Volumes/")
            status.children = (_info(f"Reloaded from <code>{_ENV_PATH}</code>.", "info"),)

        def _test_path(_):
            path = config_dir_wgt.value.strip()
            if not path:
                status.children = (_info("⚠️ Enter a Config Directory path first.", "warn"),)
                return
            test_file = os.path.join(path, ".dashdq_write_test")
            try:
                os.makedirs(path, exist_ok=True)
                with open(test_file, "w") as f:
                    f.write("ok")
                os.remove(test_file)
                status.children = (_info(
                    f"✅ Path <code>{path}</code> is writable.", "ok"
                ),)
            except Exception as exc:
                status.children = (_info(
                    f"❌ Cannot write to <code>{path}</code>: {exc}", "error"
                ),)

        save_btn.on_click(_save)
        reload_btn.on_click(_reload)
        test_btn.on_click(_test_path)

        root = w.VBox([
            _sec("⚙️  DashDQ Environment Setup"),
            _info(
                f"Settings are saved to <code>{_ENV_PATH}</code> "
                f"(override with <code>$DASHDQ_ENV_PATH</code>). "
                "The wizard reads these on every launch.", "info"
            ),
            w.VBox([
                _label("Config Directory"),
                _h("<div style='font-size:11px;color:#888;margin-bottom:4px'>"
                   "Where check configs are saved as "
                   "<code>config_dir/catalog/schema/table.json</code>. "
                   "Use a Workspace path e.g. "
                   "<code>/Workspace/Shared/dashdq_configs</code> "
                   "or a Volume path.</div>"),
                config_dir_wgt,
            ], layout=w.Layout(margin="0 0 12px 0")),
            w.HBox([
                _field("Default Catalog", default_cat_wgt),
                w.HTML("&nbsp;&nbsp;"),
                _field("Default Schema",  default_sch_wgt),
            ]),
            _field("Default Volume Output Path", vol_path_wgt),
            w.HBox([save_box, reload_box, test_box],
                   layout=w.Layout(margin="6px 0 0 0")),
            status,
        ], layout=w.Layout(max_width="860px", padding="14px"))
        root.add_class("dq-root")
        root.add_class("dq-form-box")
        display(root)


# ═════════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════════

def env_setup() -> None:
    """
    Open the DashDQ environment setup panel.

    Configure once; settings persist to ``~/dashdq_env.json`` and are read
    automatically by every subsequent ``dashdq.configure()`` call::

        dashdq.env_setup()   # set config_dir, default catalog/schema, volume path
        config = dashdq.configure(spark=spark)
    """
    global _active_wizard
    _active_wizard = DashDQEnvSetup()


def configure(spark=None) -> dict:
    """
    Open the DashDQ sequential wizard (5 steps).
    Returns a config dict that is filled when you click **💾 Save Config**.
    Pass it (or the saved file path) to ``dashdq.run_checks(config)``.
    """
    global _active_wizard
    config: dict = {}
    _active_wizard = DashDQWizard(spark=spark, config_target=config)
    return config


def run_checks(config: dict, spark=None):
    """Execute config returned by ``configure()`` and display the DQReport."""
    from dashdq.suite import run_checks as _run
    report = _run(config, spark)

    s = report.summary()
    display(HTML(
        f"<div class='dq-summary'>"
        f"<span>Total: {s['total_checks']}</span>&nbsp;&nbsp;"
        f"<span class='dq-pass'>✅ Passed: {s['passed']}</span>&nbsp;&nbsp;"
        f"<span class='dq-fail'>❌ Failed: {s['failed']}</span>&nbsp;&nbsp;"
        f"<span>Pass Rate: {s['pass_rate_pct']}%</span>"
        f"</div>"
    ))
    report.display()
    return report


def launch(spark=None):
    """All-in-one: open wizard + Run Checks button."""
    config = configure(spark)
    result_out = w.VBox([])
    run_box, run_btn = _styled_btn("▶  Run Checks", "primary")
    run_btn.layout = w.Layout(height="38px", min_width="160px")

    def _run(_):
        if not config.get("checks"):
            result_out.children = (
                _info("⚠️ Complete the wizard and click 💾 Save Config first.", "warn"),
            )
            return
        result_out.children = (_info("⏳ Running checks…", "info"),)
        try:
            run_checks(config, spark)
        except Exception as exc:
            result_out.children = (_info(f"❌ {exc}", "error"),)

    run_btn.on_click(_run)
    display(w.VBox([
        _h("<hr style='margin:16px 0'>"),
        run_box,
        result_out,
    ]))
