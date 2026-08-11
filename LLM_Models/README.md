# LLM_Models/ — Local model store & LoRA merging

## Contents

| Item | Purpose |
|------|---------|
| `merge_lora.py` | Merge the ADM-data LoRA adapter (`qwen_lora_adm`) into the base model → `qwen_adm_merged`. |
| `merge_lora_baseline.py` | Merge the prompt-data LoRA adapter (`qwen_lora_baseline`) → `qwen_baseline_merged`. |
| `models/` | HF cache + LoRA adapters + merged checkpoints. **Git-ignored** (100s of GB). |

## Fine-tuned Qwen variants

Two QLoRA fine-tunes of `Qwen/Qwen3-Next-80B-A3B-Instruct` (trained via `ADM/finetune_qwen.py`,
data built in `Data/`):

| Adapter | Merged | Trained on | Serves as |
|---------|--------|-----------|-----------|
| `models/qwen_lora_adm` | `models/qwen_adm_merged` | ADM per-factor Q→A traces | "Qwen-FT" |
| `models/qwen_lora_baseline` | `models/qwen_baseline_merged` | plain baseline prompts | "Qwen-FT-baseline" |

Merged checkpoints are served with online `--quantization fp8`; the served name is `Qwen-3-80B`
so the runner (`--model qwen`) picks whichever checkpoint is loaded.

## Serving

vLLM launch scripts live in `scripts/servers/` (git-ignored). Base Qwen/Llama and the merged
Qwen fine-tunes use `.venv`; **GPT-OSS uses `.venv_11_2`**. Ports: Llama 8000, GPT-OSS 8001,
Qwen prompt-FT 8002, Qwen ADM-FT 8003.
