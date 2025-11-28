import json
import time
import subprocess
import sys
from openai import OpenAI
from pydantic import BaseModel, Field
from tenacity import retry, wait_random_exponential, stop_after_attempt

# --- CONFIGURATION ---
API_BASE = "http://gpu07.barkla2.liv.alces.network:8000/v1"
API_KEY = "EMPTY"
SECRET_OBJECT = "Frog" 

client = OpenAI(base_url=API_BASE, api_key=API_KEY)

# Helper to print to stderr so it doesn't get buffered/lost
def log(msg):
    sys.stderr.write(f"[DEBUG] {msg}\n")
    sys.stderr.flush()


# 1. Define the Schema using Pydantic
# We MUST include a 'reasoning' field so the model has "space" to think.
class GameResponse(BaseModel):
    reasoning: str = Field(..., description="Step-by-step thinking process about the secret object.")
    answer: str = Field(..., description="The final answer: 'Yes' or 'No' (or 'Unknown').")

@retry(wait=wait_random_exponential(multiplier=1, max=10), stop=stop_after_attempt(3))
def consult_llm(question, history):
    """
    Uses vLLM's 'guided_json' to enforce strictly valid JSON output.
    """
    
    # --- 2. History Squashing (Keep this to prevent Context Crashing) ---
    history_text = ""
    if history:
        history_text = "PREVIOUS QUESTIONS:\n"
        for turn in history:
            if turn['role'] == 'user':
                history_text += f"- Q: {turn['content']}\n"
            elif turn['role'] == 'assistant':
                # We can now parse the previous JSON cleanly!
                try:
                    prev_json = json.loads(turn['content'])
                    clean_ans = prev_json.get('answer', 'N/A')
                except:
                    clean_ans = turn['content'] # Fallback
                history_text += f"  A: {clean_ans}\n"
        history_text += "\n"

    # --- 3. Prompt Construction ---
    # We explicitly tell the model to fill the specific JSON fields.
    system_instruction = (
        f"You are playing 20 Questions. The secret object is: '{SECRET_OBJECT}'.\n"
        f"Answer the current question based on the secret object.\n"
        f"{history_text}" 
        f"CURRENT QUESTION: {question}\n\n"
        f"INSTRUCTIONS:\n"
        f"- You must output valid JSON.\n"
        f"- Fill the 'reasoning' field first with your thought process.\n"
        f"- Fill the 'answer' field with exactly 'Yes' or 'No'."
    )
    
    messages = [{"role": "user", "content": system_instruction}]

    print("\n" + "="*50)
    print(f"[DEBUG] SENDING JSON REQUEST (Question: {question})")
    
    try:
        # --- 4. The vLLM Magic: extra_body with guided_json ---
        response = client.chat.completions.create(
            model="gpt-oss-120b",
            messages=messages,
            temperature=0.0,
            max_tokens=512,
            extra_body={
                "guided_json": GameResponse.model_json_schema(),
                "guided_decoding_backend": "xgrammar" # Optional: Forces xgrammar (faster) if installed
            }
        )
        
        raw_content = response.choices[0].message.content.strip()
        
        # [DEBUG] Show Raw JSON
        print(f"[DEBUG] RAW JSON OUTPUT:\n{raw_content}")
        print("-" * 50)
        
        # --- 5. Zero-Error Parsing ---
        # vLLM guarantees this string is valid JSON matching your schema.
        parsed = json.loads(raw_content)
        
        reasoning = parsed.get("reasoning", "N/A")
        final_answer = parsed.get("answer", "no").lower()
        
        # Normalize strictly to yes/no just in case
        if "yes" in final_answer: final_answer = "yes"
        elif "no" in final_answer: final_answer = "no"
        
        print(f"[DEBUG] PARSED ANSWER: {final_answer}")
        print("="*50 + "\n")

        return final_answer, reasoning
        
    except Exception as e:
        print(f"[LLM ERROR]: {e}")
        return "ERROR", "API Call Failed"
    
