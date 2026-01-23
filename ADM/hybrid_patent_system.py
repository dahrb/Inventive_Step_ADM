"""
Hybrid Patent System

Last Updated: 16.01.2025

Status: Only need to implement an Ensemble tool-calling mode 

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
import subprocess
import random
import traceback
import socket

logger = logging.getLogger("Hybrid_System")
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

#sets concurrency
REQUEST_SEMAPHORE = asyncio.Semaphore(40)
print('Request Semaphore: ', REQUEST_SEMAPHORE._value)

#folder paths (will be initialised from CLI args in async_main)
BASE_CASE_DIR = "../Outputs/Valid_Cases"
ADM_SCRIPT_PATH = '../ADM/UI.py'
# RAW_DATA will be loaded after CLI parsing into the global `RAW_DATA` variable
RAW_DATA = None

#model configurations
MODELS = {
    "gpt": {"id": "gpt-oss-120b"},
    "llama": {"id": "Llama-3.3-70B-Instruct"},
    "gpt_small": {"id": "gpt-oss-20b"},
}

#initialised defaults
CURRENT_CONFIG = None
LLM_TEMPERATURE = 0.0

#sets JSON structure for output
class ADM_INTERFACE(BaseModel):
    reasoning: str = Field(..., description="step-by-step thinking process.")
    answer: str = Field(..., description="the answer")
    
class ADM_TRAIN(BaseModel):
    reasoning: str = Field(..., description="step-by-step thinking process.")
    score: int = Field(..., description="confidence score. MUST be one of: 0 (No), 1 (Low), 2 (Medium), 3 (High).")
    answer: str = Field(..., description="a yes/no answer to the question")

def ADM_text_clean(text):
    """helper func that removes decorative separator lines."""
    lines = text.splitlines()
    out_lines = [l for l in lines if not (len(l.strip()) >= 3 and all(c == l.strip()[0] for c in l.strip()) and l.strip()[0] in "=-_~*")]
    return "\n".join(out_lines).strip()

def log_to_json(turn_num, question, raw_content, reasoning, final_answer, model_id, hidden_reasoning, score=None, file_path="log.json", metadata=None):
    """
    creates a JSON log
    
    Args:
        turn_num (_type_): _description_
        question (_type_): _description_
        raw_content (_type_): _description_
        reasoning (_type_): _description_
        final_answer (_type_): _description_
        model_id (_type_): _description_
        hidden_reasoning (_type_): _description_
        file_path (str, optional): _description_. Defaults to "log.json".
        metadata (_type_, optional): _description_. Defaults to None.
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
        "score": score,
        "hidden_reasoning": hidden_reasoning,
        "raw_content": raw_content,
        "model_id": model_id,
        "metadata": metadata or {},
    }
    
    log_data.append(entry)

    #write
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)

