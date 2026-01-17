"""
Hybrid Patent System

Last Updated: 16.01.2025

Status: Refining

"""

import argparse
import json
import asyncio
import sys
import os
import re
from datetime import datetime
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
import logging
import time
import pandas as pd
from collections import Counter

logger = logging.getLogger("Hybrid_System")
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

#folder paths
BASE_CASE_DIR = "../Outputs/Eval_Cases"
ADM_SCRIPT_PATH = '../ADM/UI.py'
RAW_DATA = pd.read_pickle('/users/sgdbareh/scratch/ADM_JURIX/Data/Inv_Step_Test.pkl')

#model configurations
MODELS = {
    "gpt": {"id": "gpt-oss-120b"},
    "llama": {"id": "Llama-3.3-70B-Instruct"},
    "qwen": {"id": "Qwen3-Next-80B-A3B-Thinking"},
}

inv_step = pd.read_pickle('/users/sgdbareh/scratch/ADM_JURIX/Data/Inv_Step_Test.pkl')

#initialised defaults
CURRENT_CONFIG = None
LLM_TEMPERATURE = 0.1

#sets JSON srtucture for output
class ADM_INTERFACE(BaseModel):
    reasoning: str = Field(..., description="Step-by-step thinking process.")
    answer: str = Field(..., description="The final answer: respond accordingly to the output the question expects.")

#JSON logging system: tracks each conversation turn and saves it to a file
def log_to_json(turn_num, question, raw_content, reasoning, final_answer, model_id, hidden_reasoning, file_path="log.json", metadata=None):
    """
    Append a standardized entry to the case log file as JSON.
    Each turn is a dict with question, answer, reasoning, etc.
    """
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_dir = os.path.dirname(file_path)
    
    #create and load folders for log
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    log_data = []
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                log_data = json.load(f)
        except Exception:
            log_data = []

    #define entry
    entry = {
        "turn": turn_num,
        "timestamp": timestamp,
        "question": question,
        "answer": final_answer,
        "reasoning": reasoning,
        "hidden_reasoning": hidden_reasoning,
        "raw_content": raw_content,
        "model_id": model_id,
        "metadata": metadata or {},
    }
    
    log_data.append(entry)

    #write
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)

def clean_combined_text(text: str):
    """Removes decorative separator lines."""
    lines = text.splitlines()
    out_lines = [l for l in lines if not (len(l.strip()) >= 3 and all(c == l.strip()[0] for c in l.strip()) and l.strip()[0] in "=-_~*")]
    return "\n".join(out_lines).strip()

