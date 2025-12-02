import os
import json
import time
import pickle
from openai import OpenAI
import re
from tenacity import retry, wait_random_exponential, stop_after_attempt
from termcolor import colored  

# --- CONFIGURATION ---
# Replace with your actual server URL from the SLURM log (e.g., http://gpu12:8000/v1)
API_BASE = "http://gpu33.barkla2.liv.alces.network:8000/v1"
API_KEY = "EMPTY"

# Initialize Synchronous Client
client = OpenAI(base_url=API_BASE, api_key=API_KEY)

# --- 1. TOOL IMPLEMENTATION ---
def execute_weather_tool(location, unit="celsius"):
    """
    Simulates checking a weather API.
    """
    # Database of fake weather conditions
    weather_db = {
        "liverpool": "Rainy, 12 degrees, Wind: High",
        "san francisco": "Foggy, 16 degrees, Wind: Moderate",
        "london": "Cloudy, 15 degrees, Wind: Low",
        "marengo": "Sunny, 25 degrees, Wind: None",
    }
    
    # Simple lookup logic
    key = location.lower()
    for city, weather in weather_db.items():
        if city in key:
            return json.dumps({"location": location, "weather": weather, "unit": unit})
            
    return json.dumps({"error": f"Location '{location}' not found."})

@retry(wait=wait_random_exponential(multiplier=1, max=40), stop=stop_after_attempt(3))
def chat_completion_request(messages, tools=None, tool_choice=None, model="gpt-oss-120b"):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            temperature=0.0,
            reasoning_effort='high',
            tool_choice=tool_choice,
        )
        return response
    except Exception as e:
        print("Unable to generate ChatCompletion response")
        print(f"Exception: {e}")
        return e
# --- 2. PROCESSING ---
def process_question(q, index):
    messages = [
        {"role": "system", "content": "You are a weather helper. If any question doesn't concern a location for which the user wishes to know the weather then respond that the request is invalid. Call tools to answer the weather."},
        {"role": "user", "content": q}
    ]

    try:
        start_time = time.time()
        
        tools = [{
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get current weather",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {"type": "string", "description":"location of the place we need the weather for "},
                                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                            },
                            "required": ["location"]
                        }
                    }
                }]
                        
        #generate initial tool call
        chat_response = chat_completion_request(
        messages, tools=tools, tool_choice={"type": "function", "function": {"name": "get_weather"}})
        assistant_message = chat_response.choices[0].message
        messages.append(assistant_message)
        print(assistant_message)
        
        tool_calls = assistant_message.tool_calls

        print(tool_calls)
        # --- CHECK 1: Native Tool Call ---
        if tool_calls:
            tool_call_id = tool_calls[0].id
            tool_function_name = tool_calls[0].function.name
            tool_query_string = json.loads(tool_calls[0].function.arguments)
    
            # Step 3: Call the function and retrieve results. Append the results to the messages list.      
            if tool_function_name == 'get_weather':
                location = tool_query_string["location"]
                
                try:
                    unit = tool_query_string['unit']
                    tool_result = execute_weather_tool(location=location,unit=unit)

                except:
                    unit = 'celsius'
                    tool_result = execute_weather_tool(location=location,unit=unit)
                

                messages.append({
                    "role":"tool", 
                    "tool_call_id":tool_call_id, 
                    "name": tool_function_name, 
                    "content":tool_result
                })
                
                # Step 4: Invoke the chat completions API with the function response appended to the messages list
                # Note that messages with role 'tool' must be a response to a preceding message with 'tool_calls'
                
                chat_response = chat_completion_request(
                messages)
                
                assistant_message = chat_response.choices[0].message
                messages.append(assistant_message)
                
                print(f"--- Result {index+1} ---")
                print(f"Q: {q}")
                print(f"Action: Called function(location:{location},unit:{unit})")
                print(f"Result: {tool_result}")
                print(f"Final Answer: {chat_response.choices[0].message.content}")
                return chat_response
        else:
            return f"Error: function {tool_function_name} does not exist"              

    except Exception as e:
        print(f"\n[ERROR] {q}: {e}")
        return None

# --- 3. MAIN LOOP ---
def main():
    print(f"Connecting to Server at {API_BASE}...", flush=True)
    
    questions = [
        "What is the weather like in Liverpool?",
        # "9.11 and 9.8, which is greater?",
        # "Check weather for London",
        #"What is the weather like in Los Angeles?"
    ]

    print(f"Processing {len(questions)} questions sequentially...")
    global_start = time.time()
    
    results = []
    
    # Simple Loop
    for i, q in enumerate(questions):
        res = process_question(q, i)
        if res:
            results.append(res)
    
    total_time = time.time() - global_start
    print(f"\nTotal Execution Time: {total_time:.2f}s")

    # # Save responses
    # with open("llm_oss_weather_sync_responses.pkl", "wb") as f:
    #     pickle.dump(results, f)
    # print("Saved responses to 'llm_oss_weather_sync_responses.pkl'.")

if __name__ == "__main__":
    main()