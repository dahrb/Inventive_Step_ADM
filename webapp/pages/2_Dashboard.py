"""
Dashboard
=========
Headline classification metrics across models, configurations, and runs.

Focus:
  • F1  (positive class = "Yes" = inventive step)
  • MCC (Matthews Correlation Coefficient — robust to class imbalance)
  • Confidence: per-model/config dispersion across runs (mean ± 95% CI)

Baseline configurations are charted alongside ADM configurations so the
contribution of the ADM tooling is visible at a glance.
"""

from __future__ import annotations
import sys, math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

import data_loader as dl
import adm_helpers as ah


st.set_page_config(
    page_title="Dashboard", page_icon="📊",
    layout="wide", initial_sidebar_state="expanded",
)
st.title("📊 Dashboard — F1, MCC & Confidence")
st.caption(
    "All metrics computed against the held-out ground-truth labels. "
    "Positive class = `Yes` (inventive step). "
    "Error bars show 95 % confidence intervals across runs (Student-t, n−1 df)."
)


# ─── metric helpers ──────────────────────────────────────────────────────────
def _confusion(y_true: list[str], y_pred: list[str]) -> tuple[int, int, int, int]:
    tp = tn = fp = fn = 0
    for t, p in zip(y_true, y_pred):
        t = (t or "").strip().lower(); p = (p or "").strip().lower()
        if t == "yes" and p == "yes": tp += 1
        elif t == "no" and p == "no": tn += 1
        elif t == "no" and p == "yes": fp += 1
        elif t == "yes" and p == "no": fn += 1
    return tp, tn, fp, fn


def _f1(tp, fp, fn) -> float:
    denom = 2 * tp + fp + fn
    return (2 * tp / denom) if denom else float("nan")


def _mcc(tp, tn, fp, fn) -> float:
    num = tp * tn - fp * fn
    den = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return (num / den) if den else float("nan")


def _accuracy(tp, tn, fp, fn) -> float:
    n = tp + tn + fp + fn
    return ((tp + tn) / n) if n else float("nan")


def _ci95(values: list[float]) -> tuple[float, float]:
    """Mean and half-width of a 95 % CI (Student-t, n−1 df)."""
    arr = np.asarray([v for v in values if not (v is None or (isinstance(v, float) and math.isnan(v)))],
                     dtype=float)
    if arr.size == 0:
        return float("nan"), 0.0
    mean = float(arr.mean())
    if arr.size < 2:
        return mean, 0.0
    sd = float(arr.std(ddof=1))
    # t critical for small n; fall back to 1.96 for n>30
    from math import sqrt
    t_table = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571,
               7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262}
    t = t_table.get(arr.size, 1.96 if arr.size > 30 else 2.262)
    return mean, t * sd / sqrt(arr.size)


# ─── data assembly ───────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner="Crunching results …")
def build_metrics_table() -> pd.DataFrame:
    gt = dl.get_ground_truth()
    rows = []
    for exp in dl.get_experiments():
        for cfg in dl.get_configs(exp):
            vm = dl.get_verdict_map(exp, cfg)
            for run_key, run_dict in (vm or {}).items():
                if not isinstance(run_dict, dict):
                    continue
                y_true, y_pred = [], []
                for case, pred in run_dict.items():
                    truth = gt.get(case)
                    if truth is None or pred is None:
                        continue
                    y_true.append(str(truth)); y_pred.append(str(pred))
                if not y_true:
                    continue
                tp, tn, fp, fn = _confusion(y_true, y_pred)
                rows.append({
                    "model":    exp,
                    "model_label": ah.MODEL_LABELS.get(exp, exp),
                    "config":   cfg,
                    "config_label": ah.CONFIG_LABELS.get(cfg, cfg),
                    "is_baseline": ah.is_baseline(cfg),
                    "run":      run_key,
                    "n":        len(y_true),
                    "tp": tp, "tn": tn, "fp": fp, "fn": fn,
                    "f1":       _f1(tp, fp, fn),
                    "mcc":      _mcc(tp, tn, fp, fn),
                    "accuracy": _accuracy(tp, tn, fp, fn),
                })
    return pd.DataFrame(rows)


df = build_metrics_table()
if df.empty:
    st.warning("No verdict files found — nothing to plot.")
    st.stop()


# ─── sidebar filters ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    models = sorted(df["model"].unique())
    sel_models = st.multiselect(
        "Models", models, default=models,
        format_func=lambda m: ah.MODEL_LABELS.get(m, m),
    )
    configs = sorted(df["config"].unique())
    sel_configs = st.multiselect(
        "Configurations", configs, default=configs,
        format_func=lambda c: ah.CONFIG_LABELS.get(c, c),
    )
    show_baseline_line = st.checkbox(
        "Overlay baseline as a horizontal reference", value=True
    )

