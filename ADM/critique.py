import json
import os
import argparse
import pickle
import pandas as pd
from typing import Dict, Any
from inventive_step_ADM import question_mapping
import re
import asyncio
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
import logging
import time
import random
import traceback


# bounded concurrency for LLM calls from this script
REQUEST_SEMAPHORE = asyncio.Semaphore(20)
logger = logging.getLogger("critique")

#sets JSON structure for output
class OUTPUT(BaseModel):
    critique: str = Field(..., description="Start with stating either Warning or Precedent. Then proceed to a self-contained critique which should be understandable on its own if one has not read any of the case material. do not mention 'the model' or 'the prediction' or 'the ground truth'. state the legal principle as absolute fact.")
    answer: str = Field(..., description="the answer either MATCH or MISMATCH")
    
async def consult_llm(system_prompt, client, metadata=None, timeout=30, max_retries=4):
    """Local async LLM caller used by critique pipeline.

    Mirrors core behaviour from `hybrid_patent_system.consult_llm` but kept local
    so `critique.py` can run independently. Returns a tuple `(answer, reasoning)`.
    On failure returns `("ERROR", "API Call Failed")`.
    """

    model_id = "gpt-oss-120b"

    messages = [{"role": "user", "content": system_prompt}]
    
    guided_json = OUTPUT.model_json_schema()
    
    base_req = {
        "model": model_id,
        "messages": messages,
        "max_tokens": 8096,
        "reasoning_effort": "medium",
        "temperature": 0.0,
        "top_p": 1.0,
        "seed": 42,
        "extra_body": {"guided_json": guided_json},
    }

    base_backoff = 0.5

    for attempt in range(1, max_retries + 1):
        try:
            async with REQUEST_SEMAPHORE:
                coro = client.chat.completions.create(**base_req)
                resp = await asyncio.wait_for(coro, timeout=timeout)

            # extract response text
            raw_content = ""
            try:
                raw_content = resp.choices[0].message.content.strip()
            except Exception:
                raw_content = str(resp)

            logger.debug(f"[LLM RESPONSE] (len={len(raw_content)}): {raw_content[:400]}")

            # attempt to parse JSON with fields 'answer' and 'reasoning'
            answer = None
            reasoning = ""
            try:
                parsed = json.loads(raw_content)
                if isinstance(parsed, dict):
                    answer = parsed.get('answer') or parsed.get('final_answer') or parsed.get('verdict')
                    reasoning = parsed.get('critique') or parsed.get('explanation') or ""

            except Exception:
                # not JSON — fall back to heuristics: last line as answer if short
                lines = [l.strip() for l in raw_content.splitlines() if l.strip()]
                if lines:
                    last = lines[-1]
                    # if last line is a single token like 'Yes'/'No' or 'MATCH'/'MISMATCH'
                    if re.fullmatch(r"[A-Za-z\s]{1,40}", last) and len(last.split()) <= 4:
                        answer = last
                        reasoning = "\n".join(lines[:-1])

            if answer is None:
                # fallback: use full content as answer (so caller can inspect)
                answer = raw_content

            return (answer, reasoning)

        except asyncio.TimeoutError as te:
            logger.warning(f"LLM call timed out on attempt {attempt}/{max_retries}: {te}")
            err = te
        except Exception as e:
            logger.warning(f"LLM request exception (attempt {attempt}/{max_retries}): {type(e).__name__}: {e}")
            logger.debug("Traceback:\n" + "".join(traceback.format_exception(type(e), e, e.__traceback__)))
            err = e

        # decide to retry or give up
        if attempt >= max_retries:
            logger.error(f"LLM call failed after {max_retries} attempts: {err}")
            return ("ERROR", "API Call Failed")

        # backoff + jitter
        backoff = base_backoff * (2 ** (attempt - 1))
        jitter = random.uniform(0, backoff * 0.5)
        await asyncio.sleep(backoff + jitter)


RAW_DATA = pd.read_pickle('../Data/train_data_Inv_Step.pkl')

# invert question_mapping: map numeric tag -> list of factor keys
Q_TO_FACTORS = {}
for k, v in question_mapping.items():
    Q_TO_FACTORS.setdefault(v, []).append(k)

def extract_q_tag(text):
    """Extracts Q num from Q text"""
    match = re.search(r'\[Q(\d+)\]', text)
    if match:
        return int(f"{match.group(1)}")
    return None

