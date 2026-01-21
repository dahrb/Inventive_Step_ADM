import os
import json
import re
import pandas as pd
import argparse

# --- 1. QUESTION MAPPING (From your provided file) ---
RAW_MAPPING = {
    # --- Inventive Step: Preconditions ---
    "SimilarPurpose": 1,
    "SimilarEffect": 2,
    "SameField": 3,
    "SimilarField": 3,
    "Contested": 4,
    "Textbook": 5,
    "TechnicalSurvey": 5,
    "PublicationNewField": 5,
    "SinglePublication": 5,
    "SkilledIn": 6,
    "Average": 7,
    "Aware": 8,
    "Access": 9,
    "Individual": 10,
    "ResearchTeam": 10,
    "ProductionTeam": 10,
    "SingleReference": 11,
    "MinModifications": 12,
    "AssessedBy": 12,
    "CombinationAttempt": 13,
    "SameFieldCPA": 14,
    "SimilarFieldCPA": 14,
    "CombinationMotive": 15,
    "BasisToAssociate": 16,

    # --- Sub-ADM 1 ---
    "IndependentContribution": 17,
    "CombinationContribution": 18,
    "ComputerSimulation": 19,
    "NumericalData": 19,
    "MathematicalMethod": 19,
    "OtherExclusions": 19,
    "CircumventTechProblem": 20,
    "TechnicalAdaptation": 21,
    "IntendedTechnicalUse": 22,
    "TechUseSpecified": 23,
    "SpecificPurpose": 24,
    "FunctionallyLimited": 25,
    "UnexpectedEffect": 26,
    "PreciseTerms": 27,
    "OneWayStreet": 28,
    "Credible": 29,
    "Reproducible": 29,
    "NonReproducible": 29,
    "ClaimContainsEffect": 30,
    "SufficiencyOfDisclosureRaised": 31,

    # --- Inventive Step: Main ---
    "Synergy": 32,
    "FunctionalInteraction": 33,

    # --- Sub-ADM 2 ---
    "Encompassed": 34,
    "Embodied": 35,
    "ScopeOfClaim": 36,
    "WrittenFormulation": 37,
    "Hindsight": 38,
    "WouldAdapt": 39,
    "WouldModify": 39,

    # --- Inventive Step: Main (Continued) ---
    "DisadvantageousMod": 40,
    "Foreseeable": 41,
    "UnexpectedAdvantage": 42,
    "BioTech": 43,
    "Antibody": 44,
    "PredictableResults": 45,
    "ReasonableSuccess": 46,
    "KnownTechnique": 47,
    "OvercomeTechDifficulty": 48,
    "GapFilled": 49,
    "WellKnownEquivalent": 50,
    "KnownProperties": 51,
    "AnalogousUse": 52,
    "KnownDevice": 53,
    "ObviousCombination": 54,
    "AnalogousSubstitution": 55,
    "ChooseEqualAlternatives": 56,
    "NormalDesignProcedure": 57,
    "SimpleExtrapolation": 58,
    "ChemicalSelection": 59
}

# Invert mapping: Q number (int) -> Factor Name (str)
Q_TO_FACTOR = {}
for factor, q_num in RAW_MAPPING.items():
    tag = f"Q{q_num}"
    if tag in Q_TO_FACTOR:
        Q_TO_FACTOR[tag] += f" / {factor}"
    else:
        Q_TO_FACTOR[tag] = factor

# --- 2. HELPER FUNCTIONS ---

def extract_q_tag(text):
    if not text: return None
    match = re.search(r'\[Q(\d+)\]', text)
    if match: return f"Q{match.group(1)}"
    return None

def find_termination_reason(log_path):
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None

    if not isinstance(data, list) or not data:
        return None

    for entry in reversed(data):
        question = entry.get('question', '')
        tag = extract_q_tag(question)
        
        if tag:
            factor_name = Q_TO_FACTOR.get(tag, "Unknown_Factor")
            return {
                "last_q_tag": tag,
                "factor": factor_name,
                "answer": entry.get('answer', 'N/A')
            }
    return None

def parse_directory_structure(root_path):
    results = []
    print(f"Scanning directory: {root_path} ...")
    
    for root, dirs, files in os.walk(root_path):
        if "log.json" in files:
            log_path = os.path.join(root, "log.json")
            parts = log_path.split(os.sep)
            
            # Robust ID extraction
            try:
                if "Valid_Cases" in parts:
                    base_idx = parts.index("Valid_Cases")
                    case_id = parts[base_idx + 1]
                    config_id = parts[base_idx + 3] # run_1 is at +2
                else:
                    case_id = parts[-4]
                    config_id = parts[-2]
            except IndexError:
                case_id, config_id = "Unknown", "Unknown"

            reason_data = find_termination_reason(log_path)
            
            if reason_data:
                results.append({
                    "CaseID": case_id,
                    "Config": config_id,
                    "Factor": reason_data['factor'],
                    "Last_Answer": reason_data['last_q_tag']
                })

    return pd.DataFrame(results)

# --- 3. MAIN EXECUTION ---

if __name__ == "__main__":
    # Default path based on your prompt
    DEFAULT_PATH = "/users/sgdbareh/scratch/ADM_JURIX/Outputs/Valid_Cases"
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str, default=DEFAULT_PATH, help="Path to Valid_Cases")
    args = parser.parse_args()

    if not os.path.exists(args.path):
        print(f"Error: Path not found: {args.path}")
        exit(1)

    df = parse_directory_structure(args.path)

    if not df.empty:
        print("\n" + "="*60)
        print(f"ANALYSIS COMPLETE: Found {len(df)} logs")
        print("="*60)
        
        # 1. Factor Frequencies
        print("\n--- TOP TERMINATION FACTORS (Where did the cases end?) ---")
        print(df['Factor'].value_counts().to_string())
        
        # 2. Config Breakdown (if applicable)
        if df['Config'].nunique() > 1:
            print("\n" + "="*60)
            print("--- BREAKDOWN BY CONFIGURATION ---")
            pivot = pd.crosstab(df['Factor'], df['Config'])
            pivot['Total'] = pivot.sum(axis=1)
            pivot = pivot.sort_values('Total', ascending=False).drop(columns='Total')
            print(pivot.to_string())
            print("="*60)
        
    else:
        print("No valid logs found.")