"""
data_loader.py
==============
All filesystem / data access for the ADM Results Explorer.

Key functions
-------------
get_ground_truth()          -> {case_ref: "Yes"|"No"}
get_experiments()           -> list of experiment names under Outputs/
get_configs(experiment)     -> list of config dir names
get_cases(experiment, cfg)  -> list of case refs with at least run_1
get_runs(exp, cfg, case)    -> list of available run ids (1,2,3)
get_verdict(exp, cfg, run)  -> dict {case_ref: "Yes"|"No"} from results JSON
get_adm_summary(exp,cfg,case,run) -> list of ADM entry dicts
get_log(exp,cfg,case,run)   -> list of turn dicts
get_case_text(case_ref, field) -> str (field: "claims","CPA","appeal")
get_all_verdicts()          -> nested dict for dashboard
"""

import os
import json
import re
import pickle
from functools import lru_cache
from pathlib import Path

# ─── paths ────────────────────────────────────────────────────────────────────
_BASE      = Path(__file__).resolve().parent.parent
_OUTPUTS   = _BASE / "Outputs"
_DATA      = _BASE / "Data"
_PKL_PATH  = _DATA / "test_data_Inv_Step.pkl"

# Config number extraction from dir names like tool_both_default_cfg2
_CFG_RE = re.compile(r"cfg(\d+)")

# Mapping config dir name -> inner config_N directory used in path
# e.g.  tool_both_default_cfg2  ->  inner dir is config_2
def _cfg_num(cfg_dir: str) -> int:
    m = _CFG_RE.search(cfg_dir)
    return int(m.group(1)) if m else 1


def _inner_path(case_dir: Path, run_id: int, cfg_dir: str) -> Path | None:
    """
    Walk into case_dir/run_{run_id}/config_{N}/<mode>/<adm_config>/<adm_initial>/
    and return the deepest directory that contains adm_summary.json or log.json.
    """
    run_dir = case_dir / f"run_{run_id}"
    if not run_dir.is_dir():
        return None

    # Find first matching config_N subdir
    cfg_n = _cfg_num(cfg_dir)
    config_dir = run_dir / f"config_{cfg_n}"
    if not config_dir.is_dir():
        # Fallback: any config_* dir
        subdirs = sorted(config_dir.parent.iterdir()) if config_dir.parent.is_dir() else []
        config_dirs = [d for d in subdirs if d.is_dir() and d.name.startswith("config_")]
        if not config_dirs:
            return None
        config_dir = config_dirs[0]

    # Descend through mode/adm_config/adm_initial
    for d in _iter_leaf(config_dir):
        if (d / "adm_summary.json").exists() or (d / "log.json").exists():
            return d

    return None


def _iter_leaf(path: Path):
    """Yield leaf directories (depth-first)."""
    if not path.is_dir():
        return
    children = [d for d in path.iterdir() if d.is_dir()]
    if not children:
        yield path
    else:
        for child in children:
            yield from _iter_leaf(child)


# ─── ground truth ─────────────────────────────────────────────────────────────

# Outcome column: 'Reversed' = appeal won = inventive step present = Yes
#                  'Affirmed' = appeal dismissed = no inventive step = No
_OUTCOME_MAP = {"Reversed": "Yes", "Affirmed": "No"}


@lru_cache(maxsize=1)
def get_ground_truth() -> dict:
    """Return {case_ref: 'Yes'|'No'} from the test pkl.

    Uses the 'Outcome' column with mapping Reversed→Yes, Affirmed→No,
    consistent with the analysis notebooks.
    """
    if not _PKL_PATH.exists():
        return {}
    try:
        import pandas as pd
        df = pd.read_pickle(_PKL_PATH)
        mapped = df["Outcome"].astype(str).map(
            lambda v: _OUTCOME_MAP.get(v.strip(), v.strip())
        )
        return dict(zip(df["Reference"].astype(str), mapped))
    except Exception as e:
        print(f"[data_loader] Could not load ground truth pkl: {e}")
        return {}