#LLM processing
async def consult_llm(question, history, client, turn_num, log_file, context_text="", generation_mode="tool", metadata=None):
    model_id = CURRENT_CONFIG["id"]  
    
    if generation_mode == "baseline":
        system_instruction = (
            f"You are objectively assessing Inventive Step for the European Patent Office (EPO).\n"
            f"Use the data provided. Try to avoid using outside knowledge, except for common knowledge, if you believe this would have been known prior to the common knowledge cut-off date given.\n"
            f"Do not use outside knowledge but you can make reasonable assumptions not explicitly contained within the data.\n"
            f"However, you can make reasonable assumptions not explicitly contained within the data.\n"
            f"Do not just do as the data tells you directly, i.e. if the data says party X has appealed because they believe invention I has inventive step, do not just assume they are correct.\n"
            f"Your job is to critically analysis the information given to you to come to an informed, reasoned judgment.\n"
            f"Determine whether the patent fulfils the inventive step criteria or not.\n"
            f"You are trying to objectively assess whether inventive step is present, when answering the question think carefully and use your own judegment.\n "
            f"=== CASE DATA ===\n{context_text}\n=== END CASE DATA ===\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Provide a step-by-step reasoning trace.\n"
            f"2. Conclude with a final 'Yes' or 'No' answer.\n"
            f"3. Output valid JSON with keys 'reasoning' and 'answer'."
        )
        
        question = ''
    
    else:
        system_instruction = (
            f"You are objectively assessing Inventive Step for the European Patent Office (EPO).\n"
            f"Use the data provided. Try to avoid using outside knowledge, except for common knowledge, if you believe this would have been known prior to the common knowledge cut-off date given.\n"
            f"However, you can make reasonable assumptions not explicitly contained within the data.\n"
            f"Do not just do as the data tells you directly, i.e. if the data says party X has appealed because they believe invention I has inventive step, do not just assume they are correct.\n"
            f"Your job is to critically analysis the information given to you to come to an informed, reasoned judgment.\n"
            f"You will be asked questions generated from an argumentation tool designed for inventive step to help you reason to a conclusion on whether inventive step is present.\n"
            f"Do not try and answer the questions to guarantee a certain outcome because you believe that is the correct one, just answer them as objectively as possible."
            f"You are trying to objectively assess whether inventive step is present, when answering each question think carefully and use your own critical analysis and discretion.\n "
            f"=== CASE DATA ===\n{context_text}\n=== END CASE DATA ===\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Answer questions based ONLY on the text above.\n"
            f"2. Output valid JSON with keys 'reasoning' and 'answer'."
        )
        
        messages = []
        
    #provides only the previous 10 answers
    hist_text = "HISTORY:\n" + "\n".join([f"{h['role'].upper()}: {h['content']}" for h in history[-10:]])
    messages = [{"role": "user", "content": f"{system_instruction}\n\n{hist_text}\n\nCURRENT QUESTION: {question}"}]

    #print full prompt for debug
    logger.debug(f"\n{'-'*20} LLM PROMPT (Turn {turn_num} | Mode: {generation_mode.upper()}) {'-'*20}")
    for m in messages:
        role = m['role'].upper()
        content = m['content']
        logger.debug(f"[{role}]: {content}")
    logger.debug(f"{'-'*60}\n")


    #base request params
    base_req = {
        "model": model_id,
        "messages": messages,
        "max_tokens": 8096,
        "reasoning_effort":'medium',
        "extra_body": {"guided_json": ADM_INTERFACE.model_json_schema()},
    }



    # Single-shot fallback (original behaviour)
    temp = globals().get('LLM_TEMPERATURE', 0.1)
    req_params = {**base_req, 'temperature': temp}
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = await client.chat.completions.create(**req_params)
            raw_content = response.choices[0].message.content.strip()
            hidden_reasoning = response.choices[0].message.reasoning_content
            logger.debug(f"\n[LLM RESPONSE]:\n{raw_content}\n{'-'*60}\n")
            reasoning, final_answer = "No reasoning", ""
            try:
                parsed = json.loads(raw_content)
                reasoning = parsed.get("reasoning", "")
                final_answer = str(parsed.get("answer", "")).strip()
            except:
                reasoning = raw_content
                final_answer = raw_content
                
            log_to_json(turn_num, question, raw_content, reasoning, final_answer, model_id, hidden_reasoning, file_path=log_file, metadata=metadata)
            return final_answer, reasoning
        except Exception as e:
            print(f"[LLM ERROR]: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                return "ERROR", "API Call Failed"

#tool-assisted runs
async def run_tool_session(client, case_name, context_text, run_id, metadata):
    """

    """
    logger.debug(f"\nSTARTING TOOL MODE: {case_name} (Run {run_id})")
    
    config_num = metadata.get('config') if metadata and 'config' in metadata else 'X'
    # Directory structure: {case}/{run_id}/config_{config}/tool/
    log_dir = os.path.join(BASE_CASE_DIR, case_name, f"run_{run_id}", f"config_{config_num}", "tool")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "log.json")
    if os.path.exists(log_file):
        os.remove(log_file)
    start_time = time.time()

    # Prepare CLI args for UI.py
    config_num = metadata.get('config') if metadata and 'config' in metadata else 'X'
    mode = metadata.get('mode') if metadata and 'mode' in metadata else 'tool'
    folder_base = BASE_CASE_DIR
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-u', ADM_SCRIPT_PATH,
        '--run_id', str(run_id),
        '--config', str(config_num),
        '--mode', str(mode),
        '--folder_base', str(folder_base),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )

    history = []
    turn = 1
    buffer = []
    final_verdict = "UNKNOWN"

    while True:
        try:
            chunk = await asyncio.wait_for(process.stdout.read(4096), timeout=0.25)
            if not chunk: break
            decoded_chunk = chunk.decode('utf-8', errors='replace')
            buffer.append(decoded_chunk)
            
            if decoded_chunk.strip():
                print(f"[STDOUT from UI.py]: {decoded_chunk.strip()}")
                
        except asyncio.TimeoutError:
            pass

        combined = "".join(buffer)
        clean = clean_combined_text(combined)
        
        if not clean and process.returncode is None:
            continue
        
        if process.returncode is not None and not clean:
            break

        #detect prompt logic
        # 1. Check for specific [Q] tag (used by UI.py inputs)
        # 2. Check for standard endings (?, :) or specific phrases
        is_prompt = False
        
        if re.search(r"\[Q\d*\]", clean):
            is_prompt = True
        elif any(l.strip().startswith(p) for l in clean.splitlines() for p in ("QUESTION:", "GUESS:")):
            is_prompt = True
        elif "enter your choice" in clean.lower():
            is_prompt = True
        elif clean.strip().endswith("?") or clean.strip().endswith(":"):
            is_prompt = True

        #deal with case name
        if "[Q] Enter case name" in clean:
            print(f"[STDIN to UI.py]: {case_name}")
            process.stdin.write((case_name + "\n").encode('utf-8'))
            await process.stdin.drain()
            buffer = []
            continue

        if is_prompt:
            q_text = clean
            
            #use 'tool' mode prompt
            ans, reas = await consult_llm(q_text, history, client, turn, log_file, context_text, generation_mode="tool", metadata=metadata)
            
            if ans == "ERROR": 
                process.terminate()
                break
            
            print(f"[STDIN to UI.py]: {ans}")
            process.stdin.write((str(ans) + "\n").encode('utf-8'))
            await process.stdin.drain()

            history.append({"role": "user", "content": q_text})
            history.append({"role": "assistant", "content": json.dumps({"reasoning": reas, "answer": ans})})
            turn += 1
            buffer = []
            await asyncio.sleep(0.1) 

    #final Verdict
    final_combined = "".join(buffer).strip()
    if final_combined:
        print(f"[STDOUT Final]: {final_combined}")


    context_for_final = f"SESSION OUTPUT:\n{final_combined}\n\n{summary_question}"
    
    logger.debug(context_for_final)
    
    final_ans, final_reas = await consult_llm(context_for_final, history, client, turn, log_file, context_text, generation_mode="tool", metadata=metadata)
    end_time = time.time()
    elapsed = end_time - start_time
    # Add timing info to the last log entry
    try:
        # Load log, update last entry with elapsed time
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                log_data = json.load(f)
            if log_data:
                log_data[-1]["elapsed_seconds"] = elapsed
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Timer Write Error]: {e}")

    if final_ans != "ERROR":
        final_verdict = final_ans.upper()
    print(f"Tool Session for {case_name} (Run {run_id}) Finished. Verdict: {final_verdict}. Time: {elapsed:.2f}s")
    # ADM saving is now handled exclusively by UI.py subprocess. No direct CLI ADM saving here.
    return final_verdict

