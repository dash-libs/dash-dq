"""
DashDQ interactive configuration wizard for Databricks notebooks.

Usage::

    # Cell 1 — open wizard, fill in UI, click "Save Config"
    config = dashdq.configure()

    # Cell 2 — run after saving config
    report = dashdq.run_checks(config)
    report.display()

Or all-in-one::

    dashdq.launch()
"""
from __future__ import annotations
from datetime import datetime


def _spark():
    from pyspark.sql import SparkSession
    return SparkSession.getActiveSession()


def _dim_badge(dimension: str) -> str:
    colors = {
        "Completeness": "#1565C0",
        "Accuracy":     "#2E7D32",
        "Integrity":    "#6A1B9A",
        "Consistency":  "#E65100",
    }
    c = colors.get(dimension, "#555")
    return (f"<span style='background:{c};color:#fff;padding:2px 8px;"
            f"border-radius:10px;font-size:11px;font-weight:600'>{dimension}</span>")


def _suggested_filename(table: str) -> str:
    short = table.split(".")[-1] if "." in table else table
    return f"dq_{short}_{datetime.now().strftime('%Y%m%d')}"


def _make_param_widgets(params: list, all_cols: list):
    """Build one ipywidget per parameter in the check's params list."""
    import ipywidgets as w
    widgets = {}
    for p in params:
        if p in ("min_value", "max_value"):
            widgets[p] = w.FloatText(
                description=f"{p}:",
                layout=w.Layout(width="240px"),
                style={"description_width": "90px"},
            )
        elif p == "value_set":
            widgets[p] = w.Textarea(
                description="value_set:",
                placeholder="A, B, C  (comma-separated)",
                layout=w.Layout(width="340px", height="60px"),
                style={"description_width": "90px"},
            )
        elif p == "regex":
            widgets[p] = w.Text(
                description="regex:",
                placeholder=r"^\d{4}-\d{2}-\d{2}$",
                layout=w.Layout(width="340px"),
                style={"description_width": "90px"},
            )
        elif p == "strftime_format":
            widgets[p] = w.Text(
                value="%Y-%m-%d",
                description="format:",
                layout=w.Layout(width="240px"),
                style={"description_width": "90px"},
            )
        elif p == "type_":
            widgets[p] = w.Dropdown(
                options=["string", "int", "long", "double", "float",
                         "boolean", "date", "timestamp", "decimal"],
                description="type_:",
                style={"description_width": "90px"},
            )
        elif p == "column_b":
            widgets[p] = w.Dropdown(
                options=[""] + list(all_cols),
                description="column_b:",
                style={"description_width": "90px"},
            )
    return widgets


def _read_params(param_widgets: dict) -> dict:
    out = {}
    for k, widget in param_widgets.items():
        val = widget.value
        if k == "value_set":
            out[k] = [v.strip() for v in str(val).split(",") if v.strip()]
        else:
            out[k] = val
    return out


# ── configure() ───────────────────────────────────────────────────────────────