async def process_case(truth_path: str, pred_path: str, case_id: str, client: AsyncOpenAI):
    
    # 1. Load Data
    try:
        with open(truth_path, 'r', encoding='utf-8') as f: truth_data = json.load(f)
        with open(pred_path, 'r', encoding='utf-8') as f: pred_data = json.load(f)
    except Exception as e:
        print(f"Error loading {case_id}: {e}")
        return []

    
    # Build mappings of truth and predictions by question tag (Q number)
    truth_by_q = {}
    
    for item in truth_data:
        q_text = item.get('question', '')
        tag = extract_q_tag(q_text)
        entry = {
            'question': q_text,
            'answer': item.get('answer'),
            'reasoning': item.get('reasoning', ''),
            'raw': item
        }
        if tag is not None:
            truth_by_q.setdefault(tag, []).append(entry)

    pred_by_q = {}
    
    for item in pred_data:
        q_text = item.get('question', '')
        tag = extract_q_tag(q_text)
        entry = {
            'question': q_text,
            'answer': item.get('answer'),
            'reasoning': item.get('reasoning', ''),
            'raw': item
        }
        if tag is not None:
            pred_by_q.setdefault(tag, []).append(entry)

    # For each question tag, produce a single summary record that:
    # - lists candidate factor keys (from `question_mapping`)
    # - records truth/pred answers and reasonings
    # - attempts to map those answers to factor keys (heuristic)
    # - sets `match=True` if any mapped keys intersect
    question_pairs = []
    
    for tag in sorted(set(list(truth_by_q.keys()) + list(pred_by_q.keys()))):
        
        truths = truth_by_q.get(tag, []) or None
        preds = pred_by_q.get(tag, []) or None
        
        if truths is None or preds is None:
            print(f'Skipping {tag} as no truth or prediction found',)
            continue

        truth_question_text = [t.get('question') for t in truths]
        pred_question_text = [t.get('question') for t in preds]
          
        truth_answers = [t.get('answer') for t in truths]
        truth_reasonings = [t.get('reasoning') for t in truths]
    
        pred_answers = [p.get('answer') for p in preds]
        pred_reasonings = [p.get('reasoning') for p in preds]
        
        question_pairs.append({
            'case_id': case_id,
            'q_tag': tag,
            'truth_questions': truth_question_text,
            'truth_answers': truth_answers,
            'truth_reasonings': truth_reasonings,
            'pred_questions': pred_question_text,
            'pred_answers': pred_answers,
            'pred_reasonings': pred_reasonings
        })
        
    tasks = []

    for pair in question_pairs:
        
        id = pair['case_id']
        
        try:
            board_reasons = str(RAW_DATA.loc[RAW_DATA['Reference'] == id, 'Decision Reasons'].iloc[0])
            summary = str(RAW_DATA.loc[RAW_DATA['Reference'] == id, 'Summary Facts'].iloc[0])

        except:
            raise NameError('No case id in RAW_DATA')
        
        if len(pair['pred_questions']) > 1:
            
            print(pair['pred_questions'])
        
            # 2. Iterate through Predictions ONE BY ONE
            for i, q_text in enumerate(pair['pred_questions']):
                
                sys_reasoning = pair['pred_reasonings'][i]
                sys_answer = pair['pred_answers'][i]
                

                # 3. Create the Prompt for this specific prediction
                # We embed the WHOLE truth menu so the LLM can find the semantic match
               
                prompt = ("You will be acting like a patent examiner helping to annotate legal factors to help in assessing Inventive Step for the European Patent Office (EPO). These cases are appeals against the examaining boards original decision.\n"
                      "The overall system uses a formal argumentation model and uses an LLM to answer question to reason to a decision."
                      "You will be provided with the question, reasoning and answer to a legal factor given by the Board of Appeals (our ground truth) and one given by an LLM model as a prediction."
                      "Your task is to provide feedback on the prediction using the ground truth and to determine whether it is a MATCH the outcomes and the reasoning align for both the ground truth and the prediction or a MISMATCH if this is not the case."
                      "Please provide an explanation as to why the prediction and ground truth answers/reasoning are a MATCH or MISMATCH."
                      "If it is a MATCH please formulate a 'precedent' style rule explaining why this worked. If it is a MISMATCH formulate a 'warning' rule explaining why the reasoning went wrong. These rules will be used in a future system."
                      "Do not ever mention vague terms like 'the model' or 'the prediction' or 'the ground truth' in the critique. State the specific legal principle. Give technical details as evidence."
                      "I will also provide you with the summary of facts from the appeal to give you some context for your critique."
                      "You will be given multiple different questions, reasoning and answers for the ground truth as these do not necessarily directly align with the predictions. The ground truth questions align in the order they are given i.e. the first TRUTH question aligns with the first TRUTH answer."
                      "Select the truth question/reasoning/answer set which best matches the prediction to judge whether it is a MATCH or MISMATCH using that. The most important part is the clear critique which illuminates the resaoning process using either a 'warning' or a 'precedent'. "
                      
                        f"=== CASE DATA ===\n{summary}\n=== END CASE DATA ===\n\n"
                        f"=== PREDICTION QUESTION ===\n{q_text}\n=== END QUESTION ===\n\n"
                        f"=== PREDICTION REASONING ===\n{sys_reasoning}\n=== END REASONING ===\n\n"
                        f"=== PREDICTION ANSWER ===\n{sys_answer}\n=== END ANSWER ===\n\n"
                        f"=== TRUTH QUESTIONS ===\n{pair['truth_questions']}\n=== END QUESTIONS ===\n\n"
                        f"=== TRUTH REASONING ===\n{pair['truth_reasonings']}\n=== END REASONING ===\n\n"
                        f"=== TRUTH ANSWERS ===\n{pair['truth_answers']}\n=== END ANSWERS ===\n\n"
                        f"INSTRUCTIONS:\n"
                        f"1. Answer questions based ONLY on the text above.\n"
                        f"1. Output valid JSON with keys 'critique' and 'answer'. Ensuring the explanation is understandable to someone who has never read the ground truth or any of the case details."
            )
                # schedule the consult_llm call as a Task for this specific prediction
                task = asyncio.create_task(consult_llm(prompt, client, metadata={"temperature": 0.0}))
                meta = {
                    "case_id": pair['case_id'],
                    "q_tag": pair['q_tag'],
                    "pred_index": i,
                    "pred_question": q_text,
                    "pred_answer": sys_answer,
                    "pred_reasoning": sys_reasoning,
                    "truth_questions": pair['truth_questions'],
                    "truth_answers": pair['truth_answers'],
                    "truth_reasonings": pair['truth_reasonings'],
                    "prompt": prompt,
                }
                tasks.append((task, meta))
                
        else:

            prompt = ("You will be acting like a patent examiner helping to annotate legal factors to help in assessing Inventive Step for the European Patent Office (EPO). These cases are appeals against the examaining boards original decision.\n"
                      "The overall system uses a formal argumentation model and uses an LLM to answer question to reason to a decision."
                      "You will be provided with the question, reasoning and answer to a legal factor given by the Board of Appeals (our ground truth) and one given by an LLM model as a prediction."
                      "Your task is to provide feedback on the prediction using the ground truth and to determine whether it is a MATCH the outcomes and the reasoning align for both the ground truth and the prediction or a MISMATCH if this is not the case."
                      "Do not merely state that the answers are different, you must abstract the legal principle."
                      "If it is a MATCH please formulate a 'precedent' style rule explaining why this worked. If it is a MISMATCH formulate a 'warning' rule explaining why the reasoning went wrong. These rules will be used in a future system."
                      "Do not ever mention vague terms like 'the model' or 'the prediction' or 'the ground truth' in the critique. State the specific legal principle. Give technical details as evidence."
                      "I will also provide you with the summary of facts from the appeal to give you some context for your critique."
                      "Sometimes the truth question may differ to the prediction question, do not penalize the prediction for this unless there is something objectively incorrect as there are many ways of phrasing similar information." 
                      "The most important part is the clear critique which illuminates the resaoning process using either a 'warning' or a 'precedent'."
                       
                        f"=== CASE DATA ===\n{summary}\n=== END CASE DATA ===\n\n"
                        f"=== PREDICTION QUESTION ===\n{pair['pred_questions']}\n=== END QUESTION ===\n\n"
                        f"=== PREDICTION REASONING ===\n{pair['pred_reasonings']}\n=== END REASONING ===\n\n"
                        f"=== PREDICTION ANSWER ===\n{pair['pred_answers']}\n=== END ANSWER ===\n\n"
                        f"=== TRUTH QUESTIONS ===\n{pair['truth_questions']}\n=== END QUESTIONS ===\n\n"
                        f"=== TRUTH REASONING ===\n{pair['truth_reasonings']}\n=== END REASONING ===\n\n"
                        f"=== TRUTH ANSWERS ===\n{pair['truth_answers']}\n=== END ANSWERS ===\n\n"
                        f"INSTRUCTIONS:\n"
                        f"1. Answer questions based ONLY on the text above.\n"
                        f"1. Output valid JSON with keys 'critique' and 'answer'. Ensuring the explanation is understandable to someone who has never read the ground truth or any of the case details."
            )
                   
            # schedule the consult_llm call as a Task and keep metadata inline (no separate wrapper function)
            task = asyncio.create_task(consult_llm(prompt, client, metadata={"temperature": 0.0}))
            # This branch uses the older single-prompt format where prediction fields are lists.
            # Record the full lists (so caller can inspect alignment) and mark pred_index=0.
            meta = {
                "case_id": pair['case_id'],
                "q_tag": pair['q_tag'],
                "pred_index": 0,
                "pred_question": pair.get('pred_questions'),
                "pred_answer": pair.get('pred_answers'),
                "pred_reasoning": pair.get('pred_reasonings'),
                "truth_questions": pair['truth_questions'],
                "truth_answers": pair['truth_answers'],
                "truth_reasonings": pair['truth_reasonings'],
                "prompt": prompt,
            }
            tasks.append((task, meta))
                

    print(f"Prepared {len(tasks)} tasks for case {case_id}")
    
    return tasks
