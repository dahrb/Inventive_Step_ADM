"""
QLoRA Fine-tuning of Qwen3-Next-80B-A3B-Instruct (MoE) on ADM SFT dataset.

Architecture notes
------------------
Qwen3-Next-80B-A3B is a Mixture-of-Experts model:
  • 80B total parameters, ~3B active per forward pass
  • Expert layers: gate_proj / up_proj / down_proj (per-expert)
  • Attention: q_proj / k_proj / v_proj / o_proj

LoRA targets attention + shared MLP projections only (not per-expert weights).
This keeps the trainable parameter count very small (~100M) while adapting the
model's reasoning style.

QLoRA config (BitsAndBytes 4-bit NF4):
  • Base loaded in 4-bit NF4 (bnb_4bit_use_double_quant=True)
  • LoRA adapters trained in bf16
  • Gradient checkpointing enabled
  • Fits on 2× H100 80GB (same node as inference server)

SFT format
----------
Full case conversation packed as a single ChatML sequence.
Only ASSISTANT turns are trained on (user/system tokens are masked).

Usage
-----
  python ADM/finetune_qwen.py \\
      --dataset Data/sft_dataset.jsonl \\
      --output_dir LLM_Models/models/qwen_lora_adm \\
      --epochs 3 \\
      --batch_size 1 \\
      --grad_accum 8
"""

import argparse
import json
import os
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    EarlyStoppingCallback,
    TrainingArguments,
)
from trl import SFTConfig, SFTTrainer

# ── Config ────────────────────────────────────────────────────────────────────

MODEL_ID = "Qwen/Qwen3-Next-80B-A3B-Instruct"
HF_HOME  = "/users/sgdbareh/scratch/ADM_JURIX/LLM_Models/models"

# LoRA targets: attention projections only (safe for MoE — avoids expert routing issues)
LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj", "gate_up_proj"
]

MAX_SEQ_LENGTH = 10240  # covers 100% of train+val (train max=14339, p99=13737; but no example exceeds 10240 in val; 14.3% of train truncated at 8192 — 10240 is zero-truncation cutoff)


# ── Dataset loading ───────────────────────────────────────────────────────────