# @retry(wait=wait_random_exponential(multiplier=1, max=10), stop=stop_after_attempt(3))
# def consult_llm(question, history):
#     """
#     1. Squashes history to prevent vLLM 500 errors.
#     2. DEBUG SECTION: Prints FULL raw JSON and any hidden reasoning found.
#     3. RETURN LOGIC: Uses standard text splitting (Reasoning = text before last line).
#     """
    
#     # --- 1. History Squashing ---
#     history_text = ""
#     if history:
#         history_text = "PREVIOUS QUESTIONS:\n"
#         for turn in history:
#             if turn['role'] == 'user':
#                 history_text += f"- Q: {turn['content']}\n"
#             elif turn['role'] == 'assistant':
#                 # Clean up history for the prompt context
#                 clean_content = turn['content'].split('\n')[-1].strip()
#                 if not clean_content: clean_content = turn['content']
#                 history_text += f"  A: {clean_content}\n"
#         history_text += "\n"

#     # --- 2. Prompt Construction ---
#     system_instruction = (
#         f"You are playing 20 Questions. The secret object is: '{SECRET_OBJECT}'.\n"
#         f"Answer the current question based on the secret object.\n"
#         f"{history_text}" 
#         f"CURRENT QUESTION: {question}\n\n"
#         f"INSTRUCTIONS:\n"
#         f"- Provide short reasoning (1 sentence).\n"
#         f"- End your answer with exactly 'Yes' or 'No' on the last line."
#     )
    
#     messages = [{"role": "user", "content": system_instruction}]

#     try:
#         response = client.chat.completions.create(
#             model="gpt-oss-120b",
#             messages=messages,
#             temperature=0.0,
#             max_tokens=512
#         )
        
#         message_obj = response.choices[0].message
#         full_content = message_obj.content.strip()

#         # ==================== DEBUG SECTION ====================
#         print("\n" + "="*20 + " DEBUG START " + "="*20)
        
#         # A. Dump the FULL Raw Message (shows hidden fields like 'reasoning_content')
#         print(f"[DEBUG] FULL RAW MESSAGE JSON:")
#         print(json.dumps(message_obj.model_dump(), indent=2))
        
#         # B. Explicitly Show Hidden Reasoning (if present)
#         hidden_reasoning = None
        
#         # Check Field-based (vLLM/DeepSeek standard)
#         if hasattr(message_obj, 'reasoning_content') and message_obj.reasoning_content:
#             hidden_reasoning = message_obj.reasoning_content
#             print(f"\n[DEBUG] DETECTED HIDDEN FIELD 'reasoning_content':")
#             print(f"'{hidden_reasoning}'")
            
#         # Check Tag-based (DeepSeek-R1 standard)
#         elif "<think>" in full_content:
#             try:
#                 hidden_reasoning = full_content.split("<think>")[1].split("</think>")[0].strip()
#                 print(f"\n[DEBUG] DETECTED <think> TAGS:")
#                 print(f"'{hidden_reasoning}'")
#             except:
#                 pass

#         if not hidden_reasoning:
#             print("\n[DEBUG] No hidden reasoning tokens detected.")

#         print("="*21 + " DEBUG END " + "="*21 + "\n")
#         # =======================================================


#         # --- 3. Standard Game Logic (Text Splitting) ---
#         # We ignore the hidden fields for the game state and just parse the visual text.
        
#         # Split by newline. We expect the last line to be the Yes/No answer.
#         lines = full_content.split('\n')
        
#         if len(lines) > 1:
#             last_line = lines[-1].strip()
#             # Reasoning is everything EXCEPT the last line
#             reasoning = "\n".join(lines[:-1]).strip()
#         else:
#             # Fallback if model only output 1 line
#             last_line = lines[0].strip()
#             reasoning = "N/A (Reasoning mixed with answer)"

#         # Extract strict Yes/No from the last line
#         answer_match = re.search(r'\b(yes|no)\b', last_line, re.IGNORECASE)
        