# --- MAIN ---

async def run_experiment_batch(pred_cases, train_good_set, pred_root, truth_root, client, out_file="critique_results.json"):
    """Process cases sequentially (per-case LLM calls run concurrently) and write incremental output.

    This keeps runs reliable: each case's results are gathered and appended to disk immediately.
    """

    results_all = []

    for case_id in pred_cases:
        # filter by train_good_set if provided
        if train_good_set and case_id not in train_good_set:
            continue

        pred_log = os.path.join(pred_root, case_id, 'run_1', 'config_3', 'tool', 'log.json')
        truth_log = os.path.join(truth_root, case_id, 'run_1', 'config_3', 'train', 'log.json')

        if not os.path.exists(pred_log) or not os.path.exists(truth_log):
            print(f"Skipping {case_id}: missing pred_log={os.path.exists(pred_log)} truth_log={os.path.exists(truth_log)}")
            continue

        # get coroutines for this case
        case_tasks = await process_case(truth_log, pred_log, case_id, client)

        if not case_tasks:
            continue

        # case_tasks is a list of (Task, meta) pairs — await tasks and pair outputs with metadata
        tasks_only = [t for (t, m) in case_tasks]
        metas = [m for (t, m) in case_tasks]

        try:
            raw_results = await asyncio.gather(*tasks_only, return_exceptions=True)
        except Exception as e:
            logger.warning(f"Error gathering tasks for case {case_id}: {e}")
            raw_results = []

        case_results = []
        for res, meta in zip(raw_results, metas):
            if isinstance(res, Exception):
                logger.warning(f"Task for case {meta.get('case_id')} q_tag {meta.get('q_tag')} raised: {res}")
                continue
            parsed_answer, parsed_reasoning = res
            entry = {
                **meta,
                "model_raw_output_parsed": parsed_answer,
                "model_parsed_reasoning": parsed_reasoning,
                "timestamp": time.time()
            }
            case_results.append(entry)

        # append and write incrementally
        results_all.extend(case_results)

        # write incremental results to output file
        try:
            with open(out_file, 'w', encoding='utf-8') as f:
                json.dump(results_all, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to write incremental output to {out_file}: {e}")

        print(f"Processed {case_id}: wrote {len(case_results)} records (total {len(results_all)})")

    print(f"\nExperiment Completed. Results saved to {out_file}")
    return results_all
        
    
async def main():
    parser = argparse.ArgumentParser(description="Generate critic prompts from truth/pred logs")
    parser.add_argument('--pred_root', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'Outputs', 'Train_Cases_Pred'), help='Prediction root folder with case subfolders')
    parser.add_argument('--truth_root', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'Outputs', 'Train_Cases_Truth'), help='Truth root folder with case subfolders')
    parser.add_argument('--train_good', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'Data', 'train_good_reasons.pkl'), help='Pickle file listing references to include')
    parser.add_argument('--gpu', type=str, default='gpu31')
    parser.add_argument('--out', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'Outputs', 'critique_results.json'), help='Output JSON file for consolidated results')
    parser.add_argument('--concurrency', type=int, default=20, help='Max concurrent LLM calls')
    args = parser.parse_args()

    # load train_good_reasons (accept pandas pickle or plain pickle)
    train_good_set = set()
  
    # try pandas first
    train_df = pd.read_pickle(args.train_good)
    # if it's a Series or DataFrame with a 'Reference' column

    train_good_set = train_df.index.tolist()

    print(f"Loaded {len(train_good_set)}")

    print(f"Scanning pred_root={args.pred_root} and truth_root={args.truth_root}... (filtering by {len(train_good_set)} train refs)")

    # set semaphore concurrency for this script
    global REQUEST_SEMAPHORE
    REQUEST_SEMAPHORE = asyncio.Semaphore(args.concurrency)

    #CHANGE!!!
    #collect case ids present in the prediction root (assume truth root mirrors structure)
    pred_cases = sorted([d for d in os.listdir(args.pred_root) if os.path.isdir(os.path.join(args.pred_root, d))])

    # input the api to your LLM here
    API_BASE = f"http://{args.gpu}.barkla2.liv.alces.network:8000/v1"

    try:
        # use async client for the LLM
        client = AsyncOpenAI(base_url=API_BASE, api_key="EMPTY")
    except Exception as e:
        print(f"Error: LLM API unreachable: {e}")
        return

    # run exp and write to args.out incrementally
    await run_experiment_batch(pred_cases, train_good_set, args.pred_root, args.truth_root, client, out_file=args.out)

if __name__ == "__main__":
    asyncio.run(main())
   