async def consult_llm(system_prompt, history, client, turn_num, log_file, question=None, generation_mode="baseline", metadata=None, train_data=False):
    """Robust LLM call with bounded concurrency, retries, timeout and backoff.

    Keeps behaviour same externally: returns (answer, reasoning) or ("ERROR","API Call Failed").
    """
    model_id = CURRENT_CONFIG["id"]

    #construct messages
    if generation_mode == "baseline":
        messages = [{"role": "user", "content": system_prompt}]
        
    elif generation_mode == "summary":
        hist_text = "HISTORY:\n" + "\n".join([f"{h['role'].upper()}: {h['content']}" for h in history[-10:]])
        messages = [{"role": "user", "content": f"{system_prompt}\n\n{hist_text}"}]

    else:
        hist_text = "HISTORY:\n" + "\n".join([f"{h['role'].upper()}: {h['content']}" for h in history[-10:]])
        messages = [{"role": "user", "content": f"{system_prompt}\n\n{hist_text}\n\nCURRENT QUESTION: {question}"}]

    logger.debug(f"LLM PROMPT (Turn {turn_num} | Mode: {generation_mode})")

    if train_data:
        guided_json = ADM_TRAIN.model_json_schema()

    else:
        guided_json = ADM_INTERFACE.model_json_schema()
    
    
    base_req = {
        "model": model_id,
        "messages": messages,
        "max_tokens": 8096,
        "reasoning_effort": "medium",
        "temperature": globals().get("LLM_TEMPERATURE", 0.0),
        "top_p": 1.0,
        "seed":42,
        "extra_body": {"guided_json": guided_json},
    }

    #retries with exponential backoff + jitter; throttle concurrent outbound LLM calls
    max_retries = 5
    base_backoff = 0.6
    
    for attempt in range(1, max_retries + 1):
        try:
            async with REQUEST_SEMAPHORE:
                #per-call timeout to avoid hangs
                try:
                    resp = await asyncio.wait_for(client.chat.completions.create(**base_req), timeout=120)
                except asyncio.TimeoutError as te:
                    logger.warning(f"LLM call timeout (attempt {attempt}/{max_retries}): {te}")
                    raise

            #success
            raw_content = resp.choices[0].message.content.strip()
            hidden_reasoning = getattr(resp.choices[0].message, "reasoning_content", None)
            logger.debug(f"[LLM RESPONSE]: {raw_content[:1000]}")
            
            if train_data:
                
                try:
                    parsed = json.loads(raw_content)
                    reasoning = parsed.get("reasoning", "")
                    final_answer = str(parsed.get("answer", "")).strip()
                    score = parsed.get("score", "")
                    
                    
                except Exception:
                    #log raw content for inspection
                    logger.debug("Failed to parse LLM JSON response; storing raw output")
                    reasoning = raw_content
                    final_answer = raw_content

                log_to_json(turn_num, question, raw_content, reasoning, final_answer, model_id, hidden_reasoning, score=score, file_path=log_file, metadata=metadata)
    
            else:
                
                try:
                    parsed = json.loads(raw_content)
                    reasoning = parsed.get("reasoning", "")
                    final_answer = str(parsed.get("answer", "")).strip()
                    
                except Exception:
                    # log raw content for inspection
                    logger.debug("Failed to parse LLM JSON response; storing raw output")
                    reasoning = raw_content
                    final_answer = raw_content

                log_to_json(turn_num, question, raw_content, reasoning, final_answer, model_id, hidden_reasoning, file_path=log_file, metadata=metadata)
            
            return final_answer, reasoning

        except Exception as e:
            # characterize exception and decide to retry
            logger.warning(f"LLM request exception (attempt {attempt}/{max_retries}): {type(e).__name__}: {e}")
            logger.debug("Traceback:\n" + "".join(traceback.format_exception(type(e), e, e.__traceback__)))
            if attempt >= max_retries:
                logger.error("LLM request failed after retries")
                return "ERROR", "API Call Failed"
            # backoff + jitter
            backoff = base_backoff * (2 ** (attempt - 1))
            jitter = random.uniform(0, backoff * 0.5)
            await asyncio.sleep(backoff + jitter)
                    
