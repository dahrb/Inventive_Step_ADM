# Outputs/ — Experiment results (canonical archives)

**This folder contains only `.tar.gz` archives — one per run-group.** Loose/extracted result
directories are never kept here: the analysis notebooks read the archives directly, and keeping
both caused confusion about which runs are current. If you re-run experiments, **compress the
output and drop the `.tar.gz` here** (see below).

## Canonical archives

Each archive holds a tree of `<experiment>/results_*.json` (+ per-case logs), where an
experiment folder is `<mode>_<adm_config>_<questions>[_cfgN]`.

### TRAIN set (95 cases)
| Archive | Model | Mode | `adm_initial` |
|---------|-------|------|:---:|
| `GPT_TRAIN.tar.gz` | GPT | tool + baseline | False |
| `GPT_TRAIN_MODE.tar.gz` | GPT | train (oracle) | False |
| `GPT_TRAIN_DEFAULT.tar.gz` | GPT | tool | True |
| `GPT_TRAIN_MODE_DEFAULT.tar.gz` | GPT | train | True |
| `LLAMA_TRAIN.tar.gz` | Llama | tool + baseline | False |
| `LLAMA_TRAIN_MODE.tar.gz` | Llama | train | False |
| `LLAMA_TRAIN_02_05.tar.gz` | Llama | tool | True |
| `LLAMA_TRAIN_MODE_02_05.tar.gz` | Llama | train | True |
| `QWEN_TRAIN.tar.gz` | Qwen | tool + baseline | False |
| `QWEN_TRAIN_MODE.tar.gz` | Qwen | train | False |
| `QWEN_TRAIN_DEFAULT_02_05.tar.gz` | Qwen | tool | True |
| `QWEN_TRAIN_MODE_DEFAULT_02_05.tar.gz` | Qwen | train | True |

### TEST set (879 cases) — config 1/2/3 = appeal · claims+CPA · full
| Archive | Variant | Notes |
|---------|---------|-------|
| `GPT_TEST.tar.gz` | GPT | baseline (cfg1-3) + tool (cfg1-3) |
| `GPT_TEST_2.tar.gz` | GPT | supplementary GPT tool cfg3 run |
| `LLAMA_TEST_02_05.tar.gz` | Llama | tool cfg1-3, baseline cfg3 |
| `QWEN_TEST_02_05.tar.gz` | Qwen (base) | baseline + tool, cfg1-3 |
| `QWEN_TEST_INIT_03_05.tar.gz` | Qwen-init | tool cfg1-3, `adm_initial=True` |
| `QWEN_FINETUNED_TEST_03_05.tar.gz` | Qwen-FT | ADM-data fine-tune, baseline + tool |
| `RECONSTRUCTED.tar.gz` | GPT / Qwen-init / Llama | runs rebuilt from per-case logs (supplement the above) |

The exact archive→variant mapping is encoded in the `ARCHIVES` / `TEST_ARCHIVES` catalogues in
[`../Analysis/llm_results.ipynb`](../Analysis/llm_results.ipynb). If you add or rename an archive,
update that catalogue.

## Pending runs (to be added)

Runs queued to close known gaps — drop the compressed archive here when complete and add a
catalogue entry:
- **`QWEN_BASELINE_FT_TEST*.tar.gz`** — prompt-data fine-tuned Qwen, full test grid (18 runs).
- Llama `baseline` cfg1 & cfg2 (currently only cfg3).
- GPT `tool` cfg3 (+1 run), Qwen-FT `tool` cfg3 (+2 runs).

## How to compress a new run

Runs are produced as a directory (e.g. `MY_RUN/tool_both_default/results_*.json`). Archive it
with the run-group name as the top-level member (the notebooks filter tar members by this prefix):

```bash
tar czf Outputs/MY_RUN.tar.gz -C /path/to/run_parent MY_RUN
rm -rf /path/to/run_parent/MY_RUN        # keep Outputs/ tar-only
```

Then add a `dict(..., type='tar', path=.../'MY_RUN.tar.gz', prefix='MY_RUN')` entry to the
notebook catalogue.

## Backup

A full snapshot of the pre-pruning Outputs (extracted dirs + logs included) is kept **outside the
repo** at `/mnt/scratch/users/sgdbareh/Outputs_backup_<date>.tar.gz`.
