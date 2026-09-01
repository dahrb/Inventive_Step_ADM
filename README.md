# ADM-JURIX — Inventive-Step ADM + LLMs

Can a structured legal-reasoning model guide an LLM to reproduce patent "inventive step"
decisions? This repo builds an **Abstract Dialectical Model (ADM)** of the EPO Problem–Solution
approach to Article 56 EPC and uses it to drive LLMs (GPT-OSS-120B, Llama-3.3-70B,
Qwen3-Next-80B, and a QLoRA-fine-tuned Qwen) over EPO Board-of-Appeal decisions.

- **Ground truth:** appeal outcome — `Reversed → Yes` (inventive step present), `Affirmed → No`.
- **Datasets:** 95 TRAIN decisions (53 Yes / 42 No) · 879 held-out TEST decisions (448 / 431).
- **ADM design:** see the two specs in [`Docs/`](Docs/).

## The model at a glance

![Compact map of the Inventive-Step ADM, its preconditions, and the two sub-ADMs](Analysis/adm_viz/00_compact_map.png)

The full decision model: the **Preconditions** ADM gates the main **Inventive Step** ADM, which
loops over each distinguishing feature and objective technical problem by instantiating
**Sub-ADM 1** and **Sub-ADM 2** (dashed purple = instantiate/result loop). Nodes are coloured by
role — issues, abstract factors, and base-level factors — and green/red edges denote
supporting/negating conditions. Regenerate with the last cell of
[`Analysis/ADM_viz.ipynb`](Analysis/ADM_viz.ipynb) (vector source:
[`00_compact_map.svg`](Analysis/adm_viz/00_compact_map.svg)).

## Repository layout

| Folder | Contents |
|--------|----------|
| [`ADM/`](ADM/) | Core ADM engine, traversal, the batched LLM runner, fine-tuning, questions. |
| [`Data/`](Data/) | Ground-truth datasets, case corpora, dataset-build scripts, CPC schema. |
| [`Analysis/`](Analysis/) | Results notebooks + ADM visualisation notebook. |
| [`Outputs/`](Outputs/) | **Canonical experiment results, one `.tar.gz` per run-group.** |
| [`LLM_Models/`](LLM_Models/) | LoRA-merge scripts; local model store (`models/`, git-ignored). |
| [`Docs/`](Docs/) | ADM specification + inference-rules documents (PDF). |
| [`Tests/`](Tests/) | Unit tests for the ADM engine (CI runs these). |
| [`Figs/`](Figs/) | **All generated figures land here** (git-ignored). |
| [`webapp/`](webapp/) | Streamlit explorer/dashboard (optional, self-contained). |
| `scripts/` | All SLURM launch/run `.sh` scripts (git-ignored — see below). |
| `requirements/` | Fully-pinned freezes of both environments. |

## Environments (uv only)

`uv` is the sole environment manager. Two environments are needed because the GPT-OSS server
requires a vLLM/torch combination that conflicts with everything else:

| Env | Purpose | vLLM / torch | Recreate |
|-----|---------|--------------|----------|
| **`.venv`** (primary, ~90% of code) | ADM engine, training, Llama/Qwen serving, analysis | 0.19 / 2.10+cu128 | `uv sync` |
| **`.venv_11_2`** (secondary) | GPT-OSS-120B vLLM server only | 0.11.2 / 2.9 | `uv venv .venv_11_2 --python 3.12` then `uv pip sync --python .venv_11_2 requirements/vllm-0.11.2.txt` |

Source of truth for the primary env: `pyproject.toml` + `uv.lock`. Fully-pinned snapshots of
**both** envs are in `requirements/` for exact rebuilds. Python 3.12 for both.

```bash
uv sync --group dev          # primary env + pre-commit/ruff
uv run pre-commit install    # enable hooks (notebooks are left intact)
```

## Reproducing the results — end to end

1. **Data.** Ground truth is `Data/train_data_Inv_Step.pkl` / `Data/test_data_Inv_Step.pkl`
   (see [`Data/README.md`](Data/README.md)).
2. **Serve a model** (SLURM, H100) from `scripts/servers/` — distinct ports so co-located jobs
   don't collide: Llama `8000`, GPT-OSS `8001`, Qwen prompt-FT `8002`, Qwen ADM-FT `8003`.
   Base Qwen/Llama use `.venv`; GPT-OSS uses `.venv_11_2`.
   ```bash
   sbatch scripts/servers/start_llama_server.sh
   squeue -u "$USER"                    # note the NODE it lands on
   ```
3. **Run the ADM harness** against the server (one experiment = mode × ADM-config × question-set):
   ```bash
   python ADM/batched_hybrid_system.py --model llama --port 8000 --gpu <node> \
          --mode tool --adm_config both --questions_file ADM/questions.json ...
   ```
   Batch launchers for the full grid live in `scripts/slurm/`.
4. **Compress the run output** into `Outputs/` as a `.tar.gz` (results are analysed from the
   archives, never loose dirs — see [`Outputs/README.md`](Outputs/README.md) for the exact
   command and naming convention).
5. **Analyse** in [`Analysis/llm_results.ipynb`](Analysis/llm_results.ipynb) (test set, final
   results) and `llm_train_results.ipynb` (train-set diagnostics). The notebooks read the
   `Outputs/*.tar.gz` catalogue directly.

## Headline findings (see `Analysis/` for full tables)



## Conventions

- **Figures:** any code that writes `.png/.svg` routes to `Figs/` (via `FIGS_DIR`); override with
  the `FIGS_DIR` env var.
- **Scripts:** all `.sh` live under `scripts/` and are **git-ignored** (cluster-specific paths).
  Copy/adapt rather than assuming they run unmodified elsewhere.
- **Secrets:** `api_key.key` (LLM API key) is git-ignored — never commit it.
