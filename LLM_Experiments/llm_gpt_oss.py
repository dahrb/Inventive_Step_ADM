import json
import os
from openai_harmony import (
    HarmonyEncodingName,
    load_harmony_encoding,
    Conversation,
    Message,
    Role,
    SystemContent,
    DeveloperContent,
    ToolDescription
)
from vllm import LLM, SamplingParams
from vllm.inputs import TokensPrompt

def main():   
    # --- 1) Setup Harmony with Tool Definitions ---
    encoding = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
    
    # Define the Weather Tool
    weather_tool = ToolDescription(
        name="get_weather",
        description="Get the current weather for a specific location.",
        parameters={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA"
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "The temperature unit to use."
                }
            },
            "required": ["location"]
        }
    )

    # Register tool in Developer instructions
    dev_content = (
        DeveloperContent.new()
        .with_instructions("You are a helpful assistant. Use tools when necessary.")
        .with_function_tools([weather_tool]) 
    )

    convo = Conversation.from_messages(
        [
            Message.from_role_and_content(Role.SYSTEM, SystemContent.new()),
            Message.from_role_and_content(Role.DEVELOPER, dev_content),
            Message.from_role_and_content(Role.USER, "What is the weather like in SF?"),
        ]
    )
    
    # --- 2) Initialize vLLM ---
    llm = LLM(
        model="openai/gpt-oss-120b",
        tensor_parallel_size=2,
        distributed_executor_backend='mp',
        max_model_len=8192,
        enforce_eager=True,
        gpu_memory_utilization=0.90,
        trust_remote_code=True
    )
    
    sampling = SamplingParams(
        max_tokens=512,
        temperature=0.0, 
        stop_token_ids=encoding.stop_tokens_for_assistant_actions(),
    )

    # --- 3) First Pass: Get Tool Call ---
    print(f"\n{'='*20} FIRST PASS (Thinking & Calling) {'='*20}")
    prefill_ids = encoding.render_conversation_for_completion(convo, Role.ASSISTANT)
    
    outputs = llm.generate(
        prompts=TokensPrompt(prompt_token_ids=prefill_ids),
        sampling_params=sampling,
    )
    
    gen_ids = outputs[0].outputs[0].token_ids
    entries = encoding.parse_messages_from_completion_tokens(gen_ids, Role.ASSISTANT)

    tool_call_found = None
    
    for message in entries:
        msg_dict = message.to_dict()
        channel = msg_dict.get("channel")

        if channel == "analysis":
            print(f"[Reasoning]: {msg_dict['content'][0]['text']}")
            # FIX: Append directly to the messages list
            convo.messages.append(message)
            
        elif channel == "commentary":
            content = msg_dict.get("content", [])
            if content and content[0].get("type") == "function_call":
                tool_call = content[0]
                print(f"\n[Tool Call Detected]: {tool_call['name']}({tool_call['arguments']})")
                tool_call_found = tool_call
                # FIX: Append directly to the messages list
                convo.messages.append(message)

    # --- 4) Execution & Second Pass ---
    if tool_call_found and tool_call_found['name'] == 'get_weather':
        # Execute Tool (Mock)
        try:
            args = json.loads(tool_call_found['arguments'])
            loc = args.get('location', 'Unknown')
            print(f" -> Executing get_weather('{loc}')...")
            
            # Mock result
            tool_result = f"The weather in {loc} is currently 18 degrees Celsius and foggy."
        except Exception as e:
            tool_result = f"Error executing tool: {str(e)}"
        
        # Create Tool Response Message
        tool_msg = Message.from_tool_result(
            tool_name="get_weather",
            tool_call_id=tool_call_found.get("call_id", "call_0"), 
            content=tool_result
        )
        # FIX: Append directly to the messages list
        convo.messages.append(tool_msg)

        # Generate Final Answer
        print(f"\n{'='*20} SECOND PASS (Final Answer) {'='*20}")
        prefill_ids_2 = encoding.render_conversation_for_completion(convo, Role.ASSISTANT)
        
        outputs_2 = llm.generate(
            prompts=TokensPrompt(prompt_token_ids=prefill_ids_2),
            sampling_params=sampling,
        )
        
        gen_ids_2 = outputs_2[0].outputs[0].token_ids
        entries_2 = encoding.parse_messages_from_completion_tokens(gen_ids_2, Role.ASSISTANT)
        
        for message in entries_2:
            msg_dict = message.to_dict()
            if not msg_dict.get("channel") or msg_dict.get("channel") == "voice": 
                for part in msg_dict.get("content", []):
                    if part["type"] == "text":
                        print(f"[Final Answer]: {part['text']}")

if __name__ == '__main__':
    main()