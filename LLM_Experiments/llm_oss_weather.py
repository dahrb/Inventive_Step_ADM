import os
from openai import OpenAI
import json
from openai_harmony import ToolDescription # Helper for easy tool definition
import time
import pickle

# --- CONFIGURATION ---
# Replace 'gpu13' with the actual node name from your server log
# If running on the SAME node, use "localhost"
API_BASE = "http://gpu07.barkla2.liv.alces.network:8000/v1" 
API_KEY = "EMPTY"

client = OpenAI(base_url=API_BASE, api_key=API_KEY)

def main():
    print(f"Connecting to Server at {API_BASE}...",flush=True)

    # # 1. Define Tools (OpenAI Format)
    # tools = [{
    #     "type": "function",
    #     "function": {
    #         "name": "get_weather",
    #         "description": "Get current weather",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "location": {"type": "string"},
    #                 "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
    #             },
    #             "required": ["location"]
    #         }
    #     }
    # }]
    
    questions = [
        "Tell me about the battle of Marengo?",
        "What is the weather like in Liverpool?",
        "Who was the first president of the USA?",
        "How do you code a loop in Python?",
        "What is the capital of France?",
        "Is AI sentient?",
        "9.11 and 9.8, which is greater?",
    ]

    responses = []
    for q in questions:
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": q}
        ]
        try:
            start_time = time.time()
            response = client.chat.completions.create(
                model="gpt-oss-120b",
                messages=messages,
                temperature=0.0,
                reasoning_effort="high"
            )
            elapsed = time.time() - start_time
            msg = response.choices[0].message
            reasoning = getattr(msg, "reasoning_content", None)
            print(f"\nQ: {q}",flush=True)
            if reasoning:
                print(f"Reasoning: {reasoning}",flush=True)
            print(f"Answer: {msg.content}",flush=True)
            print(f"Inference time: {elapsed:.2f} seconds\n",flush=True)
            responses.append(response)
        except Exception as e:
            print(f"\n[ERROR] Could not connect to server for question: {q}\n{e}",flush=True)
            responses.append(e)

    # Save raw responses to .pkl for later exploration
    with open("llm_oss_weather_raw_responses.pkl", "wb") as f:
        pickle.dump(responses, f)
        
    # # 3. Check for Tool Calls
    # if msg.tool_calls:
    #     t = msg.tool_calls[0]
    #     print(f"\n[SUCCESS] Model requested tool: {t.function.name}")
    #     print(f"Arguments: {t.function.arguments}")
    # else:
    #     print(f"\n[RESPONSE] {msg.content}")

if __name__ == "__main__":
    main()