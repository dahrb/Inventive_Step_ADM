"""
Merge the ADM LoRA adapter into the Qwen base model and save as a standalone
model. The merged model can then be served with plain vllm serve (no --enable-lora)
which avoids the SHM timeout bug in vLLM 0.19 during CUDA graph capture.
"""
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import os

BASE_MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct"
ADAPTER_PATH = "/users/sgdbareh/scratch/ADM_JURIX/LLM_Models/models/qwen_lora_adm/adapter_final"
OUTPUT_PATH = "/users/sgdbareh/scratch/ADM_JURIX/LLM_Models/models/qwen_adm_merged"

HF_HOME = "/users/sgdbareh/scratch/ADM_JURIX/LLM_Models/models"
os.environ["HF_HOME"] = HF_HOME
os.environ["HUGGINGFACE_HUB_CACHE"] = f"{HF_HOME}/hub"
os.environ["TRANSFORMERS_CACHE"] = f"{HF_HOME}/transformers"

print(f"Loading base model: {BASE_MODEL}")
print("(loading in bfloat16 on CPU to avoid GPU memory constraints)")

model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.bfloat16,
    device_map="cpu",
    trust_remote_code=True,
)

print(f"Loading LoRA adapter from: {ADAPTER_PATH}")
model = PeftModel.from_pretrained(model, ADAPTER_PATH)

print("Merging LoRA weights into base model...")
model = model.merge_and_unload()

print(f"Saving merged model to: {OUTPUT_PATH}")
model.save_pretrained(OUTPUT_PATH, safe_serialization=True)

print("Saving tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
tokenizer.save_pretrained(OUTPUT_PATH)

print("Done. Merged model saved.")