async def run_baseline_session(client, case_name, context_text, run_id, metadata):
    """
    runs a baseline mode without tool use 

    Args:
        client: the LLM client
        case_name: name of the case
        context_text: the relevant text depending on the experimental setup
        run_id: run number
        metadata: experiment metadata

    Returns:
        answer: the verdict of the case 
    """
    
    logger.debug(f"\nSTARTING BASELINE MODE: {case_name} (Run {run_id})")
    
    #get experiment type
    config_num = metadata.get('config') if metadata and 'config' in metadata else 'X'
    
    #directory structure for ouput: {case}/{run_id}/config_{config}/baseline/
    log_dir = os.path.join(BASE_CASE_DIR, case_name, f"run_{run_id}", f"config_{config_num}", "baseline")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "log.json")
    if os.path.exists(log_file):
        os.remove(log_file)
    
    start_time = time.time()
    
    prompt = (
        f"You are objectively assessing Inventive Step for the European Patent Office (EPO). These cases are appeals against the examaining boards original decision.\n"
        f"Use the data provided. Try to avoid using outside knowledge, except for common knowledge where you may use yor own judgement, if you believe this would have been known prior to the common knowledge cut-off date given.\n"
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

    #run the prompt
    ans, reas = await consult_llm(prompt, [], client, 1, log_file, question=prompt, generation_mode="baseline", metadata=metadata)
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    #writes time to data log
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
    
    return ans.upper()

async def run_tool_session(client, case_name, context_text, run_id, metadata, train_data=False):
    """
    runs the tool session

    Args:
        client (_type_): _description_
        case_name (_type_): _description_
        context_text (_type_): _description_
        run_id (_type_): _description_
        metadata (_type_): _description_
    """
    
    logger.debug(f"\nSTARTING TOOL MODE: {case_name} (Run {run_id})")

    config_num = metadata.get('config') if metadata and 'config' in metadata else 'X'
    mode = metadata.get('mode') if metadata and 'mode' in metadata else 'tool'

    #directory structure: {case}/{run_id}/config_{config}/tool/
    if train_data:
        log_dir = os.path.join(BASE_CASE_DIR, case_name, f"run_{run_id}", f"config_{config_num}", "train")
    else:
        log_dir = os.path.join(BASE_CASE_DIR, case_name, f"run_{run_id}", f"config_{config_num}", "tool")

    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "log.json")
    if os.path.exists(log_file):
        os.remove(log_file)
        
    start_time = time.time()
    
    #prep the UI.py i.e. the ADM tool
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-u', ADM_SCRIPT_PATH,
        '--run_id', str(run_id),
        '--config', str(config_num),
        '--mode', str(mode),
        '--folder_base', str(BASE_CASE_DIR),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    history = []
    turn = 1
    buffer = []
    final_verdict = "UNKNOWN"
    
    while True:
        
        #tries to asyncronously read the ADM tool output
        try:
            chunk = await asyncio.wait_for(process.stdout.read(4096), timeout=0.25)
            
            #end tool conversation if no more output
            if not chunk: 
                break
            
            decoded_chunk = chunk.decode('utf-8', errors='replace')
            buffer.append(decoded_chunk)
            
            if decoded_chunk.strip():
                print(f"[STDOUT from UI.py]: {decoded_chunk.strip()}")
                
        except asyncio.TimeoutError:
            pass

        combined = "".join(buffer)
        clean = ADM_text_clean(combined)
        
        if not clean and process.returncode is None:
            continue
        
        if process.returncode is not None and not clean:
            break

        #detect prompt logic eith [Q] or sentence endings as backup
        is_prompt = False
        
        if re.search(r"\[Q\d*\]", clean):
            is_prompt = True
        elif any(l.strip().startswith(p) for l in clean.splitlines() for p in ("QUESTION:", "GUESS:")):
            is_prompt = True
        elif "enter your choice" in clean.lower():
            is_prompt = True
        elif clean.strip().endswith("?") or clean.strip().endswith(":"):
            is_prompt = True

        #deal with case name automatically 
        if "[Q] Enter case name" in clean:
            logger.debug(f"[STDIN to UI.py]: {case_name}")
            try:
                process.stdin.write((case_name + "\n").encode('utf-8'))
                await process.stdin.drain()
            except (ConnectionResetError, BrokenPipeError) as e:
                logger.error(f"ADM subprocess stdin closed while writing case name: {e}")
                break
            buffer = []
            continue
        
                #this mode gives access to the decision and real reasons to allow generation of training data for critic system
        if train_data:
            reasons = str(RAW_DATA.loc[RAW_DATA['Reference'] == case_name, 'Decision Reasons'].iloc[0])
            decision = str(RAW_DATA.loc[RAW_DATA['Reference'] == case_name, 'Order'].iloc[0])
            
            system_instruction = ("You are helping annotate legal factors to help in assessing Inventive Step for the European Patent Office (EPO). These cases are appeals against the examaining boards original decision.\n"
                                    "Only use the data provided. Try to avoid using outside knowledge, except for common knowledge where you may use yor own judgement, if you believe this would have been known prior to the common knowledge cut-off date given.\n"
                                    "However, you can make reasonable assumptions not explicitly contained within the data.\n"
                                    "You will be given access to the patent claims, closest prior art document/s, the reasons for decision and the outcome of the case.\n"
                                    "Remember with the outcome that if a decision is 'Affirmed' then inventive step is not present; if it 'Reversed' then it is present.\n"
                                    "Be as faithful to the actual reasoning as possible, we want to map the decision as closely as possible."
                                    f"=== CASE DATA ===\n{context_text}\n=== END CASE DATA ===\n\n"
                                    f"=== REASONS FOR DECICISION ===\n{reasons}\n=== END REASONS FOR DECIISION ===\n\n"
                                    f"=== DECISION ===\n{decision}\n=== END DECISION ===\n\n"
                                    f"INSTRUCTIONS:\n"
                                    f"1. Answer questions based ONLY on the text above.\n"
                                    f"2. Output valid JSON with keys 'reasoning' and 'answer'."
            )
            
        else:
            system_instruction = (
            f"You are objectively assessing Inventive Step for the European Patent Office (EPO). These cases are appeals against the examaining boards original decision.\n"
            f"Use the data provided. Try to avoid using outside knowledge, except for common knowledge where you may use yor own judgement, if you believe this would have been known prior to the common knowledge cut-off date given.\n"
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

        if is_prompt:
                        
            q_text = clean
            
            #consult the LLM
            ans, reas = await consult_llm(system_instruction, history, client, turn, log_file, question=q_text, generation_mode="tool", metadata=metadata)
            
            if ans == "ERROR": 
                process.terminate()
                break
            
            logger.debug(f"[STDIN to UI.py]: {ans}")
            #write output to ADM tool (guard against closed stdin)
            try:
                process.stdin.write((str(ans) + "\n").encode('utf-8'))
                await process.stdin.drain()
            except (ConnectionResetError, BrokenPipeError) as e:
                logger.error(f"ADM subprocess stdin closed while writing answer: {e}")
                try:
                    process.kill()
                except Exception:
                    pass
                break

            #track response history 
            history.append({"role": "user", "content": q_text})
            history.append({"role": "assistant", "content": json.dumps({"reasoning": reas, "answer": ans})})
            turn += 1
            buffer = []
            await asyncio.sleep(0.1) 
            
    #final verdict
    final_combined = "".join(buffer).strip()
    if final_combined:
        print(f"[STDOUT Final]: {final_combined}")

    #allow CLI override of summary question
    global SUMMARY_OVERRIDE_ALLOWED
    if globals().get('SUMMARY_OVERRIDE_ALLOWED', False):
        summary_question = (
            "Based on the session interaction above, what is your final outcome?\n"
            "You may disagree with the answer provided by the inventive step tool if your reasoning justifies it.\n"
            "State a single final decision on whether an inventive step is present: 'Yes' or 'No'."
        )
    
    else:
        
        if train_data:            
            summary_question = (
                "Based on the session interaction above and the real outcome of the case you have been given. Are the outcomes the same and does the resaoning make sense from the real decision's reasoning? i.e. if the case was affirmed or dismissed then inventive step was likely not present but if the outcome was reversed then it must be present. State whether the outcome here does match the real outcome true with 'Yes' or 'No'\n"
                )
        
            context_for_final = f"SESSION OUTPUT:\n{final_combined}\n\n{summary_question}"
            
            logger.debug(context_for_final)
            
            final_ans, final_reas = await consult_llm(system_instruction, history, client, turn, log_file, question=context_for_final, generation_mode="tool", metadata=metadata, train_data=True)
        
        else:
            summary_question = (
            "Based on the session interaction above, what was the final outcome?\n"
            "State a single final decision based on whether an inventive step is present: 'Yes' or 'No'."
            )

            context_for_final = f"SESSION OUTPUT:\n{final_combined}\n\n{summary_question}"
            
            logger.debug(context_for_final)
            
            final_ans, final_reas = await consult_llm(context_for_final, history, client, turn, log_file, question=context_for_final, generation_mode="baseline", metadata=metadata)
        
    end_time = time.time()
    elapsed = end_time - start_time
    
    #add timing to log
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

    if final_ans != "ERROR":
        final_verdict = final_ans.upper()
        
    print(f"Tool Session for {case_name} (Run {run_id}) Finished. Verdict: {final_verdict}. Time: {elapsed:.2f}s")

    return final_verdict   

async def run_ensemble_session(client, case_name, context_text, run_id, metadata):
    """
    Ensemble tool-mode session.

    """
    #

    ENSEMBLE_Q_IDS = [17, 380, 32, 36, 39, 49]  # user will populate as needed, e.g. [1, 5, 38]

    logger.debug(f"\nSTARTING ENSEMBLE MODE: {case_name} (Run {run_id})")

    config_num = metadata.get('config') if metadata and 'config' in metadata else 'X'
    mode = metadata.get('mode') if metadata and 'mode' in metadata else 'tool'

    # directory structure: {case}/{run_id}/config_{config}/ensemble/
    log_dir = os.path.join(BASE_CASE_DIR, case_name, f"run_{run_id}", f"config_{config_num}", "ensemble")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "log.json")
    if os.path.exists(log_file):
        os.remove(log_file)

    start_time = time.time()

    # prepare ADM subprocess (same as tool)
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-u', ADM_SCRIPT_PATH,
        '--run_id', str(run_id),
        '--config', str(config_num),
        '--mode', str(mode),
        '--folder_base', str(BASE_CASE_DIR),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )

    history = []
    turn = 1
    buffer = []
    final_verdict = "UNKNOWN"

    async def parse_raw(raw):
        try:
            parsed = json.loads(raw)
            return parsed.get('answer', ''), parsed.get('reasoning', ''), raw
        except Exception:
            return raw, raw, raw

    model_id = CURRENT_CONFIG["id"]

    while True:
        # read ADM stdout
        try:
            chunk = await asyncio.wait_for(process.stdout.read(4096), timeout=0.25)
            if not chunk:
                break
            decoded_chunk = chunk.decode('utf-8', errors='replace')
            buffer.append(decoded_chunk)
            if decoded_chunk.strip():
                print(f"[STDOUT from UI.py]: {decoded_chunk.strip()}")
        except asyncio.TimeoutError:
            pass

        combined = "".join(buffer)
        clean = ADM_text_clean(combined)

        if not clean and process.returncode is None:
            continue
        if process.returncode is not None and not clean:
            break

        # detect prompts same heuristic as tool session
        is_prompt = False
        q_nums = set()
        
        if re.search(r"\[Q\d*\]", clean):
            is_prompt = True
            # extract all question ids present
            q_nums = set(int(x) for x in re.findall(r"\[Q(\d+)\]", clean))

        elif any(l.strip().startswith(p) for l in clean.splitlines() for p in ("QUESTION:", "GUESS:")):
            is_prompt = True
        elif "enter your choice" in clean.lower():
            is_prompt = True
        elif clean.strip().endswith("?") or clean.strip().endswith(":"):
            is_prompt = True

        # auto-enter case name
        if "[Q] Enter case name" in clean:
            logger.debug(f"[STDIN to UI.py]: {case_name}")
            try:
                process.stdin.write((case_name + "\n").encode('utf-8'))
                await process.stdin.drain()
            except (ConnectionResetError, BrokenPipeError) as e:
                logger.error(f"ADM subprocess stdin closed while writing case name: {e}")
                break
            buffer = []
            continue

        if is_prompt:
            system_instruction = (
                f"You are objectively assessing Inventive Step for the European Patent Office (EPO). These cases are appeals against the examaining boards original decision.\n"
                f"Use the data provided. Try to avoid using outside knowledge, except for common knowledge where you may use yor own judgement, if you believe this would have been known prior to the common knowledge cut-off date given.\n"
                f"However, you can make reasonable assumptions not explicitly contained within the data.\n"
                f"Do not just do as the data tells you directly, i.e. if the data says party X has appealed because they believe invention I has inventive step, do not just assume they are correct.\n"
                f"Your job is to critically analysis the information given to you to come to an informed, reasoned judgment.\n"
                f"You will be asked questions generated from an argumentation tool designed for inventive step to help you reason to a conclusion on whether inventive step is present.\n"
                f"Do not try and answer the questions to guarantee a certain outcome because you believe that is the correct one, just answer them as objectively as possible.\n"
                f"You are trying to objectively assess whether inventive step is present, when answering each question think carefully and use your own critical analysis and discretion.\n "
                f"=== CASE DATA ===\n{context_text}\n=== END CASE DATA ===\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Answer questions based ONLY on the text above.\n"
                f"2. Output valid JSON with keys 'reasoning' and 'answer'."
            )

            q_text = clean

            use_ensemble_here = bool(ENSEMBLE_Q_IDS and (q_nums & set(ENSEMBLE_Q_IDS)))

            # If ensemble is configured for this question, run ensemble logic
            if use_ensemble_here:
                samples = []
                for _ in range(int(globals().get("ENSEMBLE_N", 3))):
                    # build request
                    base_req = {
                        "model": model_id,
                        "messages": [{"role": "user", "content": f"{system_instruction}\n\nHISTORY:\n{''.join([h['content'] for h in history[-10:]])}\n\nCURRENT QUESTION: {q_text}"}],
                        "max_tokens": 8096,
                        "temperature": float(globals().get("ENSEMBLE_TEMP", 0.9)),
                        "reasoning_effort": "medium",
                        "top_p": 1,
                        "extra_body": {"guided_json": ADM_INTERFACE.model_json_schema()},
                    }
                    try:
                        async with REQUEST_SEMAPHORE:
                            cresp = await asyncio.wait_for(client.chat.completions.create(**base_req), timeout=120)
                        raw = cresp.choices[0].message.content.strip()
                    
                    except Exception as e:
                        raw = f"[ERROR] {e}"
                    
                    ans_i, reas_i, raw_i = await parse_raw(raw)
                    samples.append({'answer': str(ans_i).strip(), 'reasoning': reas_i})

                # Send ALL samples to the deterministic verifier (no majority pre-selection)
                hidden_reasoning = None
                # safe fallback sample values
                fallback_sample = samples[0] if samples else {'answer': '', 'reasoning': ''}
                fallback_answer = fallback_sample.get('answer', '')
                fallback_reasoning = fallback_sample.get('reasoning', '')

                verify_payload = {
                    "instruction": (
                        "For this question you will also be given an array 'ensemble_samples' of other opinions on the question's answer (each item has 'answer','reasoning').\n"
                        "Using ALL samples, decide the final answer and provide a concise final_reasoning and provide the JSON as stated previously.\n"
                    ),
                    "ensemble_samples": samples
                    #"metadata": {"case": case_name, "question_text": q_text},
                }

                verify_prompt = f"{system_instruction}\n\nHISTORY:\n{''.join([h['content'] for h in history[-10:]])}\n\nCURRENT QUESTION: {q_text}" + "\n\n" + json.dumps(verify_payload, indent=2)
                
                logger.debug('VERIFY_PROMPT: ' + verify_prompt + '\n')

                try:
                    vreq = {
                        "model": model_id,
                        "messages": [{"role": "user", "content": verify_prompt}],
                        "max_tokens": 8096,
                        "reasoning_effort": "medium",
                        "top_p": 0.9,
                        "seed":42,
                        "temperature": float(globals().get("VERIFIER_TEMP", 0.0)),
                        "extra_body": {"guided_json": ADM_INTERFACE.model_json_schema()},
                    }
                    async with REQUEST_SEMAPHORE:
                        vresp = await asyncio.wait_for(client.chat.completions.create(**vreq), timeout=60)
                    vraw = vresp.choices[0].message.content.strip()
                    try:
                        vparsed = json.loads(vraw)
                        final_answer = str(vparsed.get('final_answer', fallback_answer)).strip()
                        final_reasoning = vparsed.get('final_reasoning', fallback_reasoning)
                        hidden_reasoning = getattr(vresp.choices[0].message, "reasoning_content", None)
                    except Exception:
                        # fallback to first sample if verifier returns non-JSON
                        final_answer = fallback_answer
                        final_reasoning = fallback_reasoning
                except Exception:
                    final_answer = fallback_answer
                    final_reasoning = fallback_reasoning

                # log ensemble samples and final
                log_to_json(turn, q_text, json.dumps({'ensemble_samples': samples}), final_reasoning, final_answer, model_id, hidden_reasoning, file_path=log_file, metadata=metadata)
                ans, reas = final_answer, final_reasoning

            else:
                # fallback: single tool-style consult
                ans, reas = await consult_llm(system_instruction, history, client, turn, log_file, question=q_text, generation_mode="tool", metadata=metadata)
                if ans == "ERROR":
                    process.terminate()
                    break

            logger.debug(f"[STDIN to UI.py]: {ans}")
            
            try:
                process.stdin.write((str(ans) + "\n").encode('utf-8'))
                await process.stdin.drain()
            except (ConnectionResetError, BrokenPipeError) as e:
                logger.error(f"ADM subprocess stdin closed while writing answer: {e}")
                try:
                    process.kill()
                except Exception:
                    pass
                break

            # track history
            history.append({"role": "user", "content": q_text})
            history.append({"role": "assistant", "content": json.dumps({"reasoning": reas, "answer": ans})})
            turn += 1
            buffer = []
            await asyncio.sleep(0.1)

    # final verdict (same post-processing as tool session)
    final_combined = "".join(buffer).strip()
    if final_combined:
        print(f"[STDOUT Final]: {final_combined}")

    global SUMMARY_OVERRIDE_ALLOWED
    if globals().get('SUMMARY_OVERRIDE_ALLOWED', False):
        summary_question = (
            "Based on the session interaction above, what is your final outcome?\n"
            "You may disagree with the answer provided by the inventive step tool if your reasoning justifies it.\n"
            "State a single final decision on whether an inventive step is present: 'Yes' or 'No'."
        )
    else:
        summary_question = (
            "Based on the session interaction above, what was the final outcome?\n"
            "State a single final decision based on whether an inventive step is present: 'Yes' or 'No'."
        )

    context_for_final = f"SESSION OUTPUT:\n{final_combined}\n\n{summary_question}"
    logger.debug(context_for_final)

    final_ans, final_reas = await consult_llm(context_for_final, history, client, turn, log_file, question=None, generation_mode="summary", metadata=metadata)

    end_time = time.time()
    elapsed = end_time - start_time

    # write timing into log
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

    if final_ans != "ERROR":
        final_verdict = final_ans.upper()

    print(f"Ensemble Session for {case_name} (Run {run_id}) Finished. Verdict: {final_verdict}. Time: {elapsed:.2f}s")
    return final_verdict