# ─── experiments / configs ────────────────────────────────────────────────────

def get_experiments() -> list[str]:
    """List experiment names (top-level dirs in Outputs/ that contain sub-dirs)."""
    if not _OUTPUTS.is_dir():
        return []
    exps = []
    for d in sorted(_OUTPUTS.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            # Must have at least one config subdir
            subdirs = [s for s in d.iterdir() if s.is_dir()]
            if subdirs:
                exps.append(d.name)
    return exps


def get_configs(experiment: str) -> list[str]:
    """List config dir names (e.g. tool_both_default_cfg1, baseline_default)."""
    exp_dir = _OUTPUTS / experiment
    if not exp_dir.is_dir():
        return []
    return sorted(
        d.name for d in exp_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


def get_cases(experiment: str, cfg_dir: str) -> list[str]:
    """List case refs that have at least one results entry or output dir."""
    base = _OUTPUTS / experiment / cfg_dir

    # Prefer reading from results JSON (fast)
    for f in base.glob("results_*.json"):
        try:
            with open(f) as fh:
                d = json.load(fh)
            # d may be {"run_1": {case: verdict}, ...} or {case: verdict}
            first = next(iter(d.values()))
            if isinstance(first, dict):
                return sorted(first.keys())
            else:
                return sorted(d.keys())
        except Exception:
            continue

    # Fallback: list case dirs
    return sorted(
        d.name for d in base.iterdir()
        if d.is_dir() and re.match(r"T\d+", d.name)
    )


def get_runs(experiment: str, cfg_dir: str, case_ref: str) -> list[int]:
    """List run ids (integers) available for a case."""
    case_dir = _OUTPUTS / experiment / cfg_dir / case_ref
    if not case_dir.is_dir():
        return []
    runs = []
    for d in sorted(case_dir.iterdir()):
        m = re.match(r"run_(\d+)", d.name)
        if m:
            runs.append(int(m.group(1)))
    return sorted(runs)


# ─── verdict loading ──────────────────────────────────────────────────────────

@lru_cache(maxsize=64)
def get_verdict_map(experiment: str, cfg_dir: str) -> dict:
    """
    Return nested dict: {run_id_str: {case_ref: verdict}}.
    Reads the results_*.json aggregate file if present, otherwise
    falls back to walking individual adm_summary.json files.
    """
    base = _OUTPUTS / experiment / cfg_dir

    for f in base.glob("results_*.json"):
        try:
            with open(f) as fh:
                d = json.load(fh)
            # Normalise to {run_N: {case: verdict}}
            first_val = next(iter(d.values()), None)
            if isinstance(first_val, dict):
                return d
            else:
                return {"run_1": d}
        except Exception:
            continue

    return {}


def get_verdict(experiment: str, cfg_dir: str, case_ref: str, run_id: int = 1) -> str | None:
    """Return 'Yes', 'No', or None for a specific run."""
    vm = get_verdict_map(experiment, cfg_dir)
    run_key = f"run_{run_id}"
    return vm.get(run_key, {}).get(case_ref)


# ─── adm_summary / log ────────────────────────────────────────────────────────

@lru_cache(maxsize=512)
def get_adm_summary(experiment: str, cfg_dir: str, case_ref: str, run_id: int) -> list:
    case_dir = _OUTPUTS / experiment / cfg_dir / case_ref
    inner = _inner_path(case_dir, run_id, cfg_dir)
    if inner is None:
        return []
    fp = inner / "adm_summary.json"
    if not fp.exists():
        return []
    try:
        with open(fp) as fh:
            return json.load(fh)
    except Exception:
        return []


@lru_cache(maxsize=512)
def get_log(experiment: str, cfg_dir: str, case_ref: str, run_id: int) -> list:
    case_dir = _OUTPUTS / experiment / cfg_dir / case_ref
    inner = _inner_path(case_dir, run_id, cfg_dir)
    if inner is None:
        return []
    fp = inner / "log.json"
    if not fp.exists():
        return []
    try:
        with open(fp) as fh:
            return json.load(fh)
    except Exception:
        return []


# ─── case text ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=256)
def get_case_text(case_ref: str, field: str) -> str:
    """
    field: 'claims' | 'CPA' | 'appeal'
    Returns the file content as a string, or empty string if not found.
    """
    mapping = {"claims": "claims.txt", "CPA": "CPA.txt", "appeal": "appeal.txt"}
    fname = mapping.get(field, field)
    fp = _DATA / "TEST" / case_ref / fname
    if fp.exists():
        return fp.read_text(errors="replace")
    return ""


def get_available_fields(case_ref: str) -> list[str]:
    """Return which text files are available for this case."""
    fields = []
    for field in ("claims", "CPA", "appeal"):
        mapping = {"claims": "claims.txt", "CPA": "CPA.txt", "appeal": "appeal.txt"}
        fp = _DATA / "TEST" / case_ref / mapping[field]
        if fp.exists():
            fields.append(field)
    return fields


# Config-number → which document fields were injected into the prompt.
# Mirrors _load_context() in batched_hybrid_system.py exactly:
#   config 1 → appeal only
#   config 2 → claims + CPA
#   config 3 → appeal + claims + CPA  (also baseline_default uses cfg3)
_CONFIG_FIELDS: dict[int, list[str]] = {
    1: ["appeal"],
    2: ["claims", "CPA"],
    3: ["appeal", "claims", "CPA"],
}


def get_fields_for_config(cfg_dir: str, case_ref: str) -> list[str]:
    """
    Return the document fields that were actually injected for this config,
    filtered to only those that physically exist for the case.
    Mirrors _load_context() in batched_hybrid_system.py:
      cfg1 → appeal only
      cfg2 → claims + CPA
      cfg3 → appeal + claims + CPA
    Baseline configs (no cfgN suffix) use cfg3 (all docs).
    """
    m = _CFG_RE.search(cfg_dir)
    num = int(m.group(1)) if m else 3   # baseline has no suffix → cfg3 = all docs
    allowed = _CONFIG_FIELDS.get(num, list(_CONFIG_FIELDS[3]))
    available = get_available_fields(case_ref)
    order = ["appeal", "claims", "CPA"]
    return [f for f in order if f in allowed and f in available]


# ─── dashboard aggregate ─────────────────────────────────────────────────────

def get_all_verdicts() -> dict:
    """
    Return nested dict:
      {experiment: {cfg_dir: {run_key: {case_ref: verdict}}}}
    Used by the dashboard page.
    """
    result = {}
    for exp in get_experiments():
        result[exp] = {}
        for cfg in get_configs(exp):
            result[exp][cfg] = get_verdict_map(exp, cfg)
    return result


def compute_accuracy(experiment: str, cfg_dir: str, run_id: int = 1) -> dict:
    """
    Compare verdict map for a run against ground truth.
    Returns {"accuracy": float, "n": int, "correct": int, "verdicts": {case: verdict}}
    """
    gt = get_ground_truth()
    vm = get_verdict_map(experiment, cfg_dir)
    run_key = f"run_{run_id}"
    verdicts = vm.get(run_key, {})

    n = 0
    correct = 0
    for case, pred in verdicts.items():
        truth = gt.get(case)
        if truth is None:
            continue
        n += 1
        if str(pred).strip().lower() == str(truth).strip().lower():
            correct += 1

    return {
        "accuracy": correct / n if n > 0 else 0.0,
        "correct": correct,
        "n": n,
        "verdicts": verdicts,
    }


def get_log_by_node(log: list, node_question: str) -> list[dict]:
    """
    Find log turns whose question text contains the node's question text
    (or vice versa). Returns matching turns.
    """
    if not node_question:
        return []
    q_lower = node_question.lower().strip()[:80]  # first 80 chars for matching
    matches = []
    for turn in log:
        tq = turn.get("question", "").lower()
        if q_lower in tq or tq[:80] in q_lower:
            matches.append(turn)
    return matches
