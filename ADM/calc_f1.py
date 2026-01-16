"""
Add a eval and test flag 
"""
import json
import numpy as np
from sklearn.metrics import f1_score, accuracy_score
import os
import glob
from datetime import datetime
import re

# Hard-coded ground truth for the comvik example
comvik = ['NO', 'NO', 'NO', 'YES', 'NO']
validation = ['NO','YES','YES','YES','NO','NO','NO','YES','YES','NO']
    
def _find_elapsed_in_obj(obj):
    """Recursively search obj (dict/list) for 'elapsed_seconds' values and return list."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == 'elapsed_seconds':
                try:
                    found.append(float(v))
                except Exception:
                    pass
            else:
                found.extend(_find_elapsed_in_obj(v))
    elif isinstance(obj, list):
        for el in obj:
            found.extend(_find_elapsed_in_obj(el))
    return found


def compute_avg_setup_time(results_filepath, runs=None, outputs_base=None):
    """Compute average experiment setup time (seconds) by scanning log.json
    files under Outputs/Eval_Cases for the case inferred from `results_filepath`.

    - Prefers `elapsed_seconds` in the log JSON. If missing, falls back to
      computing span from the earliest to latest `timestamp` entries in the file.
    - If `runs` is provided (list like ['run_1']), limits search to those run
      folders under each matching case.
    """
    if outputs_base is None:
        outputs_base = '/users/sgdbareh/scratch/ADM_JURIX/Outputs/Eval_Cases'

    fname = os.path.basename(results_filepath)
    root, _ext = os.path.splitext(fname)
    parts = root.split('_')
    parsed_case = None
    mode = None
    config_dir = None
    if len(parts) >= 2 and parts[0].startswith('results'):
        parsed_case = parts[1]
        if len(parts) >= 3:
            mode = parts[2]
        if len(parts) >= 4:
            cfg = parts[3]
            m = re.match(r'(config)[_-]?(\d+)', cfg)
            if m:
                config_dir = f"config_{m.group(2)}"
            else:
                config_dir = cfg

    # Choose which case folders to scan
    lower_fname = results_filepath.lower()
    if 'comvik' in lower_fname:
        case_pattern = os.path.join(outputs_base, 'comvik*')
    else:
        case_pattern = os.path.join(outputs_base, 'T*')

    case_dirs = sorted(glob.glob(case_pattern))
    if parsed_case:
        specific = os.path.join(outputs_base, parsed_case)
        if os.path.exists(specific):
            case_dirs = [specific]

    files = []
    for case_dir in case_dirs:
        if runs:
            for run_id in runs:
                if config_dir and mode:
                    candidate = os.path.join(case_dir, run_id, config_dir, mode, 'log.json')
                    if os.path.exists(candidate):
                        files.append(candidate)
                elif mode:
                    pattern = os.path.join(case_dir, run_id, '**', mode, 'log.json')
                    files.extend(glob.glob(pattern, recursive=True))
                else:
                    pattern = os.path.join(case_dir, run_id, '**', 'tool', 'log.json')
                    files.extend(glob.glob(pattern, recursive=True))
        else:
            if config_dir and mode:
                pattern = os.path.join(case_dir, '*/', config_dir, mode, 'log.json')
            elif mode:
                pattern = os.path.join(case_dir, '**', mode, 'log.json')
            else:
                pattern = os.path.join(case_dir, '**', 'tool', 'log.json')
            files.extend(glob.glob(pattern, recursive=True))

    durations = []
    for fpath in files:
        try:
            with open(fpath, 'r') as fh:
                j = json.load(fh)
        except Exception:
            continue

        # Prefer explicit elapsed_seconds
        elapsed_vals = _find_elapsed_in_obj(j)
        if elapsed_vals:
            try:
                durations.append(float(elapsed_vals[0]))
                continue
            except Exception:
                pass

        # Fallback to timestamp span
        timestamps = []
        if isinstance(j, list):
            for entry in j:
                if not isinstance(entry, dict):
                    continue
                ts = entry.get('timestamp')
                if not ts:
                    continue
                try:
                    dt = datetime.strptime(ts.strip(), '%Y-%m-%d %H:%M:%S')
                except Exception:
                    try:
                        dt = datetime.strptime(ts.strip()[:19], '%Y-%m-%d %H:%M:%S')
                    except Exception:
                        continue
                timestamps.append(dt)

        if len(timestamps) >= 2:
            duration = (max(timestamps) - min(timestamps)).total_seconds()
            if duration >= 0:
                durations.append(duration)

    if len(durations) == 0:
        return None, None, 0

    mean_sec = float(np.mean(durations))
    std_sec = float(np.std(durations))
    return mean_sec, std_sec, len(durations)


def process_results_file(results_filepath):
    """Load a results JSON, compute F1/accuracy per run (using the existing
    `comvik` ground truth mapping), and print metrics and setup-time summary.
    """
    with open(results_filepath, 'r') as f:
        predictions_data = json.load(f)

    f1_scores = []
    acc_scores = []

    print("File:", os.path.basename(results_filepath))
    print(f"{'Run ID':<10} | {'Accuracy':<10} | {'F1 Score':<10}")
    print("-" * 48)

    for run_id, preds_dict in predictions_data.items():
        sorted_keys = sorted(preds_dict.keys())
        y_pred = [preds_dict[key] for key in sorted_keys]
        # choose ground truth based on results filename
        fname = os.path.basename(results_filepath).lower()
        if 'comvik' in fname:
            gt = comvik
        else:
            gt = validation

        if len(y_pred) != len(gt):
            f1 = float('nan')
            acc = float('nan')
        else:
            try:
                f1 = f1_score(gt, y_pred, pos_label='YES')
                acc = accuracy_score(gt, y_pred)
            except Exception:
                f1 = float('nan')
                acc = float('nan')
        f1_scores.append(f1)
        acc_scores.append(acc)
        print(f"{run_id:<10} | {acc:.4f}     | {f1:.4f}")

    print("-" * 48)
    print("FINAL STATISTICS")
    print("-" * 48)
    if len(f1_scores) > 0:
        print(f"Mean Acc:     {np.nanmean(acc_scores)*100:.4f}")
        print(f"Acc Std Dev: {np.nanstd(acc_scores)*100:.6f}")
        print(f"Mean F1:      {np.nanmean(f1_scores)*100:.4f}")
        print(f"F1 Std Dev:  {np.nanstd(f1_scores)*100:.6f}")
    else:
        print("No runs found in results file.")

    # Compute avg setup time for runs present in this results file
    run_ids = list(predictions_data.keys()) if isinstance(predictions_data, dict) else None
    mean_sec, std_sec, count = compute_avg_setup_time(results_filepath, runs=run_ids)
    if count > 0:
        def format_seconds(s):
            s = int(round(s))
            hrs, rem = divmod(s, 3600)
            mins, secs = divmod(rem, 60)
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"

        print("-" * 48)
        print("Experiment setup time (based on log.json files)")
        print(f"Files considered: {count}")
        print(f"Mean duration: {mean_sec:.2f} seconds  ({format_seconds(mean_sec)})")
        print(f"Std dev: {std_sec:.2f} seconds  ({format_seconds(std_sec)})")
    else:
        print("-" * 48)
        print("No valid log.json files found to compute experiment setup time.")
    print("\n\n")


if __name__ == '__main__':
    results_pattern = '/users/sgdbareh/scratch/ADM_JURIX/Outputs/results_*.json'
    result_files = sorted(glob.glob(results_pattern))
    if not result_files:
        print('No results_*.json files found under Outputs/')
    for rf in result_files:
        process_results_file(rf)


