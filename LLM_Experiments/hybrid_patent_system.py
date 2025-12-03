"""
To Do -

- prompt engineering i.e. EPO
- check formatting of markdown
- ensure conclusions are also printed
"""

import argparse
import json
import time
import subprocess
import sys
import os
from datetime import datetime
from pydantic import BaseModel, Field
from tenacity import retry, wait_random_exponential, stop_after_attempt
from openai import OpenAI
import random
import select
import fcntl
import re
import shutil

# Globals
ID = 5
LOG_FILE = f"./adm_log_{ID}.md"

# Model configurations (same style as llm_20q_any_model)
MODELS = {
    "gpt": {"id": "gpt-oss-120b", "mode": "squash"},
    "llama": {"id": "Llama-3.3-70B-Instruct", "mode": "chat"},
    "qwen": {"id": "Qwen3-Next-80B-A3B-Thinking", "mode": "chat"},
}

CURRENT_CONFIG = None

class GameResponse(BaseModel):
    reasoning: str = Field(..., description="Step-by-step thinking process.")
    answer: str = Field(..., description="The final answer: 'Yes' or 'No'.")


# ...existing code...
def log_to_markdown(turn_num, question, raw_content, hidden_reasoning, final_answer, model_id):
    """
    Append a compact, machine-friendly and human-friendly entry to LOG_FILE.
    - One-line header with turn/time/model/decision
    - Question inline next to 'Question:'
    - Extracted reasoning in a code block
    - Collapsible raw/hidden reasoning
    - Append a small JSON line (commented) for easy parsing if needed
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            # simple YAML-ish header for metadata (not required by parser)
            f.write(f"---\n")
            f.write(f"title: ADM Session Log\n")
            f.write(f"date: {datetime.now().strftime('%Y-%m-%d')}\n")
            f.write(f"---\n\n")

    # Try extracting structured reasoning from raw_content JSON if present
    extracted_reasoning = None
    try:
        if isinstance(raw_content, str):
            parsed = json.loads(raw_content)
            if isinstance(parsed, dict):
                extracted_reasoning = parsed.get("reasoning")
    except Exception:
        extracted_reasoning = None

    # Hidden/raw fallback
    hidden_text = hidden_reasoning if hidden_reasoning else (raw_content if raw_content else "No hidden reasoning available.")
    if not extracted_reasoning:
        extracted_reasoning = hidden_text if hidden_text else "No reasoning found."

    # Decide how to render the final answer: color only for explicit yes/no answers.
    try:
        ans_text = str(final_answer).strip()
    except Exception:
        ans_text = str(final_answer)

    # Render badges (HTML spans; falls back to text if renderer strips HTML)
    if ans_text.lower() == "yes":
        decision_badge = f'<span style="background:#e6ffed;color:#065f46;padding:2px 6px;border-radius:4px;font-weight:600">YES</span>'
    elif ans_text.lower() == "no":
        decision_badge = f'<span style="background:#ffecec;color:#7b1414;padding:2px 6px;border-radius:4px;font-weight:600">NO</span>'
    else:
        # preserve original content for non-boolean answers
        # show excerpt if long
        short = ans_text if len(ans_text) < 80 else ans_text[:77] + "..."
        decision_badge = f'`{short}`'

    # Compose entry: compact header, question inline, reasoning & collapsible raw
    entry_lines = []
    entry_lines.append(f"## Step {turn_num} — {timestamp}`\n")
    entry_lines.append(f"**Question:** {question}\n\n")
    entry_lines.append(f"**Reasoning (extracted):**\n\n```text\n{extracted_reasoning}\n```\n")
    entry_lines.append("<details>\n<summary>Show hidden/raw reasoning</summary>\n\n```text\n")
    entry_lines.append(f"{hidden_text}\n")
    entry_lines.append("```\n\n</details>\n")
    entry_lines.append(f"**Answer:** {decision_badge}")
    entry_lines.append(f"---\n\n")

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.writelines(entry_lines)
        # Append a single-line JSON comment for machine parsing (keeps human file clean)
        try:
            meta = json.dumps({
                "turn": turn_num,
                "time": timestamp,
                "question": question,
                "answer": ans_text,
                "model": model_id
            }, ensure_ascii=False)
            f.write(f"<!-- JSON: {meta} -->\n\n")
        except Exception:
            pass


def append_visual_to_markdown(viz_path: str):
    """Copy a visualization file into the LOG_FILE directory and append a markdown image link.

    Returns the destination path written into the markdown (relative basename).
    """
    try:
        viz_path = viz_path.strip()
        if not os.path.isabs(viz_path):
            viz_path = os.path.abspath(viz_path)
        if not os.path.exists(viz_path):
            raise FileNotFoundError(viz_path)

        # target directory is the directory containing LOG_FILE (or current dir)
        target_dir = os.path.dirname(os.path.abspath(LOG_FILE)) or os.getcwd()
        os.makedirs(target_dir, exist_ok=True)

        base = os.path.basename(viz_path)
        dest = os.path.join(target_dir, base)
        # avoid clobbering existing files: add timestamp suffix if needed
        if os.path.exists(dest):
            name, ext = os.path.splitext(base)
            dest = os.path.join(target_dir, f"{name}_{int(time.time())}{ext}")
            base = os.path.basename(dest)

        shutil.copy2(viz_path, dest)

        # Append an inline markdown image to the LOG_FILE
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n\n**Visualization:**\n\n")
            # Use relative path (basename) so the markdown stays portable inside log dir
            f.write(f"![]({base})\n\n")
            try:
                meta = json.dumps({"visual": base, "source": viz_path})
                f.write(f"<!-- JSON: {meta} -->\n\n")
            except Exception:
                pass

        return dest
    except Exception as e:
        raise

def is_separator_line(line: str) -> bool:
    s = line.strip()
    return len(s) >= 3 and all(c == s[0] for c in s) and s[0] in "=-_~*"

def clean_combined_text(text: str) -> str:
    """Remove decorative separator blocks and short banners from UI output.

    Specifically removes sequences like:
      ========\nHEADER\n========
    and any standalone separator lines.
    """
    lines = text.splitlines()
    out_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if is_separator_line(line):
            # if pattern sep / header / sep, skip the three
            if i + 2 < len(lines) and not is_separator_line(lines[i+1]) and is_separator_line(lines[i+2]):
                i += 3
                continue
            # otherwise skip this separator line
            i += 1
            continue
        # skip very short header lines like 'Query Domain' when surrounded by separators
        out_lines.append(line)
        i += 1
    # remove leading/trailing blank lines
    cleaned = "\n".join(out_lines).strip()
    return cleaned

@retry(wait=wait_random_exponential(multiplier=1, max=10), stop=stop_after_attempt(3))
def consult_llm(question, history, client, turn_num):
    """
    Implementation adapted from llm_20q_any_model.py.
    """
    model_id = CURRENT_CONFIG["id"] if isinstance(CURRENT_CONFIG, dict) else "test_stub"
    mode = CURRENT_CONFIG["mode"] if isinstance(CURRENT_CONFIG, dict) else "squash"
    
    # Limit history to the last N question/answer pairs to avoid growing prompts
    max_pairs = 10
    max_entries = max_pairs * 2  # each pair is two entries: user + assistant
    recent_history = history[-max_entries:] if history else []

    # Build messages depending on mode
    if mode == "squash":
        history_text = ""
        if recent_history:
            history_text = "PREVIOUS QUESTIONS:\n"
            for turn in recent_history:
                if turn['role'] == 'user':
                    history_text += f"- Q: {turn['content']}\n"
                elif turn['role'] == 'assistant':
                    try:
                        prev_json = json.loads(turn['content'])
                        clean_ans = prev_json.get('answer', 'N/A')
                    except Exception:
                        clean_ans = turn['content']
                    history_text += f"  A: {clean_ans}\n"
            history_text += "\n"

        system_instruction = (
            f"You are answering questions about a new invention called an Umbrella Lamp being submitted for a patent to the European Patent Office.\
            Answer no to the questions about a skilled person \n"
            f"{history_text}"
            f"CURRENT QUESTION: {question}\n\n"
            f"INSTRUCTIONS:\n- Output valid JSON with keys 'reasoning' and 'answer'"
        )
        messages = [{"role": "user", "content": system_instruction}]
    else:
        sys_msg = f"You are answering questions about a new invention called an Umbrella Lamp"
        messages = [{"role": "system", "content": sys_msg}]
        for turn in recent_history:
            content = turn['content']
            if turn['role'] == 'assistant':
                try:
                    data = json.loads(content)
                    content = json.dumps({"answer": data.get("answer", "unknown")})
                except Exception:
                    pass
            messages.append({"role": turn['role'], "content": content})
        messages.append({"role": "user", "content": f"Output valid JSON with 'reasoning' and 'answer'. Question: {question}"})
    # Prepare request params
    req_params = {
        "model": model_id,
        "messages": messages,
        "max_tokens": 32768,
        "extra_body": {"guided_json": GameResponse.model_json_schema()},
        "temperature": 0.1
    }
    
    try:
        print("DEBUG: Asking LLM")
        response = client.chat.completions.create(**req_params)
        message_obj = response.choices[0].message
        raw_content = message_obj.content.strip()

        hidden_reasoning = ""
        if hasattr(message_obj, 'reasoning_content') and message_obj.reasoning_content:
            hidden_reasoning = message_obj.reasoning_content
        elif "</think>" in raw_content:
            try:
                parts = raw_content.split("</think>")
                hidden_reasoning = parts[0].replace("<think>", "").strip()
                raw_content = parts[1].strip()
            except Exception:
                pass

        try:
            parsed = json.loads(raw_content)
            reasoning = hidden_reasoning if hidden_reasoning else parsed.get("reasoning", "N/A")
            final_raw = parsed.get("answer", None)
            if final_raw is None:
                final_answer = ""
            else:
                final_raw = str(final_raw).strip()
                # Normalize only for explicit yes/no or pure numeric answers
                if final_raw.lower() in ("yes", "no"):
                    final_answer = final_raw.lower()
                elif re.fullmatch(r"-?\d+(?:\.\d+)?", final_raw):
                    final_answer = final_raw
                else:
                    # preserve original content for non-boolean, non-numeric answers
                    final_answer = final_raw
        except json.JSONDecodeError:
            # Don't normalize when JSON parsing fails; keep raw output as the answer
            reasoning = hidden_reasoning if hidden_reasoning else raw_content
            final_answer = raw_content.strip()

        log_to_markdown(turn_num, question, raw_content, reasoning, final_answer, model_id)
        return final_answer, reasoning
    except Exception as e:
        print(f"[LLM ERROR]: {e}")
        return "ERROR", "API Call Failed"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="gpt", choices=["gpt", "llama", "qwen"]) 
    parser.add_argument('--gpu', type=str, default='gpu07')
    args = parser.parse_args()
    global CURRENT_CONFIG
    CURRENT_CONFIG = MODELS.get(args.model, MODELS['gpt'])

    # try to configure client for real LLM usage
    API_BASE = f"http://{args.gpu}.barkla2.liv.alces.network:8000/v1"
    try:
        client = OpenAI(base_url=API_BASE, api_key="EMPTY")
    except Exception:
        client = None

    game_script_path = '/users/sgdbareh/scratch/ADM_JURIX/UI.py'

    # Launch child in unbuffered binary mode and read raw chunks from stdout fd
    process = subprocess.Popen(
        ['python', '-u', game_script_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
        bufsize=0,
    )

    child_fd = process.stdout.fileno()
    # set non-blocking on the stdout fd
    flags = fcntl.fcntl(child_fd, fcntl.F_GETFL)
    fcntl.fcntl(child_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    history = []
    turn_count = 1
    output_buffer = []

    while True:
        rlist, _, _ = select.select([child_fd], [], [], 0.25)
        if rlist:
            try:
                raw = os.read(child_fd, 4096)
            except BlockingIOError:
                raw = b''
            except OSError:
                raw = b''

            if not raw:
                if process.poll() is not None:
                    break
                continue

            try:
                chunk = raw.decode('utf-8', errors='replace')
            except Exception:
                chunk = str(raw)
            output_buffer.append(chunk)
        else:
            continue

        # Build combined from buffered chunks (do not print until prompt detected)
        combined = "".join(output_buffer)
        combined = clean_combined_text(combined)
        if not combined:
            continue

        # Detect visualization markers printed by UI.py and attach the images to the markdown log
        try:
            viz_matches = re.findall(r'ADM_VISUALIZATION:([^\s]+)', combined)
            for vm in viz_matches:
                try:
                    attached = append_visual_to_markdown(vm)
                    print(f"[VISUAL ATTACHED]: {attached}")
                except Exception as e:
                    print(f"[VISUAL ATTACH ERROR]: {e}")
        except Exception:
            pass

        lower = combined.lower()
        lines = combined.splitlines()
        is_prompt = any(l.strip().startswith(prefix) for l in lines for prefix in ("QUESTION:", "GUESS:"))
        if "enter your choice" in lower or "enter choice" in lower:
            is_prompt = True
        last_line = lines[-1].strip() if lines else ''
        # Treat any trailing ':' or '?' on the last line as a prompt for input - FIX THIS
        if last_line.endswith(":") or last_line.endswith("?"):
            is_prompt = True

        if is_prompt:
            # print the accumulated output block once
            print("\n[ADM SAYS]: " + combined)

            if ":" in last_line:
                q_text = last_line.split(":", 1)[1].strip()
                if not q_text:
                    q_text = combined
            else:
                q_text = combined

            # remove any decorative lines from the question text as well
            q_text = clean_combined_text(q_text)

            ans, reas = consult_llm(q_text, history, client, turn_count)
            if ans == "ERROR":
                break

            print(f"[REASONING]: {reas}")
            print(f"[ANSWER]:    {str(ans).upper()}")

            # write answer to child's stdin as bytes
            try:
                process.stdin.write((str(ans) + "\n").encode('utf-8'))
                process.stdin.flush()
            except Exception:
                pass

            history.append({"role": "user", "content": q_text})
            history.append({"role": "assistant", "content": json.dumps({"reasoning": reas, "answer": ans})})
            turn_count += 1

            # reset buffer after answering
            output_buffer = []

            time.sleep(0.5)

    # Child exited. If there's any remaining buffered output, print it and ask the model
    final_combined = "".join(output_buffer).strip()
    if final_combined:
        print("\n[ADM FINAL OUTPUT]:\n" + final_combined)

        # Ask the model to summarize and come to a final decision based on the session
        summary_question = (
            "Please summarize the session output below and state a single final decision (Yes/No) with brief reasoning.\n\n"
            + final_combined
        )

        final_ans, final_reas = consult_llm(summary_question, history, client, turn_count)
        if final_ans != "ERROR":
            print(f"\n[FINAL REASONING]: {final_reas}")
            print(f"[FINAL DECISION]: {str(final_ans).upper()}")
            # Log final decision
            try:
                log_to_markdown(turn_count, "Session Summary", json.dumps({"reasoning": final_reas, "answer": final_ans}), final_reas, final_ans, CURRENT_CONFIG.get('id') if isinstance(CURRENT_CONFIG, dict) else 'unknown')
            except Exception:
                pass

    print("\nProcess Finished.")


if __name__ == "__main__":
    main()