def configure() -> dict:
    """
    Open the DQ configuration wizard. Returns a dict that fills in when
    you click **Save Config**. Pass it to ``dashdq.run_checks(config)``.
    """
    try:
        import ipywidgets as w
        from IPython.display import display, HTML
    except ImportError:
        raise RuntimeError("ipywidgets required. Run: %pip install ipywidgets")

    from dashdq.checks import CHECKS_REGISTRY, DQ_DIMENSIONS

    config: dict = {}
    all_cols: list = []
    configured_checks: list = []
    param_widgets_ref: list = [{}]   # mutable container so closures can update it

    # ─── Tab 1: Source & Metadata ─────────────────────────────────────────────
    table_inp = w.Text(
        placeholder="catalog.schema.table_name",
        description="Table:",
        layout=w.Layout(width="420px"),
        style={"description_width": "80px"},
    )
    load_btn = w.Button(description="Load Columns", button_style="info",
                        layout=w.Layout(width="140px"))
    load_out = w.Output()

    owner_inp   = w.Text(description="Data Owner:",    placeholder="optional",
                         layout=w.Layout(width="340px"), style={"description_width": "120px"})
    steward_inp = w.Text(description="Data Steward:",  placeholder="optional",
                         layout=w.Layout(width="340px"), style={"description_width": "120px"})
    domain_inp  = w.Text(description="Domain:",        placeholder="optional",
                         layout=w.Layout(width="340px"), style={"description_width": "120px"})
    desc_inp    = w.Textarea(description="Description:", placeholder="optional",
                             layout=w.Layout(width="420px", height="60px"),
                             style={"description_width": "120px"})

    tab1 = w.VBox([
        w.HTML("<b>Source table</b>"),
        w.HBox([table_inp, load_btn]),
        load_out,
        w.HTML("<hr><b>Metadata <span style='color:#888;font-weight:normal'>(all optional)</span></b>"),
        owner_inp, steward_inp, domain_inp, desc_inp,
    ])

    # ─── Tab 2: Check Builder ─────────────────────────────────────────────────
    col_dd = w.Dropdown(
        description="Column:",
        options=["(load columns first)"],
        layout=w.Layout(width="300px"),
        style={"description_width": "70px"},
    )

    # Options grouped by dimension
    check_opts = []
    for dim in DQ_DIMENSIONS:
        for cname, meta in CHECKS_REGISTRY.items():
            if meta["dimension"] == dim:
                check_opts.append((f"[{dim[:4]}] {cname}", cname))

    check_dd = w.Dropdown(
        description="Check:",
        options=check_opts,
        layout=w.Layout(width="560px"),
        style={"description_width": "70px"},
    )
    check_desc_out = w.Output()
    threshold_sl = w.FloatSlider(
        value=100.0, min=0.0, max=100.0, step=0.5,
        description="Threshold %:",
        readout_format=".1f",
        layout=w.Layout(width="440px"),
        style={"description_width": "110px"},
    )
    params_box = w.VBox([])
    add_btn = w.Button(description="＋ Add Check", button_style="success",
                       layout=w.Layout(width="140px"))
    checks_list_out = w.Output()

    def refresh_check_desc(change=None):
        cname = check_dd.value
        entry = CHECKS_REGISTRY.get(cname, {})
        dim = entry.get("dimension", "")
        desc = entry.get("description", "")
        with check_desc_out:
            check_desc_out.clear_output()
            display(HTML(f"{_dim_badge(dim)}&nbsp; <span style='color:#555'>{desc}</span>"))
        pw = _make_param_widgets(entry.get("params", []), all_cols)
        param_widgets_ref[0] = pw
        params_box.children = list(pw.values()) if pw else [
            w.HTML("<i style='color:#aaa'>No parameters required</i>")
        ]
        if entry.get("table_level"):
            col_dd.options = ["_TABLE_LEVEL_"]
            col_dd.value = "_TABLE_LEVEL_"
        elif all_cols:
            col_dd.options = all_cols

    check_dd.observe(refresh_check_desc, names="value")

    def refresh_checks_list():
        with checks_list_out:
            checks_list_out.clear_output()
            if not configured_checks:
                display(HTML("<i style='color:#aaa'>No checks added yet</i>"))
                return
            rows = []
            for i, c in enumerate(configured_checks, 1):
                dim = CHECKS_REGISTRY.get(c["check_name"], {}).get("dimension", "")
                short = c["check_name"].replace("expect_", "").replace("_", " ")
                p_str = ", ".join(f"{k}={v}" for k, v in c.get("params", {}).items()) or "—"
                rows.append(
                    f"<tr style='border-bottom:1px solid #eee'>"
                    f"<td style='padding:4px 8px;color:#888'>{i}</td>"
                    f"<td style='padding:4px 8px'><b>{c['column']}</b></td>"
                    f"<td style='padding:4px 8px;font-size:12px'>{short}</td>"
                    f"<td style='padding:4px 8px'>{_dim_badge(dim)}</td>"
                    f"<td style='padding:4px 8px'>{c['threshold_pct']}%</td>"
                    f"<td style='padding:4px 8px;color:#888;font-size:11px'>{p_str}</td>"
                    f"</tr>"
                )
            display(HTML(
                "<table style='border-collapse:collapse;width:100%'>"
                "<tr style='background:#f5f5f5;font-size:12px'>"
                "<th style='padding:4px 8px'>#</th>"
                "<th style='padding:4px 8px'>Column</th>"
                "<th style='padding:4px 8px'>Check</th>"
                "<th style='padding:4px 8px'>Dimension</th>"
                "<th style='padding:4px 8px'>Threshold</th>"
                "<th style='padding:4px 8px'>Params</th>"
                "</tr>" + "".join(rows) + "</table>"
            ))

    def on_add(b):
        col = col_dd.value
        if not col or col == "(load columns first)":
            with checks_list_out:
                checks_list_out.clear_output()
                print("⚠️  Load columns first (Tab 1).")
            return
        configured_checks.append({
            "check_name": check_dd.value,
            "column": col,
            "threshold_pct": round(threshold_sl.value, 1),
            "params": _read_params(param_widgets_ref[0]),
        })
        refresh_checks_list()

    add_btn.on_click(on_add)
    refresh_check_desc()

    tab2 = w.VBox([
        w.HTML("<b>Configure a check</b>"),
        col_dd, check_dd, check_desc_out,
        threshold_sl,
        w.HTML("<b>Parameters</b>"),
        params_box,
        w.HBox([add_btn]),
        w.HTML("<hr><b>Configured checks</b>"),
        checks_list_out,
    ])

    # ─── Tab 3: Output ────────────────────────────────────────────────────────
    output_radio = w.RadioButtons(
        options=[
            ("DataFrame only (no file saved)", "dataframe"),
            ("Delta Table",                    "delta"),
            ("Volume — JSON file",             "volume_json"),
            ("Volume — CSV file",              "volume_csv"),
        ],
        value="dataframe",
        description="Write to:",
        style={"description_width": "80px"},
    )
    delta_inp = w.Text(
        description="Delta table:",
        placeholder="catalog.schema.dq_results",
        layout=w.Layout(width="440px"),
        style={"description_width": "120px"},
    )
    vol_path_inp = w.Text(
        description="Volume path:",
        placeholder="/Volumes/catalog/schema/volume/dq/",
        layout=w.Layout(width="440px"),
        style={"description_width": "120px"},
    )
    filename_inp = w.Text(
        description="Filename:",
        placeholder="(auto-suggested after loading table)",
        layout=w.Layout(width="440px"),
        style={"description_width": "120px"},
    )
    output_detail = w.VBox([])

    def on_output_change(change=None):
        otype = output_radio.value
        if otype == "dataframe":
            output_detail.children = [
                w.HTML("<i style='color:#888'>Results returned as a Spark DataFrame and displayed inline.</i>")
            ]
        elif otype == "delta":
            output_detail.children = [delta_inp]
        else:
            output_detail.children = [vol_path_inp, filename_inp]

    output_radio.observe(on_output_change, names="value")
    on_output_change()

    tab3 = w.VBox([
        w.HTML("<b>Where to write results</b><br>"
               "<span style='color:#888;font-size:12px'>Output is 1 row per check × column combination</span>"),
        w.HTML("<br>"),
        output_radio,
        output_detail,
    ])

    # ─── Load Columns handler ─────────────────────────────────────────────────
    def on_load(b):
        nonlocal all_cols
        tbl = table_inp.value.strip()
        if not tbl:
            with load_out:
                load_out.clear_output()
                print("⚠️  Enter a table name first.")
            return
        with load_out:
            load_out.clear_output()
            try:
                df = _spark().table(tbl)
                all_cols = list(df.columns)
                col_dd.options = all_cols
                col_dd.value = all_cols[0] if all_cols else ""
                if "column_b" in param_widgets_ref[0]:
                    param_widgets_ref[0]["column_b"].options = [""] + all_cols
                filename_inp.value = _suggested_filename(tbl)
                display(HTML(
                    f"<span style='color:#2E7D32'>✅ {len(all_cols)} columns loaded: "
                    f"{', '.join(all_cols[:10])}{'…' if len(all_cols) > 10 else ''}</span>"
                ))
            except Exception as exc:
                display(HTML(f"<span style='color:#c62828'>❌ {exc}</span>"))

    load_btn.on_click(on_load)

    # ─── Tabs + Save ──────────────────────────────────────────────────────────
    tabs = w.Tab(children=[tab1, tab2, tab3])
    tabs.set_title(0, "1 · Source & Metadata")
    tabs.set_title(1, "2 · Checks")
    tabs.set_title(2, "3 · Output")

    save_btn = w.Button(description="💾 Save Config", button_style="primary",
                        layout=w.Layout(width="160px", height="38px"))
    save_out = w.Output()

    def on_save(b):
        tbl = table_inp.value.strip()
        if not tbl:
            with save_out:
                save_out.clear_output()
                print("⚠️  Enter a table name in Tab 1.")
            return
        if not configured_checks:
            with save_out:
                save_out.clear_output()
                print("⚠️  Add at least one check in Tab 2.")
            return

        otype = output_radio.value
        if otype == "delta":
            out_cfg = {"type": "delta", "delta_table": delta_inp.value.strip()}
        elif otype in ("volume_json", "volume_csv"):
            out_cfg = {
                "type": otype,
                "volume_path": vol_path_inp.value.strip(),
                "filename": filename_inp.value.strip() or _suggested_filename(tbl),
            }
        else:
            out_cfg = {"type": "dataframe"}

        config.update({
            "source": {"table": tbl},
            "metadata": {
                "data_owner":      owner_inp.value.strip(),
                "data_steward":    steward_inp.value.strip(),
                "business_domain": domain_inp.value.strip(),
                "description":     desc_inp.value.strip(),
            },
            "checks": list(configured_checks),
            "output": out_cfg,
        })
        with save_out:
            save_out.clear_output()
            display(HTML(
                f"<div style='background:#E8F5E9;padding:10px;border-radius:6px'>"
                f"✅ Config saved — <b>{len(configured_checks)} check(s)</b> on <b>{tbl}</b>.<br>"
                f"Run <code>report = dashdq.run_checks(config)</code> in the next cell."
                f"</div>"
            ))

    save_btn.on_click(on_save)

    display(w.VBox([
        w.HTML("<h2 style='color:#1565C0;margin-bottom:4px'>🔍 DashDQ — Data Quality</h2>"),
        tabs,
        w.HTML("<hr style='margin:8px 0'>"),
        w.HBox([save_btn]),
        save_out,
    ], layout=w.Layout(padding="16px", border="1px solid #ddd", border_radius="8px",
                       width="780px")))

    return config


