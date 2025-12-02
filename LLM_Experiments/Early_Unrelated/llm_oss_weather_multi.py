"""
This script's purpose is to test asyncronous requests and process the requests in parallel batches 

"""


import os
import asyncio
import json
import time
import pickle
from openai import AsyncOpenAI  # Use Async client

# --- CONFIGURATION ---
# Replace with your actual server URL (e.g. from your SLURM log)
API_BASE = "http://gpu07.barkla2.liv.alces.network:8000/v1"
API_KEY = "EMPTY"

# Initialize Async Client
client = AsyncOpenAI(base_url=API_BASE, api_key=API_KEY)

async def process_question(q, index):
    """
    Async function to handle a single question interaction.
    """
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": q}
    ]
    
    try:
        start_time = time.time()
        # Await the response so other tasks can run while this waits
        response = await client.chat.completions.create(
            model="gpt-oss-120b",
            messages=messages,
            temperature=0.0,
            # extra_body={"reasoning_effort": "high"} # Uncomment if supported
        )
        elapsed = time.time() - start_time
        
        msg = response.choices[0].message
        
        # Print output safely (async prints can interleave, so we format as a block)
        output_text = f"\n--- Result {index+1} ---\n"
        output_text += f"Q: {q}\n"
        if getattr(msg, "reasoning.content", None):
             output_text += f"Reasoning: {msg.reasoning[:100]}...\n"
        output_text += f"Answer: {msg.content}\n"
        output_text += f"Time: {elapsed:.2f}s"
        print(output_text, flush=True)
        
        return response
        
    except Exception as e:
        print(f"\n[ERROR] Question '{q}': {e}", flush=True)
        return None

async def main():
    print(f"Connecting to Server at {API_BASE}...", flush=True)
    
    questions = [
        "Tell me about the battle of Marengo?",
        "What is the weather like in Liverpool?",
        "Who was the first president of the USA?",
        "How do you code a loop in Python?",
        "What is the capital of France?",
        "Is AI sentient?",
        "9.11 and 9.8, which is greater?",
    ]

    # Create a list of async tasks
    tasks = [process_question(q, i) for i, q in enumerate(questions)]
    
    print(f"Sending {len(questions)} requests in parallel...", flush=True)
    global_start = time.time()
    
    # Run all tasks concurrently
    results = await asyncio.gather(*tasks)
    
    total_time = time.time() - global_start
    print(f"\nTotal Batch Time: {total_time:.2f}s")

    # Filter out failed requests (None)
    valid_responses = [r for r in results if r is not None]

    # Save responses
    with open("llm_oss_weather_raw_responses.pkl", "wb") as f:
        pickle.dump(valid_responses, f)
    print("Saved responses to pickle.")

if __name__ == "__main__":
    asyncio.run(main())