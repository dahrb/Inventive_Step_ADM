# ADM-JURIX — Inventive-Step ADM + LLMs

Reproducing EPO Board-of-Appeal "inventive step" outcomes with an Abstract Dialectical
Model (ADM) that guides LLMs (GPT-OSS-120B, Llama-3.3-70B, Qwen3-Next-80B, and a
QLoRA-fine-tuned Qwen). See [Analysis/report.md](Analysis/report.md) for methodology,
experiment coverage, and results, and [Docs/](Docs/) for the ADM specification.

## Environments (uv only)

`uv` is the sole environment manager. There are **two** environments because the GPT-OSS
server needs a vLLM/torch combination that conflicts with everything else:

| Env | Purpose | vLLM / torch | How to recreate |
|-----|---------|--------------|-----------------|
| **`.venv`** (primary, ~90% of code) | ADM engine, training, Llama/Qwen serving, analysis | 0.19 / 2.10+cu128 | `uv sync` |
| **`.venv_11_2`** (secondary) | GPT-OSS-120B vLLM server only | 0.11.2 / 2.9 | `uv venv .venv_11_2 --python 3.12` then `uv pip sync --python .venv_11_2 requirements/vllm-0.11.2.txt` |

- Primary source of truth: `pyproject.toml` + `uv.lock`.
- Fully-pinned snapshots of **both** envs: `requirements/vllm-0.19.txt`, `requirements/vllm-0.11.2.txt`
  (exact rebuilds without a resolve; e.g. `uv pip sync --python .venv requirements/vllm-0.19.txt`).
- Python 3.12 for both.

## Dev tooling

```bash
uv sync --group dev            # installs pre-commit + ruff into .venv
uv run pre-commit install      # enable git hooks
uv run pre-commit run --all-files
```

Notebooks are deliberately **not** stripped by the hooks — the Analysis notebooks keep their
rendered results/figures.

## Serving models (SLURM, H100)

vLLM servers live in [LLM_Models/](LLM_Models/): `start_llama_server.sh` (`.venv`, port 8000),
`start_gptoss_server.sh` (`.venv_11_2`, port 8001), `start_baseline_server.sh` (Qwen prompt-FT,
port 8002), `start_adm_ft_server.sh` (Qwen ADM-FT, port 8003). Ports are distinct so co-located
jobs don't collide. Point the harness at a server with
`--model {gpt|llama|qwen} --port <port> --gpu <node>`.
