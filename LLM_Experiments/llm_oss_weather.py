import os
from vllm import LLM, SamplingParams
from vllm.inputs import TokensPrompt
from openai_harmony import load_harmony_encoding, HarmonyEncodingName, Conversation, Message, Role, DeveloperContent, ToolDescription
import json

# --- 1. THE "GAME" (Your Dynamic Tool) ---
# This represents your CMD line program or external API
SECRET_WEATHER_STATE = {
    "location": "Liverpool",
    "condition": "Rainy",
    "temperature": "Cold",
    "wind": "High"
}

def check_weather_oracle(question_type):
    """
    The 'Game' that answers specific questions about the hidden weather state.
    """
    print(f"\n[GAME SYSTEM] Processing query: {question_type}...")
    
    if question_type == "check_rain":
        return "Yes, it is currently raining." if SECRET_WEATHER_STATE["condition"] == "Rainy" else "No rain."
    elif question_type == "check_temp":
        return f"The temperature feels {SECRET_WEATHER_STATE['temperature']}."
    elif question_type == "check_wind":
        return f"Wind speeds are {SECRET_WEATHER_STATE['wind']}."
    elif question_type == "check_location":
        return f"You are in {SECRET_WEATHER_STATE['location']}."
    else:
        return "Unknown sensor reading."

# --- 2. SETUP LLM & TOOLS ---
def main():
    # Define the tools the LLM can use to play the game
    tools = [
        ToolDescription(
            name="consult_weather_sensor",
            description="Check a specific weather sensor to gather clues.",
            parameters={
                "type": "object",
                "properties": {
                    "sensor_type": {
                        "type": "string",
                        "enum": ["check_rain", "check_temp", "check_wind", "check_location"],
                        "description": "The specific sensor to query."
                    }
                },
                "required": ["sensor_type"]
            }
        ),
        ToolDescription(
            name="submit_final_report",
            description="Submit your final determination of the weather.",
            parameters={
                "type": "object",
                "properties": {
                    "conclusion": {"type": "string", "description": "The final weather report summary."}
                },
                "required": ["conclusion"]
            }
        )
    ]

    # Setup Harmony
    encoding = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
    dev_content = DeveloperContent.new().with_instructions("You are a Weather Detective. You cannot see outside. You must use your tools to query sensors one by one to build a complete picture of the weather. Once you are sure, submit your final report.").with_function_tools(tools)

    convo = Conversation.from_messages([
        Message.from_role_and_content(Role.SYSTEM, dev_content),
        Message.from_role_and_content(Role.USER, "Start the investigation. What is the weather right now?"),
    ])

    # Initialize vLLM (Offline Mode, kept alive)
    llm = LLM(
        model="openai/gpt-oss-120b", # Or your 20B model
        tensor_parallel_size=2,      # Adjust for your A100 setup
        distributed_executor_backend='mp',
        quantization="mxfp4",
        enforce_eager=True,
        gpu_memory_utilization=0.90,
        trust_remote_code=True
    )

    sampling = SamplingParams(temperature=0.0, max_tokens=256, stop_token_ids=encoding.stop_tokens_for_assistant_actions())

    # --- 3. THE GAME LOOP ---
    max_turns = 10
    turn = 0
    game_over = False

    print(f"\n{'='*40}\nSTARTING GAME LOOP\n{'='*40}")

    while turn < max_turns and not game_over:
        turn += 1
        print(f"\n--- TURN {turn} ---")

        # A. GENERATE THOUGHT/ACTION
        prefill_ids = encoding.render_conversation_for_completion(convo, Role.ASSISTANT)
        outputs = llm.generate(prompts=TokensPrompt(prompt_token_ids=prefill_ids), sampling_params=sampling)
        
        gen_ids = outputs[0].outputs[0].token_ids
        entries = encoding.parse_messages_from_completion_tokens(gen_ids, Role.ASSISTANT)

        tool_call_found = None

        for message in entries:
            msg_dict = message.to_dict()
            # Add thought/action to history
            convo.messages.append(message)

            if msg_dict.get("channel") == "analysis":
                print(f"[Reasoning]: {msg_dict['content'][0]['text']}")
            
            elif msg_dict.get("channel") == "commentary":
                content = msg_dict.get("content", [])
                if content and content[0].get("type") == "function_call":
                    tool_call = content[0]
                    print(f"[Tool Call]: {tool_call['name']} ({tool_call['arguments']})")
                    tool_call_found = tool_call

        # B. EXECUTE TOOL (The "Offline" dynamic part)
        if tool_call_found:
            name = tool_call_found['name']
            args = json.loads(tool_call_found['arguments'])

            if name == "consult_weather_sensor":
                # Call the local python function (Game Engine)
                result = check_weather_oracle(args["sensor_type"])
                print(f"[Tool Result]: {result}")
                
                # Feed result back to LLM
                tool_msg = Message.from_tool_result(
                    tool_name=name,
                    tool_call_id=tool_call_found.get("call_id", "call_0"), 
                    content=str(result)
                )
                convo.messages.append(tool_msg)

            elif name == "submit_final_report":
                print(f"\n[VICTORY]: Agent reported -> {args['conclusion']}")
                game_over = True
        else:
            # If the model just talked without calling a tool, push it to continue
            print("[System]: Model output text but no tool. Nudging...")
            # (Optional: Add a user message forcing a tool use if it gets stuck)

    if not game_over:
        print("\n[GAME OVER]: Max turns reached.")

if __name__ == "__main__":
    main()