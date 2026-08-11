# ADM/ — Core engine, runner, fine-tuning

The ADM (Abstract Dialectical Model) of the EPO inventive-step / Problem–Solution assessment,
plus the harness that drives LLMs through it.

## Modules

| File | Role |
|------|------|
| `ADM_Construction.py` | ADM framework: `ADM`, `Node`, `SubADMNode`, `EvaluationNode`, `GatedBLF`, graph traversal, and the `visualise*` methods (figures → `Figs/`). |
| `inventive_step_ADM.py` | Builds the concrete inventive-step ADM: `adm_initial` (preconditions), `adm_main(sub_adm_1, sub_adm_2)`, `sub_adm_1` (reliable technical character), `sub_adm_2` (objective technical problem). Loads question sets. |
| `batched_hybrid_system.py` | Async runner: walks the ADM, asks each factor question of a served LLM (vLLM/OpenAI API), writes per-case logs, `adm_summary.json`, and `results_*.json`. |
| `UI.py` | CLI wrapper (`CLI`) for interactive single-case runs and ADM visualisation. |
| `finetune_qwen.py` | QLoRA fine-tuning of Qwen3-Next-80B on an SFT dataset. |
| `reconstruct_gpt_train_results.py` | Rebuilds `results_*.json` from per-case `log.json` when a job died before writing the aggregate. |
| `questions.json` / `lenient_questions.json` / `strict_questions.json` | Factor questions in three framings (`default` / `lenient` / `strict`). |

## Model / server mapping

`batched_hybrid_system.py` selects a model with `--model {gpt|llama|qwen}` (see the `MODELS`
dict). The value sent to vLLM is the model's `id` (e.g. `qwen` → `Qwen-3-80B`), so the served
model name must match — this is how fine-tuned Qwen checkpoints are swapped in transparently.

## Experiment axes

- **Mode:** `tool` (case data only) · `train` (case data **+** oracle decision reasoning) ·
  `baseline` (single-shot, no ADM).
- **ADM config:** `both` · `sub_adm_1` · `sub_adm_2` · `none`.
- **Question set:** `default` · `lenient` · `strict`.
- **`--adm_initial`:** precondition questions on/off (default runs use `False`).

Batch launchers for the full grid are in `scripts/slurm/`. Servers are in `scripts/servers/`.

## Tests

`Tests/test_ADM.py` covers this package (~90%). Run: `uv run --no-project python -m unittest test_ADM.py -v` from `Tests/`.
