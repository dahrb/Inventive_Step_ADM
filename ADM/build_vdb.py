import json
import re
import os
import numpy as np
import faiss
from openai import OpenAI
from typing import List, Dict
from inventive_step_ADM import question_mapping
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings


# --- CONFIGURATION ---
INPUT_FILE = "../Outputs/critiques_clean.json"  # The file containing your output list
OUTPUT_INDEX = "patent_precedents.faiss"
OUTPUT_META = "patent_precedents_meta.json"
EMBED_MODEL = "text-embedding-3-small"
MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"

# invert question_mapping: map numeric tag -> list of factor keys
Q_TO_FACTORS = {}
for k, v in question_mapping.items():
    Q_TO_FACTORS.setdefault(v, []).append(k)

#client = OpenAI(api_key=OPENAI_API_KEY)

def load_truth_log_for_case(case_id):
    """Load the train log.json for a given case_id if present, else return []."""
    if not case_id:
        return []
    base = os.path.join(os.path.dirname(__file__), '..', 'Outputs', 'Train_Cases_Truth')
    log_path = os.path.join(base, case_id, 'run_1', 'config_3', 'train', 'log.json')
    log_path = os.path.normpath(log_path)
    if not os.path.exists(log_path):
        return []
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def extract_from_log(log_items: list) -> Dict[str, str]:
    """Heuristically extract invention name, description and prior art from a loaded log list."""
    out = {
        'invention_name': '',
        'description': '',
        'relevant_prior_art': ''
    }
    if not log_items:
        return out

    for item in log_items:
        q = (item.get('question') or '').lower()
        ans = item.get('answer') or ''
        if not out['invention_name'] and 'title of your invention' in q:
            out['invention_name'] = ans
        if not out['description'] and ('brief description of your invention' in q or 'brief description of the technical field' in q):
            # prefer the explicit brief description question
            out['description'] = ans
        if not out['relevant_prior_art'] and ('relevant prior art' in q or 'please briefly describe the relevant prior art' in q):
            out['relevant_prior_art'] = ans

    #trim lengths
    for k in out:
        if isinstance(out[k], str):
            out[k] = out[k].strip()[:800]

    return out

def clean_question(q_list: List[str]) -> str:
    """Cleans the raw list format from the JSON (keeps original behaviour)."""
    if not q_list:
        return ""
    text = q_list[0]
    text = re.sub(r'\[Q\d+\]', '', text)
    return text.split('\n')[0][:200].strip()

def build_index():

    with open(INPUT_FILE, 'r') as f:
        data = json.load(f)

    docs_to_index = []
    
    print(f"Processing {len(data)} critiques...")
    
    embeddings = HuggingFaceEmbeddings(
        model_name=MODEL_ID,
        model_kwargs={
            'device': 'cpu', 
            'trust_remote_code': True # Qwen often requires this for custom architectures
        },
        encode_kwargs={'normalize_embeddings': True} # Critical for Cosine Similarity
    )

    # 2. Process Loop
    for idx, entry in enumerate(data):
        try:
            case_id = entry.get('case_id')
            q_tag = int(entry.get('q_tag'))
            
            factors = Q_TO_FACTORS.get(q_tag, []) if q_tag is not None else []
            
            factor = factors[0]

            question_text = clean_question(entry.get('pred_question', []))

            #load the ground truth case 
            log_json = load_truth_log_for_case(case_id)
            
            context = extract_from_log(log_json)
    
            # B. Construct the Search Vector String
            # Format: "Factor: Synergy | Context: Power Plant Mercury Removal | Question: How do features create effect?"
            vector_text = f"Factor: {factor} | Name: {context.get('invention_name', '')} | Description: {context.get('description', '')} | Relevant Prior Art: {context.get('relevant_prior_art', '')} | Question: {question_text}"
            
            # D. Save Payload (What the ADM sees at runtime)
            metadata = {
                "case_id": case_id,
                "factor": factor,
                "invention_name": context.get('invention_name', ''),
                "description": context.get('description', ''),
                "relevant_prior_art": context.get('relevant_prior_art', ''),
                "question": context.get('question', ''),
                "answer": entry.get('pred_answer', ''),
                "reasoning": entry.get('pred_reasoning', ''),
                "truth_questions": entry.get('truth_questions', []),
                "truth_answers": entry.get('truth_answers', []),
                "truth_reasonings": entry.get('truth_reasonings', []),
                "prompt": entry.get('prompt', ''),
                "critique": entry.get('model_parsed_reasoning', 'No critique available.'),
                "match_status": entry.get('model_raw_output_parsed', 'UNKNOWN')
            }
            
            # Create the Document object
            doc = Document(page_content=vector_text, metadata=metadata)
            docs_to_index.append(doc)
            
            if idx % 10 == 0:
                print(f"  Processed {idx}/{len(data)}: {case_id} ({factor})")
            
        except Exception as e:
            print(f"  Skipping index {idx}: {e}")

    vector_store = FAISS.from_documents(
        documents=docs_to_index, 
        embedding=embeddings
    )

    # 3. Save to Disk
    vector_store.save_local(OUTPUT_INDEX)
    print(f"Saved FAISS index to {OUTPUT_INDEX}")
   
if __name__ == "__main__":
    build_index()