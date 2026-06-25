"""
DashDQ interactive UI for Databricks notebooks.
Call dashdq.launch() to open the widget.
"""
from __future__ import annotations


def launch():
    """Launch the DashDQ configuration UI inside a Databricks notebook."""
    try:
        import ipywidgets as w
        from IPython.display import display
    except ImportError:
        raise RuntimeError("ipywidgets required. Run: %pip install ipywidgets")

    from dashdq.suite import DQSuite

    # ── Styles ────────────────────────────────────────────────────────────
    header_style = {"font_size": "18px", "font_weight": "bold"}
    section_style = {"font_size": "13px", "font_weight": "bold"}

    # ── Input source ──────────────────────────────────────────────────────
    source_toggle = w.ToggleButtons(
        options=["DataFrame variable", "UC Table", "SQL Query"],
        description="Data source:",
        style={"button_width": "160px"},
    )
    df_name_input = w.Text(placeholder="e.g.  df  or  spark.table(...)", description="Variable:")
    table_input = w.Text(placeholder="catalog.schema.table", description="Table:")
    sql_input = w.Textarea(placeholder="SELECT * FROM ...", description="SQL:", rows=3, layout=w.Layout(width="100%"))
    source_box = w.VBox([df_name_input])

    def on_source_change(change):
        opt = change["new"]
        if opt == "DataFrame variable":
            source_box.children = [df_name_input]
        elif opt == "UC Table":
            source_box.children = [table_input]
        else:
            source_box.children = [sql_input]

    source_toggle.observe(on_source_change, names="value")

    # ── Check builder ─────────────────────────────────────────────────────
    check_type = w.Dropdown(
        options=[
            "No Nulls", "Null Rate ≤ threshold", "Unique values",
            "Values in set", "Column range", "Regex pattern",
            "Min row count", "Freshness (max age)",
        ],
        description="Check type:",
        layout=w.Layout(width="300px"),
    )
    col_input = w.Text(placeholder="column_name", description="Column:")
    param_input = w.Text(placeholder="parameter (threshold / values / pattern…)", description="Parameter:")
    add_btn = w.Button(description="＋ Add check", button_style="primary")
    rules_output = w.Output()
    rules: list[dict] = []

    def on_add(b):
        rule = _build_rule(check_type.value, col_input.value.strip(), param_input.value.strip())
        if rule:
            rules.append(rule)
            with rules_output:
                rules_output.clear_output()
                for i, r in enumerate(rules, 1):
                    print(f"  {i}. {r}")
        else:
            with rules_output:
                print("⚠️  Please fill in column and parameter.")

    add_btn.on_click(on_add)

    # ── Output options ────────────────────────────────────────────────────
    save_toggle = w.Checkbox(value=False, description="Save results to Delta table")
    save_table_input = w.Text(placeholder="catalog.schema.dq_results", description="Delta table:", disabled=True)

    def on_save_toggle(change):
        save_table_input.disabled = not change["new"]

    save_toggle.observe(on_save_toggle, names="value")

    # ── Run button + output ───────────────────────────────────────────────
    run_btn = w.Button(description="▶  Run DQ Checks", button_style="success",
                       layout=w.Layout(height="40px", width="200px"))
    run_output = w.Output()

    def on_run(b):
        with run_output:
            run_output.clear_output()
            try:
                suite = _build_suite(source_toggle.value, df_name_input.value,
                                     table_input.value, sql_input.value, rules)
                save_to = save_table_input.value.strip() if save_toggle.value else None
                report = suite.run(save_to=save_to)
                report.display()
            except Exception as e:
                print(f"❌ Error: {e}")

    run_btn.on_click(on_run)

    # ── Layout ────────────────────────────────────────────────────────────
    ui = w.VBox([
        w.HTML("<h2 style='color:#1976D2'>🔍 DashDQ — Data Quality</h2>"),
        w.HTML("<b>Step 1: Select data source</b>"),
        source_toggle, source_box,
        w.HTML("<hr><b>Step 2: Add quality checks</b>"),
        w.HBox([check_type, col_input, param_input, add_btn]),
        rules_output,
        w.HTML("<hr><b>Step 3: Output options</b>"),
        save_toggle, save_table_input,
        w.HTML("<hr>"),
        run_btn,
        run_output,
    ], layout=w.Layout(padding="16px", border="1px solid #ddd", border_radius="8px"))

    display(ui)


def _build_rule(check_type: str, column: str, param: str) -> dict | None:
    if check_type == "No Nulls":
        return {"type": "no_nulls", "column": column} if column else None
    if check_type == "Null Rate ≤ threshold":
        try:
            return {"type": "null_rate", "column": column, "max_rate": float(param)}
        except ValueError:
            return None
    if check_type == "Unique values":
        return {"type": "unique", "column": column} if column else None
    if check_type == "Values in set":
        values = [v.strip() for v in param.split(",") if v.strip()]
        return {"type": "values_in_set", "column": column, "allowed": values} if column and values else None
    if check_type == "Column range":
        parts = [p.strip() for p in param.split(",")]
        min_v = float(parts[0]) if len(parts) > 0 and parts[0] else None
        max_v = float(parts[1]) if len(parts) > 1 and parts[1] else None
        return {"type": "column_range", "column": column, "min_val": min_v, "max_val": max_v}
    if check_type == "Regex pattern":
        return {"type": "regex", "column": column, "pattern": param} if column and param else None
    if check_type == "Min row count":
        try:
            return {"type": "row_count", "min_rows": int(param)}
        except ValueError:
            return None
    if check_type == "Freshness (max age)":
        try:
            return {"type": "freshness", "column": column, "max_age_hours": float(param)}
        except ValueError:
            return None
    return None


def _build_suite(source: str, df_var: str, table: str, sql: str, rules: list):
    from dashdq.suite import DQSuite
    import IPython
    shell = IPython.get_ipython()

    if source == "DataFrame variable":
        df = shell.user_ns.get(df_var.strip()) if shell else None
        if df is None:
            raise ValueError(f"Variable '{df_var}' not found in notebook namespace.")
        suite = DQSuite(df=df)
    elif source == "UC Table":
        suite = DQSuite(table=table.strip())
    else:
        suite = DQSuite(query=sql.strip())

    suite.from_config({"rules": rules})
    return suite
