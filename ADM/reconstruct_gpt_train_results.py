#!/usr/bin/env python3
"""
reconstruct_gpt_train_results.py
─────────────────────────────────
Rebuilds results_*.json files from per-case log.json files on disk.
Used when the job hung before writing the final results file, but
individual case logs were saved successfully.

Usage:
    python reconstruct_gpt_train_results.py

Writes / merges into:
    tool_sub1_default/results_main_tool_config3_sub_adm_1_True.json  (runs 1,2,3)
    tool_sub2_default/results_main_tool_config3_sub_adm_2_True.json  (runs 1,2 only)
"""

import json
import os
from pathlib import Path

OUT_BASE = Path("/users/sgdbareh/scratch/ADM_JURIX/Outputs/GPT_TRAIN_DEFAULT")

EXPERIMENTS = [
    {
        "exp_dir":    "tool_sub1_default",
        "results_fn": "results_main_tool_config3_sub_adm_1_True.json",
        "config":     "3",
        "mode":       "tool",
        "adm_config": "sub_adm_1",
        "adm_initial":"True",
        "runs":       [1, 2, 3],
    },
    {
        "exp_dir":    "tool_sub2_default",
        "results_fn": "results_main_tool_config3_sub_adm_2_True.json",
        "config":     "3",
        "mode":       "tool",
        "adm_config": "sub_adm_2",
        "adm_initial":"True",
        "runs":       [1, 2],          # run_3 still missing — will be run separately
    },
]

def read_verdict(log_path: Path) -> str | None:
    """Extract verdict from a per-case log.json.

    Two formats observed:
      - dict  : data["verdict"] or data["final_verdict"]
      - list  : list of turn-dicts; entry with question=="FINAL_VERDICT" holds answer
    """
    try:
        data = json.loads(log_path.read_text())
        if isinstance(data, dict):
            for key in ("verdict", "final_verdict", "outcome"):
                if key in data:
                    return data[key]
        elif isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict) and entry.get("question") == "FINAL_VERDICT":
                    return entry.get("answer")
    except Exception as e:
        print(f"  WARN: could not read {log_path}: {e}")
    return None

def reconstruct(exp: dict):
    exp_dir     = OUT_BASE / exp["exp_dir"]
    results_fn  = exp_dir / exp["results_fn"]
    adm_config  = exp["adm_config"]
    adm_initial = exp["adm_initial"]
    config      = exp["config"]

    # Load existing results file if present (may already have some runs)
    if results_fn.exists():
        existing = json.loads(results_fn.read_text())
        print(f"{exp['exp_dir']}: loaded existing results ({list(existing.keys())})")
    else:
        existing = {}

    case_dirs = sorted(
        d for d in exp_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    print(f"{exp['exp_dir']}: found {len(case_dirs)} case directories")

    changed = False
    for run_num in exp["runs"]:
        run_key = f"run_{run_num}"
        if run_key in existing:
            n = len(existing[run_key])
            print(f"  {run_key}: already present ({n} cases) — skipping")
            continue

        run_results = {}
        missing = 0
        for case_dir in case_dirs:
            # log path: <case>/<run_N>/config_<C>/tool/<adm_config>/<adm_initial>/log.json
            log_path = (case_dir / f"run_{run_num}" / f"config_{config}"
                        / "tool" / adm_config / adm_initial / "log.json")
            if not log_path.exists():
                missing += 1
                continue
            verdict = read_verdict(log_path)
            if verdict is not None:
                run_results[case_dir.name] = verdict
            else:
                # fall back: store the raw log contents
                try:
                    run_results[case_dir.name] = json.loads(log_path.read_text())
                except Exception:
                    missing += 1

        print(f"  {run_key}: reconstructed {len(run_results)} cases  (missing logs: {missing})")
        if run_results:
            existing[run_key] = run_results
            changed = True

    if changed:
        results_fn.write_text(json.dumps(existing, indent=4))
        print(f"  → written to {results_fn}")
    else:
        print(f"  → no changes needed")

if __name__ == "__main__":
    for exp in EXPERIMENTS:
        print(f"\n{'='*60}")
        print(f"Reconstructing: {exp['exp_dir']}")
        print(f"{'='*60}")
        reconstruct(exp)
    print("\nDone.")
