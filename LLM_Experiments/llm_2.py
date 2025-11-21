from vllm import LLM, SamplingParams

# It's recommended to use a distilled version for easier local execution
model_id = "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B"

# Initialize the LLM engine
# For larger models, you may need to set tensor_parallel_size
# llm = LLM(model=model_id, trust_remote_code=True, tensor_parallel_size=2)
llm = LLM(model=model_id, trust_remote_code=True)

# Define the sampling parameters
sampling_params = SamplingParams(temperature=0.7, top_p=0.95, max_tokens=512)

# Define your prompts
prompts = [
    "What is the primary advantage of using a reasoning model?",
    "Write a short story about a robot that learns to paint.",
]

# Generate the outputs
outputs = llm.generate(prompts, sampling_params)

# Print the results
for output in outputs:
    prompt = output.prompt
    generated_text = output.outputs[0].text
    print(f"Prompt: {prompt!r}")
    print(f"Generated text: {generated_text!r}\n")