def load_context(data_path, case_name, dataset, config):
    """
    loads the appropriate data context

    Args:
        base_path (_type_): _description_
        case_name (_type_): _description_
        dataset (_type_): _description_
        config (_type_): _description_

    Returns:
        _type_: _description_
    """
    
    path = os.path.join(data_path, case_name)
    parts = []

    #for initial comvik exps
    if dataset == "comvik":
        
        cpa = os.path.join(path, "CPA.txt")
        
        if os.path.exists(cpa): 
            parts.append(f"--- CLOSEST PRIOR ART INFORMATION---\n{open(cpa).read()}")
        
        if config == 1:
            pat = os.path.join(path, "patent.txt")
            if os.path.exists(pat): 
                parts.append(f"--- PATENT APPLICATION CLAIMS ---\n{open(pat).read()}")
        
        elif config == 2:
            full = os.path.join(path, "full.txt")
            if os.path.exists(full): 
                parts.append(f"--- FULL REASONING ABOUT THE PATENT APPLICATION ---\n{open(full).read()}")

    #for test cases
    else:
        
        appeal = os.path.join(path, "appeal.txt")
        claims = os.path.join(path, "claims.txt")
        cpa = os.path.join(path, "CPA.txt")

        #just appeal summary text
        if config == 1:
            if os.path.exists(appeal): 
                parts.append(f"--- SUMMARY OF FACTS FROM THE APPEAL ---\n{open(appeal).read()}")
        
        #claims + cpa
        elif config == 2:
            if os.path.exists(claims): 
                parts.append(f"--- PATENT APPLICATION CLAIMS ---\n{open(claims).read()}")
            
            if os.path.exists(cpa): 
                parts.append(f"--- CLOSEST PRIOR ART DOCUMENT/S ---\n{open(cpa).read()}")
        
        #appeal summary + claims + cpa
        elif config == 3:
            if os.path.exists(appeal): 
                parts.append(f"--- SUMMARY OF FACTS FROM THE APPEAL ---\n{open(appeal).read()}")
            
            if os.path.exists(claims): 
                parts.append(f"--- PATENT APPLICATION CLAIMS ---\n{open(claims).read()}")
            
            if os.path.exists(cpa): 
                parts.append(f"--- CLOSEST PRIOR ART DOCUMENT/S ---\n{open(cpa).read()}")
            
    #add the filing date 
    try:
        print(case_name)
        year = str(RAW_DATA.loc[RAW_DATA['Reference'] == case_name, 'Year'].iloc[0])
    except:
        year = "UNKNOWN"
        
    parts.append(f"--- COMMON KNOWLEDGE DATE CUTOFF ---\n{year}")

    return "\n\n".join(parts)