# ── run_checks() public wrapper ───────────────────────────────────────────────

def run_checks(config: dict, spark=None):
    """Execute the config returned by configure() and display the DQReport."""
    from dashdq.suite import run_checks as _run
    from IPython.display import display, HTML

    report = _run(config, spark)
    report.display()

    s = report.summary()
    display(HTML(
        f"<div style='background:#E3F2FD;padding:8px 12px;border-radius:6px;margin-top:8px'>"
        f"<b>Summary:</b> {s['total_checks']} checks — "
        f"<span style='color:#2E7D32'><b>{s['passed']}</b> PASS</span> / "
        f"<span style='color:#c62828'><b>{s['failed']}</b> FAIL</span> — "
        f"{s['pass_rate_pct']}% pass rate"
        f"</div>"
    ))
    return report


# ── launch() — all-in-one ─────────────────────────────────────────────────────

def launch():
    """Open the DashDQ wizard. Configure checks, then click Run Checks."""
    try:
        import ipywidgets as w
        from IPython.display import display
    except ImportError:
        raise RuntimeError("ipywidgets required. Run: %pip install ipywidgets")

    run_out = w.Output()
    run_btn = w.Button(description="▶ Run Checks", button_style="success",
                       layout=w.Layout(width="160px", height="38px"))

    config = configure()

    def on_run(b):
        with run_out:
            run_out.clear_output()
            if not config:
                print("⚠️  Click 'Save Config' first.")
                return
            print("⏳ Running checks…")
            try:
                run_checks(config)
            except Exception as exc:
                print(f"❌ {exc}")

    run_btn.on_click(on_run)
    display(w.VBox([w.HTML("<hr>"), run_btn, run_out]))
