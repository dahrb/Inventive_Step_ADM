"""
Build SFT (Supervised Fine-Tuning) dataset from QWEN_TRAIN_MODE logs.

Format: per-factor
------------------
Each individual question→answer turn becomes its own training example:
  [system: case context]  [user: factor question]  [assistant: {answer, reasoning}]

This gives ~2900 short examples (~400-600 tokens each) from 93 GT-correct cases,
matching the inference-time distribution (model answers one question at a time).

Filtering
---------
- Only cases from `train_both_default`.
- Only cases where the model's FINAL_VERDICT matched the ground truth.
- Train/val split is done at the CASE level (not turn level) to avoid leakage:
    70 cases → train  (~2000 turns)
    23 cases → val    (~600 turns)

Output
------
  Data/sft_train.jsonl
  Data/sft_val.jsonl
  Data/sft_dataset_stats.json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

# ── GT stripping ──────────────────────────────────────────────────────────────

_GT_SECTION_RE = re.compile(
    r"=== REASONS FOR DECISION ===.*?=== END REASONS FOR DECISION ===\n*"
    r"|=== DECISION ===.*?=== END DECISION ===\n*",
    re.DOTALL,
)

_TRAIN_INSTRUCTIONS = (
    "INSTRUCTIONS:\n"
    "1. Provide a step-by-step reasoning trace with explicit reference to the case data as to why you gave your answer..\n"
    "2. Conclude with a final 'Yes' or 'No' answer, or the specific text requested.\n"
    "3. Do not refer to case law, patents or other specific inventions directly that you have not been provided with.\n"
    "4. You may make reasonable assumptions about the skilled person or common general knowledge.\n"
    "5. Follow the reasoning from the 'reasons for decision' as closely as possible when ascribing factors.\n"
    "6. You MUST try and follow the actual decision of the case as closely as possible.\n"
)

_TOOL_INSTRUCTIONS = (
    "INSTRUCTIONS:\n"
    "1. Provide a step-by-step reasoning trace with explicit reference to the case data as to why you gave your answer.\n"
    "2. Conclude with a final 'Yes' or 'No' answer, or the specific text requested.\n"
    "3. Do not refer to case law, patents or other specific inventions directly that you have not been provided with.\n"
    "4. You may make reasonable assumptions about the skilled person or common general knowledge.\n"
    "5. Do not follow any conclusions in the case data blindly — critically assess all information.\n"
    "6. Ensure you remember that these questions are here to guide your reasoning, think about the case holistically as well when answering them."
)


def _strip_gt(text: str) -> str:
    cleaned = _GT_SECTION_RE.sub("", text)
    cleaned = cleaned.replace(_TRAIN_INSTRUCTIONS, _TOOL_INSTRUCTIONS)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


# ── Turn helpers ──────────────────────────────────────────────────────────────

def _get_final_verdict(turns: list) -> str | None:
    for t in reversed(turns):
        if t.get("source") == "final_verdict" or "FINAL_VERDICT" in str(t.get("question", "")):
            ans = str(t.get("answer", "")).strip().lower()
            if "yes" in ans:
                return "Yes"
            if "no" in ans:
                return "No"
    return None


def _is_valid_turn(turn: dict) -> bool:
    if turn.get("source") in ("final_verdict", "summary_event"):
        return False
    answer = str(turn.get("answer", "")).strip()
    if not answer or answer.upper() in ("ERROR", "PENDING"):
        return False
    if "FINAL_VERDICT" in str(turn.get("question", "")):
        return False
    return True


def _extract_system(turns: list) -> str | None:
    """Get the system prompt from the first turn that has one."""
    for t in turns:
        fp = t.get("full_prompt", [])
        if fp and fp[0].get("role") == "system":
            return _strip_gt(fp[0]["content"])
    return None


def turns_to_examples(case_name: str, turns: list) -> list[dict]:
    """Convert valid turns into per-factor training examples."""
    system = _extract_system(turns)
    if system is None:
        return []

    examples = []
    for t in turns:
        if not _is_valid_turn(t):
            continue

        question  = str(t.get("question", "")).strip()
        answer    = str(t.get("answer", "")).strip()
        reasoning = str(t.get("reasoning", "")).strip()

        if not question or not answer:
            continue

        examples.append({
            "case_name": case_name,
            "source": t.get("source", ""),
            "messages": [
                {"role": "system",    "content": system},
                {"role": "user",      "content": question},
                {"role": "assistant", "content": json.dumps(
                    {"answer": answer, "reasoning": reasoning},
                    ensure_ascii=False,
                )},
            ],
        })

    return examples


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs_root", type=str, default="Outputs/QWEN_TRAIN_MODE")
    parser.add_argument("--variant",   type=str, default="train_both_default")
    parser.add_argument("--gt_pkl",    type=str, default="Data/train_data_Inv_Step.pkl")
    parser.add_argument("--train_out", type=str, default="Data/sft_train.jsonl")
    parser.add_argument("--val_out",   type=str, default="Data/sft_val.jsonl")
    parser.add_argument("--stats_out", type=str, default="Data/sft_dataset_stats.json")
    parser.add_argument("--n_train",   type=int, default=70,
                        help="Number of CASES for training (turns from these cases go to train).")
    parser.add_argument("--n_val",     type=int, default=25,
                        help="Number of CASES for validation.")
    parser.add_argument("--min_turns", type=int, default=5,
                        help="Skip cases with fewer than this many valid turns.")
    args = parser.parse_args()

    # ── Ground truth ──────────────────────────────────────────────────────────
    df = pd.read_pickle(args.gt_pkl)
    gt_map = {
        row["Reference"]: ("Yes" if row["Outcome"] == "Reversed" else "No")
        for _, row in df.iterrows()
    }
    print(f"GT loaded: {len(gt_map)} cases")

    # ── Scan logs ─────────────────────────────────────────────────────────────
    log_root = Path(args.logs_root) / args.variant
    if not log_root.exists():
        print(f"ERROR: {log_root} does not exist", file=sys.stderr)
        sys.exit(1)

    log_files = sorted(log_root.glob("*/run_1/config_3/train/*/False/log.json"))
    print(f"Found {len(log_files)} log files")

    correct_cases = []   # list of (case_name, examples_list)
    skipped = []

    for log_path in log_files:
        case_name = log_path.parts[len(log_root.parts)]
        gt = gt_map.get(case_name)
        if gt is None:
            skipped.append({"case": case_name, "reason": "no_gt"})
            continue

        try:
            with open(log_path) as f:
                turns = json.load(f)
        except Exception as e:
            skipped.append({"case": case_name, "reason": f"read_error:{e}"})
            continue

        verdict = _get_final_verdict(turns)
        if verdict is None:
            skipped.append({"case": case_name, "reason": "no_verdict"})
            continue
        if verdict != gt:
            print(f"  SKIP {case_name}: model={verdict} GT={gt} (wrong)")
            skipped.append({"case": case_name, "reason": f"wrong_verdict:model={verdict},gt={gt}"})
            continue

        examples = turns_to_examples(case_name, turns)
        if len(examples) < args.min_turns:
            skipped.append({"case": case_name, "reason": f"too_few_turns:{len(examples)}"})
            continue

        print(f"  OK   {case_name}: GT={gt} {len(examples)} turns")
        correct_cases.append((case_name, examples))

    print(f"\n{len(correct_cases)} GT-correct cases, {len(skipped)} skipped")

    # ── Case-level split (sorted for reproducibility) ─────────────────────────
    correct_cases.sort(key=lambda x: x[0])

    total_needed = args.n_train + args.n_val
    if len(correct_cases) < total_needed:
        print(f"WARNING: only {len(correct_cases)} cases, adjusting split proportionally.")
        frac = len(correct_cases) / total_needed
        n_train = int(args.n_train * frac)
        n_val   = len(correct_cases) - n_train
    else:
        n_train = args.n_train
        n_val   = args.n_val

    train_cases = correct_cases[:n_train]
    val_cases   = correct_cases[n_train:n_train + n_val]

    train_examples = [ex for _, exs in train_cases for ex in exs]
    val_examples   = [ex for _, exs in val_cases   for ex in exs]

    # ── Write ─────────────────────────────────────────────────────────────────
    for path, examples, label in [
        (args.train_out, train_examples, "Train"),
        (args.val_out,   val_examples,   "Val"),
    ]:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    # ── Stats ─────────────────────────────────────────────────────────────────
    def _stats(cases, examples):
        tok = [sum(len(str(m["content"])) for m in ex["messages"]) // 4
               for ex in examples]
        src = {}
        for ex in examples:
            src[ex.get("source","?")] = src.get(ex.get("source","?"), 0) + 1
        return {
            "n_cases":  len(cases),
            "n_turns":  len(examples),
            "cases":    [c for c, _ in cases],
            "sources":  src,
            "est_tokens_mean":  round(sum(tok)/len(tok), 0) if tok else 0,
            "est_tokens_total": sum(tok),
        }

    stats = {
        "variant": args.variant,
        "format": "per_factor",
        "total_gt_correct_cases": len(correct_cases),
        "train": _stats(train_cases, train_examples),
        "val":   _stats(val_cases,   val_examples),
        "skipped_n": len(skipped),
        "skipped": skipped,
    }
    with open(args.stats_out, "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\nTrain: {len(train_cases)} cases → {len(train_examples)} turn examples  ({stats['train']['est_tokens_total']} est tokens)")
    print(f"Val:   {len(val_cases)} cases → {len(val_examples)} turn examples  ({stats['val']['est_tokens_total']} est tokens)")
    print(f"Stats  → {args.stats_out}")
    print(f"Train  → {args.train_out}")
    print(f"Val    → {args.val_out}")


if __name__ == "__main__":
    main()
