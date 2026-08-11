"""
adm_viz.py
==========
Plotly figure factory for the interactive ADM tree.

Coloring is driven by the per-node `status` field (see adm_graph.evaluate_case):
    accepted → green,  rejected → red,  unknown → light grey.

Shapes by node type (root = circle with a thick outline — no star):
"""

import plotly.graph_objects as go


_COLORS = {
    "accepted":     "#2ECC71",
    "rejected":     "#E74C3C",
    "unknown":      "#BDC3C7",
    "edge_support": "#27AE60",
    "edge_attack":  "#C0392B",
    "edge_neutral": "#95A5A6",
    "text_dark":    "#2C3E50",
}

_SHAPES = {
    "root":       "circle",
    "issue":      "hexagon",
    "abstract":   "circle-open",
    "blf":        "square",
    "sub_adm":    "diamond",
    "evaluation": "square-open",
}

_SIZES = {
    "root": 36, "issue": 24, "abstract": 18,
    "blf": 14, "sub_adm": 22, "evaluation": 16,
}


def _node_color(node: dict) -> str:
    return _COLORS.get(node.get("status", "unknown"), _COLORS["unknown"])


def _status_label(status: str) -> str:
    return {
        "accepted": "✅ Accepted",
        "rejected": "❌ Rejected",
        "unknown":  "○ Unknown / not derivable",
    }.get(status, status)


def make_adm_figure(
    graph_data: dict,
    selected_node: str | None = None,
    height: int = 700,
    title: str = "ADM Tree",
) -> go.Figure:
    nodes = {n["name"]: n for n in graph_data["nodes"]}
    edges = graph_data["edges"]

    fig = go.Figure()

    for edge in edges:
        src = nodes.get(edge["source"]); tgt = nodes.get(edge["target"])
        if src is None or tgt is None:
            continue
        color = (
            _COLORS["edge_attack"]  if edge["sign"] == "-" else
            _COLORS["edge_support"] if edge["sign"] == "+" else
            _COLORS["edge_neutral"]
        )
        fig.add_trace(go.Scatter(
            x=[src["x"], tgt["x"], None], y=[src["y"], tgt["y"], None],
            mode="lines", line=dict(color=color, width=1.5),
            hoverinfo="skip", showlegend=False,
        ))

    groups: dict[str, list] = {}
    for n in graph_data["nodes"]:
        groups.setdefault(n["node_type"], []).append(n)

    for ntype, group in groups.items():
        xs = [n["x"] for n in group]
        ys = [n["y"] for n in group]
        names = [n["name"] for n in group]
        colors = [_node_color(n) for n in group]
        sizes = [_SIZES.get(ntype, 14) for _ in group]
        is_root = (ntype == "root")
        border_widths = [
            4 if (n["name"] == selected_node) else (3 if is_root else 1)
            for n in group
        ]
        border_colors = [
            "gold" if (n["name"] == selected_node) else _COLORS["text_dark"]
            for n in group
        ]

        hover_texts = [
            f"<b>{n['name']}</b><br>Type: {n['node_type']}<br>"
            f"{_status_label(n.get('status','unknown'))}"
            for n in group
        ]

        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers+text",
            marker=dict(
                symbol=_SHAPES.get(ntype, "circle"),
                size=sizes, color=colors,
                line=dict(color=border_colors, width=border_widths),
            ),
            text=names,                          # raw CamelCase, no humanise
            textposition="top center",
            textfont=dict(size=9, color=_COLORS["text_dark"]),
            hovertext=hover_texts, hoverinfo="text",
            customdata=names,
            name=ntype.replace("_", " ").title(),
            showlegend=True,
        ))

    # status legend swatches
    for label, color in [
        ("Accepted", _COLORS["accepted"]),
        ("Rejected", _COLORS["rejected"]),
        ("Unknown",  _COLORS["unknown"]),
    ]:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=10, color=color, symbol="circle"),
            name=label, showlegend=True,
        ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=16)),
        height=height, hovermode="closest", showlegend=True,
        legend=dict(orientation="v", x=1.01, y=1,
                    bordercolor="#BDC3C7", borderwidth=1),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor="white", paper_bgcolor="#F8F9FA",
        margin=dict(l=20, r=180, t=60, b=20),
        clickmode="event+select",
    )
    return fig