mask = df["model"].isin(sel_models) & df["config"].isin(sel_configs)
fdf = df[mask].copy()
if fdf.empty:
    st.warning("Current filter excludes all rows.")
    st.stop()


# ─── aggregate (mean ± CI) ───────────────────────────────────────────────────
def aggregate(metric: str) -> pd.DataFrame:
    grp = (fdf.groupby(["model", "model_label", "config", "config_label",
                        "is_baseline"], dropna=False)[metric]
              .apply(list).reset_index(name="values"))
    means, cis = [], []
    for vs in grp["values"]:
        m, c = _ci95(vs)
        means.append(m); cis.append(c)
    grp["mean"] = means
    grp["ci"]   = cis
    grp["n_runs"] = grp["values"].apply(len)
    return grp


# ─── headline cards ──────────────────────────────────────────────────────────
st.subheader("Best per model (across selected configs)")
cards = st.columns(max(1, len(sel_models)))
for col, m in zip(cards, sorted(sel_models)):
    sub = fdf[fdf["model"] == m]
    if sub.empty:
        col.info(ah.MODEL_LABELS.get(m, m) + " — no data")
        continue
    best_idx = sub["f1"].idxmax()
    r = sub.loc[best_idx]
    with col:
        st.markdown(f"**{ah.MODEL_LABELS.get(m, m)}**")
        st.metric("Best F1",  f"{r['f1']:.3f}",
                  help=f"{r['config_label']} · {r['run']}")
        st.metric("MCC",      f"{r['mcc']:.3f}" if not math.isnan(r['mcc']) else "—")
        st.metric("Accuracy", f"{r['accuracy']:.3f}")


# ─── shared bar plotter ──────────────────────────────────────────────────────
COLOR_MAP = px.colors.qualitative.Set2  # colour-blind friendly


def plot_metric(metric: str, ylabel: str, ymin=0.0, ymax=1.0):
    agg = aggregate(metric)
    if agg.empty:
        st.info(f"No data for {metric}.")
        return
    # x = config, grouped/colored by model
    fig = go.Figure()
    models_present = sorted(agg["model"].unique())
    palette = {m: COLOR_MAP[i % len(COLOR_MAP)] for i, m in enumerate(models_present)}
    cfg_order = sorted(agg["config"].unique(),
                       key=lambda c: (not ah.is_baseline(c), c))
    for m in models_present:
        sub = agg[agg["model"] == m].set_index("config").reindex(cfg_order)
        fig.add_trace(go.Bar(
            x=[ah.CONFIG_LABELS.get(c, c) for c in cfg_order],
            y=sub["mean"],
            error_y=dict(type="data", array=sub["ci"], visible=True),
            name=ah.MODEL_LABELS.get(m, m),
            marker_color=palette[m],
            customdata=np.stack([
                sub["n_runs"].fillna(0).values,
                sub["ci"].fillna(0).values,
            ], axis=-1),
            hovertemplate=(
                "<b>%{x}</b><br>"
                f"{ylabel}: " "%{y:.3f} ± %{customdata[1]:.3f}<br>"
                "runs: %{customdata[0]}<extra>"
                + ah.MODEL_LABELS.get(m, m) + "</extra>"
            ),
        ))

    if show_baseline_line:
        for m in models_present:
            base = agg[(agg["model"] == m) & (agg["is_baseline"])]
            if not base.empty:
                y = float(base["mean"].iloc[0])
                fig.add_hline(
                    y=y, line_dash="dot", line_color=palette[m],
                    annotation_text=f"{ah.MODEL_LABELS.get(m, m)} baseline = {y:.3f}",
                    annotation_position="top left",
                    annotation_font_color=palette[m],
                    opacity=0.6,
                )

    fig.update_layout(
        barmode="group", height=480,
        yaxis=dict(title=ylabel, range=[ymin, ymax]),
        xaxis=dict(title="Configuration", tickangle=-15),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=20, r=20, t=40, b=80),
    )
    st.plotly_chart(fig, use_container_width=True)


# ─── tabs ────────────────────────────────────────────────────────────────────
tab_f1, tab_mcc, tab_conf, tab_lift, tab_table = st.tabs(
    ["🎯 F1", "📐 MCC", "🎚 Confidence", "📈 Tool lift over baseline", "📋 Raw table"]
)

with tab_f1:
    st.markdown("**F1** for the positive class (inventive step = Yes). "
                "Higher = better balance of precision and recall.")
    plot_metric("f1", "F1", 0.0, 1.0)

with tab_mcc:
    st.markdown(
        "**Matthews Correlation Coefficient** in [-1, 1]. "
        "0 ≈ random, 1 = perfect, < 0 = systematically wrong. "
        "Robust to class imbalance — preferred summary statistic."
    )
    plot_metric("mcc", "MCC", -1.0, 1.0)

