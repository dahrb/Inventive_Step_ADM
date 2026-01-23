import json
import os
import argparse
import pickle
import pandas as pd
from typing import Dict, Any
from inventive_step_ADM import question_mapping
import re


def extract_q_tag(text: str) -> str:
    """Extracts Q num from Q text"""
    match = re.search(r'\[Q(\d+)\]', text)
    if match:
        return int(f"{match.group(1)}")
    return None

def process_case(truth_path: str, pred_path: str, case_id: str):
    tasks = []
    
    # 1. Load Data
    try:
        with open(truth_path, 'r', encoding='utf-8') as f: truth_data = json.load(f)
        with open(pred_path, 'r', encoding='utf-8') as f: pred_data = json.load(f)
    except Exception as e:
        print(f"Error loading {case_id}: {e}")
        return []

    
    ###TO DO!!!!!!!!!!!!
    # 2. Organize Ground Truth by Factor
    # We want a list of ALL rulings for each factor.
    # Structure: truth_map['Synergy'] = [{feature: 'A', reasoning: '...'}, {feature: 'B', reasoning: '...'}]
    truth_map = {}
    
    # Handle the structure of your mined truth file
    # (Assuming it's a list of dicts, or a dict of factors)
    raw_factors = []
    if isinstance(truth_data, list):
        for item in truth_data:
            if 'factors' in item: 
                # If factors are grouped by case in the list
                raw_factors.append(item['factors'])
            elif 'factor' in item:
                # If it's a flat list of factor entries
                key = item['factor']
                if key not in truth_map: truth_map[key] = []
                truth_map[key].append(item)
    elif isinstance(truth_data, dict):
        raw_factors.append(truth_data.get('factors', {}))

    # Flatten the standard 'factors' dictionary structure if found
    for factors_dict in raw_factors:
        for key, val in factors_dict.items():
            if key not in truth_map: truth_map[key] = []
            # 'val' might be a single dict or a list if multiple features were mined
            if isinstance(val, list):
                truth_map[key].extend(val)
            else:
                truth_map[key].append(val)

    # 3. Iterate System Predictions
    for entry in pred_data:
        question = entry.get('question', '')
        q_tag = extract_q_tag(question)
        factor_key = Q_TO_FACTOR.get(q_tag)
        
        # Only process if we have Ground Truth for this factor
        if not factor_key or factor_key not in truth_map:
            continue
            
        # Get System's specific context
        sys_feature = extract_feature_context(question)
        sys_decision = normalize_decision(entry.get('answer'))
        sys_reasoning = entry.get('reasoning', '')

        # Get ALL Ground Truth entries for this factor
        all_truth_entries = truth_map[factor_key]
        
        # Format the Truth Block for the Prompt
        truth_block_str = ""
        for i, t in enumerate(all_truth_entries):
            # Try to grab a feature name if the miner extracted it, otherwise just use the text
            t_dec = normalize_decision(t.get('decision', 'N/A'))
            t_reas = t.get('reasoning', 'No reasoning provided')
            t_quote = t.get('quote', '')
            
            truth_block_str += f"""
            [Ground Truth Entry #{i+1}]
            Decision: {t_dec}
            Reasoning: {t_reas}
            Quote: "{t_quote[:300]}..."
            """

        # 4. Generate the Critic Prompt
        # We give the LLM the "Menu" of truths and ask it to pick the relevant one.
        llm_prompt = f"""
        You are a Legal Critic comparing an AI's patent analysis against the Official Board of Appeal Decision.
        
        CASE ID: {case_id}
        LEGAL FACTOR: {factor_key}
        
        --- SYSTEM PREDICTION ---
        The AI system evaluated the feature: "{sys_feature}"
        AI Decision: {sys_decision}
        AI Reasoning: {sys_reasoning}
        
        --- OFFICIAL BOARD RULINGS (GROUND TRUTH) ---
        Here are all the Board's rulings regarding '{factor_key}' for this case. 
        Note that the Board may have discussed multiple different features.
        
        {truth_block_str}
        
        --- YOUR TASK ---
        1. Identify which "Ground Truth Entry" above corresponds to the feature "{sys_feature}" discussed by the AI. (If none match, state "No Match").
        2. Compare the decisions.
        3. If the AI was WRONG: Write a "Cautionary Tale" (max 2 sentences) explaining the specific legal error. Start with "CAUTION:".
        4. If the AI was CORRECT: Write a "Precedent Principle" (max 2 sentences) summarizing the valid logic. Start with "PRECEDENT:".
        
        Output only the text of the Caution or Precedent.
        """
        
        tasks.append({
            "case_id": case_id,
            "factor": factor_key,
            "feature": sys_feature,
            "prompt": llm_prompt
        })

    return tasks

# --- MAIN ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate critic prompts from truth/pred logs")
    parser.add_argument('--pred_root', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'Outputs', 'Train_Cases_Pred'), help='Prediction root folder with case subfolders')
    parser.add_argument('--truth_root', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'Outputs', 'Train_Cases_Truth'), help='Truth root folder with case subfolders')
    parser.add_argument('--train_good', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'Data', 'train_good_reasons.pkl'), help='Pickle file listing references to include')
    args = parser.parse_args()

    # load train_good_reasons (accept pandas pickle or plain pickle)
    train_good_set = set()
  
    # try pandas first
    train_df = pd.read_pickle(args.train_good)
    # if it's a Series or DataFrame with a 'Reference' column

    train_good_set = train_df.index.tolist()

    print(f"Loaded {len(train_good_set)}")
    all_tasks = []
    
    print(f"Scanning pred_root={args.pred_root} and truth_root={args.truth_root}... (filtering by {len(train_good_set)} train refs)")

    #collect case ids present in the prediction root (assume truth root mirrors structure)
    pred_cases = sorted([d for d in os.listdir(args.pred_root) if os.path.isdir(os.path.join(args.pred_root, d))])


    # fixed expected paths under each case folder
    for case_id in pred_cases:
        # filter by train_good_set if provided
        if train_good_set and case_id not in train_good_set:
            continue
        pred_log = os.path.join(args.pred_root, case_id, 'run_1', 'config_3', 'tool', 'log.json')
        truth_log = os.path.join(args.truth_root, case_id, 'run_1', 'config_3', 'train', 'log.json')

        print(pred_log)
        if not os.path.exists(pred_log) or not os.path.exists(truth_log):
            print(f"Skipping {case_id}: missing pred_log={os.path.exists(pred_log)} truth_log={os.path.exists(truth_log)}")
            continue

        case_tasks = process_case(truth_log, pred_log, case_id)
        all_tasks.extend(case_tasks)
        
        print(case_tasks)
        
        
    # # Save results
    # with open(OUTPUT_FILENAME, 'w') as f:
    #     json.dump(all_tasks, f, indent=4)

    # print(f"\nSuccess! Generated {len(all_tasks)} critic prompts.")
    # print(f"Saved to {OUTPUT_FILENAME}")
