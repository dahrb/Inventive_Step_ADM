from vllm import LLM, SamplingParams
import os
import re

def parse_output(generated_text):
    """
    Parses the generated text by using the [RESPONSE]: tag as the primary delimiter.
    Everything before the delimiter is treated as Reasoning.
    """
    text_to_parse = generated_text.strip()
    
    # 1. Look for the [RESPONSE]: tag (case-insensitive)
    response_tag_match = re.search(r'\[RESPONSE\]:\s*', text_to_parse, re.DOTALL | re.IGNORECASE)
    
    if response_tag_match:
        # Everything from the start up to the [RESPONSE]: tag is the Reasoning
        reasoning = text_to_parse[:response_tag_match.start()].strip()
        
        # Everything after the [RESPONSE]: tag is the Content
        content = text_to_parse[response_tag_match.end():].strip()
        
        # Remove any unwanted internal tags/text from the start of reasoning if present
        reasoning = re.sub(r'Okay, so I need to figure out.*', '', reasoning, flags=re.DOTALL | re.IGNORECASE).strip()
        reasoning = reasoning.replace("</think>", "").strip()
        
        # If the reasoning is empty after cleanup, set it to the default text
        if not reasoning:
             reasoning = "N/A (Model generated minimal pre-response text.)"
            
    else:
        # If the model didn't even generate the [RESPONSE] tag, 
        # the entire output is treated as content, and reasoning is marked N/A.
        reasoning = "N/A (Response tag not found.)"
        content = text_to_parse
        
    return reasoning, content

def print_outputs(outputs):
    """
    Processes the list of CompletionOutput objects from llm.generate.
    """
    for output in outputs:
        # Extract original user prompt for display
        user_prompt_match = re.search(r"User:\s*(.*?)\s*System:|\s*User:\s*(.*)", output.prompt, re.DOTALL)
        display_prompt = user_prompt_match.group(1).strip() if user_prompt_match and user_prompt_match.group(1) else (user_prompt_match.group(2).strip() if user_prompt_match and user_prompt_match.group(2) else "N/A")
        
        generated_text = output.outputs[0].text
        
        reasoning, content = parse_output(generated_text)
        
        print(f"Prompt: {display_prompt!r}")
        print(f"Reasoning: {reasoning!r}")
        print(f"Content: {content!r}")
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
        temperature=0.6,
        top_p = 0.95,
        max_tokens=4096,
        seed = 42,
        # Stop on common tags to prevent run-on text
        stop=["<|im_end|>", "\n\n###", "\n\nUser:"] 
    )
    
    CUDA_DEVICES = int(os.environ.get("CUDA_VISIBLE_DEVICES", "1").count(',')) + 1
    print(CUDA_DEVICES)

    llm = LLM(
        model="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        tensor_parallel_size=CUDA_DEVICES)
    
    full_prompts = []
    
    for prompt in prompts:
        # REVISED PROMPT TEMPLATE: 
        # We simplify the instruction to focus only on the required output format.
        manual_prompt = f"""
        System: You MUST provide your detailed internal thought process first, followed by your final, concise factual answer. Your final output MUST end with the tag: [RESPONSE]: <final answer>. Do not generate any other text or tags.
        
        User: {prompt}
        """
        full_prompts.append(manual_prompt.strip())

    # Generate all prompts in one highly efficient batch
    outputs = llm.generate(full_prompts, sampling_params)
    
    # Process and print the results
    print_outputs(outputs)


if __name__ == "__main__":
    main()