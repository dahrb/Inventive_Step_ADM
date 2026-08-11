"""
adm_graph.py
============
Pre-computes the ADM node tree layout, and provides per-case node-status
computation that delegates to the ADM's own `evaluateNode(mode='3vl')`
(asymmetric 3-valued logic) rather than re-implementing the traversal.
"""

from __future__ import annotations
import sys
from pathlib import Path
from collections import defaultdict

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE / "ADM"))

from inventive_step_ADM import (  # noqa: E402
    adm_main, adm_initial, sub_adm_1, sub_adm_2, load_questions
)


# ─── ADM instantiation ───────────────────────────────────────────────────────
def _build_adm(adm_type: str):
    questions = load_questions()
    if adm_type == "initial":
        return adm_initial(questions=questions)
    if adm_type == "sub_adm_1":
        return sub_adm_1("<feature>", questions=questions)
    if adm_type == "sub_adm_2":
        return sub_adm_2("<problem>", questions=questions)
    return adm_main(sub_adm_1_flag=True, sub_adm_2_flag=True, questions=questions)


# ─── helpers ─────────────────────────────────────────────────────────────────
def _node_type(node, adm) -> str:
    name = node.name
    ntype = type(node).__name__
    if hasattr(adm, "root_node") and name == adm.root_node.name:
        return "root"
    if ntype == "SubADMNode":
        return "sub_adm"
    if ntype == "EvaluationNode":
        return "evaluation"
    if node.children:
        issue_nodes = (
            adm.root_node.children
            if hasattr(adm, "root_node") and adm.root_node.children
            else []
        )
        if name in issue_nodes:
            return "issue"
        return "abstract"
    return "blf"


def _bfs_levels(adm) -> dict[str, int]:
    root = adm.root_node.name if hasattr(adm, "root_node") else None
    if root is None:
        return {n: 0 for n in adm.nodes}
    levels: dict[str, int] = {root: 0}
    queue = [root]
    while queue:
        cur = queue.pop(0)
        for c in (adm.nodes[cur].children or []):
            if c in adm.nodes and c not in levels:
                levels[c] = levels[cur] + 1
                queue.append(c)
    max_lvl = max(levels.values()) if levels else 0
    for n in adm.nodes:
        levels.setdefault(n, max_lvl + 1)
    return levels


def _hierarchical_layout(adm) -> dict[str, tuple[float, float]]:
    levels = _bfs_levels(adm)
    if not levels:
        return {}
    max_level = max(levels.values())

    root = adm.root_node.name if hasattr(adm, "root_node") else None
    ordered: list[str] = []
    seen: set[str] = set()
    queue = [root] if root else list(adm.nodes.keys())[:1]
    while queue:
        n = queue.pop(0)
        if n in seen or n not in adm.nodes:
            continue
        seen.add(n); ordered.append(n)
        queue.extend(c for c in (adm.nodes[n].children or []) if c in adm.nodes)
    for n in adm.nodes:
        if n not in seen:
            ordered.append(n)

    level_nodes: dict[int, list[str]] = defaultdict(list)
    for n in ordered:
        level_nodes[levels[n]].append(n)

    H, V = 2.6, 2.4
    positions: dict[str, tuple[float, float]] = {}
    for level, nodes_at_level in level_nodes.items():
        count = len(nodes_at_level)
        for i, n in enumerate(nodes_at_level):
            positions[n] = ((i - (count - 1) / 2) * H, -level * V)

    for level in range(max_level, -1, -1):
        for name in level_nodes[level]:
            kids = [c for c in (adm.nodes[name].children or []) if c in positions]
            if kids:
                xs = [positions[c][0] for c in kids]
                positions[name] = (sum(xs) / len(xs), positions[name][1])

    for nodes_at_level in level_nodes.values():
        srt = sorted(nodes_at_level, key=lambda n: positions[n][0])
        for i in range(1, len(srt)):
            xp, _ = positions[srt[i - 1]]
            xc, yc = positions[srt[i]]
            if xc - xp < H:
                positions[srt[i]] = (xp + H, yc)
    return positions


