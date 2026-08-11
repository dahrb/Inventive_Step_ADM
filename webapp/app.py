"""
ADM Results Explorer
====================
Main Streamlit entry point.

Run from the ADM_JURIX directory:
    streamlit run webapp/app.py
"""

import sys
from pathlib import Path

# Make webapp directory importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

st.set_page_config(
    page_title="ADM Results — Overview",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS tweaks ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        padding: 6px 16px;
        border-radius: 6px 6px 0 0;
    }
    .verdict-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: bold;
        font-size: 0.9rem;
    }
    .verdict-yes  { background:#d4edda; color:#155724; }
    .verdict-no   { background:#f8d7da; color:#721c24; }
    .verdict-none { background:#e2e3e5; color:#383d41; }
    .correct-badge   { background:#cce5ff; color:#004085; padding:3px 10px; border-radius:10px; font-weight:bold; }
    .incorrect-badge { background:#fff3cd; color:#856404; padding:3px 10px; border-radius:10px; font-weight:bold; }
</style>
""", unsafe_allow_html=True)

# ── landing page ──────────────────────────────────────────────────────────────
st.title("⚖️ ADM Results — Overview")
st.markdown("""
Welcome to the **Inventive Step ADM Results Explorer**.

Use the sidebar to navigate between pages:

| Page | Description |
|---|---|
| **📋 Case Explorer** | Browse ADM trees, Q&A logs, and case documents per case / config / run |
| **📊 Dashboard** | Aggregate accuracy metrics and comparison charts |

---
""")

import data_loader as dl
import pandas as pd

with st.spinner("Loading experiment index…"):
    exps = dl.get_experiments()
    gt   = dl.get_ground_truth()

col1, col2, col3 = st.columns(3)
col1.metric("Experiments found", len(exps))
col2.metric("Ground truth cases", len(gt))
col3.metric("Ground truth positive rate",
            f"{sum(1 for v in gt.values() if v=='Yes') / max(len(gt),1):.1%}")

# ── Experiment coverage matrix ────────────────────────────────────────────────
st.subheader("Experiment Coverage")

# Human-readable model names
_MODEL_LABELS = {
    "GPT_TEST":   "GPT-OSS 120B",
    "LLAMA_TEST": "LLaMA 3.3 70B",
    "QWEN_TEST":  "Qwen-Next-80B-A3B",
}

# Canonical config columns (display name → directory name fragment)
_CONFIG_COLS = {
    "Baseline":   "baseline_default",
    "cfg 1":      "tool_both_default_cfg1",
    "cfg 2":      "tool_both_default_cfg2",
    "cfg 3":      "tool_both_default_cfg3",
}

_TICK = "✅"
_CROSS = "❌"

if exps:
    rows = []
    for exp in sorted(exps):
        cfgs = set(dl.get_configs(exp))
        label = _MODEL_LABELS.get(exp, exp)

        # Determine mode label for each config present
        def cell(dir_name: str) -> str:
            if dir_name not in cfgs:
                return _CROSS
            if dir_name == "baseline_default":
                return f"{_TICK} baseline"
            return f"{_TICK} tool_both"

        row = {"Model": label}
        for col_name, dir_name in _CONFIG_COLS.items():
            row[col_name] = cell(dir_name)
        rows.append(row)

    df = pd.DataFrame(rows).set_index("Model")
    st.dataframe(df, use_container_width=True)

    # Small note about QWEN tool_both_default (no cfg suffix)
    for exp in exps:
        cfgs = set(dl.get_configs(exp))
        extra = cfgs - set(_CONFIG_COLS.values())
        if extra:
            label = _MODEL_LABELS.get(exp, exp)
            st.caption(f"ℹ️ {label} also has additional config(s): {', '.join(sorted(extra))}")
else:
    st.warning("No experiments found in the Outputs/ directory.")