#baseline with no tool-assist runs
async def run_baseline_session(client, case_name, context_text, run_id, metadata):
    """
    """
    logger.debug(f"\nSTARTING BASELINE MODE: {case_name} (Run {run_id})")
    
    import time
    config_num = metadata.get('config') if metadata and 'config' in metadata else 'X'
    # Directory structure: {case}/{run_id}/config_{config}/baseline/
    log_dir = os.path.join(BASE_CASE_DIR, case_name, f"run_{run_id}", f"config_{config_num}", "baseline")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "log.json")
    if os.path.exists(log_file):
        os.remove(log_file)
    start_time = time.time()

    prompt = (
        "Based on the provided case data, does the claimed invention satisfy the requirement of an Inventive Step?\n"
        "Provide a detailed reasoning trace followed by a final 'Yes' or 'No' answer."
    )

    ans, reas = await consult_llm(prompt, [], client, 1, log_file, context_text, generation_mode="baseline", metadata=metadata)
    end_time = time.time()
    elapsed = end_time - start_time
    # Add timing info to the last log entry
    try:
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                log_data = json.load(f)
            if log_data:
                log_data[-1]["elapsed_seconds"] = elapsed
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Timer Write Error]: {e}")

    print(f"Baseline Session for {case_name} (Run {run_id}) Finished. Verdict: {ans.upper()}. Time: {elapsed:.2f}s")
        # Do not save ADM JSONs for baseline mode
    return ans.upper()

