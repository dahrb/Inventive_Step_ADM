import gradio as gr
from openai import OpenAI

# 1. Connect to your remote node
client = OpenAI(
    base_url="http://gpu33.barkla2.liv.alces.network:8000/v1",
    api_key="EMPTY"
)

def chat_response(message, history):
    # 2. Start with the system prompt
    messages = [{"role": "system", "content": "You are a helpful AI assistant."}]
    
    # 3. Robust History Parsing (Fixes the ValueError)
    for turn in history:
        # Case A: History is a list of lists/tuples (Standard Gradio: [user_msg, bot_msg])
        if isinstance(turn, (list, tuple)):
            # Only take the first two elements (ignores extra metadata if present)
            user_msg = turn[0] if len(turn) > 0 else None
            bot_msg = turn[1] if len(turn) > 1 else None
            
            if user_msg:
                messages.append({"role": "user", "content": str(user_msg)})
            if bot_msg:
                messages.append({"role": "assistant", "content": str(bot_msg)})

        # Case B: History is a list of dictionaries (Newer Gradio/Messages format)
        elif isinstance(turn, dict):
            # Pass the dictionary directly if it matches OpenAI format, 
            # otherwise extract content manually
            role = turn.get("role")
            content = turn.get("content")
            if role and content:
                messages.append({"role": role, "content": content})

    # 4. Add the current user message
    messages.append({"role": "user", "content": message})

    # 5. Call the API
    response = client.chat.completions.create(
        model="gpt-oss-120b", 
        messages=messages,
        temperature=0.7,
        stream=True
    )

    # 6. Stream the response
    partial_message = ""
    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            partial_message += delta
            yield partial_message

if __name__ == "__main__":
    gr.ChatInterface(
        fn=chat_response, 
        title="GPT-OSS-120b Chat",
        description="Running on gpu33 via vLLM",
    ).launch(server_name="0.0.0.0")