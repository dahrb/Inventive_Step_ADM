import sys
import time

# --- HARDCODED KNOWLEDGE TREE ---
class QuestionNode:
    def __init__(self, text, yes_node=None, no_node=None):
        self.text = text
        self.yes_node = yes_node
        self.no_node = no_node
    def is_guess(self): return self.yes_node is None and self.no_node is None

# Build Tree
# Branch: Living
guess_dog = QuestionNode("Is it a dog?")
guess_cat = QuestionNode("Is it a cat?")
q_bark = QuestionNode("Does it bark?", yes_node=guess_dog, no_node=guess_cat)

guess_eagle = QuestionNode("Is it an eagle?")
guess_goldfish = QuestionNode("Is it a goldfish?")
q_fly = QuestionNode("Can it fly?", yes_node=guess_eagle, no_node=guess_goldfish)

q_mammal = QuestionNode("Is it a mammal?", yes_node=q_bark, no_node=q_fly)

# Branch: Non-Living
guess_pizza = QuestionNode("Is it Pizza?")
guess_apple = QuestionNode("Is it an Apple?")
q_eat = QuestionNode("Is it a prepared meal?", yes_node=guess_pizza, no_node=guess_apple)

guess_car = QuestionNode("Is it a Car?")
guess_pencil = QuestionNode("Is it a Pencil?")
q_vehicle = QuestionNode("Is it a vehicle?", yes_node=guess_car, no_node=guess_pencil)

q_food = QuestionNode("Can you eat it?", yes_node=q_eat, no_node=q_vehicle)

# Root
ROOT_NODE = QuestionNode("Is it a living thing?", yes_node=q_mammal, no_node=q_food)

def main():
    # Force unbuffered output so the LLM script sees text immediately
    sys.stdout.reconfigure(line_buffering=True)
    
    print("GAME START: I will guess your secret object.")
    print("Answer 'yes' or 'no'.")
    
    current_node = ROOT_NODE
    questions = 0
    
    while True:
        questions += 1
        
        if current_node.is_guess():
            print(f"GUESS: {current_node.text}")
            # Wait for confirmation
            try:
                ans = input().strip().lower()
                if 'y' in ans:
                    print("GAME OVER: I WIN!")
                else:
                    print("GAME OVER: I LOST.")
            except EOFError:
                pass
            break
            
        # Ask Question
        print(f"QUESTION: {current_node.text}")
        
        try:
            ans = input().strip().lower()
        except EOFError:
            break
            
        if 'y' in ans:
            current_node = current_node.yes_node
        elif 'n' in ans:
            current_node = current_node.no_node
        else:
            print("INVALID: Please answer yes or no.")
            questions -= 1 # Retry

if __name__ == "__main__":
    main()