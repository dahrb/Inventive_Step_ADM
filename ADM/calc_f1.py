import json
import numpy as np
from sklearn.metrics import f1_score, accuracy_score

filepath = '/users/sgdbareh/scratch/ADM_JURIX/ADM/results_comvik_baseline_config2.json'

with open(filepath, 'r') as f:
    data = json.load(f)

print(data)
# Convert YES/NO to 1/0
y_pred = [1 if v == "YES" else 0 for v in data.values()]

print("Predicted labels:", y_pred)

print(y_pred)
# Example: if you have ground truth
comvik = [0,0,0,1,0]
validation = [0,0,0,1,0,1,1,1,1,0]

print("Accuracy:", accuracy_score(comvik, y_pred)*100)
print("F1 score:", f1_score(comvik, y_pred)*100)