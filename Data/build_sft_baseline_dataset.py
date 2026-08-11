"""
Build SFT dataset from QWEN_TRAIN_MODE baseline logs.

Format: single-turn
--------------------
Each case×run becomes one training example:
  [user: full case context + inventive step assessment prompt]
  [assistant: {"answer": "Yes"/"No", "reasoning": "..."}]

The prompt is stripped of ground-truth sections (REASONS FOR DECISION,
DECISION) and train-mode instructions are replaced with tool-mode ones,
matching inference-time distribution.

Filtering
---------
- Only the `baseline_default` variant.
- All 3 runs used; a (case, run) pair is included only if the model's
  FINAL_VERDICT for that run matched the ground truth.
- Train/val split is done at the CASE level to avoid leakage:
    cases where ≥1 run is correct → eligible
    sorted by case name for reproducibility
    first n_train cases → train  (all correct runs from those cases)
    next  n_val   cases → val    (all correct runs from those cases)

Output
------
  Data/sft_baseline_train.jsonl
  Data/sft_baseline_val.jsonl
  Data/sft_baseline_dataset_stats.json

Logs source
-----------
  The script reads directly from a .tar.gz archive (default:
  Outputs/QWEN_TRAIN_MODE.tar.gz) OR from an extracted directory,
  auto-detecting which is available.
"""

import argparse
import io
import json
import os
import re
import sys
import tarfile
from pathlib import Path

import pandas as pd

# ── GT stripping (identical to build_sft_dataset.py) ─────────────────────────

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


# ── Log helpers ───────────────────────────────────────────────────────────────

def _parse_verdict(raw: str) -> str | None:
    s = str(raw).strip().lower()
    if "yes" in s:
        return "Yes"
    if "no" in s:
        return "No"
    return None


def _get_verdict_from_turns(turns: list) -> str | None:
    """Extract final verdict from a list of turns (multi-turn format)."""
    for t in reversed(turns):
        if t.get("source") == "final_verdict" or "FINAL_VERDICT" in str(t.get("question", "")):
            return _parse_verdict(t.get("answer", ""))
    return None


def _get_verdict_from_turn(turn: dict) -> str | None:
    """Extract verdict from a single baseline turn."""
    return _parse_verdict(turn.get("answer", ""))


def log_to_example(case_name: str, run_num: int, turns: list) -> dict | None:
    """
    Convert a baseline log (list of turns) into a single training example.
    Returns None if the log is malformed.

    Baseline logs have exactly 1 turn with source='baseline'.
    The full prompt is a single 'user' message (no system role).
    """
    if not turns:
        return None

    # Find the baseline turn
    baseline_turns = [t for t in turns if t.get("source") == "baseline"]
    if not baseline_turns:
        # Fall back to first turn
        baseline_turns = turns[:1]

    turn = baseline_turns[-1]  # use last if somehow multiple

    fp = turn.get("full_prompt", [])
    if not fp:
        return None

    # Build user message — strip GT from whichever role holds the prompt
    # Baseline has no system role; full context is in the user message
    user_content = None
    for msg in fp:
        if msg.get("role") in ("user", "system"):
            user_content = _strip_gt(msg["content"])
            break

    if not user_content:
        return None

    answer    = str(turn.get("answer", "")).strip()
    reasoning = str(turn.get("reasoning", "")).strip()

    if not answer or answer.upper() in ("ERROR", "PENDING"):
        return None

    return {
        "case_name": case_name,
        "run":       run_num,
        "messages": [
            {"role": "user",      "content": user_content},
            {"role": "assistant", "content": json.dumps(
                {"answer": answer, "reasoning": reasoning},
                ensure_ascii=False,
            )},
        ],
    }


# ── Archive / directory reader ────────────────────────────────────────────────