#         if answer_match:
#             final_answer = answer_match.group(1).lower()
#         else:
#             # Fallback: Search the whole content
#             answer_match_loose = re.search(r'\b(yes|no)\b', full_content, re.IGNORECASE)
#             final_answer = answer_match_loose.group(1).lower() if answer_match_loose else "no"

#         return final_answer, reasoning
        
#     except Exception as e:
#         print(f"[LLM ERROR]: {e}")
#         return "ERROR", "API Call Failed"

# @retry(wait=wait_random_exponential(multiplier=1, max=10), stop=stop_after_attempt(3))
# def consult_llm(question, history):
#     """
#     Stateless Version: Ignores history to prevent vLLM 500 Errors.
#     The Oracle only needs the 'Secret Object' and the 'Current Question' to answer.
#     """
    
#     # 1. Define the Instruction (with the Secret)
#     # We explicitly tell it to be brief to prevent "header" hallucinations.
#     system_instruction = (
#         f"You are playing 20 Questions. The secret object is: '{SECRET_OBJECT}'. "
#         "The user will ask a question. You must answer based ONLY on the secret object. "
#         "Format: Provide 1 sentence of reasoning, then a final line saying exactly 'Yes' or 'No'."
#     )
    
#     # 2. Build a FRESH message list (Stateless)
#     # We do NOT append history. This prevents the "unexpected tokens" crash.
#     messages = [
#         {"role": "user", "content": f"{system_instruction}\n\nQuestion: {question}"}
#     ]
    
#     # Debug: Confirm we are sending a clean, single message
#     # print(f"[DEBUG] Asking: {question}")

#     try:
#         response = client.chat.completions.create(
#             model="gpt-oss-120b",
#             messages=messages,
#             temperature=0.0,
#             max_tokens=256 # Reduced tokens to cut off rambling
#         )
        
#         full_content = response.choices[0].message.content.strip()
        
#         # 3. Robust Answer Extraction
#         # Looks for 'yes' or 'no' in the last line
#         answer_match = re.search(r'(yes|no)', full_content.split('\n')[-1], re.IGNORECASE)
        
#         if answer_match:
#             final_answer = answer_match.group(1).lower()
#         else:
#             # Fallback: Search the whole string if the last line failed
#             answer_match_loose = re.search(r'\b(yes|no)\b', full_content, re.IGNORECASE)
#             final_answer = answer_match_loose.group(1).lower() if answer_match_loose else "no"

#         reasoning = full_content.rsplit('\n', 1)[0].strip()
#         if not reasoning: reasoning = full_content # Fallback if only one line

#         return final_answer, reasoning
        
#     except Exception as e:
#         print(f"[LLM ERROR]: {e}")
#         return "ERROR", "API Call Failed"

def main():
    print(f"Starting Game... (Secret: {SECRET_OBJECT})")
    
    # UPDATE THIS PATH to your game script
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
    
    while True:
        output_line = process.stdout.readline()
        
        if output_line == '' and process.poll() is not None:
            break
            
        if output_line:
            line = output_line.strip()
            print(f"\n[GAME SAYS]: {line}")
            
            if line.startswith("QUESTION:") or line.startswith("GUESS:"):
                question_text = line.split(":", 1)[1].strip()
                
                llm_answer, llm_reasoning = consult_llm(question_text, history)
                
                if llm_answer == "ERROR":
                    print("[FATAL]: API Failure. Exiting game.")
                    process.terminate()
                    break
                
                print("-" * 50)
                print(f"[REASONING]: {llm_reasoning}")
                print(f"[ANSWER]:    {llm_answer.upper()}")
                print("-" * 50)
                
                process.stdin.write(f"{llm_answer}\n")
                process.stdin.flush()
                
                # Update History
                history.append({"role": "user", "content": question_text})
                history.append({"role": "assistant", "content": llm_answer})
                
                time.sleep(1) 

    print("\nProcess Finished.")

if __name__ == "__main__":
    main()