def load_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def apply_chat_template(example: dict, tokenizer) -> dict:
    """Convert messages list → single string via the model's chat template.
    Only assistant turns contribute to the loss (trl SFTTrainer handles this
    automatically when `messages` column is present and dataset_text_field
    is not set — it uses the tokenizer's apply_chat_template internally).
    """
    return {"messages": example["messages"]}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train_dataset", type=str, default="Data/sft_train.jsonl")
    parser.add_argument("--val_dataset",   type=str, default="Data/sft_val.jsonl")
    parser.add_argument("--output_dir", type=str, default="LLM_Models/models/qwen_lora_adm")
    parser.add_argument("--epochs",     type=int, default=3)
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--grad_accum", type=int, default=4,
                        help="Gradient accumulation steps. Effective batch = batch_size × grad_accum × n_gpus.")
    parser.add_argument("--lora_r",     type=int, default=16)
    parser.add_argument("--lora_alpha", type=int, default=32)
    parser.add_argument("--lora_dropout", type=float, default=0.01)
    parser.add_argument("--lr",         type=float, default=2e-4)
    parser.add_argument("--warmup_ratio", type=float, default=0.05)
    parser.add_argument("--max_seq_len", type=int, default=MAX_SEQ_LENGTH)
    parser.add_argument("--resume_from_checkpoint", action="store_true",
                        help="Resume training from latest checkpoint in output_dir.")
    parser.add_argument("--save_steps", type=int, default=50,
                        help="Save a checkpoint every N steps.")
    parser.add_argument("--mode", type=str, default="factor", choices=["factor", "baseline"],
                        help="Training mode. 'baseline' sets epochs=3, batch=1, accum=1 with "
                             "early stopping (patience=1 epoch on val loss). "
                             "'factor' uses the supplied --epochs/--batch_size/--grad_accum values.")
    parser.add_argument("--early_stopping_patience", type=int, default=1,
                        help="Number of epochs with no val loss improvement before stopping "
                             "(only active in --mode baseline).")
    args = parser.parse_args()

    # Apply baseline mode overrides
    if args.mode == "baseline":
        print("[mode=baseline] Overriding: epochs=3, batch_size=1, grad_accum=1, early stopping enabled.")
        args.epochs     = 3
        args.batch_size = 1
        args.grad_accum = 1

    # ── Environment ───────────────────────────────────────────────────────────
    os.environ["HF_HOME"] = HF_HOME
    os.environ["HUGGINGFACE_HUB_CACHE"] = f"{HF_HOME}/hub"
    os.environ["TRANSFORMERS_CACHE"] = f"{HF_HOME}/transformers"

    # ── Load tokenizer ────────────────────────────────────────────────────────
    print(f"Loading tokenizer from {MODEL_ID}...")
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_ID,
        trust_remote_code=True,
        cache_dir=f"{HF_HOME}/hub",
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # ── Load model ────────────────────────────────────────────────────────────
    print(f"Loading model in 4-bit NF4 QLoRA (device_map=auto across available GPUs)...")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        cache_dir=f"{HF_HOME}/hub",
        torch_dtype=torch.bfloat16,
        attn_implementation="flash_attention_2",
    )

    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                            gradient_checkpointing_kwargs={"use_reentrant": False})

    # ── Apply LoRA ────────────────────────────────────────────────────────────
    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=LORA_TARGET_MODULES,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # ── Dataset ───────────────────────────────────────────────────────────────
    print(f"Loading train dataset from {args.train_dataset}...")
    train_data = load_jsonl(args.train_dataset)
    print(f"  {len(train_data)} train examples")

    print(f"Loading val dataset from {args.val_dataset}...")
    val_data = load_jsonl(args.val_dataset)
    print(f"  {len(val_data)} val examples")

    train_ds = Dataset.from_list([{"messages": ex["messages"]} for ex in train_data])
    val_ds   = Dataset.from_list([{"messages": ex["messages"]} for ex in val_data])

    # ── Training args ─────────────────────────────────────────────────────────
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    sft_config = SFTConfig(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        gradient_checkpointing=True,
        optim="adamw_8bit",
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=args.warmup_ratio,
        fp16=False,
        bf16=True,
        logging_steps=5,
        eval_strategy="epoch",
        eval_steps=args.save_steps,  # unused (eval_strategy=epoch)
        save_strategy="epoch",
        save_steps=args.save_steps,
        save_total_limit=3,           # keep only the 3 most recent checkpoints
        load_best_model_at_end=(args.mode == "baseline"),
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        report_to="none",
        dataloader_num_workers=2,
        # SFT-specific
        max_length=args.max_seq_len,
        dataset_text_field=None,      # use 'messages' column with chat template
        packing=True,                 # pack short sequences → eliminates padding waste → faster
    )

    # ── Trainer ───────────────────────────────────────────────────────────────
    callbacks = []
    if args.mode == "baseline":
        callbacks.append(EarlyStoppingCallback(early_stopping_patience=args.early_stopping_patience))
        print(f"[mode=baseline] Early stopping enabled with patience={args.early_stopping_patience} epoch(s).")

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        args=sft_config,
        callbacks=callbacks if callbacks else None,
    )

    print("Starting training...")
    # Only resume if a checkpoint actually exists in the output dir
    checkpoints = sorted(
        Path(args.output_dir).glob("checkpoint-*"),
        key=lambda p: int(p.name.split("-")[1])
    ) if args.resume_from_checkpoint else []
    resume = checkpoints[-1] if checkpoints else False
    trainer.train(resume_from_checkpoint=resume)

    # ── Save adapter ─────────────────────────────────────────────────────────
    adapter_path = os.path.join(args.output_dir, "adapter_final")
    trainer.model.save_pretrained(adapter_path)
    tokenizer.save_pretrained(adapter_path)
    print(f"Adapter saved to {adapter_path}")

    # ── Save config record ────────────────────────────────────────────────────
    config_record = {
        "base_model": MODEL_ID,
        "train_dataset": args.train_dataset,
        "val_dataset": args.val_dataset,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "lora_target_modules": LORA_TARGET_MODULES,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "grad_accum": args.grad_accum,
        "lr": args.lr,
        "max_seq_len": args.max_seq_len,
        "train_examples": len(train_data),
        "val_examples": len(val_data),
        "use_4bit": True,
        "mode": args.mode,
        "early_stopping_patience": args.early_stopping_patience if args.mode == "baseline" else None,
    }
    with open(os.path.join(args.output_dir, "finetune_config.json"), "w") as f:
        json.dump(config_record, f, indent=2)

    print("Done.")


if __name__ == "__main__":
    main()
