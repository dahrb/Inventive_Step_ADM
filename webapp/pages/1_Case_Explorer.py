"""
Case Explorer
=============
Interactive exploration of one case under one experiment / config / run.

Node statuses come from the ADM's own 3-valued evaluator
(adm_graph.evaluate_case → adm.evaluateNode(mode='3vl')); we never
re-implement traversal here.

Node names are kept exactly as authored (CamelCase). Acceptance conditions
are displayed verbatim from `node.acceptanceOriginal` (no postfix gymnastics).
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import re
import streamlit as st
import data_loader as dl
import adm_graph as ag
import adm_viz as av
import adm_helpers as ah

# Module-level variable set by render_adm_tab before calling render_node_panel
# so the panel can highlight the fired acceptance rule.
_current_accepted_set: set[str] = set()


# ─── page setup ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Case Explorer", page_icon="📋",
    layout="wide", initial_sidebar_state="expanded",
)
st.markdown(
    """
    <style>
        .block-container { padding-top: 1rem; }
        .verdict-pill { display:inline-block; padding:4px 14px;
            border-radius:14px; font-weight:600; font-size:0.95rem;
            margin-right:0.5rem; }
        .v-yes  { background:#d4edda; color:#155724; }
        .v-no   { background:#f8d7da; color:#721c24; }
        .v-none { background:#e9ecef; color:#383d41; }
        .v-correct { background:#cce5ff; color:#004085; }
        .v-wrong   { background:#fff3cd; color:#856404; }
        .small-muted { color:#6c757d; font-size:0.85rem; }
        .stTabs [data-baseweb="tab-list"] { gap: 6px; }
    </style>
    """, unsafe_allow_html=True,
)
st.title("📋 Case Explorer")


# ─── sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Selection")
    experiments = dl.get_experiments()
    if not experiments:
        st.error("No experiments found in Outputs/.")
        st.stop()

    exp_labels = {e: ah.MODEL_LABELS.get(e, e) for e in experiments}
    exp = st.selectbox("Model", experiments,
                       format_func=lambda e: exp_labels[e], key="exp_select")
    cfgs = dl.get_configs(exp)
    cfg_labels = {c: ah.CONFIG_LABELS.get(c, c) for c in cfgs}
    cfg = st.selectbox("Configuration", cfgs,
                       format_func=lambda c: cfg_labels[c], key="cfg_select")
    cases = dl.get_cases(exp, cfg)
    if not cases:
        st.error("No cases found for this experiment / config.")
        st.stop()
    case_ref = st.selectbox("Case", cases, key="case_select")
    runs = dl.get_runs(exp, cfg, case_ref)
    if not runs:
        st.warning("No runs found for this case.")
        st.stop()
    run_id = st.selectbox("Run", runs,
                          format_func=lambda r: f"Run {r}", key="run_select")
    st.divider()
    st.markdown(
        f"**Model:** {exp_labels[exp]}  \n"
        f"**Config:** {cfg_labels[cfg]}  \n"
        f"**Case:** `{case_ref}`  &nbsp; **Run:** `{run_id}`"
    )

baseline = ah.is_baseline(cfg)


# ─── load data ───────────────────────────────────────────────────────────────
gt      = dl.get_ground_truth().get(case_ref)
verdict = dl.get_verdict(exp, cfg, case_ref, run_id)
log     = dl.get_log(exp, cfg, case_ref, run_id)
summary = dl.get_adm_summary(exp, cfg, case_ref, run_id)

main_summary = next((s for s in summary if s.get("adm_type") == "main"), None)
initial_summary = next((s for s in summary if s.get("adm_type") == "initial"), None)
sub_adm_1_entries = [
    s for s in summary
    if s.get("adm_type") == "sub_adm"
    and s.get("parent_fact") == "ReliableTechnicalEffect_sub_adm_instances"
]
sub_adm_2_entries = [
    s for s in summary
    if s.get("adm_type") == "sub_adm"
    and s.get("parent_fact") == "OTPNotObvious_sub_adm_instances"
]


# ─── header ──────────────────────────────────────────────────────────────────
def verdict_pill(label: str, value: str | None) -> str:
    if value is None:
        cls, text = "v-none", "—"
    elif str(value).strip().lower() == "yes":
        cls, text = "v-yes", "Yes (inventive step)"
    else:
        cls, text = "v-no", "No (no inventive step)"
    return f'<span class="verdict-pill {cls}">{label}: {text}</span>'


def correctness_pill(verdict: str | None, gt: str | None) -> str:
    if verdict is None or gt is None:
        return ""
    correct = str(verdict).strip().lower() == str(gt).strip().lower()
    cls = "v-correct" if correct else "v-wrong"
    text = "✅ Correct" if correct else "❌ Incorrect"
    return f'<span class="verdict-pill {cls}">{text}</span>'


hdr_l, hdr_r = st.columns([3, 1])
with hdr_l:
    st.markdown(
        verdict_pill("Predicted", verdict)
        + verdict_pill("Ground truth", gt)
        + correctness_pill(verdict, gt),
        unsafe_allow_html=True,
    )
with hdr_r:
    st.metric("Q&A turns", len(log))


# ═════════════════════ BASELINE (no ADM) ═════════════════════════════════════
if baseline:
    st.info("ℹ️ Baseline configuration: model prompted directly, **no ADM**.")
    if not log:
        st.warning("No log file found for this run.")
        st.stop()
    turn = log[0]
    tab_a, tab_p, tab_d = st.tabs(["💬 Answer & Reasoning", "📜 Full Prompt", "📄 Case Documents"])
    with tab_a:
        st.subheader("Model verdict")
        st.markdown(verdict_pill("Predicted", verdict), unsafe_allow_html=True)
        st.subheader("Answer");    st.write(turn.get("answer", "—"))
        st.subheader("Reasoning"); st.write(turn.get("reasoning", "—"))
        with st.expander("Turn metadata"):
            st.json({k: v for k, v in turn.items() if k not in ("full_prompt",)})
    with tab_p:
        st.subheader("Full prompt sent to the model")
        fp = turn.get("full_prompt")
        if isinstance(fp, list):
            for msg in fp:
                with st.expander(msg.get('role', '?').upper(),
                                 expanded=(msg.get("role") == "user")):
                    st.text(msg.get("content", ""))
        else:
            st.text(turn.get("question", ""))
    with tab_d:
        cfg_fields = dl.get_fields_for_config(cfg, case_ref)
        for field in (cfg_fields or dl.get_available_fields(case_ref)):
            with st.expander(field.upper(), expanded=(field == "claims")):
                st.text(dl.get_case_text(case_ref, field))
    st.stop()


# ═════════════════════ ADM CONFIGS ═══════════════════════════════════════════
main_graph    = ag.get_graph("main")
initial_graph = ag.get_graph("initial")

if main_summary:
    main_overlay = ag.overlay_case(
        main_graph,
        case=main_summary.get("case", []),
        evaluated_nodes=main_summary.get("evaluated_nodes", []),
        adm_type="main",
    )
else:
    main_overlay = ag.overlay_case(main_graph, [], [], adm_type="main")

if initial_summary:
    initial_overlay = ag.overlay_case(
        initial_graph,
        case=initial_summary.get("case", []),
        evaluated_nodes=initial_summary.get("evaluated_nodes", []),
        adm_type="initial",
    )
else:
    initial_overlay = ag.overlay_case(initial_graph, [], [], adm_type="initial")


# ─── node-detail panel ──────────────────────────────────────────────────────
def render_node_panel(node: dict, log_data: list, feature: str | None = None):
    name = node["name"]
    status = node.get("status", "unknown")
    status_label = {
        "accepted": "✅ Accepted",
        "rejected": "❌ Rejected",
        "unknown":  "○ Unknown / not evaluated",
    }.get(status, status)

    st.markdown(f"### `{name}`")
    st.caption(f"type: **{node['node_type']}** &middot; {status_label}")

    qnum = ah.extract_q_number_from_node(node)
    if qnum:
        st.markdown(f"**Question reference:** {qnum}")

    # Acceptance conditions — shown EXACTLY as authored, paired with statements.
    # The rule that fired (i.e. whose condition evaluated to True) is highlighted
    # green.  We detect this by checking whether every BLF token in the
    # condition string is present in the node's accepted-ancestor set (the
    # 'case' is not stored per-node here, so we approximate: a condition fires
    # when the node itself is accepted AND all non-negated tokens in the
    # condition are in the graph's accepted-node set).
    rows = ah.acceptance_rows(
        node.get("acceptance_original"), node.get("statements")
    )
    if rows:
        node_accepted = (status == "accepted")
        # Build the set of accepted node names from the overlay stored in the
        # 'statuses' key if available (passed via the overlay dict), or fall
        # back to the node's own status.
        # We use a closure variable injected by render_adm_tab (see below).
        accepted_set: set[str] = _current_accepted_set

        def _rule_fired(condition: str) -> bool:
            """True if this infix condition is the one that determined
            acceptance for the current node."""
            if not node_accepted:
                return False
            # Tokenise: bare names are BLFs; 'reject X' / 'not X' negate
            import re as _re
            tokens = _re.findall(r'[A-Za-z][A-Za-z0-9_]*', condition)
            lower = condition.lower()
            for tok in tokens:
                if tok.lower() in ('and', 'or', 'not', 'reject'):
                    continue
                # if preceded by 'reject' or 'not' the token must be absent
                pat = _re.search(r'(reject|not)\s+' + re.escape(tok), lower)
                if pat:
                    if tok in accepted_set:
                        return False  # negated token is accepted → not this rule
                else:
                    if tok not in accepted_set:
                        return False  # required token not accepted
            return True

        with st.expander("📐 Acceptance rules (raw infix)", expanded=True):
            for r in rows:
                fired = not r["is_default"] and _rule_fired(r["condition"])
                default_fired = r["is_default"] and node_accepted and not any(
                    not rr["is_default"] and _rule_fired(rr["condition"]) for rr in rows
                )
                highlight = fired or default_fired
                bg = "background:#d4edda; border-left:4px solid #28a745; padding:4px 8px; border-radius:4px;" if highlight else ""
                if r["is_default"]:
                    label = f"**OTHERWISE** → _{r['statement']}_"
                else:
                    label = f"**IF** `{r['condition']}`"
                    if r["statement"]:
                        label += f"  →  _{r['statement']}_"
                if highlight:
                    st.markdown(
                        f'<div style="{bg}">✅ {label}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(f"- {label}")
    else:
        st.markdown("_Leaf factor (set directly by the LLM's answer)._")

    q_template = node.get("question")
    if q_template:
        with st.expander("❓ Question text"):
            st.text(q_template)

    if node.get("children"):
        with st.expander("👉 Depends on (children)"):
            for c in node["children"]:
                st.markdown(f"- `{c}`")

    if qnum and log_data:
        turns = ah.find_log_turns_for_node(log_data, node, feature=feature)
        if turns:
            st.markdown(
                f"### 💬 LLM answer for **{qnum}**"
                + (f" — _{feature}_" if feature else "")
            )
            for turn in turns:
                ans = turn.get("answer", "—")
                rsn = turn.get("reasoning", "")
                ts  = turn.get("timestamp", "")
                with st.container(border=True):
                    st.markdown(
                        f"**Answer:** `{ans}`  \n"
                        f"<span class='small-muted'>{ts}</span>",
                        unsafe_allow_html=True,
                    )
                    if rsn:
                        st.markdown(f"**Reasoning:** {rsn}")
        else:
            st.info(
                f"No log turn matched {qnum}"
                + (f" for feature *{feature}*." if feature else ".")
            )


# ─── ADM-graph tab renderer ─────────────────────────────────────────────────
def render_adm_tab(overlay: dict, log_data: list, *,
                   feature: str | None = None,
                   key_prefix: str, title: str = "ADM Tree"):
    nodes_by_name = {n["name"]: n for n in overlay["nodes"]}
    if not nodes_by_name:
        st.warning("Empty ADM graph.")
        return
    node_names = list(nodes_by_name.keys())
    ordered = sorted(node_names, key=lambda n: (nodes_by_name[n].get("level", 0), n))

    # We use a *separate* pending key so we never write to the widget key
    # after the widget has been instantiated (Streamlit forbids that).
    pending_key = f"{key_prefix}_pending"
    sel_key     = f"{key_prefix}_selected"

    # Seed: apply any pending click, or set root as default
    if pending_key in st.session_state and st.session_state[pending_key] in nodes_by_name:
        current = st.session_state[pending_key]
        del st.session_state[pending_key]
        # Overwrite the selectbox index BEFORE the widget is created
        if current in ordered:
            st.session_state[sel_key] = current
    elif sel_key not in st.session_state or st.session_state[sel_key] not in nodes_by_name:
        root = next(
            (n["name"] for n in overlay["nodes"] if n["node_type"] == "root"),
            ordered[0],
        )
        st.session_state[sel_key] = root

    col_g, col_d = st.columns([2.2, 1])
    with col_g:
        st.selectbox(
            "🔍 Inspect node", ordered, key=sel_key,
            format_func=lambda n: f"{n}  ({nodes_by_name[n]['node_type']})",
        )
        fig = av.make_adm_figure(
            overlay, selected_node=st.session_state[sel_key],
            height=720, title=title,
        )
        event = st.plotly_chart(
            fig, use_container_width=True,
            on_select="rerun", selection_mode=("points",),
            key=f"{key_prefix}_chart",
        )
        # Plotly click → store in pending key, then rerun so the
        # selectbox picks it up on the NEXT render before widget creation.
        sel_pts = []
        try:
            if isinstance(event, dict):
                sel_pts = event.get("selection", {}).get("points", []) or []
            elif hasattr(event, "selection"):
                sel_pts = (event.selection or {}).get("points", []) or []
        except Exception:
            sel_pts = []
        if sel_pts:
            picked = sel_pts[0].get("customdata")
            if isinstance(picked, list) and picked:
                picked = picked[0]
            if (isinstance(picked, str)
                    and picked in nodes_by_name
                    and picked != st.session_state[sel_key]):
                st.session_state[pending_key] = picked
                st.rerun()
    with col_d:
        node = nodes_by_name[st.session_state[sel_key]]
        # Make the accepted-node set available to render_node_panel
        global _current_accepted_set
        _current_accepted_set = {
            n["name"] for n in overlay["nodes"] if n.get("status") == "accepted"
        }
        render_node_panel(node, log_data, feature=feature)


# ─── sub-ADM summary helpers ────────────────────────────────────────────────
def sub_adm_status(entry: dict, adm_type: str) -> str:
    """Return 'accepted' | 'rejected' | 'unknown' for the root of a sub-ADM
    instance, using the ADM's own 3VL evaluator."""
    statuses = ag.evaluate_case(
        adm_type,
        entry.get("case", []),
        entry.get("evaluated_nodes", []),
    )
    graph = ag.get_graph(adm_type)
    root = next(
        (n["name"] for n in graph["nodes"] if n["node_type"] == "root"),
        None,
    )
    return statuses.get(root, "unknown") if root else "unknown"


def render_sub_adm_summary(entries: list, adm_type: str, label: str):
    if not entries:
        st.info(f"No {label} instances were run for this case.")
        return None
    rows = []
    for e in entries:
        st_ = sub_adm_status(e, adm_type)
        emoji = {"accepted": "✅", "rejected": "❌", "unknown": "○"}.get(st_, "?")
        rows.append({
            "#":         e.get("id", "?"),
            "Item":      e.get("item_name", ""),
            "Root":      st_,
            "Status":    f"{emoji} {st_}",
            "|case|":    len(e.get("case", []) or []),
            "|eval|":    len(e.get("evaluated_nodes", []) or []),
        })
    st.markdown(f"#### Summary — {label}")
    st.dataframe(rows, hide_index=True, use_container_width=True)


# ─── tabs ────────────────────────────────────────────────────────────────────
tabs = st.tabs([
    "🏠 Overview", "🌱 Initial ADM", "🌳 Main ADM",
    "🔬 Sub-ADM 1 — Feature Effect",
    "🎯 Sub-ADM 2 — Objective Problem",
    "💬 Q&A Log", "📄 Case Documents",
])

# Overview ───────────────────────────────────────────────────────────────────
with tabs[0]:
    c1, c2, c3 = st.columns(3)
    c1.metric("Verdict", verdict or "—")
    c2.metric("Ground truth", gt or "—")
    c3.metric(
        "Sub-ADMs run",
        f"{len(sub_adm_1_entries)} feature(s) · {len(sub_adm_2_entries)} problem(s)",
    )
    if main_summary:
        st.subheader("Main ADM reasoning chain")
        st.caption("Indented by depth. Statements emitted by the ADM as it traversed.")
        for r in main_summary.get("reasoning", []):
            depth = r.get("depth", 0)
            indent = "&nbsp;" * (depth * 4)
            st.markdown(f"{indent}↳ {r.get('statement','')}", unsafe_allow_html=True)
    else:
        st.warning("No main-ADM summary file available for this run.")

# Initial ADM ───────────────────────────────────────────────────────────────
with tabs[1]:
    st.markdown(
        "The **Initial ADM** captures the preliminary questioning of the case "
        "(skilled person, prior art relevance, combination motive, etc.)."
    )
    if initial_summary is None:
        st.info(
            "ℹ️ No Initial ADM data was recorded for this run.  "
            "The initial ADM may not have been saved in the output, "
            "or this configuration does not produce a separate initial summary."
        )
    else:
        render_adm_tab(initial_overlay, log,
                       key_prefix="initial",
                       title="Initial ADM — preliminary questioning")

# Main ADM ──────────────────────────────────────────────────────────────────
with tabs[2]:
    if main_summary is None:
        st.warning("No `adm_summary.json` for this run.")
    else:
        st.markdown(
            "The **Main ADM** integrates evidence from the sub-ADMs to reach "
            "the final verdict on inventive step."
        )
        render_adm_tab(main_overlay, log,
                       key_prefix="main",
                       title="Main ADM — inventive step")

# Sub-ADM 1 ─────────────────────────────────────────────────────────────────
with tabs[3]:
    st.markdown(
        "**Sub-ADM 1** evaluates whether each *distinguishing feature* makes "
        "a credible, reproducible technical contribution. One sub-ADM "
        "instance runs per feature."
    )
    render_sub_adm_summary(sub_adm_1_entries, "sub_adm_1", "Sub-ADM 1 instances")
    if sub_adm_1_entries:
        feat_options = [f"#{e['id']} — {e['item_name']}" for e in sub_adm_1_entries]
        idx = st.radio(
            "Pick a feature to drill in", range(len(feat_options)),
            format_func=lambda i: feat_options[i], key="sa1_feature_idx",
        )
        entry = sub_adm_1_entries[idx]
        feature_name = entry["item_name"]
        st.markdown(f"#### Feature: _{feature_name}_")
        sa1_overlay = ag.overlay_case(
            ag.get_graph("sub_adm_1"),
            case=entry.get("case", []),
            evaluated_nodes=entry.get("evaluated_nodes", []),
            adm_type="sub_adm_1",
        )
        render_adm_tab(sa1_overlay, log, feature=feature_name,
                       key_prefix=f"sa1_{idx}",
                       title=f"Sub-ADM 1 — {feature_name}")
        with st.expander("📜 Reasoning chain for this feature"):
            for r in entry.get("reasoning", []):
                depth = r.get("depth", 0)
                indent = "&nbsp;" * (depth * 4)
                st.markdown(f"{indent}↳ {r.get('statement','')}",
                            unsafe_allow_html=True)

# Sub-ADM 2 ─────────────────────────────────────────────────────────────────
with tabs[4]:
    st.markdown(
        "**Sub-ADM 2** evaluates each *candidate Objective Technical Problem*: "
        "is it well-formed, free of hindsight, and would the skilled person "
        "have arrived at the invention given it?"
    )
    render_sub_adm_summary(sub_adm_2_entries, "sub_adm_2", "Sub-ADM 2 instances")
    if sub_adm_2_entries:
        prob_options = [f"#{e['id']} — {e['item_name']}" for e in sub_adm_2_entries]
        idx = st.radio(
            "Pick an OTP to drill in", range(len(prob_options)),
            format_func=lambda i: prob_options[i], key="sa2_problem_idx",
        )
        entry = sub_adm_2_entries[idx]
        problem_name = entry["item_name"]
        st.markdown(f"#### Candidate problem: _{problem_name}_")
        sa2_overlay = ag.overlay_case(
            ag.get_graph("sub_adm_2"),
            case=entry.get("case", []),
            evaluated_nodes=entry.get("evaluated_nodes", []),
            adm_type="sub_adm_2",
        )
        render_adm_tab(sa2_overlay, log, feature=problem_name,
                       key_prefix=f"sa2_{idx}",
                       title=f"Sub-ADM 2 — {problem_name}")
        with st.expander("📜 Reasoning chain for this problem"):
            for r in entry.get("reasoning", []):
                depth = r.get("depth", 0)
                indent = "&nbsp;" * (depth * 4)
                st.markdown(f"{indent}↳ {r.get('statement','')}",
                            unsafe_allow_html=True)

# Q&A Log ───────────────────────────────────────────────────────────────────
with tabs[5]:
    if not log:
        st.warning("No log file for this run.")
    else:
        qnums = sorted(
            {ah.extract_q_number(t.get("question", "")) or "—" for t in log},
            key=lambda x: (
                x == "—",
                int(x[1:]) if x and x.startswith("Q") and x[1:].isdigit() else 999,
            ),
        )
        features = ["(any)"] + ah.list_features_in_log(log)
        c1, c2, c3 = st.columns([1, 2, 2])
        with c1: q_filter = st.multiselect("Q-number", qnums, default=[])
        with c2: feat_filter = st.selectbox("Feature / problem", features)
        with c3: kw = st.text_input("Search text", "")

        rows = []
        for t in log:
            qn  = ah.extract_q_number(t.get("question", "")) or "—"
            ctx = ah.extract_item_context(t.get("question", "")) or ""
            if q_filter and qn not in q_filter:
                continue
            if feat_filter != "(any)" and ctx != feat_filter:
                continue
            if kw and kw.lower() not in (
                (t.get("question", "") + t.get("answer", "") + t.get("reasoning", "")).lower()
            ):
                continue
            rows.append((qn, ctx, t))

        st.markdown(f"**{len(rows)} turns**")
        for qn, ctx, t in rows:
            label = f"Turn {t.get('turn','?')} · **{qn}**"
            if ctx: label += f" · _{ctx}_"
            with st.expander(label):
                st.markdown(f"**Q:** {t.get('question','')}")
                st.markdown(f"**A:** `{t.get('answer','—')}`")
                if t.get("reasoning"):
                    st.markdown(f"**Reasoning:** {t['reasoning']}")
                st.caption(t.get("timestamp", ""))

# Documents ─────────────────────────────────────────────────────────────────
with tabs[6]:
    cfg_fields = dl.get_fields_for_config(cfg, case_ref)
    all_fields = dl.get_available_fields(case_ref)
    omitted = [f for f in all_fields if f not in cfg_fields]
    if omitted:
        st.caption(
            f"ℹ️ Showing only the documents injected for **{cfg_labels[cfg]}** "
            f"(config {dl._cfg_num(cfg)}): **{', '.join(cfg_fields)}**.  "
            f"Not included for this config: {', '.join(omitted)}."
        )
    if not cfg_fields:
        st.warning("No source documents found for this case / config.")
    else:
        sub_tabs = st.tabs([f.upper() for f in cfg_fields])
        for st_tab, field in zip(sub_tabs, cfg_fields):
            with st_tab:
                st.text(dl.get_case_text(case_ref, field))
