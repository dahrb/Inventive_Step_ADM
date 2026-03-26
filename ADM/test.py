import pandas as pd
import asyncio
from openai import AsyncOpenAI
import subprocess
import time

import subprocess
import time

while True:
    try:
        choice = int(input("Enter the number of the answer you wish to choose (only enter the chosen number): ")) - 1
        if 0 <= choice < len(answers):
            selected_answer = answers[choice]
            break
        else:
            print("Invalid choice. Please try again, ensure your response is a number.")
    except ValueError:
        print("Invalid input. Please ensure you only give a number.")