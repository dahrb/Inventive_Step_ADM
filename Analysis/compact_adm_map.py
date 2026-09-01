"""
THROWAWAY / SCRATCH — compact "constellation" view of all ADMs together.

Renders adm_initial, adm_main, sub_adm_1, sub_adm_2 as one graph of small
coloured dots:
    * issue            -> orange
    * (abstract) factor-> blue
    * base-level factor-> green
Special roles keep the category colour but get a distinct outline/shape:
    * root determination -> black diamond
    * sub-ADM link node  -> purple double-circle (this is where the loop lives)

The loop is drawn explicitly: the sub-ADM link node in the main ADM has a
self-loop ("↺ for each feature/problem") and a dashed edge into the root of the
sub-ADM it instantiates, plus a dashed return edge showing the result flowing
back to instantiate the base-level factor.

Run:  python Analysis/compact_adm_map.py
Out:  Analysis/adm_viz/00_compact_map.{svg,png}
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pydot

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "ADM"))
from inventive_step_ADM import adm_initial, adm_main, sub_adm_1, sub_adm_2  # noqa: E402

OUT = HERE / "adm_viz"
OUT.mkdir(exist_ok=True)

# ── palette ─────────────────────────────────────────────────────────────────
COL = {
    "issue": "#E67E22",   # orange
    "factor": "#3498DB",  # blue
    "blf": "#2ECC71",     # green
    "eval": "#2ECC71",    # green (base-level factor, but sub-ADM-derived)
    "loop": "#8E44AD",    # purple (sub-ADM link)
}
# per-sub-ADM accent rings: eval-node rings (and cluster borders) are coloured
# by which sub-ADM the result comes from.
SUB_RING = {
    "sub1": "#0E6655",    # teal   – Sub-ADM 1 (per distinguishing feature)
    "sub2": "#B9770E",    # amber  – Sub-ADM 2 (per objective technical problem)
}
LOOP_RING = "#4A235A"     # dark purple ring on the sub-ADM link nodes
EDGE = {
    "pos": "#27AE60",     # green   – supporting condition
    "neg": "#C0392B",     # red     – negated / reject condition
    "loop": "#8E44AD",    # purple  – sub-ADM loop (instantiate / result)
}


def classify(adm):
    """name -> category for every node in an ADM."""
    root = getattr(adm, "root_node", None)
    root_name = root.name if root else None
    issues = set(root.children) if root and root.children else set()
    # which sub-ADM each SubADMNode drives (by its loop function)
    subadm_src = {}
    for n, nd in adm.nodes.items():
        if type(nd).__name__ == "SubADMNode":
            fn = getattr(getattr(nd, "function", None), "__name__", "")
            subadm_src[n] = "sub1" if "feat" in fn else ("sub2" if "obj" in fn else "sub1")
    cats = {}
    for name, node in adm.nodes.items():
        t = type(node).__name__
        if t == "SubADMNode":
            cats[name] = "loop"
        elif t == "EvaluationNode":
            # base-level factor populated from sub-ADM results; tag with origin
            cats[name] = "eval_" + subadm_src.get(node.source_blf, "sub1")
        elif name == root_name:
            cats[name] = "root"
        elif name in issues:
            cats[name] = "issue"
        elif node.children:  # non-leaf, non-issue -> abstract factor
            cats[name] = "factor"
        else:
            cats[name] = "blf"
    return cats, root_name


def build_adm_dot(adm, title, accent=None):
    """Build a standalone Dot for ONE ADM (raw node names as SVG titles).
    Returns (dot, root_name, subadm_fns) where subadm_fns maps SubADMNode -> fn name."""
    g = pydot.Dot(graph_type="digraph", rankdir="LR", nodesep="0.08",
                  ranksep="0.30", bgcolor="white")
    g.set_edge_defaults(arrowhead="vee")
    cluster = pydot.Cluster(
        "c", label=title, fontname="Arial", fontsize="15", style="rounded",
        color=accent or "#BBBBBB", fontcolor=accent or "#222222", labeljust="l",
        penwidth="2.2" if accent else "1",
    )
    cats, root_name = classify(adm)
    for name, node in adm.nodes.items():
        cat = cats[name]
        if cat == "root":
            shape, fill, outline, w, pen = "diamond", "#222222", "#000000", "0.30", "2"
        elif cat == "loop":
            shape, fill, outline, w, pen = "doublecircle", COL["loop"], LOOP_RING, "0.20", "2"
        elif cat.startswith("eval_"):
            ring = SUB_RING[cat.split("_", 1)[1]]
            shape, fill, outline, w, pen = "doublecircle", COL["blf"], ring, "0.16", "2.5"
        else:
            shape, fill, outline, w, pen = "circle", COL[cat], "#555555", "0.18", "1"
        cluster.add_node(pydot.Node(
            name, label="", shape=shape, style="filled", fillcolor=fill,
            color=outline, penwidth=pen, width=w, height=w, fixedsize="true",
        ))
    for name, node in adm.nodes.items():
        if not node.children:
            continue
        for child in node.children:
            if child not in adm.nodes:
                continue
            neg = False
            if node.acceptance:
                for cond in node.acceptance:
                    toks = cond.split()
                    if child in toks and ("reject" in toks or "not" in toks):
                        neg = True
                        break
            cluster.add_edge(pydot.Edge(name, child,
                                        color=EDGE["neg"] if neg else EDGE["pos"],
                                        arrowsize="0.5", penwidth="0.8"))
    g.add_subgraph(cluster)

    subadm_fns = {}
    for name, node in adm.nodes.items():
        if type(node).__name__ == "SubADMNode":
            subadm_fns[name] = getattr(getattr(node, "function", None), "__name__", "")
    return g, root_name, subadm_fns


def render_parse(dot):
    """Render an ADM Dot to SVG and extract its content group + node centres."""
    svg = dot.create_svg().decode("utf-8")
    _, _, w, h = _viewbox(svg)
    m = re.search(r'<g id="graph0"[^>]*translate\(([-\d.]+)[ ,]+([-\d.]+)\)', svg)
    tx, ty = float(m.group(1)), float(m.group(2))
    group = svg[svg.index('<g id="graph0"'): svg.rindex("</g>") + 4]
    centers = {}
    for block in re.split(r'<g id="node\d+" class="node">', svg)[1:]:
        nm = re.search(r"<title>(.*?)</title>", block)
        if not nm:
            continue
        em = re.search(r'<ellipse[^>]*cx="([-\d.]+)" cy="([-\d.]+)"[^>]*rx="([-\d.]+)"', block)
        if em:
            cx, cy, r = float(em.group(1)), float(em.group(2)), float(em.group(3))
        else:
            pm = re.search(r'<polygon[^>]*points="([^"]+)"', block)
            pts = [tuple(map(float, p.split(","))) for p in pm.group(1).split()]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
            r = max(max(xs) - min(xs), max(ys) - min(ys)) / 2
        centers[nm.group(1)] = (cx, cy, r)
    return {"group": group, "tx": tx, "ty": ty, "w": w, "h": h, "centers": centers}


def _abs(P, off, name):
    cx, cy, r = P["centers"][name]
    return off[0] + P["tx"] + cx, off[1] + P["ty"] + cy, r


def _arc(x1, y1, x2, y2, y_top, color, width, dashed=True, marker="url(#ah)"):
    dash = ' stroke-dasharray="5,4"' if dashed else ""
    return (f'<path d="M {x1:.1f} {y1:.1f} C {x1:.1f} {y_top:.1f} {x2:.1f} {y_top:.1f} '
            f'{x2:.1f} {y2:.1f}" fill="none" stroke="{color}" stroke-width="{width}"'
            f'{dash} marker-end="{marker}"/>')


def _selfloop(x, y, r, color, marker="url(#ah)"):
    top = y - r - 4
    return (f'<path d="M {x-6:.1f} {top:.1f} C {x-20:.1f} {top-22:.1f} '
            f'{x+20:.1f} {top-22:.1f} {x+7:.1f} {top:.1f}" fill="none" '
            f'stroke="{color}" stroke-width="1.6" marker-end="{marker}"/>')


def main(png_scale=2.0):
    specs = [
        ("init", adm_initial, (), "Preconditions for Inventive Step", None),
        ("main", adm_main, (True, True), "Inventive Step ADM", None),
        ("sub1", sub_adm_1, ("feature",), "Sub-ADM 1  (per distinguishing feature)", SUB_RING["sub1"]),
        ("sub2", sub_adm_2, ("problem",), "Sub-ADM 2  (per objective technical problem)", SUB_RING["sub2"]),
    ]
    P, roots, sub_fns = {}, {}, {}
    for key, f, args, title, accent in specs:
        dot, root_name, fns = build_adm_dot(f(*args), title, accent=accent)
        P[key] = render_parse(dot)
        roots[key] = root_name
        sub_fns[key] = fns

    # ── wide tiling: the four ADMs in a single left->right row ────────────────
    order = ["init", "main", "sub1", "sub2"]
    ml, gap, y0 = 20, 44, 58
    off, x = {}, ml
    for k in order:
        off[k] = (x, y0)
        x += P[k]["w"] + gap
    graph_w = x - gap + ml
    graph_h = y0 + max(P[k]["h"] for k in order) + 30

    parts = [f'<g transform="translate({off[k][0]},{off[k][1]})">{P[k]["group"]}</g>'
             for k in order]

    # ── connection arrows (drawn in the top margin so they clear the boxes) ───
    y_top = y0 - 30
    arrows = []
    # preconditions BOX -> inventive step BOX (straight arrow between the boxes)
    iy = off["init"][1] + P["init"]["h"] / 2
    ir = off["init"][0] + P["init"]["w"] - 4
    ml_ = off["main"][0] + 4
    arrows.append(f'<path d="M {ir:.1f} {iy:.1f} L {ml_:.1f} {iy:.1f}" fill="none" '
                  f'stroke="#888888" stroke-width="2" marker-end="url(#ahg)"/>')
    # main sub-ADM links -> sub-ADM roots: arcs only (self loop + instantiate +
    # result), no text; the legend explains the purple edges.
    for i, (name, fn) in enumerate(sub_fns["main"].items()):
        sub = "sub1" if "feat" in fn else "sub2"
        yt = y_top - i * 20        # separate the two instantiate arcs vertically
        sx, sy, sr = _abs(P["main"], off["main"], name)
        tx_, ty_, _ = _abs(P[sub], off[sub], roots[sub])
        arrows.append(_selfloop(sx, sy, sr, COL["loop"]))
        if sub == "sub1":  # adjacent on the right -> straight instantiate line
            arrows.append(
                f'<path d="M {sx:.1f} {sy:.1f} L {tx_:.1f} {ty_:.1f}" fill="none" '
                f'stroke="{COL["loop"]}" stroke-width="1.8" stroke-dasharray="5,4" '
                f'marker-end="url(#ah)"/>')
            # result: shallow bow *below* the straight line so it stays in the gap
            # and doesn't ride up over the "Sub-ADM 1" title text
            arrows.append(_arc(tx_, ty_, sx, sy, (ty_ + sy) / 2 + 30, COL["loop"], 1.0))
        else:
            arrows.append(_arc(sx, sy, tx_, ty_, yt, COL["loop"], 1.8))
            arrows.append(_arc(tx_, ty_, sx, sy, yt + 14, COL["loop"], 1.0))

    # ── legend: tuck into the empty area below the (short) sub-ADMs, filling the
    #    bottom-right whitespace left by the tall Inventive Step ADM ────────────
    leg, lw, lh = make_legend_group()
    lx = off["sub1"][0]
    ly = y0 + max(P["sub1"]["h"], P["sub2"]["h"]) + 40
    canvas_w = max(graph_w, lx + lw + ml)
    canvas_h = max(graph_h, ly + lh + 18)
    legend = f'<g transform="translate({lx:.1f},{ly:.1f})">{leg}</g>'

    defs = (
        '<defs>'
        f'<marker id="ah" markerWidth="9" markerHeight="9" refX="7" refY="3" '
        f'orient="auto" markerUnits="userSpaceOnUse">'
        f'<path d="M0,0 L8,3 L0,6 Z" fill="{COL["loop"]}"/></marker>'
        '<marker id="ahg" markerWidth="9" markerHeight="9" refX="7" refY="3" '
        'orient="auto" markerUnits="userSpaceOnUse">'
        '<path d="M0,0 L8,3 L0,6 Z" fill="#999999"/></marker>'
        '</defs>'
    )
    body = (
        f'<rect x="0" y="0" width="{canvas_w:.1f}" height="{canvas_h:.1f}" fill="white"/>'
        + "".join(parts) + "".join(arrows) + legend
    )
    svg = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{canvas_w:.0f}pt" height="{canvas_h:.0f}pt" '
        f'viewBox="0 0 {canvas_w:.1f} {canvas_h:.1f}">{defs}{body}</svg>'
    )
    svg_path = OUT / "00_compact_map.svg"
    svg_path.write_text(svg, encoding="utf-8")
    print("wrote", svg_path, f"({canvas_w:.0f}x{canvas_h:.0f})")
    png_path = svg_to_png(svg_path, scale=png_scale)
    if png_path:
        print("wrote", png_path)
    return svg_path, png_path


def svg_to_png(svg_path, scale=2.0):
    """Rasterise an SVG to PNG next to it. This graphviz build has no PNG
    target, so use rsvg-convert if present, else cairosvg. Returns the path
    (or None if neither is available)."""
    svg_path = Path(svg_path)
    png_path = svg_path.with_suffix(".png")
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        subprocess.run([rsvg, "-z", str(scale), str(svg_path), "-o", str(png_path)],
                       check=True)
        return png_path
    try:
        import cairosvg
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), scale=scale)
        return png_path
    except Exception as e:  # pragma: no cover
        print(f"[png export skipped: no rsvg-convert or cairosvg — {e}]")
        return None


# ── hand-built SVG legend (2 columns) ────────────────────────────────────────
def _circle(cx, cy, r, fill, stroke, sw=1.0):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw}"/>')


def _ring(cx, cy, fill, ring):
    return (f'<circle cx="{cx}" cy="{cy}" r="8" fill="none" stroke="{ring}" stroke-width="2.6"/>'
            f'<circle cx="{cx}" cy="{cy}" r="4.3" fill="{fill}" stroke="none"/>')


def _diamond(cx, cy, fill):
    return (f'<polygon points="{cx},{cy-8} {cx+8},{cy} {cx},{cy+8} {cx-8},{cy}" '
            f'fill="{fill}" stroke="#000000" stroke-width="1"/>')


def _bar(cx, cy, color):
    return f'<rect x="{cx-12}" y="{cy-3}" width="24" height="6" rx="1" fill="{color}"/>'


def _text(x, y, s, size=12, bold=False, color="#222222", anchor="start"):
    weight = ' font-weight="bold"' if bold else ""
    return (f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" '
            f'font-size="{size}"{weight} fill="{color}" text-anchor="{anchor}">{s}</text>')


def _swatch(kind, color, ring, cx, cy):
    if kind == "dot":
        return _circle(cx, cy, 7, color, "#555555")
    if kind == "ring":
        return _ring(cx, cy, color, ring)
    if kind == "diamond":
        return _diamond(cx, cy, color)
    if kind == "bar":
        return _bar(cx, cy, color)
    return ""


def make_legend_group():
    """Return (svg_markup, width, height) for a 2-column legend box."""
    pad, row_h = 12, 25
    colL, colR = pad, 322
    y_title, y_header, y0 = 22, 46, 68

    left = [
        ("dot", COL["issue"], None, "issue"),
        ("dot", COL["factor"], None, "abstract factor"),
        ("dot", COL["blf"], None, "base-level factor"),
        ("ring", COL["blf"], SUB_RING["sub1"], "base-level factor (from Sub-ADM 1)"),
        ("ring", COL["blf"], SUB_RING["sub2"], "base-level factor (from Sub-ADM 2)"),
        ("ring", COL["loop"], LOOP_RING, "sub-ADM link (loop)"),
        ("diamond", "#222222", None, "root / determination"),
    ]
    right = [
        ("bar", EDGE["pos"], None, "supporting condition"),
        ("bar", EDGE["neg"], None, "negated / reject condition"),
        ("bar", EDGE["loop"], None, "sub-ADM loop (instantiate / result)"),
    ]

    W = colR + 292 + pad
    H = y0 + len(left) * row_h + 4

    el = [f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="9" '
          f'fill="white" stroke="#999999" stroke-width="1"/>']
    el.append(_text(colL + 2, y_title, "Legend", size=14, bold=True))
    el.append(_text(colL + 2, y_header, "Node type", size=11, bold=True, color="#444444"))
    el.append(_text(colR + 2, y_header, "Edge type", size=11, bold=True, color="#444444"))

    for i, (kind, color, ring, text) in enumerate(left):
        cy = y0 + i * row_h
        el.append(_swatch(kind, color, ring, colL + 16, cy - 4))
        el.append(_text(colL + 34, cy, text))
    for i, (kind, color, ring, text) in enumerate(right):
        cy = y0 + i * row_h
        el.append(_swatch(kind, color, ring, colR + 16, cy - 4))
        el.append(_text(colR + 34, cy, text))

    return "".join(el), W, H


def _viewbox(svg):
    m = re.search(r'viewBox="([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)"', svg)
    return tuple(float(x) for x in m.groups())


if __name__ == "__main__":
    main()