#data loader
def load_context(base_path, case_name, dataset, config):
    path = os.path.join(base_path, case_name)
    parts = []

    if dataset == "comvik":
        cpa = os.path.join(path, "CPA.txt")
        if os.path.exists(cpa): parts.append(f"--- CLOSEST PRIOR ART INFORMATION---\n{open(cpa).read()}")
        
        if config == 1:
            pat = os.path.join(path, "patent.txt")
            if os.path.exists(pat): parts.append(f"--- PATENT APPLICATION CLAIMS ---\n{open(pat).read()}")
        elif config == 2:
            full = os.path.join(path, "full.txt")
            if os.path.exists(full): parts.append(f"--- FULL REASONING ABOUT THE PATENT APPLICATION ---\n{open(full).read()}")

    else:
        appeal = os.path.join(path, "appeal.txt")
        claims = os.path.join(path, "claims.txt")
        cpa = os.path.join(path, "CPA.txt")

        if config == 1:
            if os.path.exists(appeal): parts.append(f"--- APPEAL SUMMARY OF FACTS ---\n{open(appeal).read()}")
        elif config == 2:
            if os.path.exists(claims): parts.append(f"--- PATENT APPLICATION CLAIMS ---\n{open(claims).read()}")
            if os.path.exists(cpa): parts.append(f"--- CLOSEST PRIOR ART INFORMATION ---\n{open(cpa).read()}")
        elif config == 3:
            if os.path.exists(appeal): parts.append(f"--- APPEAL SUMMARY OF FACTS ---\n{open(appeal).read()}")
            if os.path.exists(claims): parts.append(f"--- PATENT APPLICATION CLAIMS ---\n{open(claims).read()}")
            if os.path.exists(cpa): parts.append(f"--- CLOSEST PRIOR ART INFORMATION ---\n{open(cpa).read()}")
            
    #add the filing date 
    year = str(RAW_DATA.loc[RAW_DATA['Reference'] == case_name, 'Year'].iloc[0])
    parts.append(f"--- COMMON KNOWLEDGE DATE CUTOFF ---\n{year}")


    return "\n\n".join(parts)

