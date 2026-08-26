# Outputs/ — Experiment results (canonical archives)

**This folder contains only `.tar.gz` archives — one self-contained archive per
(model, split, variant).** Loose/extracted result directories are never kept here: the analysis
notebooks read the archives directly, and keeping both caused confusion about which runs are
current. If you re-run experiments, **compress the output and drop the `.tar.gz` here** (see below).

## Naming convention

```
<MODEL>_<SPLIT>_<VARIANT>.tar.gz        top-level folder inside == filename stem (== notebook prefix)
```

- **MODEL** — `GPT` · `LLAMA` · `QWEN`
- **SPLIT** — `TRAIN` (95 cases) · `TEST` (879 held-out cases)
- **VARIANT**
  - TEST: `BASE` (`adm_initial=False`) · `INIT` (`adm_initial=True`) · `FT` (ADM-trace SFT weights) ·
    `FTBASE` (plain-prompt SFT weights)
  - TRAIN: `TOOL` (tool mode, `adm_initial=False`, all question sets) · `TOOL_INIT` (tool, `adm_initial=True`,
    default questions) · `ORACLE` (train/oracle mode, `adm_initial=False`, all question sets) ·
    `ORACLE_INIT` (oracle, `adm_initial=True`, default)

Each archive is **self-contained** — every `(mode, config, run)` aggregate is complete inside its
own tar. (The old split/patch archives `GPT_TEST_2`, `RECONSTRUCTED`, and the `_02_05`/`_03_05`
date-suffixed tars were folded in and removed on 2026-08-13.) Inside each archive the tree is
`<experiment>/results_*.json` (+ per-case `log.json`), where the experiment folder is
`<mode>_<adm_config>_<questions>[_cfgN]`.

## Canonical archives

### TRAIN set (95 cases) — always data-config 3 (full context)
| Archive | Model | Mode | `adm_initial` | Question sets |
|---------|-------|------|:---:|---|
| `GPT_TRAIN_TOOL.tar.gz` | GPT | tool + baseline | False | default/lenient/strict |
| `GPT_TRAIN_TOOL_INIT.tar.gz` | GPT | tool | True | default |
| `GPT_TRAIN_ORACLE.tar.gz` | GPT | train (oracle) + train_baseline | False | default/lenient/strict |
| `GPT_TRAIN_ORACLE_INIT.tar.gz` | GPT | train | True | default |
| `LLAMA_TRAIN_TOOL.tar.gz` | Llama | tool + baseline | False | default/lenient/strict |
| `LLAMA_TRAIN_TOOL_INIT.tar.gz` | Llama | tool | True | default |
| `LLAMA_TRAIN_ORACLE.tar.gz` | Llama | train + train_baseline | False | default/lenient/strict |
| `LLAMA_TRAIN_ORACLE_INIT.tar.gz` | Llama | train | True | default |
| `QWEN_TRAIN_TOOL.tar.gz` | Qwen | tool + baseline | False | default/lenient/strict |
| `QWEN_TRAIN_TOOL_INIT.tar.gz` | Qwen | tool | True | default |
| `QWEN_TRAIN_ORACLE.tar.gz` | Qwen | train + train_baseline | False | default/lenient/strict |
| `QWEN_TRAIN_ORACLE_INIT.tar.gz` | Qwen | train | True | default |

`tool`/`train` cover the 4 ADM configs (`both`/`none`/`sub_adm_1`/`sub_adm_2`); `_INIT`/`ORACLE` are
1 run each, the rest 3 runs. (`GPT_TRAIN_TOOL_INIT` carries one empty `tool/none/default` init
aggregate — a real gap in GPT's init grid, preserved as-is.)

### TEST set (879 cases) — config 1/2/3 = appeal · claims+CPA · full, `adm_config=both`, default Qs, 3 runs
| Archive | Variant | Model / weights | Coverage |
|---------|---------|-----------------|----------|
| `GPT_TEST_BASE.tar.gz` | GPT | gpt-oss-120b | baseline + tool, cfg1–3, 3 runs |
| `LLAMA_TEST_BASE.tar.gz` | Llama | Llama-3.3-70B | baseline + tool, cfg1–3, 3 runs |
| `QWEN_TEST_BASE.tar.gz` | Qwen | Qwen-3-80B (base) | baseline + tool, cfg1–3, 3 runs |
| `QWEN_TEST_INIT.tar.gz` | Qwen-init | base, `adm_initial=True` | tool cfg1–3, 3 runs |
| `QWEN_TEST_FT.tar.gz` | Qwen-FT | `qwen_adm_merged` (ADM SFT) | baseline + tool cfg1–3, 3 runs |
| `QWEN_TEST_FTBASE.tar.gz` | Qwen-FT-baseline | `qwen_baseline_merged` (prompt SFT) | baseline + tool cfg1–3, 3 runs |

The exact archive→variant mapping is encoded in the `ARCHIVES` (TRAIN) / `TEST_ARCHIVES` (TEST)
catalogues in [`../Analysis/llm_results.ipynb`](../Analysis/llm_results.ipynb) — the canonical
analysis notebook. If you add or rename an archive, update that catalogue.

## Archive status (2026-08-17)

All **18 archives** are complete and verified. No pending runs. The canonical set:

| Archives | Count |
|----------|-------|
| TRAIN (GPT/LLAMA/QWEN × TOOL/TOOL_INIT/ORACLE/ORACLE_INIT) | 12 |
| TEST (GPT/LLAMA/QWEN_BASE/QWEN_INIT/QWEN_FT/QWEN_FTBASE) | 6 |
| **Total** | **18** |

## How to compress a new run

Runs are produced as a directory (e.g. `MY_RUN/tool_both_default/results_*.json`). Archive it with
the run-group name as the top-level member (== filename stem == the prefix the notebooks filter on):

```bash
tar czf Outputs/GPT_TEST_BASE.tar.gz -C /path/to/run_parent GPT_TEST_BASE
rm -rf /path/to/run_parent/GPT_TEST_BASE        # keep Outputs/ tar-only
```

To **merge new runs into an existing archive** (top-up), extract it, add/merge the new
`results_*.json` (union the `run_*` keys) and per-case logs under the same top folder, then re-tar
under the same name. Keep the filename stem == internal top folder == catalogue `prefix`.

Then add/confirm a `dict(..., type='tar', path=.../'NAME.tar.gz', prefix='NAME')` entry in the
notebook catalogue.

