import json
import numpy as np
from sklearn.metrics import f1_score, accuracy_score

filepath = '/users/sgdbareh/scratch/ADM_JURIX/ADM/results_comvik_tool_config1.json'

with open(filepath, 'r') as f:
    data = json.load(f)

# 2. Calculate F1 for each run
run_scores = []
run_names = []

comvik = ['NO','NO','NO','YES','NO']
validation = ['NO','NO','NO','YES','NO','YES','YES','YES','YES','NO']
predictions_data = data

# Lists to store results from every run
f1_scores = []
acc_scores = []

print(f"{'Run ID':<10} | {'F1 Score':<10} | {'Accuracy':<10}")
print("-" * 38)

# 3. Iterate through runs
for run_id, preds_dict in predictions_data.items():
    # Sort keys to ensure alignment with the Ground Truth list order
    sorted_keys = sorted(preds_dict.keys())
    
    # Extract prediction values in the correct order
    y_pred = [preds_dict[key] for key in sorted_keys]
    
    # Calculate Metrics
    # pos_label='YES' is required for F1 since inputs are strings
    f1 = f1_score(comvik, y_pred, pos_label='YES')
    acc = accuracy_score(comvik, y_pred)
    
    # Store results
    f1_scores.append(f1)
    acc_scores.append(acc)
    
    print(f"{run_id:<10} | {f1:.4f}     | {acc:.4f}")

# 4. Calculate Aggregated Stats
print("-" * 38)
print("FINAL STATISTICS")
print("-" * 38)

# F1 Stats
print(f"Mean F1:      {np.mean(f1_scores)*100:.4f}")
print(f"F1 Std Dev:  {np.std(f1_scores)*100:.6f}")

print("-" * 38)

# Accuracy Stats
print(f"Mean Acc:     {np.mean(acc_scores)*100:.4f}")
print(f"Acc Std Dev: {np.std(acc_scores)*100:.6f}")

# print(data)
# # Convert YES/NO to 1/0
# y_pred = [1 if v == "YES" else 0 for v in data.values()]

# print("Predicted labels:", y_pred)

# print(y_pred)
# # Example: if you have ground truth


# print("Accuracy:", accuracy_score(validation, y_pred)*100)
# print("F1 score:", f1_score(validation, y_pred)*100)