#batch run in parallel 
async def run_experiment_batch(data_path, dataset, experiment_config, mode, num_runs, client):
    if not os.path.exists(data_path):
        print(f"Error: Data path {data_path} does not exist.")
        return

    cases = sorted([d for d in os.listdir(data_path) if os.path.isdir(os.path.join(data_path, d))])
    print(f"Found {len(cases)} cases in {dataset.upper()} set. Starting {num_runs} runs...")

    #consolidated Results: { "run_1": {case: verdict}, "run_2": ... }
    all_runs_results = {}

    for i in range(1, num_runs + 1):
        print(f"\n{'='*20} STARTING RUN {i}/{num_runs} {'='*20}")
        
        tasks = []
        case_list_for_run = []
        
        metadata = {
            "dataset": dataset,
            "mode": mode,
            "config": experiment_config,
            "run_id": i,
            "model": CURRENT_CONFIG["id"]
        }

        for case in cases:
            context = load_context(data_path, case, dataset, experiment_config)
            if not context:
                print(f"Skipping {case} (Missing context)")
                continue
                
            case_list_for_run.append(case)
            if mode == 'tool':
                tasks.append(run_tool_session(client, case, context, i, metadata))
            else:
                tasks.append(run_baseline_session(client, case, context, i, metadata))

        #run all cases for this iteration concurrently
        results = await asyncio.gather(*tasks)
        
        #store results for this run
        run_key = f"run_{i}"
        all_runs_results[run_key] = dict(zip(case_list_for_run, results))
        
        #brief pause between batch runs to be safe
        await asyncio.sleep(1)

    #save Consolidated Results JSON
    json_filename = f"../Outputs/results_{dataset}_{mode}_config{experiment_config}.json"
    with open(json_filename, 'w') as f:
        json.dump(all_runs_results, f, indent=4)
    print(f"\nExperiment Completed. Results saved to {json_filename}")

async def async_main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="gpt", choices=["gpt", "llama", "qwen"]) 
    parser.add_argument('--gpu', type=str, default='gpu07')
    parser.add_argument('--dataset', type=str, choices=['comvik', 'main'], required=True)
    parser.add_argument('--data_path', type=str, default="/users/sgdbareh/scratch/ADM_JURIX/Data/VALIDATION")
    parser.add_argument('--exp_config', type=int, required=True)
    parser.add_argument('--mode', type=str, default='tool', choices=['tool', 'baseline'])
    parser.add_argument('--runs', type=int, default=1, help="Number of times to repeat the experiment.")
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--use_ensemble', action='store_true', help='Use ensemble (self-consistency) sampling')
    parser.add_argument('--ensemble_n', type=int, default=3, help='Number of ensemble samples (default 3)')
    parser.add_argument('--ensemble_temp', type=float, default=0.5, help='Temperature for ensemble sampling (default 0.5)')
    parser.add_argument('--verifier_temp', type=float, default=0.0, help='Temperature for deterministic verifier (default 0.0)')
    parser.add_argument('--temperature', type=float, default=0.1, help='Sampling temperature for LLM (default: 0.1)')
    parser.add_argument('--allow_summary_override', action='store_true', help='Allow LLM to override the tool answer in the summary question if justified.')

    args = parser.parse_args()

    #if user flags --debug, switch level to DEBUG
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)        
        print("--- DEBUG MODE ENABLED ---")
    
    global CURRENT_CONFIG
    CURRENT_CONFIG = MODELS.get(args.model, MODELS['gpt'])

    # ensemble/verifier globals
    global USE_ENSEMBLE, ENSEMBLE_N, ENSEMBLE_TEMP, VERIFIER_TEMP
    USE_ENSEMBLE = args.use_ensemble
    ENSEMBLE_N = args.ensemble_n
    ENSEMBLE_TEMP = args.ensemble_temp
    VERIFIER_TEMP = args.verifier_temp

    #store temperature globally for use in consult_llm
    global LLM_TEMPERATURE
    LLM_TEMPERATURE = args.temperature

    #store summary override flag globally
    global SUMMARY_OVERRIDE_ALLOWED
    SUMMARY_OVERRIDE_ALLOWED = args.allow_summary_override

    #input the api to your LLM here!!!
    API_BASE = f"http://{args.gpu}.barkla2.liv.alces.network:8000/v1"
    
    try:
        # Use Async Client
        client = AsyncOpenAI(base_url=API_BASE, api_key="EMPTY")
    except:
        print("Error: LLM API unreachable.")
        return

    await run_experiment_batch(args.data_path, args.dataset, args.exp_config, args.mode, args.runs, client)

if __name__ == "__main__":
    asyncio.run(async_main())