# ─── structural graph (no case overlay) ──────────────────────────────────────
def build_adm_graph(adm_type: str = "main") -> dict:
    adm = _build_adm(adm_type)
    positions = _hierarchical_layout(adm)
    levels = _bfs_levels(adm)

    nodes = []
    for name, node in adm.nodes.items():
        x, y = positions.get(name, (0, 0))
        # acceptanceOriginal is the raw infix list — what we display
        acc_original = list(getattr(node, "acceptanceOriginal", []) or [])
        statements = list(
            getattr(node, "statement", None)
            or getattr(node, "statements", None)
            or []
        )
        nodes.append({
            "name": name,
            "x": x, "y": y,
            "node_type": _node_type(node, adm),
            "level": levels.get(name, 0),
            "question": getattr(node, "question", None),
            "acceptance_original": acc_original,
            "acceptance_postfix": list(getattr(node, "acceptance", []) or []),
            "statements": statements,
            "children": list(node.children or []),
            "class": type(node).__name__,
        })

    edges = []
    for name, node in adm.nodes.items():
        for child in (node.children or []):
            if child not in adm.nodes:
                continue
            sign = "+"
            for cond in (getattr(node, "acceptanceOriginal", []) or []):
                tokens = cond.split()
                if child in tokens and ("reject" in tokens or "not" in tokens):
                    sign = "-"
                    break
            edges.append({"source": name, "target": child, "sign": sign})
    return {"nodes": nodes, "edges": edges, "levels": levels}


_GRAPH_CACHE: dict[str, dict] = {}


def get_graph(adm_type: str = "main") -> dict:
    if adm_type not in _GRAPH_CACHE:
        _GRAPH_CACHE[adm_type] = build_adm_graph(adm_type)
    return _GRAPH_CACHE[adm_type]


# ─── per-case status via the ADM's own 3VL evaluator ────────────────────────
_EVAL_CACHE: dict = {}


def evaluate_case(
    adm_type: str,
    case: list[str],
    evaluated_nodes: list[str],
) -> dict[str, str]:
    """Return {name: 'accepted'|'rejected'|'unknown'} using ADM 3VL."""
    case_set = set(case or [])
    eval_set = set(evaluated_nodes or [])
    key = (adm_type, frozenset(case_set), frozenset(eval_set))
    if key in _EVAL_CACHE:
        return _EVAL_CACHE[key]

    adm = _build_adm(adm_type)
    adm.case = list(case_set)
    adm.evaluated_nodes = eval_set

    statuses: dict[str, str] = {}
    for name, node in adm.nodes.items():
        if name in case_set:
            statuses[name] = "accepted"
            continue
        if not node.children and not node.acceptance:
            # plain leaf BLF
            statuses[name] = "rejected" if name in eval_set else "unknown"
            continue
        try:
            result, _ = adm.evaluateNode(node, mode="3vl")
        except Exception:
            result = None
        if result is True:
            statuses[name] = "accepted"
        elif result is False:
            statuses[name] = "rejected"
        else:
            statuses[name] = "unknown"

    _EVAL_CACHE[key] = statuses
    return statuses


def overlay_case(
    graph_data: dict,
    case: list[str],
    evaluated_nodes: list[str],
    *,
    adm_type: str = "main",
) -> dict:
    """
    Annotate each node of `graph_data` with:
      - status:    'accepted' | 'rejected' | 'unknown'
      - accepted:  bool (back-compat)
      - evaluated: bool (= status != 'unknown')
    """
    statuses = evaluate_case(adm_type, case, evaluated_nodes)
    out = dict(graph_data)
    out["nodes"] = []
    for n in graph_data["nodes"]:
        st = statuses.get(n["name"], "unknown")
        n2 = dict(n)
        n2["status"] = st
        n2["accepted"] = st == "accepted"
        n2["evaluated"] = st != "unknown"
        out["nodes"].append(n2)
    out["statuses"] = statuses
    return out
