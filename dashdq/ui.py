"""DashDQ UI — Databricks-themed interactive wizard.

Tabs:
  📊 Source   — Unity Catalog cascade: catalog → schema → table
  ✅ Checks   — per-column multi-check builder with complex-check wizard
  📤 Output   — multi-destination: DataFrame, Delta, Volume JSON/CSV
  🏷️ Metadata — owner, steward, domain, tags, description (stored in output)

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

# Keep a strong reference so the wizard isn't garbage-collected mid-session.
_active_wizard: "DashDQWizard | None" = None

# ─── Theme constants ──────────────────────────────────────────────────────────

_DIM_BG   = {"Completeness": "#DBEAFE", "Accuracy": "#DCFCE7",
              "Integrity": "#FEF3C7",   "Consistency": "#F3E8FF"}
_DIM_FG   = {"Completeness": "#1E40AF", "Accuracy": "#166534",
              "Integrity": "#92400E",   "Consistency": "#6B21A8"}

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
/* ── General ── */
.dq-root { font-family: -apple-system,'Segoe UI',Roboto,Oxygen,sans-serif; }

/* ── Tab bar (supports both p- and lm- JupyterLab prefixes) ── */
.dq-tabs .p-TabBar,
.dq-tabs .lm-TabBar {
    background: #F7F8FA !important;
    border-bottom: 1px solid #E8EBF0 !important;
}
.dq-tabs .p-TabBar-tab,
.dq-tabs .lm-TabBar-tab {
    background: #F7F8FA !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    color: #5C6673 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 9px 18px !important;
    transition: color .15s;
}
.dq-tabs .p-TabBar-tab.p-mod-current,
.dq-tabs .lm-TabBar-tab.lm-mod-current {
    background: #fff !important;
    color: #1B3A4B !important;
    border-bottom: 2px solid #FF3621 !important;
    font-weight: 700 !important;
}
.dq-tabs .p-TabBar-tab:hover:not(.p-mod-current),
.dq-tabs .lm-TabBar-tab:hover:not(.lm-mod-current) {
    color: #1B3A4B !important;
    background: #EEF1F4 !important;
}
.dq-tabs .widget-tab-contents { background: #fff !important; }

/* ── Section header ── */
.dq-sec {
    background: linear-gradient(90deg,#1B3A4B 0%,#2D5A7B 100%);
    color: #fff; padding: 7px 14px; border-radius: 5px;
    font-size: 12px; font-weight: 700; letter-spacing: .3px;
    margin-bottom: 10px;
}

/* ── Dimension badges ── */
.dq-badge { padding: 2px 9px; border-radius: 12px; font-size: 11px; font-weight: 600; }
.dq-Completeness { background:#DBEAFE; color:#1E40AF; }
.dq-Accuracy     { background:#DCFCE7; color:#166534; }
.dq-Integrity    { background:#FEF3C7; color:#92400E; }
.dq-Consistency  { background:#F3E8FF; color:#6B21A8; }

/* ── Alerts ── */
.dq-info  { background:#EFF6FF; border-left:3px solid #1890FF; padding:8px 12px; border-radius:0 4px 4px 0; font-size:12px; margin:4px 0 10px 0; }
.dq-ok    { background:#F0FDF4; border-left:3px solid #43A047; padding:8px 12px; border-radius:0 4px 4px 0; font-size:12px; margin:4px 0 10px 0; }
.dq-warn  { background:#FFFBEB; border-left:3px solid #FFA000; padding:8px 12px; border-radius:0 4px 4px 0; font-size:12px; margin:4px 0 10px 0; }
.dq-error { background:#FEF2F2; border-left:3px solid #C62828; padding:8px 12px; border-radius:0 4px 4px 0; font-size:12px; margin:4px 0 10px 0; }

/* ── Buttons via class on wrapping div ── */
.dq-primary  .widget-button { background:#FF3621!important; color:#fff!important; border:none!important; border-radius:4px!important; font-weight:600!important; }
.dq-primary  .widget-button:hover { background:#D92B1A!important; }
.dq-secondary .widget-button { background:#fff!important; color:#1B3A4B!important; border:1px solid #1B3A4B!important; border-radius:4px!important; }
.dq-outline  .widget-button { background:transparent!important; color:#1890FF!important; border:1px solid #1890FF!important; border-radius:4px!important; }
.dq-danger   .widget-button { background:transparent!important; color:#C62828!important; border:1px solid #C62828!important; border-radius:4px!important; font-size:11px!important; }
.dq-success  .widget-button { background:#43A047!important; color:#fff!important; border:none!important; border-radius:4px!important; font-weight:600!important; }

/* ── Column selector ── */
.dq-col-select select {
    font-family:'Monaco','Consolas',monospace!important;
    font-size:12px!important;
    border:1px solid #E8EBF0!important;
    border-radius:4px!important;
}

/* ── Complex wizard panel ── */
.dq-wizard {
    background:#FFFBEB; border:1.5px solid #FDE68A;
    border-radius:6px; padding:14px; margin-top:10px;
}
.dq-wizard-title {
    font-size:12px; font-weight:700; color:#92400E;
    margin-bottom:10px; display:flex; align-items:center; gap:6px;
}

/* ── Summary banner ── */
.dq-summary {
    background:linear-gradient(90deg,#1B3A4B,#2D5A7B);
    color:#fff; border-radius:6px; padding:12px 20px;
    font-size:13px; font-weight:600; margin-top:12px;
}
.dq-pass { color:#86EFAC; }
.dq-fail { color:#FCA5A5; }

/* ── Container panels (ipywidgets-7-safe: no Layout border/border_radius) ── */
.dq-form-box  { border:1px solid #E8EBF0!important; border-radius:6px!important;
                padding:14px!important; margin-top:10px!important; background:#FAFBFC!important; }
.dq-check-row { border:1px solid #E8EBF0!important; border-radius:4px!important;
                padding:7px 10px!important; margin-bottom:6px!important; background:#fff!important; }
.dq-out-opts  { border:1px solid #E8EBF0!important; border-radius:6px!important;
                padding:14px!important; margin-bottom:12px!important; }
.dq-sub-panel { border:1px solid #E8EBF0!important; border-radius:4px!important;
                padding:10px 14px!important; margin-bottom:8px!important; }

/* ── HBox gap shim (ipywidgets 7 has no gap in Layout) ── */
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
    # r[0] = databaseName/namespace (schema name); r[1] = comment — use r[0]
    try:
        rows = spark.sql(f"SHOW SCHEMAS IN `{catalog}`").collect()
        return sorted(r[0] for r in rows if r[0])
    except Exception:
        return []


def _list_tables(spark, catalog: str, schema: str) -> list[str]:
    # r[0] = database, r[1] = tableName, r[2] = isTemporary
    try:
        rows = spark.sql(f"SHOW TABLES IN `{catalog}`.`{schema}`").collect()
        return sorted(r[1] for r in rows if not r[2])
    except Exception:
        return []


def _table_info(spark, full_table: str) -> tuple[list[tuple[str, str]], int]:
    """Returns ([(col, dtype), ...], row_count)."""
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


def _load_existing_checks(config_dir: str, table: str) -> list[dict]:
    """Load checks from config_dir/catalog/schema/table.json (or legacy flat layout)."""
    if not config_dir or not os.path.isdir(config_dir):
        return []
    # Preferred: config_dir/catalog/schema/table.json
    parts = table.split(".")
    if len(parts) == 3:
        cat, sch, tbl = parts
        direct = os.path.join(config_dir, cat, sch, f"{tbl}.json")
        if os.path.exists(direct):
            try:
                with open(direct) as f:
                    cfg = json.load(f)
                return cfg.get("checks", [])
            except Exception:
                pass
    # Fallback: scan flat directory (legacy or single-schema setups)
    for fname in sorted(os.listdir(config_dir)):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(config_dir, fname)) as f:
                cfg = json.load(f)
            if cfg.get("source", {}).get("table") == table:
                return cfg.get("checks", [])
        except Exception:
            pass
    return []


# ─── Widget helpers ───────────────────────────────────────────────────────────

def _h(html: str) -> w.HTML:
    return w.HTML(html)


def _sec(title: str) -> w.HTML:
    return _h(f"<div class='dq-sec'>{title}</div>")


def _label(text: str) -> w.HTML:
    return _h(f"<div style='font-size:11px;color:#5C6673;font-weight:600;margin-bottom:3px;text-transform:uppercase;letter-spacing:.4px'>{text}</div>")


def _info(text: str, kind: str = "info") -> w.HTML:
    return _h(f"<div class='dq-{kind}'>{text}</div>")


def _badge(dim: str) -> str:
    return f"<span class='dq-badge dq-{dim}'>{dim}</span>"


def _field(label: str, widget, width: str = "100%") -> w.VBox:
    widget.layout.width = width
    return w.VBox([_label(label), widget], layout=w.Layout(margin="0 0 10px 0"))


def _mk_btn(label: str, kind: str = "primary") -> w.Button:
    btn = w.Button(description=label)
    return btn


def _styled_btn(label: str, kind: str = "primary") -> w.HBox:
    btn = w.Button(description=label)
    box = w.HBox([btn])
    box.add_class(f"dq-{kind}")
    return box, btn


# ─── Check grouping ───────────────────────────────────────────────────────────

_GROUPED: dict[str, list[str]] = {}
for _k, _v in CHECKS_REGISTRY.items():
    _GROUPED.setdefault(_v["dimension"], []).append(_k)


def _check_options() -> list[tuple[str, str]]:
    opts = []
    for dim in DQ_DIMENSIONS:
        for name in _GROUPED.get(dim, []):
            opts.append((f"[{dim[:4]}] {name}", name))
    return opts


def _is_complex(check_name: str) -> bool:
    return bool(_COMPLEX_KEYS & set(CHECKS_REGISTRY.get(check_name, {}).get("params", {}).keys()))


# ═════════════════════════════════════════════════════════════════════════════
# DashDQWizard
# ═════════════════════════════════════════════════════════════════════════════

class DashDQWizard:
    """Databricks-themed 5-tab DQ configuration wizard."""

    def __init__(self, spark=None, config_target: dict | None = None):
        self.spark = spark or _get_spark()
        self.env = _load_env()

        # Runtime state
        self._catalog = self.env.get("default_catalog", "")
        self._schema  = self.env.get("default_schema", "")
        self._table   = ""
        self._full    = ""
        self._columns: list[tuple[str, str]] = []
        self._selected_col = ""
        self._checks: list[dict] = []
        self._edit_idx: int | None = None     # None = Add mode, int = Edit mode

        # Param widget refs (reset on check select)
        self._simple_widgets: dict = {}
        self._complex_widgets: dict = {}

        # Config target (mutable dict handed to the caller)
        self._config: dict = config_target if config_target is not None else {}

        # Inject CSS
        display(HTML(_CSS))

        # Build and display
        self._build()

    # ──────────────────── Build UI ────────────────────────────────────────────

    def _build(self):
        tab_source = self._make_source_tab()
        tab_checks = self._make_checks_tab()
        tab_output = self._make_output_tab()
        tab_meta   = self._make_meta_tab()

        tabs = w.Tab(children=[tab_source, tab_checks, tab_output, tab_meta])
        for i, title in enumerate([
            "📊  Source", "✅  Checks", "📤  Output", "🏷️  Metadata",
        ]):
            tabs.set_title(i, title)
        tabs.add_class("dq-tabs")

        # Collapsible env settings panel (hidden by default)
        self._env_panel = self._make_env_panel()
        self._env_panel.layout.display = "none"

        gear_box, gear_btn = _styled_btn("⚙️  Settings", "outline")
        gear_btn.layout = w.Layout(height="28px")

        def _toggle_env(_):
            self._env_panel.layout.display = (
                "none" if self._env_panel.layout.display == "" else ""
            )
        gear_btn.on_click(_toggle_env)

        header = w.HBox([
            _h("<div style='font-size:15px;font-weight:700;color:#1B3A4B;"
               "letter-spacing:.2px'>DashDQ — Data Quality Wizard</div>"),
            gear_box,
        ], layout=w.Layout(justify_content="space-between", align_items="center",
                           margin="0 0 8px 0"))

        # Save Config button
        self._save_status = w.VBox([])
        save_box, save_btn = _styled_btn("💾  Save Configuration", "success")
        save_btn.on_click(self._do_save)
        save_btn.layout = w.Layout(height="38px", min_width="200px")

        save_bar = w.HBox([save_box, self._save_status],
                          layout=w.Layout(align_items="center", margin="14px 0 0 0"))
        save_bar.add_class("dq-gap-8")

        root = w.VBox([
            header,
            self._env_panel,
            tabs,
            save_bar,
        ], layout=w.Layout(max_width="1140px", padding="12px"))
        root.add_class("dq-root")
        display(root)

        # Load catalogs immediately (no lazy tab-visit needed)
        self._do_load_catalogs()

        # Populate check form params
        self._on_check_select({"new": self._check_dd.value})

    # ──────────────────── Settings panel (collapsible) ────────────────────────

    def _make_env_panel(self) -> w.VBox:
        e = self.env
        self._e_config_dir  = w.Text(value=e.get("config_dir", ""),
                                     placeholder="/Workspace/Shared/dashdq_configs",
                                     layout=w.Layout(width="100%"))
        self._e_default_cat = w.Text(value=e.get("default_catalog", ""),
                                     placeholder="e.g. ai_innovation_gold_dev",
                                     layout=w.Layout(width="100%"))
        self._e_default_sch = w.Text(value=e.get("default_schema", ""),
                                     placeholder="e.g. sdh",
                                     layout=w.Layout(width="100%"))
        self._e_vol_path    = w.Text(value=e.get("default_volume_path", "/Volumes/"),
                                     placeholder="/Volumes/catalog/schema/volume",
                                     layout=w.Layout(width="100%"))

        env_status = w.VBox([])
        save_box, save_btn = _styled_btn("💾  Save Environment Config", "secondary")
        reload_box, reload_btn = _styled_btn("↺  Reload from Disk", "outline")

        def _save(_):
            self.env.update({
                "config_dir":          self._e_config_dir.value.strip(),
                "default_catalog":     self._e_default_cat.value.strip(),
                "default_schema":      self._e_default_sch.value.strip(),
                "default_volume_path": self._e_vol_path.value.strip(),
            })
            path = _save_env(self.env)
            env_status.children = (_info(f"✅ Saved to <code>{path}</code>", "ok"),)

        def _reload(_):
            self.env = _load_env()
            self._e_config_dir.value  = self.env.get("config_dir", "")
            self._e_default_cat.value = self.env.get("default_catalog", "")
            self._e_default_sch.value = self.env.get("default_schema", "")
            self._e_vol_path.value    = self.env.get("default_volume_path", "/Volumes/")
            env_status.children = (_info("Reloaded from disk.", "info"),)

        save_btn.on_click(_save)
        reload_btn.on_click(_reload)

        panel = w.VBox([
            _h("<div style='font-size:12px;font-weight:700;color:#1B3A4B;margin-bottom:10px'>"
               "⚙️  Environment Settings</div>"),
            _info("Defaults are loaded from <code>~/dashdq_env.json</code> "
                  "(or <code>$DASHDQ_ENV_PATH</code>). Edit and save to persist across sessions.", "info"),

            w.VBox([
                _label("DashDQ Config Directory"),
                _h("<div style='font-size:11px;color:#888;margin-bottom:4px'>"
                   "Existing check config JSON files are auto-loaded for a selected table.</div>"),
                self._e_config_dir,
            ], layout=w.Layout(margin="0 0 12px 0")),

            w.HBox([
                _field("Default Catalog", self._e_default_cat),
                w.HTML("&nbsp;&nbsp;"),
                _field("Default Schema", self._e_default_sch),
            ]),

            _field("Default Volume Output Path", self._e_vol_path),

            w.HBox([save_box, reload_box]),
            env_status,
        ], layout=w.Layout(padding="14px", margin="0 0 10px 0"))
        panel.add_class("dq-form-box")
        return panel

    # ──────────────────── Tab 1: Source ───────────────────────────────────────

    def _make_source_tab(self) -> w.VBox:
        self._cat_dd = w.Dropdown(
            options=["— loading catalogs… —"],
            layout=w.Layout(width="100%"),
        )
        self._sch_dd = w.Dropdown(
            options=["— select schema —"],
            disabled=True,
            layout=w.Layout(width="100%"),
        )
        self._tbl_dd = w.Dropdown(
            options=["— select table —"],
            disabled=True,
            layout=w.Layout(width="100%"),
        )
        self._load_tbl_btn_box, self._load_tbl_btn = _styled_btn("📥  Load Table & Columns", "primary")
        self._load_tbl_btn.disabled = True
        self._load_tbl_btn.layout  = w.Layout(height="36px")

        self._source_info = w.VBox([])   # children-swap

        self._cat_dd.observe(self._on_catalog_change, names="value")
        self._sch_dd.observe(self._on_schema_change,  names="value")
        self._tbl_dd.observe(self._on_table_change,   names="value")
        self._load_tbl_btn.on_click(self._do_load_table)

        return w.VBox([
            _sec("📊  Source Table"),
            _info("Catalogs load automatically. Select catalog → schema → table, then click Load.", "info"),

            w.VBox([_label("Catalog"), self._cat_dd], layout=w.Layout(margin="0 0 10px 0")),
            w.VBox([_label("Schema"),  self._sch_dd], layout=w.Layout(margin="0 0 10px 0")),
            w.VBox([_label("Table"),   self._tbl_dd], layout=w.Layout(margin="0 0 12px 0")),

            w.HBox([self._load_tbl_btn_box], layout=w.Layout(margin="0 0 10px 0")),
            self._source_info,
        ], layout=w.Layout(padding="18px"))

    def _do_load_catalogs(self, _=None):
        self._catalogs_loaded = True
        catalogs = _list_catalogs(self.spark) if self.spark else []
        opts = (["— select catalog —"] + catalogs) if catalogs else ["— no catalogs found —"]
        self._cat_dd.options = opts
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
        self._sch_dd.options = ["— select schema —"] + schemas
        self._sch_dd.disabled = not bool(schemas)
        self._tbl_dd.options = ["— select table —"]
        self._tbl_dd.disabled = True
        self._load_tbl_btn.disabled = True
        default = self.env.get("default_schema", "")
        if default and default in schemas:
            self._sch_dd.value = default

    def _on_schema_change(self, change):
        val = change["new"]
        if val.startswith("—"):
            return
        self._schema = val
        tables = _list_tables(self.spark, self._catalog, val) if self.spark else []
        self._tbl_dd.options = ["— select table —"] + tables
        self._tbl_dd.disabled = not bool(tables)
        self._load_tbl_btn.disabled = True

    def _on_table_change(self, change):
        val = change["new"]
        if not val.startswith("—"):
            self._table = val
            self._load_tbl_btn.disabled = False

    def _do_load_table(self, _=None):
        self._full = f"{self._catalog}.{self._schema}.{self._table}"
        self._source_info.children = (_info(f"Loading <code>{self._full}</code>…", "info"),)

        cols, count = _table_info(self.spark, self._full) if self.spark else ([], -1)
        self._columns = cols

        if not cols:
            self._source_info.children = (_info("❌ Could not load table. Check permissions.", "error"),)
            return

        rc = f"{count:,}" if count >= 0 else "—"
        schema_rows = "".join(
            f"<tr><td style='padding:3px 10px;font-family:monospace;border:1px solid #E8EBF0'>{n}</td>"
            f"<td style='padding:3px 10px;color:#888;border:1px solid #E8EBF0'>{dt}</td></tr>"
            for n, dt in cols
        )
        info_widgets = [_h(
            f"<div style='background:#F0F9FF;border:1px solid #BAE6FD;border-radius:5px;"
            f"padding:10px 14px;margin-bottom:10px;font-size:12px'>"
            f"✅ <b>{self._full}</b> &nbsp;·&nbsp; "
            f"<b>{len(cols)}</b> columns &nbsp;·&nbsp; <b>{rc}</b> rows</div>"
            f"<div style='max-height:220px;overflow-y:auto;border-radius:4px'>"
            f"<table style='border-collapse:collapse;width:100%;font-size:12px'>"
            f"<tr style='background:#F7F8FA'>"
            f"<th style='padding:4px 10px;text-align:left;border:1px solid #E8EBF0'>Column</th>"
            f"<th style='padding:4px 10px;text-align:left;border:1px solid #E8EBF0'>Type</th></tr>"
            f"{schema_rows}</table></div>"
        )]

        cfg_dir = self.env.get("config_dir", "")
        existing = _load_existing_checks(cfg_dir, self._full)
        if existing:
            self._checks = existing
            info_widgets.append(_info(
                f"✅ Loaded <b>{len(existing)} existing check(s)</b> from config directory.", "ok"
            ))

        self._source_info.children = tuple(info_widgets)

        # Refresh checks tab
        self._refresh_col_list()
        self._update_output_filename()

    # ──────────────────── Tab 4: Metadata ─────────────────────────────────────

    def _make_meta_tab(self) -> w.VBox:
        self._m_owner   = w.Text(placeholder="e.g. Jane Smith",   layout=w.Layout(width="100%"))
        self._m_steward = w.Text(placeholder="e.g. John Doe",     layout=w.Layout(width="100%"))
        self._m_domain  = w.Text(placeholder="e.g. Finance, Risk",layout=w.Layout(width="100%"))
        self._m_tags    = w.Text(placeholder="tag1, tag2, tag3",   layout=w.Layout(width="100%"))
        self._m_desc    = w.Textarea(
            placeholder="Describe the purpose of this data quality run…",
            layout=w.Layout(width="100%", height="80px"),
        )
        return w.VBox([
            _sec("🏷️  Metadata"),
            _info("All metadata fields are stored in every output row, making results fully traceable. "
                  "All fields are optional.", "info"),
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

    # ──────────────────── Tab 2: Checks ───────────────────────────────────────

    def _make_checks_tab(self) -> w.VBox:
        # Column selector
        self._col_select = w.Select(
            options=[], rows=20,
            layout=w.Layout(width="270px", height="420px"),
        )
        self._col_select.add_class("dq-col-select")
        self._col_select.observe(self._on_col_select, names="value")

        # Right panel — children-swap VBox (no Output widget, works in serverless)
        self._right_panel = w.VBox([])

        # ── Add / Edit check form ──
        self._check_dd = w.Dropdown(
            options=_check_options(),
            layout=w.Layout(width="100%"),
        )
        self._check_dd.observe(self._on_check_select, names="value")

        self._threshold = w.BoundedFloatText(
            value=100.0, min=0, max=100, step=0.5,
            layout=w.Layout(width="160px"),
        )
        self._simple_out  = w.VBox([])   # children-swap
        self._complex_out = w.VBox([])   # children-swap

        self._add_btn_box, self._add_btn = _styled_btn("＋  Add Check", "primary")
        self._add_btn.on_click(self._do_add_check)

        self._form_title = w.HTML(
            "<div style='font-size:13px;font-weight:700;color:#1B3A4B;margin-bottom:8px'>Add Check</div>"
        )

        self._add_form = w.VBox([
            self._form_title,
            _label("Check"),
            self._check_dd,
            w.HBox([
                w.VBox([_label("Pass Threshold (%)"), self._threshold]),
            ], layout=w.Layout(margin="8px 0")),
            _label("Parameters"),
            self._simple_out,
            self._complex_out,
            w.HBox([self._add_btn_box], layout=w.Layout(margin="8px 0 0 0")),
        ], layout=w.Layout(padding="14px", margin="10px 0 0 0"))
        self._add_form.add_class("dq-form-box")

        right = w.VBox([self._right_panel, self._add_form], layout=w.Layout(flex="1"))

        return w.VBox([
            _sec("✅  Checks Configuration"),
            _info("Select a column on the left to view and manage its checks. "
                  "Multi-column checks (composite PK, compound unique) use the wizard below.", "info"),
            w.HBox([
                w.VBox([
                    _h("<div style='font-size:11px;color:#5C6673;font-weight:600;"
                       "text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px'>Columns</div>"),
                    self._col_select,
                ], layout=w.Layout(margin="0 16px 0 0")),
                right,
            ], layout=w.Layout(align_items="flex-start")),
        ], layout=w.Layout(padding="18px"))

    def _refresh_col_list(self):
        """Rebuild column selector with check-count badges."""
        options = []
        for name, dtype in self._columns:
            n = sum(1 for c in self._checks if c.get("column") == name)
            badge = f"  [{n}]" if n else ""
            options.append(f"{name}  ({dtype}){badge}")
        self._col_select.options = options
        if options:
            self._col_select.value = options[0]

    def _on_col_select(self, change):
        val = change["new"]
        if not val:
            return
        # Parse "col_name  (type)  [n]" → just the col name
        self._selected_col = val.split("  ")[0].strip()
        self._render_col_checks()

    def _render_col_checks(self):
        col = self._selected_col
        dtype = next((dt for n, dt in self._columns if n == col), "")
        col_checks = [(i, c) for i, c in enumerate(self._checks) if c.get("column") == col]

        n = len(col_checks)
        header = _h(
            f"<div style='margin-bottom:10px;display:flex;align-items:center;gap:10px'>"
            f"<span style='font-size:14px;font-weight:700;color:#1B3A4B;"
            f"font-family:monospace'>{col}</span>"
            f"<span style='font-size:12px;color:#888'>{dtype}</span>"
            f"<span style='background:#FF3621;color:#fff;border-radius:10px;"
            f"padding:1px 8px;font-size:11px;font-weight:700'>{n} check{'s' if n!=1 else ''}</span>"
            f"</div>"
        )
        if not col_checks:
            self._right_panel.children = (
                header,
                _info("No checks configured for this column. Use the form below to add.", "info"),
            )
        else:
            rows = [header] + [self._build_check_row(idx, chk) for idx, chk in col_checks]
            self._right_panel.children = tuple(rows)

    def _build_check_row(self, glob_idx: int, chk: dict) -> w.HBox:
        """Return a single check-row widget (no display() call)."""
        dim  = CHECKS_REGISTRY.get(chk["check_name"], {}).get("dimension", "")
        params_str = ", ".join(f"{k}={v}" for k, v in (chk.get("params") or {}).items()) or "—"
        if len(params_str) > 80:
            params_str = params_str[:77] + "…"

        rm_box, rm_btn = _styled_btn("✕ Remove", "danger")
        rm_btn.layout = w.Layout(height="28px")

        ed_box, ed_btn = _styled_btn("✎ Edit", "outline")
        ed_btn.layout = w.Layout(height="28px")

        def _remove(_):
            self._checks.pop(glob_idx)
            self._refresh_col_list()
            self._render_col_checks()

        def _edit(_):
            self._edit_idx = glob_idx
            self._check_dd.value = chk["check_name"]
            self._threshold.value = float(chk.get("threshold_pct", 100.0))
            self._form_title.value = (
                "<div style='font-size:13px;font-weight:700;color:#1B3A4B;margin-bottom:8px'>"
                "✎ Edit Check <span style='color:#FF3621;font-size:12px'>(click Update to save)</span></div>"
            )
            self._add_btn.description = "✔  Update Check"

        rm_btn.on_click(_remove)
        ed_btn.on_click(_edit)

        row = w.HBox([
            _h(
                f"<div style='flex:1'>"
                f"<span class='dq-badge dq-{dim}'>{dim}</span>&nbsp; "
                f"<code style='font-size:12px'>{chk['check_name']}</code>"
                f"<span style='color:#888;font-size:11px;margin-left:8px'>"
                f"threshold: {chk.get('threshold_pct', 100)}%</span><br>"
                f"<span style='font-size:11px;color:#AAA;margin-top:2px;display:block'>"
                f"{params_str}</span></div>"
            ),
            w.HBox([ed_box, rm_box]),
        ], layout=w.Layout(align_items="flex-start", padding="7px 10px", margin="0 0 6px 0"))
        row.add_class("dq-check-row")
        return row

    def _on_check_select(self, change):
        check_name = change["new"] if isinstance(change, dict) else change
        entry = CHECKS_REGISTRY.get(check_name, {})
        raw_params = entry.get("params", [])

        # params in the registry is a list of param names (no defaults)
        if isinstance(raw_params, dict):
            all_params = raw_params
        else:
            all_params = {k: None for k in raw_params}

        self._simple_widgets  = {}
        self._complex_widgets = {}

        simple_params = {k: v for k, v in all_params.items() if k not in _COMPLEX_KEYS}
        if not simple_params:
            self._simple_out.children = (
                _h("<span style='color:#AAA;font-size:12px;font-style:italic'>No extra parameters.</span>"),
            )
        else:
            param_widgets = []
            for pname, default in simple_params.items():
                widget = self._make_simple_widget(pname, default)
                if widget:
                    self._simple_widgets[pname] = widget
                    param_widgets.append(w.VBox([
                        _h(f"<div style='font-size:11px;color:#5C6673;font-weight:600;margin-bottom:2px'>"
                           f"{pname.replace('_',' ').title()}</div>"),
                        widget,
                    ], layout=w.Layout(margin="0 0 8px 0")))
            self._simple_out.children = tuple(param_widgets)

        complex_params = {k: v for k, v in all_params.items() if k in _COMPLEX_KEYS}
        if complex_params:
            self._complex_out.children = (self._make_complex_wizard(check_name, complex_params),)
        else:
            self._complex_out.children = ()

        # Force col to _TABLE_LEVEL_ / _COMPOUND_ when applicable
        if entry.get("table_level") and self._selected_col not in ("", "_TABLE_LEVEL_"):
            pass  # handled in _do_add_check

    def _make_simple_widget(self, pname: str, default):
        """Return a single widget for a simple (non-complex) parameter."""
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
                placeholder="SQL WHERE clause — matching rows are FAILED\ne.g.  amount < 0 OR amount > 1000000",
                layout=w.Layout(width="100%", height="60px"),
            )
        if pname == "type_":
            return w.Dropdown(
                options=["string","int","long","double","float","boolean","date","timestamp","decimal"],
                layout=W,
            )
        return None

    def _make_complex_wizard(self, check_name: str, params: dict) -> w.VBox:
        """Inline wizard panel for complex parameters (FK, multi-column, etc.)."""
        col_names = [n for n, _ in self._columns]
        rows: list = [
            _h("<div class='dq-wizard-title'>"
               "⚙️ Advanced Parameters — "
               f"<code style='font-size:11px'>{check_name}</code></div>"),
        ]

        if "columns" in params:
            widget = w.SelectMultiple(
                options=col_names,
                rows=min(6, max(3, len(col_names))),
                layout=w.Layout(width="100%"),
            )
            self._complex_widgets["columns"] = widget
            rows.append(w.VBox([
                _h("<div style='font-size:11px;color:#5C6673;font-weight:600;margin-bottom:3px'>"
                   "COLUMNS <span style='color:#AAA;font-weight:400'>(hold Ctrl/⌘ for multi-select)</span></div>"),
                widget,
            ], layout=w.Layout(margin="0 0 10px 0")))

        if "reference_table" in params:
            widget = w.Text(placeholder="catalog.schema.reference_table",
                            layout=w.Layout(width="100%"))
            self._complex_widgets["reference_table"] = widget
            rows.append(w.VBox([_label("Reference Table"), widget],
                                layout=w.Layout(margin="0 0 8px 0")))

        if "reference_column" in params:
            widget = w.Text(placeholder="column name in reference table",
                            layout=w.Layout(width="100%"))
            self._complex_widgets["reference_column"] = widget
            rows.append(w.VBox([_label("Reference Column"), widget],
                                layout=w.Layout(margin="0 0 8px 0")))

        if "column_b" in params:
            opts = col_names or ["—"]
            widget = w.Dropdown(options=opts, layout=w.Layout(width="100%"))
            self._complex_widgets["column_b"] = widget
            rows.append(w.VBox([_label("Column B"), widget],
                                layout=w.Layout(margin="0 0 8px 0")))

        if "valid_pairs" in params:
            widget = w.Textarea(
                placeholder='[["val_a","val_b"],["val_c","val_d"]]  (JSON array of [a,b] pairs)',
                layout=w.Layout(width="100%", height="60px"),
            )
            self._complex_widgets["valid_pairs"] = widget
            rows.append(w.VBox([_label("Valid Pairs (JSON)"), widget],
                                layout=w.Layout(margin="0 0 8px 0")))

        if "expected_schema" in params:
            widget = w.Textarea(
                placeholder='[["col1","string"],["col2","int"]]  (JSON list of [name, type])',
                layout=w.Layout(width="100%", height="60px"),
            )
            self._complex_widgets["expected_schema"] = widget
            rows.append(w.VBox([_label("Expected Schema (JSON)"), widget],
                                layout=w.Layout(margin="0 0 8px 0")))

        if "check_orphans" in params:
            widget = w.Checkbox(value=False, description="Check orphans (bidirectional RI)",
                                style={"description_width": "initial"})
            self._complex_widgets["check_orphans"] = widget
            rows.append(widget)

        box = w.VBox(rows)
        box.add_class("dq-wizard")
        return box

    def _collect_params(self) -> dict:
        params: dict = {}
        for k, wgt in self._simple_widgets.items():
            val = wgt.value
            if k in ("value_set", "regex_list", "type_list"):
                val = [x.strip() for x in str(val).split(",") if x.strip()]
            elif k in ("min_value", "max_value", "sum_value", "quantile"):
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    val = None
            elif k in ("n_days", "n_minutes"):
                try:
                    val = int(val)
                except (TypeError, ValueError):
                    val = 1
            params[k] = val

        for k, wgt in self._complex_widgets.items():
            val = wgt.value
            if k in ("valid_pairs", "expected_schema"):
                try:
                    val = json.loads(val) if val else ([] if k == "valid_pairs" else {})
                except Exception:
                    val = [] if k == "valid_pairs" else {}
            elif k == "columns":
                val = list(val)        # SelectMultiple returns a tuple
            elif k == "check_orphans":
                val = bool(val)
            params[k] = val
        return params

    def _do_add_check(self, _=None):
        check_name = self._check_dd.value
        threshold  = round(float(self._threshold.value), 1)
        entry      = CHECKS_REGISTRY.get(check_name, {})

        if entry.get("table_level"):
            col = "_TABLE_LEVEL_"
        elif entry.get("compound") or "columns" in self._complex_widgets:
            col = "_COMPOUND_"
        else:
            col = self._selected_col or "_TABLE_LEVEL_"

        params = self._collect_params()
        new_chk = {"check_name": check_name, "column": col,
                   "threshold_pct": threshold, "params": params}

        if self._edit_idx is not None:
            self._checks[self._edit_idx] = new_chk
            self._edit_idx = None
            self._add_btn.description = "＋  Add Check"
            self._form_title.value = (
                "<div style='font-size:13px;font-weight:700;color:#1B3A4B;margin-bottom:8px'>Add Check</div>"
            )
        else:
            self._checks.append(new_chk)

        self._refresh_col_list()
        self._render_col_checks()

    # ──────────────────── Tab 3: Output ───────────────────────────────────────

    def _make_output_tab(self) -> w.VBox:
        self._o_df       = w.Checkbox(value=True,  description="In-memory DataFrame",
                                      style={"description_width": "initial"})
        self._o_delta    = w.Checkbox(value=False, description="Delta Table",
                                      style={"description_width": "initial"})
        self._o_vol_json = w.Checkbox(value=False, description="Volume — JSON file",
                                      style={"description_width": "initial"})
        self._o_vol_csv  = w.Checkbox(value=False, description="Volume — CSV file",
                                      style={"description_width": "initial"})

        self._o_delta_tbl = w.Text(placeholder="catalog.schema.dq_results",
                                   layout=w.Layout(width="100%"))
        self._o_vol_path  = w.Text(value=self.env.get("default_volume_path", "/Volumes/"),
                                   placeholder="/Volumes/catalog/schema/volume",
                                   layout=w.Layout(width="100%"))
        self._o_filename  = w.Text(placeholder="auto-generated on table load",
                                   layout=w.Layout(width="100%"))

        # Conditional panels
        self._delta_panel = w.VBox([
            w.VBox([_label("Delta Table Name"), self._o_delta_tbl]),
        ], layout=w.Layout(padding="10px 14px", margin="0 0 8px 0", display="none"))
        self._delta_panel.add_class("dq-sub-panel")

        self._vol_panel = w.VBox([
            _field("Volume Path", self._o_vol_path),
            w.VBox([_label("Filename (no extension)"), self._o_filename]),
        ], layout=w.Layout(padding="10px 14px", margin="0 0 8px 0", display="none"))
        self._vol_panel.add_class("dq-sub-panel")

        def _toggle_delta(change):
            self._delta_panel.layout.display = "" if change["new"] else "none"
            if change["new"] and not self._o_delta_tbl.value.strip():
                cat = self.env.get("default_catalog", "")
                sch = self.env.get("default_schema", "")
                tbl = self._full.split(".")[-1] if self._full else "dq_results"
                if cat and sch:
                    self._o_delta_tbl.value = f"{cat}.{sch}.dq_{tbl}"

        def _toggle_vol(change):
            show = self._o_vol_json.value or self._o_vol_csv.value
            self._vol_panel.layout.display = "" if show else "none"
            if show and not self._o_vol_path.value.strip():
                base = self.env.get("default_volume_path", "/Volumes/").rstrip("/")
                if self._full:
                    parts = self._full.split(".")
                    cat, sch = (parts + ["", ""])[:2]
                    self._o_vol_path.value = f"{base}/{cat}/{sch}"
                else:
                    self._o_vol_path.value = base

        self._o_delta.observe(_toggle_delta, names="value")
        self._o_vol_json.observe(_toggle_vol, names="value")
        self._o_vol_csv.observe(_toggle_vol, names="value")

        out_opts = w.VBox([
            _h("<div style='font-size:12px;font-weight:600;color:#1B3A4B;"
               "margin-bottom:8px'>Output Destinations</div>"),
            self._o_df,
            self._o_delta,
            self._o_vol_json,
            self._o_vol_csv,
        ], layout=w.Layout(padding="14px", margin="0 0 12px 0"))
        out_opts.add_class("dq-out-opts")

        return w.VBox([
            _sec("📤  Output Configuration"),
            _info("Select <b>one or more</b> output destinations. "
                  "Fields pre-fill from your Settings defaults.", "info"),
            out_opts,
            self._delta_panel,
            self._vol_panel,
        ], layout=w.Layout(padding="18px"))

    def _update_output_filename(self, _=None):
        short = self._full.split(".")[-1] if "." in self._full else (self._full or "table")
        self._o_filename.value = f"dq_{short}_{datetime.now().strftime('%Y%m%d')}"

    # ──────────────────── Save Config ─────────────────────────────────────────

    def _do_save(self, _=None):
        types = []
        if self._o_df.value:
            types.append("dataframe")
        if self._o_delta.value:
            types.append("delta")
        if self._o_vol_json.value:
            types.append("volume_json")
        if self._o_vol_csv.value:
            types.append("volume_csv")
        if not types:
            types = ["dataframe"]

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
            "checks": list(self._checks),
            "output": {
                "types":       types,
                "delta_table": self._o_delta_tbl.value.strip(),
                "volume_path": self._o_vol_path.value.strip(),
                "filename":    self._o_filename.value.strip(),
            },
        })

        n = len(self._checks)

        # Persist to disk: config_dir / catalog / schema / table.json
        config_dir = self.env.get("config_dir", "").strip()
        saved_path = ""
        if config_dir and self._full:
            try:
                parts = self._full.split(".")
                cat, sch, tbl = (parts + ["", "", ""])[:3]
                target_dir = os.path.join(config_dir, cat, sch)
                os.makedirs(target_dir, exist_ok=True)
                saved_path = os.path.join(target_dir, f"{tbl}.json")
                with open(saved_path, "w") as f:
                    json.dump(self._config, f, indent=2)
            except Exception as exc:
                self._save_status.children = (_info(
                    f"⚠️ Config built but could not save to disk: {exc}", "warn"
                ),)
                return

        file_hint = (f" · saved to <code>{saved_path}</code>" if saved_path
                     else " · set a Config Directory in ⚙️ Settings to persist to disk")
        self._save_status.children = (_info(
            f"✅ <b>{n} check{'s' if n!=1 else ''}</b> on "
            f"<code>{self._full or '(no table)'}</code>{file_hint}. "
            "Call <code>dashdq.run_checks(config)</code> or pass the file path.",
            "ok",
        ),)


# ═════════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════════

def configure(spark=None) -> dict:
    """
    Open the DashDQ wizard. Returns a dict that fills in when you click
    **Save Configuration**. Pass it to ``dashdq.run_checks(config)``.

    Tabs:
      ⚙️ Environment — set default paths and catalog
      📊 Source      — pick catalog → schema → table from dropdowns
      🏷️ Metadata    — owner, steward, domain, tags, description
      ✅ Checks      — add / edit / remove checks per column
      📤 Output      — choose one or more output destinations
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
        f"<span>Total: {s['total_checks']}</span>"
        f"<span class='dq-pass'>✅ Passed: {s['passed']}</span>"
        f"<span class='dq-fail'>❌ Failed: {s['failed']}</span>"
        f"<span>Pass Rate: {s['pass_rate_pct']}%</span>"
        f"</div>"
    ))
    report.display()
    return report


def launch(spark=None):
    """All-in-one: open wizard + Run Checks button."""
    config = configure(spark)
    result_out = w.VBox([])   # children-swap, no Output widget
    run_box, run_btn = _styled_btn("▶  Run Checks", "primary")
    run_btn.layout = w.Layout(height="38px", min_width="160px")

    def _run(_):
        if not config.get("checks"):
            result_out.children = (_info("⚠️ Click Save Configuration first and add at least one check.", "warn"),)
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