class LogReader:
    """Reads log.json files from either an extracted dir or a .tar.gz archive."""

    def __init__(self, logs_root: str, variant: str):
        self.variant = variant
        extracted = Path(logs_root) / variant
        archive   = Path(logs_root).parent / (Path(logs_root).name + ".tar.gz")
        # Also check if logs_root itself ends in .tar.gz
        if str(logs_root).endswith(".tar.gz"):
            archive = Path(logs_root)
            extracted = None
        else:
            extracted = Path(logs_root) / variant

        if extracted and extracted.exists():
            self.mode = "dir"
            self.root = extracted
            print(f"Reading from directory: {extracted}")
        elif archive.exists():
            self.mode = "tar"
            self.archive_path = str(archive)
            self.prefix = f"{Path(logs_root).name}/{variant}/"
            print(f"Reading from archive: {archive}  (prefix={self.prefix})")
        else:
            raise FileNotFoundError(
                f"Neither {extracted} nor {archive} found."
            )

    def iter_logs(self, runs: list[int]):
        """
        Yields (case_name, run_num, turns_list) for every log.json found.
        Path pattern: <case>/run_<N>/config_3/baseline/log.json
        """
        if self.mode == "dir":
            yield from self._iter_dir(runs)
        else:
            yield from self._iter_tar(runs)

    def _iter_dir(self, runs):
        for case_dir in sorted(self.root.iterdir()):
            if not case_dir.is_dir() or case_dir.name.startswith("."):
                continue
            case_name = case_dir.name
            for run_num in runs:
                log_path = case_dir / f"run_{run_num}" / "config_3" / "baseline" / "log.json"
                if not log_path.exists():
                    continue
                try:
                    turns = json.loads(log_path.read_text())
                    if isinstance(turns, dict):
                        turns = [turns]
                    yield case_name, run_num, turns
                except Exception as e:
                    print(f"  WARN: could not read {log_path}: {e}")

    def _iter_tar(self, runs):
        with tarfile.open(self.archive_path, "r:gz") as tf:
            members = {m.name: m for m in tf.getmembers() if m.isfile()}
        with tarfile.open(self.archive_path, "r:gz") as tf:
            for run_num in runs:
                pattern = re.compile(
                    rf"^{re.escape(self.prefix)}([^/]+)/run_{run_num}/config_3/baseline/log\.json$"
                )
                for name, member in sorted(members.items()):
                    m = pattern.match(name)
                    if not m:
                        continue
                    case_name = m.group(1)
                    try:
                        f = tf.extractfile(member)
                        if f is None:
                            continue
                        turns = json.loads(f.read().decode())
                        if isinstance(turns, dict):
                            turns = [turns]
                        yield case_name, run_num, turns
                    except Exception as e:
                        print(f"  WARN: could not read {name}: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs_root",  type=str, default="Outputs/QWEN_TRAIN_MODE",
                        help="Extracted dir OR base path (archive resolved as <logs_root>.tar.gz)")
    parser.add_argument("--variant",    type=str, default="baseline_default")
    parser.add_argument("--runs",       type=int, nargs="+", default=[1, 2, 3],
                        help="Run numbers to include")
    parser.add_argument("--gt_pkl",     type=str, default="Data/train_data_Inv_Step.pkl")
    parser.add_argument("--train_out",  type=str, default="Data/sft_baseline_train.jsonl")
    parser.add_argument("--val_out",    type=str, default="Data/sft_baseline_val.jsonl")
    parser.add_argument("--stats_out",  type=str, default="Data/sft_baseline_dataset_stats.json")
    parser.add_argument("--n_train",    type=int, default=70,
                        help="Number of cases for training split.")
    parser.add_argument("--n_val",      type=int, default=25,
                        help="Number of cases for validation split.")
    args = parser.parse_args()

    # ── Ground truth ──────────────────────────────────────────────────────────
    df = pd.read_pickle(args.gt_pkl)
    gt_map = {
        row["Reference"]: ("Yes" if row["Outcome"] == "Reversed" else "No")
        for _, row in df.iterrows()
    }
    print(f"GT loaded: {len(gt_map)} cases")

    # ── Scan logs ─────────────────────────────────────────────────────────────
    reader = LogReader(args.logs_root, args.variant)

    # case_name → list of correct examples across all runs
    case_examples: dict[str, list[dict]] = {}
    skipped = []

    for case_name, run_num, turns in reader.iter_logs(args.runs):
        gt = gt_map.get(case_name)
        if gt is None:
            skipped.append({"case": case_name, "run": run_num, "reason": "no_gt"})
            continue

        # Get model verdict for this run
        if len(turns) == 1 and turns[0].get("source") in ("baseline", "train_baseline", None):
            verdict = _get_verdict_from_turn(turns[0])
        else:
            verdict = _get_verdict_from_turns(turns)

        if verdict is None:
            skipped.append({"case": case_name, "run": run_num, "reason": "no_verdict"})
            continue

        if verdict != gt:
            print(f"  SKIP {case_name} run_{run_num}: model={verdict} GT={gt}")
            skipped.append({"case": case_name, "run": run_num,
                            "reason": f"wrong_verdict:model={verdict},gt={gt}"})
            continue

        example = log_to_example(case_name, run_num, turns)
        if example is None:
            skipped.append({"case": case_name, "run": run_num, "reason": "malformed_log"})
            continue

        print(f"  OK   {case_name} run_{run_num}: GT={gt}")
        case_examples.setdefault(case_name, []).append(example)

    eligible_cases = sorted(case_examples.keys())
    total_examples = sum(len(v) for v in case_examples.values())
    print(f"\n{len(eligible_cases)} cases with ≥1 correct run, "
          f"{total_examples} total correct examples, {len(skipped)} skipped")

    # ── Case-level train/val split ────────────────────────────────────────────
    total_needed = args.n_train + args.n_val
    if len(eligible_cases) < total_needed:
        print(f"WARNING: only {len(eligible_cases)} eligible cases, adjusting split.")
        frac    = len(eligible_cases) / total_needed
        n_train = int(args.n_train * frac)
        n_val   = len(eligible_cases) - n_train
    else:
        n_train = args.n_train
        n_val   = args.n_val

    train_cases = eligible_cases[:n_train]
    val_cases   = eligible_cases[n_train:n_train + n_val]

    train_examples = [ex for c in train_cases for ex in case_examples[c]]
    val_examples   = [ex for c in val_cases   for ex in case_examples[c]]

    # ── Write JSONL ───────────────────────────────────────────────────────────
    for path, examples, label in [
        (args.train_out, train_examples, "Train"),
        (args.val_out,   val_examples,   "Val"),
    ]:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        print(f"{label}: {len(examples)} examples → {path}")

    # ── Stats ─────────────────────────────────────────────────────────────────
    def _stats(cases, examples):
        tok = [sum(len(str(m["content"])) for m in ex["messages"]) // 4
               for ex in examples]
        run_counts = {}
        for ex in examples:
            r = str(ex.get("run", "?"))
            run_counts[r] = run_counts.get(r, 0) + 1
        return {
            "n_cases":          len(cases),
            "n_examples":       len(examples),
            "cases":            cases,
            "runs_included":    run_counts,
            "est_tokens_mean":  round(sum(tok) / len(tok), 0) if tok else 0,
            "est_tokens_total": sum(tok),
        }

    # per-case run breakdown for stats
    correct_runs_per_case = {c: [ex["run"] for ex in exs]
                             for c, exs in case_examples.items()}

    stats = {
        "variant":                   args.variant,
        "format":                    "single_turn",
        "runs_attempted":            args.runs,
        "total_eligible_cases":      len(eligible_cases),
        "total_correct_examples":    total_examples,
        "correct_runs_per_case":     correct_runs_per_case,
        "train":                     _stats(train_cases, train_examples),
        "val":                       _stats(val_cases,   val_examples),
        "skipped_n":                 len(skipped),
        "skipped":                   skipped,
    }

    with open(args.stats_out, "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\nTrain: {len(train_cases)} cases → {len(train_examples)} examples  "
          f"({stats['train']['est_tokens_total']} est tokens)")
    print(f"Val:   {len(val_cases)} cases → {len(val_examples)} examples  "
          f"({stats['val']['est_tokens_total']} est tokens)")
    print(f"Stats  → {args.stats_out}")


if __name__ == "__main__":
    main()