async def run_experiment_batch(data_path, dataset, experiment_config, mode, num_runs, client):
    """
    batch run the experiments in parallel

    Args:
        data_path: the filepath for the dataset
        dataset: the dataset either test or comvik
        experiment_config: choose exp setup 1,2,3
        mode: tool or baseline
        num_runs: number of runs
        client: the LLM client

    Returns:
        None
    """
    
    if not os.path.exists(data_path):
        print(f"Error: Data path {data_path} does not exist.")
        return

    #sort the cases and gather them 
    cases = sorted([d for d in os.listdir(data_path) if os.path.isdir(os.path.join(data_path, d))])
    print(f"Found {len(cases)} cases in {dataset} set. Starting {num_runs} runs...")

    #stores results for each run 
    all_runs_results = {}

    for i in range(1, num_runs + 1):
        print(f"\n{'==='} STARTING RUN {i}/{num_runs} {'==='}")
        
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
            
            elif mode == 'train':
                tasks.append(run_tool_session(client, case, context, i, metadata, train_data=True))
            
            elif mode == 'ensemble':
                tasks.append(run_ensemble_session(client, case, context, i, metadata))
            
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
        json_filename = f"{BASE_CASE_DIR}/results_{dataset}_{mode}_config{experiment_config}.json"
        with open(json_filename, 'w') as f:
            json.dump(all_runs_results, f, indent=4)
        print(f"\nExperiment Completed. Results saved to {json_filename}")

