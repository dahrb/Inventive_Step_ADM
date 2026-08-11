"""
adm_helpers.py
==============
Light-weight helpers for the ADM Results Explorer.

We deliberately do NOT re-format acceptance conditions: the ADM stores the
human-authored infix form on `node.acceptanceOriginal`, which we show as-is.
Node names are kept in their original CamelCase (e.g. SufficiencyOfDisclosure).
"""
from __future__ import annotations
import re

# ─── model & config labels ───────────────────────────────────────────────────
MODEL_LABELS: dict[str, str] = {
    "GPT_TEST":   "GPT-OSS 120B",
    "LLAMA_TEST": "LLaMA 3.3 70B",
    "QWEN_TEST":  "Qwen-Next-80B-A3B",
}

CONFIG_LABELS: dict[str, str] = {
    "baseline_default":       "Baseline (direct LLM prompt — no ADM)",
    "tool_both_default":      "Tool + ADM (both)",
    "tool_both_default_cfg1": "ADM Configuration 1",
    "tool_both_default_cfg2": "ADM Configuration 2",
    "tool_both_default_cfg3": "ADM Configuration 3",
}


def is_baseline(cfg_dir: str) -> bool:
    return cfg_dir.startswith("baseline")


# ─── log matching ────────────────────────────────────────────────────────────
_QNUM_RE         = re.compile(r"\[Q\s*(\d+)\]", re.I)
_FEATURE_RE      = re.compile(r"Feature:\s*(.+?)(?:\n|$)")
_PROBLEM_RE      = re.compile(r"Problem name:\s*(.+?)(?:\n|$)")
_ITEM_HEADER_RE  = re.compile(r"---\s*Item\s+\d+/\d+:\s*(.+?)\s*---")


def extract_q_number(text: str) -> str | None:
    if not text:
        return None
    m = _QNUM_RE.search(text)
    return f"Q{m.group(1)}" if m else None


def extract_item_context(text: str) -> str | None:
    if not text:
        return None
    for rx in (_FEATURE_RE, _PROBLEM_RE, _ITEM_HEADER_RE):
        m = rx.search(text)
        if m:
            return m.group(1).strip()
    return None


def extract_q_number_from_node(node: dict) -> str | None:
    return extract_q_number(node.get("question") or "")


def find_log_turns_for_node(
    log: list[dict],
    node: dict,
    feature: str | None = None,
) -> list[dict]:
    qnum = extract_q_number_from_node(node)
    if not qnum:
        return []
    matches: list[dict] = []
    for turn in log:
        q_text = turn.get("question") or ""
        if extract_q_number(q_text) != qnum:
            continue
        if feature is not None:
            ctx = extract_item_context(q_text)
            if ctx is None or ctx.strip().lower() != feature.strip().lower():
                continue
        matches.append(turn)
    return matches


def find_log_turns_by_qnum(log: list[dict], qnum: str) -> list[dict]:
    return [t for t in log if extract_q_number(t.get("question") or "") == qnum]


def list_features_in_log(log: list[dict]) -> list[str]:
    seen: list[str] = []
    seen_set: set[str] = set()
    for turn in log:
        ctx = extract_item_context(turn.get("question") or "")
        if ctx and ctx not in seen_set:
            seen.append(ctx); seen_set.add(ctx)
    return seen


# ─── condition rendering (raw infix; statements paired by index) ─────────────
def acceptance_rows(
    acceptance_original: list[str] | None,
    statements: list[str] | None,
) -> list[dict]:
    """
    Return [{'condition': str, 'statement': str, 'is_default': bool}, …].

    Conditions are returned EXACTLY as authored (e.g. "Encompassed and ScopeOfClaim",
    "reject Hindsight"). The last statement (when there's one extra) is the
    default fallback — same convention used by the ADM author.
    """
    acceptance = list(acceptance_original or [])
    statements = list(statements or [])
    rows: list[dict] = []
    for i, cond in enumerate(acceptance):
        rows.append({
            "condition":   cond,
            "statement":   statements[i] if i < len(statements) else "",
            "is_default":  False,
        })
    if len(statements) > len(acceptance):
        rows.append({
            "condition":   "(otherwise)",
            "statement":   statements[-1],
            "is_default":  True,
        })
    return rows
