"""
Hybrid Patent System - Async ADM Experiment Runner
Supports Tool-Assisted (ADM CLI) and Baseline (Direct LLM) modes.
Optimized for high-concurrency usage with vLLM servers.
"""

import argparse
import json
import asyncio
import sys
import os
import re
import shutil
from datetime import datetime
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

# --- CONFIGURATION ---
BASE_CASE_DIR = "./Eval_Cases"
ADM_SCRIPT_PATH = '/users/sgdbareh/scratch/ADM_JURIX/ADM/UI.py'

# Model configurations
MODELS = {
    "gpt": {"id": "gpt-oss-120b", "mode": "squash"},
    "llama": {"id": "Llama-3.3-70B-Instruct", "mode": "chat"},
    "qwen": {"id": "Qwen3-Next-80B-A3B-Thinking", "mode": "chat"},
}

CURRENT_CONFIG = None

class ADM_INTERFACE(BaseModel):
    reasoning: str = Field(..., description="Step-by-step thinking process.")
    answer: str = Field(..., description="The final answer: 'Yes' or 'No'.")


# --- LOGGING UTILS (Synchronous is acceptable for small file ops) ---
def log_to_markdown(turn_num, question, raw_content, hidden_reasoning, final_answer, model_id, file_path="log.md"):
    """
    Append a standardized entry to the case log file.
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_dir = os.path.dirname(file_path)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"---\ntitle: ADM Session Log\ndate: {datetime.now().strftime('%Y-%m-%d')}\n---\n\n")

    entry_type = "Interaction"
    type_badge = "🗣️"
    clean_question = question

    # Badging
    if "[INFO]" in question:
        entry_type = "Info Gathering"
        type_badge = "ℹ️"
        clean_question = clean_question.replace("[INFO]", "").strip()
    elif "BASELINE" in question:
        entry_type = "Baseline Assessment"
        type_badge = "🧠"
    elif re.search(r"\[Q\d*\]", question):
        match = re.search(r"\[Q\d*\]", question)
        tag = match.group(0) if match else "Q"
        entry_type = f"Decision {tag}"
        type_badge = "❓"
        clean_question = clean_question.replace(tag, "").strip()

    # Outcome Parsing
    lines = clean_question.split('\n')
    outcome_lines = []
    prompt_lines = []
    for line in lines:
        clean_line = line.strip()
        if not clean_line: continue
        if any(x in clean_line for x in ["Case Outcome:", "Sub-ADM", "is ACCEPTED", "is REJECTED"]):
            fmt_line = clean_line.replace("ACCEPTED", "<span style='color:green;font-weight:bold'>ACCEPTED</span>")
            fmt_line = fmt_line.replace("REJECTED", "<span style='color:red;font-weight:bold'>REJECTED</span>")
            outcome_lines.append(f"> {fmt_line}")
        else:
            prompt_lines.append(clean_line)
    final_prompt = "\n".join(prompt_lines).strip()

    # Answer Formatting
    try:
        ans_text = str(final_answer).strip()
    except:
        ans_text = str(final_answer)

    if ans_text.lower() in ["yes", "y", "true"]:
        decision_badge = f'<span style="background:#e6ffed;color:#065f46;padding:4px 8px;border-radius:4px;font-weight:bold;border:1px solid #065f46">YES</span>'
    elif ans_text.lower() in ["no", "n", "false"]:
        decision_badge = f'<span style="background:#ffecec;color:#7b1414;padding:4px 8px;border-radius:4px;font-weight:bold;border:1px solid #7b1414">NO</span>'
    else:
        decision_badge = f'`{ans_text}`'

    # Build Entry
    entry = []
    entry.append(f"## {type_badge} Step {turn_num} — {entry_type} <span style='font-size:0.8em;color:grey;float:right'>{timestamp}</span>\n\n")
    if outcome_lines: entry.append("**Updates:**\n" + "\n".join(outcome_lines) + "\n\n")
    if final_prompt: entry.append(f"**Input:**\n> {final_prompt}\n\n")
    if hidden_reasoning: entry.append(f"**Analysis:**\n```text\n{hidden_reasoning}\n```\n")
    entry.append(f"**Decision:** {decision_badge}\n\n")
    entry.append(f"<details><summary>Raw Output</summary>\n```json\n{raw_content}\n```\n</details>\n\n---\n\n")

    with open(file_path, "a", encoding="utf-8") as f:
        f.writelines(entry)

def clean_combined_text(text: str) -> str:
    """Removes decorative separator lines."""
    lines = text.splitlines()
    out_lines = [l for l in lines if not (len(l.strip()) >= 3 and all(c == l.strip()[0] for c in l.strip()) and l.strip()[0] in "=-_~*")]
    return "\n".join(out_lines).strip()

# --- ASYNC LLM INTERACTION ---
async def consult_llm(question, history, client, turn_num, log_file, context_text=""):
    model_id = CURRENT_CONFIG["id"]
    mode = CURRENT_CONFIG["mode"]
    
    system_instruction = (
        f"You are conducting an Inventive Step Assessment for the European Patent Office.\n"
        f"Use the provided CASE DATA strictly. Do not use outside knowledge, but you can use your own judgment.\n"
        f"=== CASE DATA ===\n{context_text}\n=== END CASE DATA ===\n\n"
        f"INSTRUCTIONS:\n"
        f"1. Answer questions based ONLY on the text above or your own interpretation of them.\n"
        f"2. Output valid JSON with keys 'reasoning' and 'answer'."
    )

    messages = []
    if mode == "squash":
        # Squash history
        hist_text = "HISTORY:\n" + "\n".join([f"{h['role'].upper()}: {h['content']}" for h in history[-10:]])
        messages = [{"role": "user", "content": f"{system_instruction}\n\n{hist_text}\n\nCURRENT QUESTION: {question}"}]
    else:
        # Chat mode
        messages = [{"role": "system", "content": system_instruction}]
        for h in history[-10:]:
            content = h['content']
            if h['role'] == 'assistant': 
                try: content = json.dumps({"answer": json.loads(content).get("answer")})
                except: pass
            messages.append({"role": h['role'], "content": content})
        messages.append({"role": "user", "content": f"Output JSON {{reasoning, answer}}. Question: {question}"})

    req_params = {
        "model": model_id,
        "messages": messages,
        "max_tokens": 4096,
        "extra_body": {"guided_json": ADM_INTERFACE.model_json_schema()},
        "temperature": 0.1
    }
    
    # Manual Async Retry Loop
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"DEBUG: Asking LLM (Attempt {attempt+1})")
            response = await client.chat.completions.create(**req_params)
            raw_content = response.choices[0].message.content.strip()
            
            reasoning, final_answer = "No reasoning", ""
            try:
                parsed = json.loads(raw_content)
                reasoning = parsed.get("reasoning", "")
                final_answer = str(parsed.get("answer", "")).strip()
                if final_answer.lower() in ['yes', 'no']: final_answer = final_answer.lower()
            except:
                reasoning = raw_content
                final_answer = raw_content

            log_to_markdown(turn_num, question, raw_content, reasoning, final_answer, model_id, file_path=log_file)
            return final_answer, reasoning
            
        except Exception as e:
            print(f"[LLM ERROR]: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                return "ERROR", "API Call Failed"

# --- EXECUTION MODES ---

async def run_tool_session(client, case_name, context_text):
    """
    Mode 1: Tool-Assisted (Async).
    Runs the ADM CLI subprocess asynchronously.
    """
    print(f"\n>>> STARTING TOOL MODE: {case_name}")
    
    case_dir = os.path.join(BASE_CASE_DIR, case_name)
    os.makedirs(case_dir, exist_ok=True)
    log_file = os.path.join(case_dir, "log_tool.md")
    if os.path.exists(log_file): os.remove(log_file)

    # Start Async Subprocess
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-u', ADM_SCRIPT_PATH,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )

    history = []
    turn = 1
    buffer = []
    final_verdict = "UNKNOWN"

    while True:
        # Read with timeout to detect "waiting for input" state
        try:
            chunk = await asyncio.wait_for(process.stdout.read(4096), timeout=0.25)
            if not chunk:
                break # EOF
            buffer.append(chunk.decode('utf-8', errors='replace'))
        except asyncio.TimeoutError:
            # Timeout means no new data; check buffer for prompts
            pass

        combined = "".join(buffer)
        clean = clean_combined_text(combined)
        
        if not clean and process.returncode is None:
            continue
        
        if process.returncode is not None and not clean:
            break

        # Auto-handle Case Name
        if "[Q] Enter case name" in clean:
            process.stdin.write((case_name + "\n").encode('utf-8'))
            await process.stdin.drain()
            buffer = []
            continue

        # Detect Prompt
        lines = clean.splitlines()
        is_prompt = any(l.strip().startswith(p) for l in lines for p in ("QUESTION:", "GUESS:"))
        if "enter your choice" in clean.lower() or (lines and (lines[-1].strip().endswith("?") or lines[-1].strip().endswith(":"))):
            is_prompt = True

        if is_prompt:
            # Extract question
            q_text = lines[-1].split(":", 1)[1].strip() if ":" in lines[-1] else clean
            
            ans, reas = await consult_llm(q_text, history, client, turn, log_file, context_text)
            
            if ans == "ERROR": 
                process.terminate()
                break
            
            process.stdin.write((str(ans) + "\n").encode('utf-8'))
            await process.stdin.drain()

            history.append({"role": "user", "content": q_text})
            history.append({"role": "assistant", "content": json.dumps({"reasoning": reas, "answer": ans})})
            turn += 1
            buffer = []
            await asyncio.sleep(0.1) # Brief yield

    # Final Verdict Logic
    final_combined = "".join(buffer).strip()
    summary_question = (
        "Based on the session interaction above, what was the final outcome?\n"
        "State a single final decision on whether an inventive step is present: 'Yes' or 'No'."
    )
    context_for_final = f"SESSION OUTPUT:\n{final_combined}\n\n{summary_question}"
    
    final_ans, final_reas = await consult_llm(context_for_final, history, client, turn, log_file, context_text)
    
    if final_ans != "ERROR":
        final_verdict = final_ans.upper()
        # Log final decision separately
        log_to_markdown(turn, "FINAL VERDICT", json.dumps({"reasoning": final_reas, "answer": final_ans}), final_reas, final_ans, CURRENT_CONFIG.get('id'), file_path=log_file)

    print(f"Tool Session for {case_name} Finished. Verdict: {final_verdict}")
    return final_verdict

async def run_baseline_session(client, case_name, context_text):
    """
    Mode 2: Baseline (Async).
    Direct LLM query.
    """
    print(f"\n>>> STARTING BASELINE MODE: {case_name}")
    
    case_dir = os.path.join(BASE_CASE_DIR, case_name)
    os.makedirs(case_dir, exist_ok=True)
    log_file = os.path.join(case_dir, "log_baseline.md")
    if os.path.exists(log_file): os.remove(log_file)

    prompt = (
        "Based on the provided case data, does the claimed invention satisfy the requirement of an Inventive Step?\n"
        "Provide a detailed reasoning trace followed by a final 'Yes' or 'No' answer."
    )

    ans, reas = await consult_llm(prompt, [], client, 1, log_file, context_text)
    
    print(f"Baseline Session for {case_name} Finished. Verdict: {ans.upper()}")
    return ans.upper()

# --- DATA LOADER ---
def load_context(base_path, case_name, dataset, config):
    path = os.path.join(base_path, case_name)
    parts = []

    if dataset == "comvik":
        cpa = os.path.join(path, "CPA.txt")
        if os.path.exists(cpa): parts.append(f"--- CLOSEST PRIOR ART ---\n{open(cpa).read()}")
        
        if config == 1:
            pat = os.path.join(path, "patent.txt")
            if os.path.exists(pat): parts.append(f"--- PATENT CLAIMS ---\n{open(pat).read()}")
        elif config == 2:
            full = os.path.join(path, "full.txt")
            if os.path.exists(full): parts.append(f"--- FULL REASONING ---\n{open(full).read()}")

    elif dataset == "validation":
        appeal = os.path.join(path, "appeal.txt")
        claims = os.path.join(path, "claims.txt")
        cpa = os.path.join(path, "CPA.txt")

        if config == 1:
            if os.path.exists(appeal): parts.append(f"--- APPEAL FACTS ---\n{open(appeal).read()}")
        elif config == 2:
            if os.path.exists(claims): parts.append(f"--- PATENT CLAIMS ---\n{open(claims).read()}")
            if os.path.exists(cpa): parts.append(f"--- CLOSEST PRIOR ART ---\n{open(cpa).read()}")
        elif config == 3:
            if os.path.exists(appeal): parts.append(f"--- APPEAL FACTS ---\n{open(appeal).read()}")
            if os.path.exists(claims): parts.append(f"--- PATENT CLAIMS ---\n{open(claims).read()}")
            if os.path.exists(cpa): parts.append(f"--- CLOSEST PRIOR ART ---\n{open(cpa).read()}")

    return "\n\n".join(parts)

# --- BATCH RUNNER ---
async def run_experiment_batch(data_path, dataset, experiment_config, mode, client):
    if not os.path.exists(data_path):
        print(f"Error: Data path {data_path} does not exist.")
        return

    cases = sorted([d for d in os.listdir(data_path) if os.path.isdir(os.path.join(data_path, d))])
    print(f"Found {len(cases)} cases in {dataset.upper()} set. Starting concurrent execution...")

    # Create tasks for all cases
    tasks = []
    case_names = []
    
    for case in cases:
        context = load_context(data_path, case, dataset, experiment_config)
        if not context:
            print(f"Skipping {case} (Missing context)")
            continue
            
        case_names.append(case)
        if mode == 'tool':
            tasks.append(run_tool_session(client, case, context))
        else:
            tasks.append(run_baseline_session(client, case, context))

    # Run all concurrently
    results = await asyncio.gather(*tasks)
    
    # Collate Results
    final_results = dict(zip(case_names, results))
    
    # Save Results JSON
    json_filename = f"results_{dataset}_{mode}_config{experiment_config}.json"
    with open(json_filename, 'w') as f:
        json.dump(final_results, f, indent=4)
    print(f"\n>>> Experiment Completed. Results saved to {json_filename}")

# --- MAIN ---
async def async_main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="gpt", choices=["gpt", "llama", "qwen"]) 
    parser.add_argument('--gpu', type=str, default='gpu07')
    parser.add_argument('--dataset', type=str, choices=['comvik', 'validation'], required=True)
    parser.add_argument('--data_path', type=str, default="/users/sgdbareh/scratch/ADM_JURIX/Data/VALIDATION")
    parser.add_argument('--exp_config', type=int, required=True)
    parser.add_argument('--mode', type=str, default='tool', choices=['tool', 'baseline'])

    args = parser.parse_args()
    
    global CURRENT_CONFIG
    CURRENT_CONFIG = MODELS.get(args.model, MODELS['gpt'])

    API_BASE = f"http://{args.gpu}.barkla2.liv.alces.network:8000/v1"
    try:
        # Use Async Client
        client = AsyncOpenAI(base_url=API_BASE, api_key="EMPTY")
    except:
        print("Error: LLM API unreachable.")
        return

    await run_experiment_batch(args.data_path, args.dataset, args.exp_config, args.mode, client)

if __name__ == "__main__":
    asyncio.run(async_main())