with tab_conf:
    st.markdown(
        "Per-run F1 distributions per model × configuration. "
        "Tight clusters ⇒ stable across runs; wide spread ⇒ noisy."
    )
    fig = go.Figure()
    models_present = sorted(fdf["model"].unique())
    palette = {m: COLOR_MAP[i % len(COLOR_MAP)] for i, m in enumerate(models_present)}
    cfg_order = sorted(fdf["config"].unique(),
                       key=lambda c: (not ah.is_baseline(c), c))
    for m in models_present:
        sub = fdf[fdf["model"] == m]
        fig.add_trace(go.Box(
            x=[ah.CONFIG_LABELS.get(c, c) for c in sub["config"]],
            y=sub["f1"], name=ah.MODEL_LABELS.get(m, m),
            marker_color=palette[m], boxpoints="all",
            jitter=0.4, pointpos=0,
        ))
    fig.update_layout(
        boxmode="group", height=480,
        yaxis=dict(title="F1", range=[0, 1]),
        xaxis=dict(title="Configuration", tickangle=-15),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=20, r=20, t=40, b=80),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### MCC distributions")
    fig2 = go.Figure()
    for m in models_present:
        sub = fdf[fdf["model"] == m]
        fig2.add_trace(go.Box(
            x=[ah.CONFIG_LABELS.get(c, c) for c in sub["config"]],
            y=sub["mcc"], name=ah.MODEL_LABELS.get(m, m),
            marker_color=palette[m], boxpoints="all",
            jitter=0.4, pointpos=0,
        ))
    fig2.update_layout(
        boxmode="group", height=480,
        yaxis=dict(title="MCC", range=[-1, 1]),
        xaxis=dict(title="Configuration", tickangle=-15),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=20, r=20, t=40, b=80),
    )
    st.plotly_chart(fig2, use_container_width=True)

with tab_lift:
    st.markdown(
        "Difference between each ADM configuration and the corresponding "
        "model's baseline (mean over runs). Positive bars ⇒ tooling helps."
    )
    rows = []
    for m in sel_models:
        sub = fdf[fdf["model"] == m]
        baseline_rows = sub[sub["is_baseline"]]
        if baseline_rows.empty:
            continue
        base_f1  = baseline_rows["f1"].mean()
        base_mcc = baseline_rows["mcc"].mean()
        for cfg, g in sub[~sub["is_baseline"]].groupby("config"):
            rows.append({
                "Model":  ah.MODEL_LABELS.get(m, m),
                "Config": ah.CONFIG_LABELS.get(cfg, cfg),
                "ΔF1":    g["f1"].mean()  - base_f1,
                "ΔMCC":   g["mcc"].mean() - base_mcc,
            })
    if not rows:
        st.info("Need both a baseline and at least one ADM config to compute lift.")
    else:
        lift_df = pd.DataFrame(rows)
        fig = px.bar(
            lift_df, x="Config", y="ΔF1", color="Model", barmode="group",
            color_discrete_sequence=COLOR_MAP, height=420,
        )
        fig.add_hline(y=0, line_color="#888")
        fig.update_layout(
            yaxis=dict(title="ΔF1 vs baseline"),
            xaxis=dict(tickangle=-15),
            plot_bgcolor="white", paper_bgcolor="white",
        )
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.bar(
            lift_df, x="Config", y="ΔMCC", color="Model", barmode="group",
            color_discrete_sequence=COLOR_MAP, height=420,
        )
        fig2.add_hline(y=0, line_color="#888")
        fig2.update_layout(
            yaxis=dict(title="ΔMCC vs baseline"),
            xaxis=dict(tickangle=-15),
            plot_bgcolor="white", paper_bgcolor="white",
        )
        st.plotly_chart(fig2, use_container_width=True)
        st.dataframe(lift_df.round(3), hide_index=True, use_container_width=True)

with tab_table:
    show = fdf[[
        "model_label", "config_label", "run", "n",
        "tp", "tn", "fp", "fn", "f1", "mcc", "accuracy",
    ]].rename(columns={
        "model_label": "Model", "config_label": "Config",
        "run": "Run", "n": "N", "f1": "F1", "mcc": "MCC", "accuracy": "Acc",
    }).sort_values(["Model", "Config", "Run"])
    st.dataframe(
        show.round({"F1": 3, "MCC": 3, "Acc": 3}),
        hide_index=True, use_container_width=True,
    )
    st.download_button(
        "⬇ Download CSV",
        data=show.to_csv(index=False).encode("utf-8"),
        file_name="dashboard_metrics.csv", mime="text/csv",
    )
