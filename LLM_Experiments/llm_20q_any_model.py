import argparse
import json
import time
import subprocess
import sys
import os
import re
from datetime import datetime
from openai import OpenAI
from pydantic import BaseModel, Field
from tenacity import retry, wait_random_exponential, stop_after_attempt

# --- CONFIGURATION MAP ---
# Define your models and their specific "mode" here.
# 'squash': Flattens history into one prompt (Fixes GPT-OSS 500 errors).
# 'chat':   Sends standard list of messages (Best for Llama 3).
MODELS = {
    "gpt": {
        "id": "gpt-oss-120b", 
        "mode": "squash",
    },
    "llama": {
        "id": "Llama-3.3-70B-Instruct", 
        "mode": "chat",
    },
    "qwen": {
        "id": "Qwen3-Next-80B-A3B-Thinking",
        "mode":  "chat",
    }
}

# Global config placeholder (set in main)
CURRENT_CONFIG = None
SECRET_OBJECT = "Dog" 
LOG_FILE = "game_log.md"

# 1. Define the Shared Schema
class GameResponse(BaseModel):
    reasoning: str = Field(..., description="Step-by-step thinking process about the secret object.")
    answer: str = Field(..., description="The final answer: 'Yes' or 'No'.")

# --- LOGGING FUNCTION ---
def log_to_markdown(turn_num, question, raw_content, hidden_reasoning, final_answer, model_id):
    """
    Appends a formatted log entry to the markdown file.
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    # Create the file with a header if it doesn't exist
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"# Game Log - {datetime.now().strftime('%Y-%m-%d')}\n\n")

    # We use explicit string formatting for the inner code blocks to avoid 
    # breaking the Python script string parsing.
    log_entry = (
        f"## Turn {turn_num} - {timestamp}\n"
        f"**Model:** `{model_id}`  \n"
        f"**Question:** **\"{question}\"**\n\n"
        f"### 🧠 Reasoning Process\n"
        f"<details>\n"
        f"<summary>Click to expand raw thought process</summary>\n\n"
        f"```text\n"
        f"{hidden_reasoning if hidden_reasoning else 'No hidden reasoning tokens found.'}\n"
        f"```\n"
        f"</details>\n\n"
        f"### 🤖 Raw JSON Output\n"
        f"```json\n"
        f"{raw_content}\n"
        f"```\n\n"
        f"### ✅ Final Decision\n"
        f"**Answer:** `{final_answer.upper()}`\n\n"
        f"---\n"
    )
    
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)
        
@retry(wait=wait_random_exponential(multiplier=1, max=10), stop=stop_after_attempt(3))
def consult_llm(question, history, client, turn_num):
    """
    Unified function that switches logic based on CURRENT_CONFIG['mode'].
    """
    model_id = CURRENT_CONFIG["id"]
    mode = CURRENT_CONFIG["mode"]

    # --- MODE A: SQUASH (For GPT-OSS-120B) ---
    if mode == "squash":
        history_text = ""
        if history:
            history_text = "PREVIOUS QUESTIONS:\n"
            for turn in history:
                if turn['role'] == 'user':
                    history_text += f"- Q: {turn['content']}\n"
                elif turn['role'] == 'assistant':
                    # Try to parse clean answer from JSON
                    try:
                        prev_json = json.loads(turn['content'])
                        clean_ans = prev_json.get('answer', 'N/A')
                    except:
                        clean_ans = turn['content']
                    history_text += f"  A: {clean_ans}\n"
            history_text += "\n"

        system_instruction = (
            f"You are playing 20 Questions. The secret object is: '{SECRET_OBJECT}'.\n"
            f"Answer the current question based on the secret object.\n"
            f"{history_text}" 
            f"CURRENT QUESTION: {question}\n\n"
            f"INSTRUCTIONS:\n"
            f"- You must output valid JSON.\n"
            f"- Fill 'reasoning' first with your thought process.\n"
            f"- Fill 'answer' with exactly 'Yes' or 'No'."
        )
        messages = [{"role": "user", "content": system_instruction}]

    # ---------------------------------------------------------
    # MODE B: CHAT (Unified for Llama & DeepSeek)
    # ---------------------------------------------------------
    else:
        sys_msg = f"You are playing 20 Questions. The secret object is '{SECRET_OBJECT}'."
        if "thinking" in model_id.lower() or "qwen" in model_id.lower():
            sys_msg += " Think deeply before answering."
            
        messages = [{"role": "system", "content": sys_msg}]
        
        # Add History with AUTO-CLEANING
        for turn in history:
            content = turn['content']
            
            # CRITICAL ADAPTATION for Qwen/Reasoning Models:
            # Strip previous JSON reasoning to prevent context pollution
            if turn['role'] == 'assistant':
                try:
                    data = json.loads(content)
                    # Only keep the answer for the context window
                    content = json.dumps({"answer": data.get("answer", "unknown")})
                except:
                    pass 
            
            messages.append({"role": turn['role'], "content": content})
            
        messages.append({
            "role": "user", 
            "content": f"The secret object is '{SECRET_OBJECT}'. Output valid JSON with 'reasoning' and 'answer' (Yes/No). Question: {question}"
        })

    print("\n" + "="*50)
    print(f"[DEBUG] SENDING REQUEST ({model_id})")
    
    try:
        req_params = {
            "model": model_id,
            "messages": messages,
            "max_tokens": 1024,
            "extra_body": {"guided_json": GameResponse.model_json_schema()}
        }
        
        # Reasoning models need higher temp to avoid repetition loops
        if "thinking" in model_id.lower():
            req_params["temperature"] = 0.6
        else:
            req_params["temperature"] = 0.1

        response = client.chat.completions.create(**req_params)
        message_obj = response.choices[0].message
        raw_content = message_obj.content.strip()
        
        # ---------------------------------------------------------
        # QWEN3 THINKING PARSER
        # ---------------------------------------------------------
        hidden_reasoning = ""
        
        # 1. Check vLLM's hidden field (Best practice for Qwen3)
        if hasattr(message_obj, 'reasoning_content') and message_obj.reasoning_content:
            hidden_reasoning = message_obj.reasoning_content

        # 2. Check </think> tag (Fallback)
        # Qwen3 template often consumes the opening <think>, so we split on the closing tag
        elif "</think>" in raw_content:
            try:
                parts = raw_content.split("</think>")
                # Everything before </think> is reasoning
                hidden_reasoning = parts[0].replace("<think>", "").strip()
                # Everything after is the actual JSON content
                raw_content = parts[1].strip()
            except: pass

        # 3. Parse JSON
        try:
            parsed = json.loads(raw_content)
            reasoning = hidden_reasoning if hidden_reasoning else parsed.get("reasoning", "N/A")
            final_answer = parsed.get("answer", "no").lower()
        except json.JSONDecodeError:
            print(f"[WARN] JSON Decode Failed. Raw: {raw_content[:50]}...")
            if "yes" in raw_content.lower(): final_answer = "yes"
            else: final_answer = "no"
            reasoning = hidden_reasoning if hidden_reasoning else raw_content

        # Normalize Answer
        if "yes" in final_answer: final_answer = "yes"
        elif "no" in final_answer: final_answer = "no"
        
        # --- LOG TO FILE ---
        log_to_markdown(turn_num, question, raw_content, reasoning, final_answer, model_id)
        
        return final_answer, reasoning
        
    except Exception as e:
        print(f"[LLM ERROR]: {e}")
        return "ERROR", "API Call Failed"
    
def main():
    # --- CLI ARGUMENT PARSING ---
    parser = argparse.ArgumentParser(description="Run 20 Questions Player with Switchable Models")
    parser.add_argument(
        "--model", 
        type=str, 
        default="gpt", 
        choices=MODELS.keys(),
        help="Select the model configuration: 'gpt' (squashed history) or 'llama' (chat history)."
    )
    parser.add_argument('--gpu',
                        type=str,
                        default='gpu07',
                        help= "Select the GPU node the VLLM head node is being hosted on.")
    args = parser.parse_args()
    
    # Set Global Config
    global CURRENT_CONFIG, GPU
    CURRENT_CONFIG = MODELS[args.model]
    GPU = args.gpu
    
    API_BASE = f"http://{GPU}.barkla2.liv.alces.network:8000/v1"
    
    # Initialize Client
    client = OpenAI(base_url=API_BASE, api_key="EMPTY")
    
    # Initialize Log File with new session header
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n\n# 🎮 NEW SESSION: {CURRENT_CONFIG['id']} (Secret: {SECRET_OBJECT})\n")
        f.write("="*50 + "\n")

    print(f"Starting Game... (Model: {CURRENT_CONFIG['id']})")
    print(f"Logging to: {os.path.abspath(LOG_FILE)}\n")
    
    # --- GAME LOOP ---
    # Update path to your actual game script
    game_script_path = '/users/sgdbareh/scratch/ADM_JURIX/LLM_Experiments/20_questions.py'

    process = subprocess.Popen(
        ['python', game_script_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1 
    )

    history = []
    turn_count = 1
    
    while True:
        output_line = process.stdout.readline()
        if output_line == '' and process.poll() is not None: break
            
        if output_line:
            line = output_line.strip()
            print(f"\n[GAME SAYS]: {line}")
            
            if line.startswith("QUESTION:") or line.startswith("GUESS:"):
                q_text = line.split(":", 1)[1].strip()
                ans, reas = consult_llm(q_text, history, client,turn_count)
                
                if ans == "ERROR": break
                
                print(f"[REASONING]: {reas}")
                print(f"[ANSWER]:    {ans.upper()}")
                
                process.stdin.write(f"{ans}\n")
                process.stdin.flush()
                
                history.append({"role": "user", "content": q_text})
                history.append({"role": "assistant", "content": json.dumps({"reasoning": reas, "answer": ans})})
                
                turn_count += 1
                
                time.sleep(0.5)
                
    print("\nProcess Finished.")

if __name__ == "__main__":
    main()