from vllm import LLM, SamplingParams
import os
import re

def parse_deepseek_output(text):
    if "</think>" in text:
        parts = text.split("</think>", 1) # Split only on the first occurrence
        
        # Part 0 is reasoning (clean up opening tag if present)
        reasoning = parts[0].replace("<think>", "").strip()
        
        # Part 1 is content
        content = parts[1].strip()
    else:
        # Fallback logic
        reasoning = "N/A" 
        content = text.strip()
        
    return reasoning, content

def print_outputs(responses):
    """
    Processes the list of RequestOutput objects from llm.chat.
    """
    for resp in responses:
        # Access the generated text from the chat response
        generated_text = resp.outputs[0].text
        
        reasoning, content = parse_deepseek_output(generated_text)
        
        # Note: We can't easily get the original prompt back from the response object in chat mode
        # without passing it through, but we can print the reasoning/content clearly.
        print("-" * 80)
        print(f"Reasoning:\n{reasoning}")
        print(f"\nContent:\n{content}")
        print("-" * 80)

def main():
    prompts = [
        "How do you code a loop in Python?",
        "Who was the first president of the USA?",
        "Tell me about the battle of Marengo",
        "Is AI sentient?",
        "9.11 and 9.8, which is greater?",
    ]

    sampling_params = SamplingParams(
        temperature=0.6,    # R1 models work well with 0.5-0.7
        top_p=0.95,
        max_tokens=4096,    # Crucial to allow enough space for the <think> block
        seed=42,
        stop=["<|im_end|>"] # Standard stop token for Qwen/DeepSeek
    )
    
  # Calculate visible devices
    cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "0")
    tensor_parallel_size = len(cuda_visible.split(','))
    pipeline_parallel_size = int(os.environ.get("SLURM_NNODES", "1"))
    print(f"Using Tensor Parallel Size: {tensor_parallel_size}")
    print(f"Using Pipeline Parallel Size: {pipeline_parallel_size}")

    llm = LLM( 
        model="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        tensor_parallel_size=tensor_parallel_size,
        pipeline_parallel_size=pipeline_parallel_size
    )
    
    # Prepare messages for llm.chat
    # We DO NOT use a system prompt to force formatting. We trust the model.
    messages_list = []
    for prompt in prompts:
        messages = [
            {"role": "user", "content": prompt}
        ]
        messages_list.append(messages)

    # 1. FIX: Use 'messages' argument instead of 'messages_list'
    # 2. llm.chat applies the correct chat template automatically
    outputs = llm.chat(messages=messages_list, sampling_params=sampling_params)
    
    print_outputs(outputs)

if __name__ == "__main__":
    main()