async def async_main():
    """
    main code
    """
    #track cli args
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="gpt", choices=["gpt", "llama", "gpt_small"]) 
    parser.add_argument('--gpu', type=str, default='gpu31')
    parser.add_argument('--dataset', type=str, choices=['comvik', 'main'], required=True)
    parser.add_argument('--data_path', type=str, default="../Data/VALIDATION")
    parser.add_argument('--exp_config', type=int, required=True)
    parser.add_argument('--temperature', type=float, default=0.0, help='Sampling temperature for LLM (default: 0.1)')
    parser.add_argument('--mode', type=str, default='tool', choices=['tool', 'baseline','ensemble','train'])
    parser.add_argument('--runs', type=int, default=1, help="Number of times to repeat the experiment.")
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--raw_data', type=str, default="../Data/Inv_Step_Sampled_Valid.pkl", help='Path to RAW_DATA pickle')
    parser.add_argument('--base_case_dir', type=str, default="../Outputs/Valid_Cases", help='Base output folder for case logs')
    parser.add_argument('--ensemble_n', type=int, default=3, help='Number of ensemble samples')
    parser.add_argument('--ensemble_temp', type=float, default=1, help='Temperature for ensemble sampling')
    parser.add_argument('--verifier_temp', type=float, default=0.0, help='Temperature for deterministic verifier')
    parser.add_argument('--allow_summary_override', action='store_true', help='Allow LLM to override the tool answer in the summary question if justified.')

    args = parser.parse_args()

    #if user flags --debug, switch level to DEBUG
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)        
        print("--- DEBUG MODE ENABLED ---")
    
    global CURRENT_CONFIG
    CURRENT_CONFIG = MODELS.get(args.model, MODELS['gpt'])

    # initialise BASE_CASE_DIR and RAW_DATA from CLI args
    global BASE_CASE_DIR, RAW_DATA
    BASE_CASE_DIR = args.base_case_dir
    try:
        RAW_DATA = pd.read_pickle(args.raw_data)
    except Exception as e:
        logger.warning(f"Could not load RAW_DATA from {args.raw_data}: {e}")
        RAW_DATA = pd.DataFrame()

    #ensemble/verifier globals
    global ENSEMBLE_N, ENSEMBLE_TEMP, VERIFIER_TEMP
    ENSEMBLE_N = args.ensemble_n
    ENSEMBLE_TEMP = args.ensemble_temp
    VERIFIER_TEMP = args.verifier_temp

    #store temperature globally for use in consult_llm
    global LLM_TEMPERATURE
    LLM_TEMPERATURE = args.temperature

    #input the api to your LLM here!!!
    API_BASE = f"http://{args.gpu}.barkla2.liv.alces.network:8000/v1"
    
    try:
        #use async client for the LLM
        client = AsyncOpenAI(base_url=API_BASE, api_key="EMPTY")
    except:
        print("Error: LLM API unreachable.")
        return

    #run exp
    await run_experiment_batch(args.data_path, args.dataset, args.exp_config, args.mode, args.runs, client)

if __name__ == "__main__":
    asyncio.run(async_main())