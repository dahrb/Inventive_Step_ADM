"""
Instantiates the Hybrid ADM System using a batched method of asking the questions

Last Updated: 26.03.2025

Status: Testing 

To Do:
- commented a lot out see if it affects anything

Test Coverage: ?

"""

import argparse
import asyncio
import contextvars
import json
import logging
import os
import re
import sys
import time
import traceback
from datetime import datetime
import pandas as pd
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from inventive_step_ADM import adm_initial, adm_main

#===LOGGER SETUP====
logger = logging.getLogger("Hybrid_ADM_System")

#track the active case for logging
CURRENT_CASE_REF = contextvars.ContextVar("current_case_ref", default="NO_CASE")
class CaseRefFilter(logging.Filter):
    def filter(self, record):
        record.case_ref = CURRENT_CASE_REF.get()
        return True

logging.basicConfig(level=logging.INFO, format='%(levelname)s [%(case_ref)s]: %(message)s')
_case_ref_filter = CaseRefFilter()
for _handler in logging.getLogger().handlers:
    _handler.addFilter(_case_ref_filter)

# logging.getLogger("httpx").setLevel(logging.WARNING)
# logging.getLogger("openai").setLevel(logging.WARNING)
# logging.getLogger("httpcore").setLevel(logging.WARNING)
# logging.getLogger("urllib3").setLevel(logging.WARNING)
# logging.getLogger("stainless").setLevel(logging.WARNING)

#===GLOBAL VARS====

#concurrency limits
REQUEST_SEMAPHORE = asyncio.Semaphore(20)

# Paths and Data Defaults
BASE_CASE_DIR = "../Outputs/Valid_Cases"
ADM_SCRIPT_PATH = '../ADM/UI.py'
RAW_DATA = None
CURRENT_CONFIG = None
LLM_TEMPERATURE = 0.0

SKILLED_PERSON_PROMPT_MARKERS = (
    "[q10]",
    "characterise the the skilled person",
    "characterise the skilled person",
    "describe the individual practitioner",
    "describe the research team",
    "describe the production or manufacturing team",
    "describe the manufacturing team",
)

MODELS = {
    "gpt": {"id": "gpt-oss-120b"},
    "llama": {"id": "Llama-3.3-70B-Instruct-FP8"},
    "qwen": {"id": "Qwen-3-80B"},
}

def complete_json_brace(raw_json: str) -> str:
    """If JSON is truncated, try to auto-complete by adding a closing brace."""
    raw_json = raw_json.rstrip()
    if raw_json.endswith('}'):
        return raw_json
    if raw_json.endswith('"'):
        return raw_json + '\n}'
    if raw_json.endswith(','):
        return raw_json[:-1] + '\n}'
    return raw_json + '\n}'


def extract_first_json_object(raw_text: str) -> str:
    """Extract first balanced JSON object from raw text; returns empty string if not found."""
    if not raw_text:
        return ""
    start = raw_text.find("{")
    if start == -1:
        return ""

    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(raw_text)):
        char = raw_text[index]

        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return raw_text[start:index + 1]

    return raw_text[start:]


def parse_model_from_raw_json(model_class, raw_json: str):
    """Robust parse flow: direct parse -> extracted object parse -> brace-completed parse."""
    if not raw_json:
        raise ValueError("Empty response from LLM")

    candidate = raw_json.strip()

    try:
        return model_class.model_validate_json(candidate), candidate
    except Exception:
        pass

    extracted = extract_first_json_object(candidate)
    if extracted:
        try:
            return model_class.model_validate_json(extracted), extracted
        except Exception:
            pass

        completed = complete_json_brace(extracted)
        if completed != extracted:
            try:
                return model_class.model_validate_json(completed), completed
            except Exception:
                pass

    completed_candidate = complete_json_brace(candidate)
    if completed_candidate != candidate:
        return model_class.model_validate_json(completed_candidate), completed_candidate

    return model_class.model_validate_json(candidate), candidate


def is_skilled_person_nature_question(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in SKILLED_PERSON_PROMPT_MARKERS)


def _question_text_for_key(question_key: str) -> str:
    key = question_key.lower()

    question_sources = [
        globals().get("ALL_EXACT_QUESTIONS", {}),
        globals().get("INITIAL_ADM_QUESTIONS", {}),
        globals().get("MAIN_ADM_QUESTIONS", {}),
        globals().get("MAIN_ADM_NO_SUB_1_QUESTIONS", {}),
        globals().get("MAIN_ADM_NO_SUB_2_QUESTIONS", {}),
        globals().get("MAIN_ADM_NO_SUB_BOTH_QUESTIONS", {}),
    ]

    for source in question_sources:
        if isinstance(source, dict) and key in source:
            return source[key]

    return ""


def _question_expects_yes_no(question_key: str) -> bool:
    question_text = _question_text_for_key(question_key).lower()
    return "answer 'yes' or 'no' only" in question_text or "(y/n)" in question_text


def _question_allowed_numeric_options(question_key: str) -> set[str]:
    question_text = _question_text_for_key(question_key)
    return set(re.findall(r"^\s*(\d+)\.\s", question_text, flags=re.MULTILINE))


def _question_numeric_option_map(question_key: str) -> dict[str, str]:
    question_text = _question_text_for_key(question_key)
    option_map = {}
    for option_num, option_text in re.findall(r"^\s*(\d+)\.\s*(.+)$", question_text, flags=re.MULTILINE):
        cleaned_option = option_text.strip()
        if cleaned_option:
            option_map[option_num] = cleaned_option
    return option_map


def _normalize_mcq_answer(raw_answer: str, question_key: str) -> str | None:
    cleaned = (raw_answer or "").strip().replace("**", "")
    lower_clean = cleaned.lower()

    if lower_clean in ["y", "yes"]:
        return "y"
    if lower_clean in ["n", "no"]:
        return "n"

    digit_match = re.search(r"\d+", cleaned)
    if digit_match:
        return digit_match.group(0)

    word_to_digit = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
    }
    for word, digit in word_to_digit.items():
        if re.search(rf"\b{word}\b", lower_clean):
            return digit

    option_map = _question_numeric_option_map(question_key)
    if option_map:
        normalized_raw = re.sub(r"\s+", " ", lower_clean).strip(" .,:;!?\"'`")
        for option_num, option_text in option_map.items():
            normalized_option = re.sub(r"\s+", " ", option_text.lower()).strip(" .,:;!?\"'`")
            if not normalized_option:
                continue
            if normalized_option in normalized_raw:
                return option_num
            if len(normalized_raw) >= 8 and normalized_raw in normalized_option:
                return option_num

    if _question_expects_yes_no(question_key):
        yn_word_match = re.search(r"\b(yes|no)\b", lower_clean)
        if yn_word_match:
            return "y" if yn_word_match.group(1) == "yes" else "n"

    logger.error(
        "No valid y/n or digit found in answer for %s: %r.",
        question_key,
        raw_answer,
    )
    return None


def _is_valid_normalized_answer(question_key: str, normalized_answer: str) -> bool:
    if not normalized_answer:
        return False

    allowed_options = _question_allowed_numeric_options(question_key)

    if _question_expects_yes_no(question_key):
        if normalized_answer in {"y", "n"}:
            return True
        if allowed_options:
            return normalized_answer in allowed_options
        return False

    if allowed_options:
        return normalized_answer in allowed_options

    return bool(re.fullmatch(r"\d+", normalized_answer))

#===PYDANTIC SCHEMAS===

class QuestionResponse(BaseModel):
    answer: str = Field(description="Your chosen answer. For multiple choice, provide the digit. For yes/no questions, provide 'y' or 'n'.")
    reasoning: str = Field(description="Your step-by-step reasoning for choosing this answer.")

class FinalVerdictResponse(BaseModel):
    answer: str = Field(description="State 'Yes' or 'No' based on whether an inventive step is present from the tool.")
    reasoning: str = Field(description="Explain whether you agree with the final outcome derived from the tool session.")
    confidence_score: int = Field(description="Confidence score from 0-100 based on your faith in the tool's outcome.")

class InitialADM_Batch(BaseModel):
    invention_title: QuestionResponse = Field(description="What is the title of your invention?")
    invention_description: QuestionResponse = Field(description="Please provide a brief description of your invention (max 100 words)")
    technical_field: QuestionResponse = Field(description="Please provide a brief description of the technical field of the invention? (max 100 words)")
    relevant_prior_art: QuestionResponse = Field(description="Please briefly describe the relevant prior art (max 100 words)")
    common_general_knowledge: QuestionResponse = Field(description="Please briefly describe the common general knowledge")
    q1_similar_purpose: QuestionResponse = Field(description="[Q1]")
    q2_similar_effects: QuestionResponse = Field(description="[Q2]")
    q3_same_field: QuestionResponse = Field(description="[Q3]")
    q4_contested: QuestionResponse = Field(description="[Q4]")
    q5_cgk_evidence: QuestionResponse = Field(description="[Q5]")
    q6_skilled_in: QuestionResponse = Field(description="[Q6]")
    q7_average: QuestionResponse = Field(description="[Q7]")
    q8_aware: QuestionResponse = Field(description="[Q8]")
    q9_access: QuestionResponse = Field(description="[Q9]")
    q10_skilled_person: QuestionResponse = Field(description="[Q10]")
    closest_prior_art_description: QuestionResponse = Field(description="Please describe the candidate for the closest prior art")
    q11_cpa: QuestionResponse = Field(description="[Q11]")
    q12_minmod: QuestionResponse = Field(description="[Q12]")
    q13_combo_attempt: QuestionResponse = Field(description="[Q13]")
    q14_combined: QuestionResponse = Field(description="[Q14]")
    q15_combo_motive: QuestionResponse = Field(description="[Q15]")
    q16_basis: QuestionResponse = Field(description="[Q16]")

class SubADM1_Batch(BaseModel):
    q17_tech_cont: QuestionResponse = Field(description="[Q17] pleas only givie the number corresponding to the chosen answer")
    q19_dist_feat: QuestionResponse = Field(description="[Q19]")
    q20_circumvent: QuestionResponse = Field(description="[Q20]")
    q21_tech_adapt: QuestionResponse = Field(description="[Q21]")
    q22_intended: QuestionResponse = Field(description="[Q22]")
    q23_tech_use: QuestionResponse = Field(description="[Q23]")
    q24_specifc_purpose: QuestionResponse = Field(description="[Q24]")
    q25_func_limited: QuestionResponse = Field(description="[Q25]")
    q26_unxpected: QuestionResponse = Field(description="[Q26]")
    q27_precise: QuestionResponse = Field(description="[Q27]")
    q28_one_way: QuestionResponse = Field(description="[Q28]")
    q29_credible: QuestionResponse = Field(description="[Q29]")
    q30_claim_contains: QuestionResponse = Field(description="[Q30]")
    q31_suff_dis: QuestionResponse = Field(description="[Q31]")

class SubADM2_Batch(BaseModel):
    q34_encompassed: QuestionResponse = Field(description="[Q34]")
    q36_scope: QuestionResponse = Field(description="[Q36]")
    q38_hindsight: QuestionResponse = Field(description="[Q38]")
    q39_would: QuestionResponse = Field(description="[Q39]")
    
class MainADM_Inter_Batch(BaseModel):
    q32_synergy: QuestionResponse = Field(description="[Q32]")
    q33_func_int: QuestionResponse = Field(description="[Q33]")

class MainADM_No_Sub_1(BaseModel):
    q100_dist_feat: QuestionResponse = Field(description="[Q100]")
    q101_tech_cont: QuestionResponse = Field(description="[Q101]")
    q102_unexpected: QuestionResponse = Field(description="[Q102]")
    q103_precise: QuestionResponse = Field(description="[Q103]")
    q104_one_way: QuestionResponse = Field(description="[Q104]")
    q105_credible: QuestionResponse = Field(description="[Q105]")    
    q106_claimcontains: QuestionResponse = Field(description="[Q106]")
    q107_suff_dis: QuestionResponse = Field(description="[Q107]")

class MainADM_No_Sub_2(BaseModel):
    obj_t_problem: QuestionResponse = Field(description="Please briefly describe the objective technical problem")
    q200_encompassed: QuestionResponse = Field(description="[Q200]")
    q201_scope: QuestionResponse = Field(description="[Q201]")
    q202_hindsight: QuestionResponse = Field(description="[Q202]")
    q203_would: QuestionResponse = Field(description="[Q203]")

class SecondaryIndicators_Batch(BaseModel):
    q99_agree_otp: QuestionResponse = Field(description="[Q99]")
    q40_disadvantage: QuestionResponse = Field(description="[Q40]")
    q41_foresee: QuestionResponse = Field(description="[Q41]")
    q42_advantage: QuestionResponse = Field(description="[Q42]")
    q43_biotech: QuestionResponse = Field(description="[Q43]")
    q44_antibody: QuestionResponse = Field(description="[Q44]")
    q45_pred_results: QuestionResponse = Field(description="[Q45]")
    q46_reasonable: QuestionResponse = Field(description="[Q46]")
    q47_known_tech: QuestionResponse = Field(description="[Q47]")
    q48_overcome: QuestionResponse = Field(description="[Q48]")
    q49_gap_filled: QuestionResponse = Field(description="[Q49]")
    q50_well_known: QuestionResponse = Field(description="[Q50]")
    q51_known_prop: QuestionResponse = Field(description="[Q51]")
    q52_analog_use: QuestionResponse = Field(description="[Q52]")
    q53_known_device: QuestionResponse = Field(description="[Q53]")
    q54_obvs_combo: QuestionResponse = Field(description="[Q54]")
    q55_analog_sub: QuestionResponse = Field(description="[Q55]")
    q56_equal_alt: QuestionResponse = Field(description="[Q56]")
    q57_normal_design: QuestionResponse = Field(description="[Q57]")
    q58_simple_extra: QuestionResponse = Field(description="[Q58]")
    q59_chem_select: QuestionResponse = Field(description="[Q59]")


#===PYDANTIC SCHEMAS===

def build_system_prompt(context_text: str, case_name: str, train_data: bool = False) -> str:
    if train_data and RAW_DATA is not None and not RAW_DATA.empty:
        reasons = str(RAW_DATA.loc[RAW_DATA['Reference'] == case_name, 'Decision Reasons'].iloc[0])
        decision = str(RAW_DATA.loc[RAW_DATA['Reference'] == case_name, 'Order'].iloc[0])
        
        return (
            f"You are helping to objectively assess Inventive Step for the European Patent Office (EPO). These cases are appeals against the examining boards' original decisions.\n"
            f"Your job is to critically analyse the information given to you to come to an informed, reasoned judgment to objectively assess the presence of inventive step within the invention.\n"
            f"You will be asked questions generated from an argumentation tool, called an ADM (ANGELIC DOMAIN MODEL) designed for inventive step to help you reason to a conclusion on whether inventive step is present.\n"
            f"An ADM is a hierarchical tree-like model which ascribes legal facts to 'base level factors' which are then processed using sets of prioritised acceptance conditions linked to more abstract factors to determine a conclusion.\n"
            f"Each question you answer corresponds to a base-level factor (BLF). Try to answer each question as if you were a legal ascriber mapping evidence to a reasoning framework.\n\n"         
            f"=== CASE DATA ===\n{context_text}\n=== END CASE DATA ===\n\n"
            f"=== REASONS FOR DECISION ===\n{reasons}\n=== END REASONS FOR DECISION ===\n\n"
            f"=== DECISION ===\n{decision}\n=== END DECISION ===\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Provide a step-by-step reasoning trace.\n"
            f"2. Conclude with a final 'Yes' or 'No' answer, or the specific text requested (e.g., a comma-separated list, a problem description, or the exact word 'BLANK' to end a loop).\n"
            f"3. Use the data provided. Do not refer to case law, patents or other specific inventions you have not been provided with.\n"
            f"4. You may make reasonable assumptions as to the nature of the skilled person or the common general knowledge of the relevant prior art so long as you believe this would have been known prior to the knowledge cut-off date given.\n"
            f"5. Ensure you follow the reasoning process from the 'reasons for decision' as closely as possible when ascribing the factors. Not all the factors will have been discussed explicitly so try and determine the most reasonable response based on the information, reasoning and conclusions you have been given.\n"
            f"6. You MUST try and follow the actual decision of the case as closely as possible in regard to whether inventive step was found to be present or not.\n"
        )
    else:
        return (
            f"You are helping to objectively assess Inventive Step for the European Patent Office (EPO). These cases are appeals against the examining boards' original decisions.\n"
            f"Your job is to critically analyse the information given to you to come to an informed, reasoned judgment to objectively assess the presence of inventive step within the invention.\n"
            f"You will be asked questions generated from an argumentation tool, called an ADM (ANGELIC DOMAIN MODEL) designed for inventive step to help you reason to a conclusion on whether inventive step is present.\n"
            f"An ADM is a hierarchical tree-like model which ascribes legal facts to 'base level factors' which are then processed using sets of prioritised acceptance conditions linked to more abstract factors to determine a conclusion.\n"
            f"Each question you answer corresponds to a base-level factor (BLF). Try to answer each question as if you were a legal ascriber mapping evidence to a reasoning framework.\n\n"         
            f"=== CASE DATA ===\n{context_text}\n=== END CASE DATA ===\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Provide a step-by-step reasoning trace.\n"
            f"2. Conclude with a final 'Yes' or 'No' answer, or the specific text requested (e.g., a comma-separated list, a problem description, or the exact word 'BLANK' to end a loop).\n"
            f"3. Use the data provided. Do not refer to case law, patents or other specific inventions you have not been provided with.\n"
            f"4. You may make reasonable assumptions as to the nature of the skilled person or the common general knowledge of the relevant prior art so long as you believe this would have been known prior to the knowledge cut-off date given.\n"
            f"5. Do not follow the conclusions or reasoning in the case data blindly, i.e. if the data says party X has appealed because they believe an invention has inventive step, do not just assume they are correct. Critically assess all information.\n"
        )
        
def build_history_messages(full_responses_log: dict) -> list:
    """Build minimal history with only the most recent Q&A pair to reduce context size."""
    history_msgs = []
    if not full_responses_log:
        return history_msgs
    
    # Only include the most recent Sequential_Features entry (immediate previous Q&A)
    if "Sequential_Features" in full_responses_log:
        features = full_responses_log["Sequential_Features"]
        if features:
            # Get the last feature entry
            last_key = max(features.keys(), key=lambda x: int(x.split('_')[1]) if x.startswith('Feature_') else 0)
            feat_data = features[last_key]
            
            # Add only the immediate previous question and answer
            if "question" in feat_data:
                history_msgs.append({"role": "user", "content": feat_data["question"]})
            if "answer" in feat_data or "answer_json" in feat_data:
                answer_content = feat_data.get("answer_json", json.dumps({
                    "answer": feat_data.get("answer"),
                    "reasoning": feat_data.get("reasoning", "")
                }))
                history_msgs.append({"role": "assistant", "content": answer_content})
    
    # Do NOT include batch sections to minimize context
    # Each batch call is self-contained with only immediate prior context
            
    return history_msgs


def keep_only_last_qa_pair(history_msgs: list) -> list:
    """Keep only the most recent user/assistant Q&A pair from history messages."""
    if not history_msgs:
        return []

    if len(history_msgs) >= 2:
        return history_msgs[-2:]

    return history_msgs[-1:]


def log_full_prompt_messages(call_name: str, messages: list):
    """Log the exact prompt payload sent to the LLM."""
    logger.debug("=== %s FULL PROMPT START ===", call_name)
    for index, message in enumerate(messages):
        role = message.get("role", "unknown")
        content = message.get("content", "")
        logger.debug("[PROMPT][%s][%d][%s][len=%d]", call_name, index, role, len(content))
        logger.debug("%s", content)
    logger.debug("=== %s FULL PROMPT END ===", call_name)

def build_final_verdict_context(full_responses_log: dict) -> list:
    """
    Build a comprehensive context for the final verdict LLM call from all collected responses.
    This includes information from batch calls and dynamic responses, even if UI exited early.
    
    Returns:
        list: History messages containing all relevant information for the final verdict decision.
    """
    history_msgs = []
    
    if not full_responses_log:
        return history_msgs

    # Always include the final ADM output summary if available
    if "Final_ADM_Output" in full_responses_log:
        final_adm_output = str(full_responses_log.get("Final_ADM_Output", "")).strip()
        if final_adm_output:
            history_msgs.append({
                "role": "user",
                "content": f"Final ADM Output Summary:\n{final_adm_output}",
            })
            history_msgs.append({
                "role": "assistant",
                "content": "Final ADM outcome captured and will be used for the final verdict.",
            })

    # Include constrained sub-ADM conclusion blocks (latest only) for final verdict
    sub_adm_conclusions = full_responses_log.get("Sub_ADM_Conclusions", [])
    if isinstance(sub_adm_conclusions, list) and sub_adm_conclusions:
        recent_blocks = [str(block).strip()[:1200] for block in sub_adm_conclusions[-4:] if str(block).strip()]
        if recent_blocks:
            packed = "\n\n---\n\n".join(recent_blocks)
            history_msgs.append({
                "role": "user",
                "content": f"Sub-ADM Conclusion Summaries (latest):\n{packed}",
            })
            history_msgs.append({
                "role": "assistant",
                "content": "Sub-ADM conclusions noted for final verdict assessment.",
            })
    
    # Extract information from Initial_ADM batch
    if "Initial_ADM" in full_responses_log:
        init_data = full_responses_log["Initial_ADM"]
        summary = "Initial Assessment Summary:\n"
        
        # Add key information fields
        if "invention_title" in init_data:
            summary += f"- Invention Title: {init_data['invention_title']}\n"
        if "invention_description" in init_data:
            summary += f"- Invention Description: {init_data['invention_description']}\n"
        if "technical_field" in init_data:
            summary += f"- Technical Field: {init_data['technical_field']}\n"
        if "relevant_prior_art" in init_data:
            summary += f"- Relevant Prior Art: {init_data['relevant_prior_art']}\n"
        if "closest_prior_art_description" in init_data:
            summary += f"- Closest Prior Art: {init_data['closest_prior_art_description']}\n"
        if "common_general_knowledge" in init_data:
            summary += f"- Common General Knowledge: {init_data['common_general_knowledge']}\n"
        
        # Add answers to key questions
        q_summary = "Key Question Answers:\n"
        q_map = {
            "q1_similar_purpose": "Q1 - Similar Purpose",
            "q2_similar_effects": "Q2 - Similar Effects",
            "q3_same_field": "Q3 - Same Field",
            "q6_skilled_in": "Q6 - Skilled Person In Field",
            "q7_average": "Q7 - Skilled Person Average",
            "q8_aware": "Q8 - Aware of CGK",
            "q9_access": "Q9 - Access to Prior Art",
            "q10_skilled_person": "Q10 - Skilled Person Type",
            "q11_cpa": "Q11 - Closest Prior Art Identified",
            "q12_minmod": "Q12 - Min Modifications to CPA",
        }
        
        for field, label in q_map.items():
            if field in init_data:
                answer = init_data[field]
                q_summary += f"- {label}: {answer}\n"
        
        if len(q_summary) > len("Key Question Answers:\n"):
            summary += "\n" + q_summary
        
        if len(summary) > len("Initial Assessment Summary:\n"):
            history_msgs.append({"role": "user", "content": summary})
            history_msgs.append({"role": "assistant", "content": "Information noted. Ready to assess inventive step based on provided information."})
    
    # Extract information from Sub_ADM_1 if present (Technical Character assessment)
    if "Sub_ADM_1" in full_responses_log:
        sub1_data = full_responses_log["Sub_ADM_1"]
        sub1_summary = "Technical Character Assessment (Sub-ADM 1):\n"
        
        sub1_map = {
            "q17_tech_cont": "Q17 - Technical Contribution",
            "q19_dist_feat": "Q19 - Distinguishing Features",
            "q20_circumvent": "Q20 - Technical Solution",
            "q21_tech_adapt": "Q21 - Technical Adaptation",
            "q22_intended": "Q22 - Intended Technical Effect",
            "q23_tech_use": "Q23 - Technical Use",
            "q30_claim_contains": "Q30 - Claim Contains Tech Features",
        }
        
        for field, label in sub1_map.items():
            if field in sub1_data:
                answer = sub1_data[field]
                sub1_summary += f"- {label}: {answer}\n"
        
        if len(sub1_summary) > len("Technical Character Assessment (Sub-ADM 1):\n"):
            history_msgs.append({"role": "user", "content": sub1_summary})
            history_msgs.append({"role": "assistant", "content": "Technical character assessment noted."})
    
    # Include the most recent Q&A pair if available
    if "Sequential_Features" in full_responses_log:
        features = full_responses_log["Sequential_Features"]
        if features:
            last_key = max(features.keys(), key=lambda x: int(x.split('_')[1]) if x.startswith('Feature_') else 0)
            feat_data = features[last_key]
            
            if "question" in feat_data:
                history_msgs.append({"role": "user", "content": feat_data["question"]})
            if "answer" in feat_data or "answer_json" in feat_data:
                answer_content = feat_data.get("answer_json", json.dumps({
                    "answer": feat_data.get("answer"),
                    "reasoning": feat_data.get("reasoning", "")
                }))
                history_msgs.append({"role": "assistant", "content": answer_content})
    
    return history_msgs

def extract_exact_questions(adm_instance) -> dict:
    extracted_questions = {}
    
    info_mapping = {
        "INVENTION_TITLE": "invention title",
        "INVENTION_DESCRIPTION": "description",
        "INVENTION_TECHNICAL_FIELD": "technical field",
        "REL_PRIOR_ART": "prior art",
        "CGK": "common general knowledge",
        "OBJ_T_PROBLEM": "obj_t_problem"
    }
    
    if hasattr(adm_instance, 'information_questions'):
        for key, question_text in adm_instance.information_questions.items():
            mapped_key = info_mapping.get(key, key.lower())
            extracted_questions[mapped_key] = f"[Q] {question_text}:"
    
    # Add the closest prior art description question for initial ADM
    extracted_questions["closest prior art description"] = "[Q] Please describe the candidate for the closest prior art:"

    if hasattr(adm_instance, 'questionOrder'):
        for item_name in adm_instance.questionOrder:
            if hasattr(adm_instance, 'information_questions') and item_name in adm_instance.information_questions:
                continue
                
            elif hasattr(adm_instance, 'question_instantiators') and item_name in adm_instance.question_instantiators:
                inst = adm_instance.question_instantiators[item_name]
                q_text = inst.get('question', '')
                
                match = re.search(r"\[(Q\d*)\]", q_text)
                q_tag = match.group(1).lower() if match else item_name.lower()
                
                formatted_q = f"{q_text}\n"
                mapping = inst.get('blf_mapping', {})
                for i, option_text in enumerate(mapping.keys(), 1):
                    formatted_q += f"{i}. {option_text}\n"
                
                formatted_q += "\nEnter the number of the answer you wish to choose (only enter the chosen number):"
                extracted_questions[q_tag] = formatted_q.strip()
                
            elif hasattr(adm_instance, 'nodes') and item_name in adm_instance.nodes:
                node = adm_instance.nodes[item_name]
                
                # Handle SubADMNode - extract questions from the sub-ADM
                if hasattr(node, 'sub_adm') and callable(node.sub_adm):
                    # Create a sample sub-ADM instance to extract questions
                    try:
                        sample_sub_adm = node.sub_adm("sample_item")
                        if hasattr(sample_sub_adm, 'question_instantiators') and isinstance(getattr(sample_sub_adm, 'question_instantiators', None), dict):
                            for q_order_name, inst in sample_sub_adm.question_instantiators.items():
                                q_text = inst.get('question', '')
                                match = re.search(r"\[(Q\d*)\]", q_text)
                                q_tag = match.group(1).lower() if match else q_order_name.lower()
                                
                                formatted_q = f"{q_text}\n"
                                mapping = inst.get('blf_mapping', {})
                                for i, option_text in enumerate(mapping.keys(), 1):
                                    formatted_q += f"{i}. {option_text}\n"
                                
                                formatted_q += "\nEnter the number of the answer you wish to choose (only enter the chosen number):"
                                extracted_questions[q_tag] = formatted_q.strip()
                        
                        if hasattr(sample_sub_adm, 'nodes'):
                            for sub_node_name, sub_node in sample_sub_adm.nodes.items():
                                if hasattr(sub_node, 'question') and sub_node.question:
                                    match = re.search(r"\[(Q\d*)\]", sub_node.question)
                                    q_tag = match.group(1).lower() if match else sub_node_name.lower()
                                    
                                    formatted_q = f"{sub_node.question}\n"
                                    if hasattr(sub_node, 'dictionary') and isinstance(sub_node.dictionary, dict):
                                        for i, option_text in enumerate(sub_node.dictionary.keys(), 1):
                                            formatted_q += f"{i}. {option_text}\n"
                                    
                                    formatted_q += "\nAnswer 'yes' or 'no' only (y/n):"
                                    extracted_questions[q_tag] = formatted_q.strip()
                    except Exception as e:
                        logger.warning(f"Could not extract questions from SubADMNode {item_name}: {e}")
                
                elif hasattr(node, 'question') and node.question:
                    match = re.search(r"\[(Q\d*)\]", node.question)
                    q_tag = match.group(1).lower() if match else item_name.lower()
                    
                    formatted_q = f"{node.question}\n"
                    if hasattr(node, 'dictionary') and isinstance(node.dictionary, dict):
                        for i, option_text in enumerate(node.dictionary.keys(), 1):
                            formatted_q += f"{i}. {option_text}\n"
                    
                    formatted_q += "\nAnswer 'yes' or 'no' only (y/n):"
                    extracted_questions[q_tag] = formatted_q.strip()
                    
    return extracted_questions

INITIAL_ADM_QUESTIONS = extract_exact_questions(adm_initial())
MAIN_ADM_QUESTIONS = extract_exact_questions(adm_main(sub_adm_1_flag=True, sub_adm_2_flag=True))
MAIN_ADM_NO_SUB_1_QUESTIONS = extract_exact_questions(adm_main(sub_adm_1_flag=False, sub_adm_2_flag=True))
MAIN_ADM_NO_SUB_2_QUESTIONS = extract_exact_questions(adm_main(sub_adm_1_flag=True, sub_adm_2_flag=False))
MAIN_ADM_NO_SUB_BOTH_QUESTIONS = extract_exact_questions(adm_main(sub_adm_1_flag=False, sub_adm_2_flag=False))
ALL_EXACT_QUESTIONS = {**INITIAL_ADM_QUESTIONS, **MAIN_ADM_QUESTIONS}


# --- LLM FUNCTIONS ---

async def consult_final_verdict(client, context_text: str, history_msgs: list, case_name: str, train_data: bool = False):
    """
    Get final verdict using final ADM context plus the latest interactive exchange.
    Includes the final ADM output summary whenever available, recent sub-ADM
    conclusions, and the latest Q&A pair before asking for the final verdict.
    
    Robust implementation with:
    - Aggressive history trimming if needed
    - Increased token allocation
    - JSON recovery and fallback mechanisms
    - Better error handling
    """
    # Add explicit instruction to always end with a single closing brace
    system_prompt = build_system_prompt(context_text, case_name, train_data)
    system_prompt += "\n\nIMPORTANT: Your response MUST be a single valid JSON object and MUST end with a single closing curly brace '}'. Do not output anything after the closing brace."
    
    if train_data:
        summary_question = (
            "FINAL_VERDICT\n"
            "Based on the session interaction above, what was the final outcome from the tool?\n"
            "State a single final decision based on whether an inventive step is present from the tool: 'Yes' or 'No'. "
            "Additionally, explain whether you agree with the final outcome derived from the tool session by comparing it to the real decision's outcome which you have been provided. Also provide a confidence score from 0-100 based on your faith in the tool's outcome."
            "You MUST make reference to the real case outcome and actual reasons for decision you have been provided to compare with the tool's output."
        )
    else:
        summary_question = (
            "FINAL_VERDICT\n"
            "Based on the session interaction above, what was the final outcome?\n"
            "State a single final decision based on whether an inventive step is present from the tool: 'Yes' or 'No'. "
            "Additionally, explain whether you agree with the final outcome derived from the tool session. You can choose to disagree with the tool's decisions and reasons if you do not agree. Also provide a confidence score from 0-100 based on your faith in the tool's outcome."
        )

    # Build messages with the final ADM state preserved.
    messages = [{"role": "system", "content": system_prompt}]

    history_msgs = history_msgs or []
    important_history = []
    trailing_history = keep_only_last_qa_pair(history_msgs)

    for history_item in history_msgs:
        content = str(history_item.get("content", ""))
        if (
            "Final ADM Output Summary:" in content
            or "Sub-ADM Conclusion Summaries" in content
        ):
            important_history.append(history_item)

    selected_history = []
    seen_entries = set()
    for history_item in important_history + trailing_history:
        cache_key = (history_item.get("role"), history_item.get("content"))
        if cache_key in seen_entries:
            continue
        selected_history.append(history_item)
        seen_entries.add(cache_key)

    logger.info(
        "Final verdict context assembled: %d message(s), important=%d, trailing=%d",
        len(selected_history),
        len(important_history),
        len(trailing_history),
    )

    for h in selected_history:
        messages.append({"role": h["role"], "content": h["content"]})
    
    # Append the final verdict question
    messages.append({"role": "user", "content": summary_question})
    
    # Calculate max_tokens with more conservative approach
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    estimated_input_tokens = max(total_chars // 3, total_chars // 4)  # More conservative estimate
    max_context = 32000  # Model's context window
    
    # Aggressive trimming if history is too large, while preserving the final ADM state.
    if estimated_input_tokens > 20000:
        logger.warning(f"History too large ({estimated_input_tokens} tokens). Aggressively trimming...")
        preserved_history = [messages[0]]
        preserved_history.extend(
            msg for msg in messages[1:-1]
            if "Final ADM Output Summary:" in str(msg.get("content", ""))
            or "Sub-ADM Conclusion Summaries" in str(msg.get("content", ""))
        )
        recent_tail = messages[-3:-1]
        for msg in recent_tail:
            if msg not in preserved_history:
                preserved_history.append(msg)
        preserved_history.append(messages[-1])
        messages = preserved_history
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        estimated_input_tokens = max(total_chars // 3, total_chars // 4)
    
    # Allocate tokens: be very conservative to ensure completion
    reserved_for_response = 12000  # Guarantee 12k tokens for response (includes overhead)
    available_tokens = max_context - estimated_input_tokens - 1000  # 1k safety buffer
    max_tokens_to_use = min(reserved_for_response, max(5000, available_tokens))
    
    logger.debug(f"Final verdict - Input tokens: {estimated_input_tokens}, allocated: {max_tokens_to_use}")
    logger.info(f"==> Calling LLM for FINAL VERDICT...")
    max_attempts = 10
    base_delay = 2
    attempt = 0
    extra_instruction = ""
    while attempt < max_attempts:
        start_time = time.time()
        try:
            # Always use FinalVerdictResponse schema
            # On each retry, append a stronger warning to the user message
            if attempt > 0:
                extra_instruction = f"\n\nWARNING: Your previous response was not valid JSON or did not match the required schema. You MUST return a valid JSON object matching this schema: {FinalVerdictResponse.model_json_schema()} and end with a single closing brace '}}'. Do NOT output anything else."
                messages[-1]["content"] = summary_question + extra_instruction
            log_full_prompt_messages(f"FINAL_VERDICT_ATTEMPT_{attempt+1}", messages)
            completion = await client.chat.completions.create(
                model=CURRENT_CONFIG["id"],
                messages=messages,
                extra_body={"guided_json": FinalVerdictResponse.model_json_schema()},
                temperature=LLM_TEMPERATURE,
                max_tokens=max_tokens_to_use
            )
            elapsed = time.time() - start_time
            raw_json = completion.choices[0].message.content.strip() if completion.choices[0].message.content else ""
            logger.debug(f"Final verdict response length: {len(raw_json)} chars, elapsed: {elapsed:.2f}s")
            reasoning_tokens = getattr(completion.choices[0].message, 'reasoning', '')
            if not reasoning_tokens and hasattr(completion.choices[0], 'reasoning'):
                reasoning_tokens = completion.choices[0].reasoning

            try:
                parsed_data, normalized_json = parse_model_from_raw_json(FinalVerdictResponse, raw_json)
                logger.debug(f"Successfully parsed verdict: answer='{parsed_data.answer}', confidence={parsed_data.confidence_score}")
                return parsed_data, normalized_json, elapsed, reasoning_tokens
            except Exception as parse_error:
                logger.warning(f"JSON parse error: {parse_error}. Attempting regex recovery...")
                # Try to extract answer from response using regex (robust, multiline)
                answer_match = re.search(r'"answer"\s*:\s*["\']?([Yy][Ee][Ss]|[Nn][Oo])["\']?', raw_json)
                answer = answer_match.group(1).capitalize() if answer_match else "UNKNOWN"
                # Try to extract reasoning (greedy, up to next field or end)
                reason_match = re.search(r'"reasoning"\s*:\s*["\'](.+?)["\']\s*(,|\}|$)', raw_json, re.DOTALL)
                reasoning = reason_match.group(1).strip() if reason_match else ""
                # Try to extract confidence (allow float or int)
                conf_match = re.search(r'"confidence_score"\s*:\s*(\d+(?:\.\d+)?)', raw_json)
                confidence = None
                if conf_match:
                    try:
                        confidence = int(float(conf_match.group(1)))
                    except Exception:
                        confidence = None
                if answer != "UNKNOWN" and reasoning and confidence is not None:
                    logger.info(f"Recovered answer from malformed JSON: {answer}")
                    recovered = FinalVerdictResponse(
                        answer=answer,
                        reasoning=reasoning,
                        confidence_score=confidence
                    )
                    logger.info(f"Successfully recovered verdict: {answer}, confidence: {confidence}")
                    return recovered, raw_json, elapsed, reasoning_tokens
                # If regex recovery fails, fall through to retry
            # If we reach here, parsing failed, so retry
        except Exception as e:
            logger.error(f"Final Verdict call failed (Attempt {attempt+1}/{max_attempts}): {type(e).__name__}: {str(e)[:200]}")
        delay = base_delay * (2 ** attempt)
        logger.warning(f"Retrying in {delay}s...")
        await asyncio.sleep(delay)
        attempt += 1
    # If all attempts fail, raise an error (never return UNKNOWN)
    raise RuntimeError("Final Verdict call failed after all attempts: Could not obtain a valid FinalVerdictResponse JSON.")


async def consult_single_structured_question(
    client,
    system_prompt: str,
    history_msgs: list,
    question_key: str,
    question_text: str,
    feature_name: str = None,
):
    """Fallback path: ask one question at a time using QuestionResponse schema."""
    context_hint = ""
    if feature_name:
        context_hint = f"\n[CONTEXT: {feature_name}]"

    messages = [{"role": "system", "content": system_prompt}]
    for h in keep_only_last_qa_pair(history_msgs):
        messages.append({"role": h["role"], "content": h["content"]})

    user_content = (
        f"QUESTION KEY: {question_key}\n"
        f"QUESTION:\n{question_text}\n\n"
        f"TASK: Return only valid JSON for this schema.{context_hint}"
    )
    messages.append({"role": "user", "content": user_content})

    max_retries = 6
    base_delay = 2

    for attempt in range(max_retries):
        start_time = time.time()
        try:
            log_full_prompt_messages(f"SINGLE_{question_key}_ATTEMPT_{attempt+1}", messages)
            completion = await client.chat.completions.create(
                model=CURRENT_CONFIG["id"],
                messages=messages,
                extra_body={"guided_json": QuestionResponse.model_json_schema()},
                temperature=LLM_TEMPERATURE,
                max_tokens=900,
                reasoning_effort="medium",
                top_p=1,
                seed=42,
            )
            elapsed = time.time() - start_time
            raw_json = completion.choices[0].message.content or ""
            parsed_data, normalized_json = parse_model_from_raw_json(QuestionResponse, raw_json)

            reasoning_tokens = getattr(completion.choices[0].message, "reasoning", "")
            if not reasoning_tokens and hasattr(completion.choices[0], "reasoning"):
                reasoning_tokens = completion.choices[0].reasoning

            return parsed_data, normalized_json, elapsed, reasoning_tokens
        except Exception as error:
            logger.warning(
                f"Single-question fallback failed for {question_key} "
                f"(Attempt {attempt + 1}/{max_retries}): {error}"
            )
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            await asyncio.sleep(delay)

async def consult_llm_batch(client, context_text: str, model_class: BaseModel, section_name: str, keys_to_fetch: list, case_name: str, train_data: bool = False, history_msgs: list = None, feature_name: str = None):
    if history_msgs is None:
        history_msgs = []
    
    # Determine which questions dictionary to use based on section name
    if "No Sub-ADM 1" in section_name and "No Sub-ADM 2" not in section_name:
        # Sub-ADM 1 skipped, Sub-ADM 2 included
        questions_dict = MAIN_ADM_NO_SUB_1_QUESTIONS
    elif "No Sub-ADM 2" in section_name and "No Sub-ADM 1" not in section_name:
        # Sub-ADM 1 included, Sub-ADM 2 skipped
        questions_dict = MAIN_ADM_NO_SUB_2_QUESTIONS
    elif "No Sub-ADM 1" in section_name and "No Sub-ADM 2" in section_name:
        # Both Sub-ADMs skipped
        questions_dict = MAIN_ADM_NO_SUB_BOTH_QUESTIONS
    else:
        # Full flow with both Sub-ADMs
        questions_dict = ALL_EXACT_QUESTIONS
        
    exact_questions_text = "QUESTIONS TO ANSWER:\n"
    for key in keys_to_fetch:
        q_text = questions_dict.get(key.lower(), f"Question {key} not found.")
        # If this is a sub-ADM batch and feature_name is provided, replace 'sample_item' with the actual feature name
        if feature_name and isinstance(q_text, str):
            q_text = q_text.replace("sample_item", feature_name)
        exact_questions_text += f"\n--- {key.upper()} ---\n{q_text}\n"

    system_prompt = build_system_prompt(context_text, case_name, train_data)
   
    messages = [{"role": "system", "content": system_prompt}]
    
    for h in keep_only_last_qa_pair(history_msgs):
        messages.append({"role": h["role"], "content": h["content"]})
        
    # Add item context if this is a sub-ADM batch
    # For sub-ADM 1: feature context, for sub-ADM 2: OTP context
    item_context = ""
    if feature_name:
        # Determine if this is sub-ADM 1 (features) or sub-ADM 2 (OTP)
        # Sub-ADM 1 questions: Q17-Q31, Sub-ADM 2 questions: Q34, Q36, Q38, Q39
        sub2_question_tags = ['q34', 'q36', 'q38', 'q39']
        is_sub2 = any(tag in section_name.lower() or tag in str(keys_to_fetch).lower() for tag in sub2_question_tags)
        
        if is_sub2:
            item_context = f"\n[CONTEXT: Evaluating objective technical problem: {feature_name}]"
        else:
            item_context = f"\n[CONTEXT: Evaluating feature: {feature_name}]"
    
    messages.append({
        "role": "user", 
        "content": f"{exact_questions_text}\n\nTASK: Fill out the structured JSON schema completely.{item_context}"
    })
    
    # Calculate approximate token count (rough estimate: 1 token ~= 4 characters)
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    estimated_input_tokens = total_chars // 4
    
    # Model context length is 32000, leave buffer for response
    max_context = 32000
    # Dynamically adjust max_tokens to fit within context window
    available_tokens = max_context - estimated_input_tokens - 500  # 500 token safety buffer
    max_tokens_to_use = min(12000, max(2000, available_tokens))
    
    logger.info(f"==> Calling LLM for section: {section_name}...")
    logger.debug(f"Estimated input tokens: {estimated_input_tokens}, max_tokens: {max_tokens_to_use}")
    max_retries = 5
    base_delay = 2
    
    for attempt in range(max_retries):
        start_time = time.time()
        try:
            log_full_prompt_messages(f"BATCH_{section_name}_ATTEMPT_{attempt+1}", messages)
            completion = await client.chat.completions.create(
                model=CURRENT_CONFIG["id"], 
                messages=messages,
                extra_body={"guided_json": model_class.model_json_schema()},
                temperature=LLM_TEMPERATURE,
                max_tokens=max_tokens_to_use,
                reasoning_effort="medium",
                top_p=1,
                seed=42
            )
            elapsed = time.time() - start_time
            raw_json = completion.choices[0].message.content
            
            # DEBUG: Log full response
            logger.debug(f"\n=== LLM RESPONSE for {section_name} ===")
            logger.debug(f"Raw JSON Response:\n{raw_json}")
            logger.debug(f"Response Length: {len(raw_json)} chars")
            logger.debug(f"Model: {CURRENT_CONFIG['id']}, Elapsed: {elapsed:.2f}s")
            logger.debug(f"=== END LLM RESPONSE ===\n")
            
            # Extract reasoning tokens if available from message object
            reasoning_tokens = getattr(completion.choices[0].message, 'reasoning', '')
            # Also try to extract from completion object itself if not in message
            if not reasoning_tokens and hasattr(completion.choices[0], 'reasoning'):
                reasoning_tokens = completion.choices[0].reasoning

            parsed_data, normalized_json = parse_model_from_raw_json(model_class, raw_json)
            
            # DEBUG: Log parsed data structure
            logger.debug(f"Parsed Data for {section_name}:")
            for field_name, field_value in parsed_data.model_dump().items():
                if isinstance(field_value, dict):
                    logger.debug(f"  {field_name}: answer='{field_value.get('answer')}' | reasoning={field_value.get('reasoning', '')[:100]}...")
                else:
                    logger.debug(f"  {field_name}: {field_value}")
            
            return parsed_data, normalized_json, elapsed, reasoning_tokens
        except Exception as e:
            logger.error(f"Batch failed for {section_name} (Attempt {attempt+1}/{max_retries}): {e}")
            logger.debug(f"Exception traceback:\n{traceback.format_exc()}")
            if attempt == max_retries - 1:
                logger.error(f"Batch failed for {section_name} after {max_retries} attempts. Falling back to per-question mode.")
                break
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Batch call failed for {section_name} ({e}). Retrying in {delay}s...")
            await asyncio.sleep(delay)

    system_prompt = build_system_prompt(context_text, case_name, train_data)
    field_names = list(model_class.model_fields.keys())
    if len(field_names) != len(keys_to_fetch):
        raise RuntimeError(
            f"Cannot fallback per-question for {section_name}: "
            f"field/key mismatch ({len(field_names)} fields vs {len(keys_to_fetch)} keys)."
        )

    logger.warning(f"Using per-question fallback for section: {section_name}")
    assembled = {}
    raw_payload = {}
    max_elapsed = 0.0
    combined_reasoning_tokens = []

    for field_name, key in zip(field_names, keys_to_fetch):
        question_text = ALL_EXACT_QUESTIONS.get(key.lower(), f"Question {key} not found.")
        if feature_name and isinstance(question_text, str):
            question_text = question_text.replace("sample_item", feature_name)

        q_data, q_raw_json, q_elapsed, q_reasoning_tokens = await consult_single_structured_question(
            client=client,
            system_prompt=system_prompt,
            history_msgs=history_msgs,
            question_key=key,
            question_text=question_text,
            feature_name=feature_name,
        )

        assembled[field_name] = q_data.model_dump()
        raw_payload[key] = q_raw_json
        max_elapsed = max(max_elapsed, q_elapsed)
        if q_reasoning_tokens:
            combined_reasoning_tokens.append(str(q_reasoning_tokens))

    parsed_data = model_class.model_validate(assembled)
    return parsed_data, json.dumps(raw_payload), max_elapsed, "\n".join(combined_reasoning_tokens)

async def consult_llm_dynamic(client, context_text: str, current_question: str, full_responses_log: dict, case_name: str, train_data: bool = False):
    system_prompt = build_system_prompt(context_text, case_name, train_data)
    is_skilled_person_prompt = is_skilled_person_nature_question(current_question)
    strict_dynamic_instruction = (
        "\n\nIMPORTANT OUTPUT FORMAT: Return exactly one JSON object matching this schema: "
        "{\"answer\": \"...\", \"reasoning\": \"...\"}. "
        "Both fields are required. Do not omit 'reasoning'. "
        "Do not output markdown, code fences, or extra text before/after the JSON object."
    )
    
    # Identical to batched: system prompt + history from build_history_messages + current question
    history_msgs = keep_only_last_qa_pair(build_history_messages(full_responses_log))
    
    messages = [{"role": "system", "content": system_prompt}]
    
    for h in history_msgs:
        messages.append({"role": h["role"], "content": h["content"]})
    
    messages.append({"role": "user", "content": current_question + strict_dynamic_instruction})
    
    # Debug: Log the message structure
    logger.debug(f"Dynamic call messages structure: {len(messages)} messages")
    logger.debug(f"System prompt present: {messages[0]['role'] == 'system'}")
    logger.debug(f"Current question: {current_question[:100]}...")
    if is_skilled_person_prompt:
        recent_history = history_msgs[-4:] if history_msgs else []
        history_summary = [
            {
                "role": message.get("role", "unknown"),
                "len": len(message.get("content", ""))
            }
            for message in recent_history
        ]
        logger.info(
            "[SKILLED_PERSON_DEBUG] Dynamic question detected | question_len=%d | history_count=%d | system_prompt_len=%d",
            len(current_question),
            len(history_msgs),
            len(system_prompt),
        )
        logger.info("[SKILLED_PERSON_DEBUG] Current question repr: %r", current_question)
        logger.info("[SKILLED_PERSON_DEBUG] Recent history summary: %s", history_summary)
    
    max_retries = 5
    base_delay = 2
    
    for attempt in range(max_retries):
        start_time = time.time()
        try:
            log_full_prompt_messages(f"DYNAMIC_ATTEMPT_{attempt+1}", messages)
            completion = await client.chat.completions.create(
                model=CURRENT_CONFIG["id"], 
                messages=messages,
                extra_body={"guided_json": QuestionResponse.model_json_schema()},
                temperature=LLM_TEMPERATURE,
                max_tokens=350,
                reasoning_effort="medium",
                top_p=1,
                seed=42
            )
            elapsed = time.time() - start_time
            raw_json = completion.choices[0].message.content
            
            # DEBUG: Log full response
            logger.debug(f"\n=== LLM DYNAMIC RESPONSE ===")
            logger.debug(f"Raw JSON Response:\n{raw_json}")
            logger.debug(f"Response Length: {len(raw_json)} chars")
            logger.debug(f"Model: {CURRENT_CONFIG['id']}, Elapsed: {elapsed:.2f}s")
            logger.debug(f"Current Question: {current_question[:200]}...")
            logger.debug(f"=== END DYNAMIC RESPONSE ===\n")
            if is_skilled_person_prompt:
                trailing_whitespace = len(raw_json) - len(raw_json.rstrip())
                logger.info(
                    "[SKILLED_PERSON_DEBUG] Raw response stats | len=%d | trailing_whitespace=%d | newline_count=%d",
                    len(raw_json),
                    trailing_whitespace,
                    raw_json.count("\n"),
                )
            
            # Extract reasoning tokens if available from message object
            reasoning_tokens = getattr(completion.choices[0].message, 'reasoning', '')
            # Also try to extract from completion object itself if not in message
            if not reasoning_tokens and hasattr(completion.choices[0], 'reasoning'):
                reasoning_tokens = completion.choices[0].reasoning
            
            parsed_data, normalized_json = parse_model_from_raw_json(QuestionResponse, raw_json)
            
            # DEBUG: Log parsed answer
            logger.debug(f"Parsed Answer: '{parsed_data.answer}'")
            logger.debug(f"Parsed Reasoning: {parsed_data.reasoning[:150]}...")
            
            # Check for BLANK response - this indicates the LLM didn't understand the question
            if parsed_data.answer.strip().upper() == "BLANK":
                if attempt < max_retries - 1:
                    logger.warning(f"LLM returned 'BLANK' answer. Retrying with stronger instruction (Attempt {attempt+1}/{max_retries})...")
                    # Add a stronger instruction for retry - include both answer and reasoning requirement
                    messages.append({"role": "assistant", "content": raw_json})
                    messages.append({
                        "role": "user",
                        "content": (
                            "The answer 'BLANK' is not acceptable. You MUST provide: "
                            "1) A proper answer based on the case information (for multiple choice provide a digit 1-5, for yes/no provide 'y' or 'n'), "
                            "and 2) your reasoning explaining why you chose this answer. "
                            "If uncertain, make an educated guess based on the context provided. "
                            "Return exactly one valid JSON object with BOTH fields: 'answer' and 'reasoning'."
                        )
                    })
                    continue
            
            return parsed_data, normalized_json, elapsed, reasoning_tokens
        except Exception as e:
            logger.error(f"Dynamic call failed (Attempt {attempt+1}/{max_retries}): {e}")
            logger.debug(f"Exception traceback:\n{traceback.format_exc()}")
            if is_skilled_person_prompt:
                logger.info(
                    "[SKILLED_PERSON_DEBUG] Parse/API failure on skilled-person prompt | attempt=%d/%d | question_repr=%r",
                    attempt + 1,
                    max_retries,
                    current_question,
                )
            if attempt == max_retries - 1:
                logger.error(f"Dynamic call failed after {max_retries} attempts: {e}")
                raise RuntimeError(
                    f"Dynamic call failed after {max_retries} attempts for prompt: {current_question[:120]}"
                )
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Dynamic call failed ({e}). Retrying in {delay}s...")
            await asyncio.sleep(delay)

# --- ROUTING & EXECUTION ---

def create_log_entry(turn_num: int, question: str, answer: str, reasoning: str, score: int, raw_json: str, elapsed: float, metadata: dict, hidden_reasoning: str = "") -> dict:
    return {
        "turn": turn_num,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "question": question, 
        "answer": answer,
        "reasoning": reasoning,
        "hidden_reasoning": hidden_reasoning,  # Reasoning tokens from LLM
        "score": score,
        "raw_content": raw_json,
        "elapsed_seconds": elapsed,
        "model_id": metadata.get("model", "Unknown"),
        "metadata": metadata
    }

def ADM_text_clean(text):
    """Helper func that removes decorative separator lines so prompts are detected cleanly."""
    lines = text.splitlines()
    out_lines = [l for l in lines if not (len(l.strip()) >= 3 and all(c == l.strip()[0] for c in l.strip()) and l.strip()[0] in "=-_~*")]
    return "\n".join(out_lines).strip()


def extract_latest_case_outcome_block(raw_text: str) -> str:
    """Extract the latest ADM case outcome block from UI output.

    Tries to capture from "Case Outcome:" through summary/reasoning lines until
    the summary append line or the next major UI section starts.
    """
    if not raw_text:
        return ""

    marker = "Case Outcome:"
    last_idx = raw_text.rfind(marker)
    if last_idx == -1:
        return ""

    tail = raw_text[last_idx:]

    end_markers = [
        "ADM and sub-ADM summaries appended to:",
        "\nINFO: ADM created",
        "\n[Q]",
        "\n[Q1]",
        "\n[Q100]",
        "\n[UI.py] [Q]",
        "\n[UI.py] [Q1]",
        "\n[UI.py] [Q100]",
    ]

    end_positions = [pos for marker_text in end_markers if (pos := tail.find(marker_text)) != -1]
    end_idx = min(end_positions) if end_positions else len(tail)

    block = tail[:end_idx].strip()
    return block


def extract_sub_adm_conclusion_block(clean_text: str) -> str:
    """Extract a sub-ADM conclusion/early-stop block from current cleaned UI text."""
    if not clean_text:
        return ""

    start_candidates = [
        clean_text.find("[Early Stop]"),
        clean_text.find("Case Outcome:"),
        clean_text.find("Sub-ADM Summary ==="),
    ]
    valid_starts = [idx for idx in start_candidates if idx != -1]
    if not valid_starts:
        return ""

    start_idx = min(valid_starts)
    tail = clean_text[start_idx:]

    end_markers = [
        "\n[Q",
        "\nINFO: ADM created",
        "\n--- Item",
        "\n=== Evaluating",
    ]
    end_positions = [pos for marker in end_markers if (pos := tail.find(marker)) != -1]
    end_idx = min(end_positions) if end_positions else len(tail)

    return tail[:end_idx].strip()

def load_context(data_path, case_name, dataset, config):
    path = os.path.join(data_path, case_name)
    parts = []

    if dataset == "comvik":
        cpa = os.path.join(path, "CPA.txt")
        if os.path.exists(cpa): parts.append(f"--- CLOSEST PRIOR ART INFORMATION---\n{open(cpa).read()}")
        
        if config == 1:
            pat = os.path.join(path, "patent.txt")
            if os.path.exists(pat): parts.append(f"--- PATENT APPLICATION CLAIMS ---\n{open(pat).read()}")
        elif config == 2:
            full = os.path.join(path, "full.txt")
            if os.path.exists(full): parts.append(f"--- FULL REASONING ABOUT THE PATENT APPLICATION ---\n{open(full).read()}")
    else:
        appeal = os.path.join(path, "appeal.txt")
        claims = os.path.join(path, "claims.txt")
        cpa = os.path.join(path, "CPA.txt")

        if config == 1:
            if os.path.exists(appeal): parts.append(f"--- SUMMARY OF FACTS FROM THE APPEAL ---\n{open(appeal).read()}")
        elif config == 2:
            if os.path.exists(claims): parts.append(f"--- PATENT APPLICATION CLAIMS ---\n{open(claims).read()}")
            if os.path.exists(cpa): parts.append(f"--- CLOSEST PRIOR ART DOCUMENT/S ---\n{open(cpa).read()}")
        elif config == 3:
            if os.path.exists(appeal): parts.append(f"--- SUMMARY OF FACTS FROM THE APPEAL ---\n{open(appeal).read()}")
            if os.path.exists(claims): parts.append(f"--- PATENT APPLICATION CLAIMS ---\n{open(claims).read()}")
            if os.path.exists(cpa): parts.append(f"--- CLOSEST PRIOR ART DOCUMENT/S ---\n{open(cpa).read()}")
            
    try:
        if RAW_DATA is not None and not RAW_DATA.empty:
            year = str(RAW_DATA.loc[RAW_DATA['Reference'] == case_name, 'Year'].iloc[0])
        else:
            year = "UNKNOWN"
    except:
        year = "UNKNOWN"
        
    parts.append(f"--- COMMON KNOWLEDGE DATE CUTOFF ---\n{year}")
    return "\n\n".join(parts)

async def fetch_batch_for_key(client, context_text: str, key: str, full_responses_log: dict, case_name, train_data=False, feature_name: str = None):
    new_answers = {}
    history_msgs = build_history_messages(full_responses_log)
    
    initial_keys = ['invention title', 'description', 'technical field', 'prior art', 'common general knowledge', 'closest prior art description'] + [f"Q{i}" for i in range(1, 17)]
    sub1_keys = ['Q17', 'Q19', 'Q20', 'Q21', 'Q22', 'Q23', 'Q24', 'Q25', 'Q26', 'Q27', 'Q28', 'Q29', 'Q30', 'Q31']
    main_inter_keys = ['Q32', 'Q33']
    sub2_keys = ['Q34', 'Q36', 'Q38', 'Q39']
    main_no_sub1_keys = [f"Q{i}" for i in range(100, 108)]
    main_no_sub2_keys = ['obj_t_problem'] + [f"Q{i}" for i in  range(200, 204)]
    secondary_keys = ['Q99'] + [f"Q{i}" for i in range(40, 60)]
    
    if key in initial_keys:
        data, raw_json, elapsed, reasoning_tokens = await consult_llm_batch(
            client, context_text, InitialADM_Batch, "Initial Preconditions",
            keys_to_fetch=initial_keys, case_name=case_name, train_data=train_data, history_msgs=history_msgs
        )
        full_responses_log["Initial_ADM"] = data.model_dump()
        new_answers.update({
            "invention title": data.invention_title,
            "description": data.invention_description,
            "technical field": data.technical_field,
            "prior art": data.relevant_prior_art,
            "common general knowledge": data.common_general_knowledge,
            "closest prior art description": data.closest_prior_art_description,
            "Q1": data.q1_similar_purpose, "Q2": data.q2_similar_effects,
            "Q3": data.q3_same_field, "Q4": data.q4_contested,
            "Q5": data.q5_cgk_evidence, "Q6": data.q6_skilled_in,
            "Q7": data.q7_average, "Q8": data.q8_aware,
            "Q9": data.q9_access, "Q10": data.q10_skilled_person,
            "Q11": data.q11_cpa, "Q12": data.q12_minmod,
            "Q13": data.q13_combo_attempt, "Q14": data.q14_combined,
            "Q15": data.q15_combo_motive, "Q16": data.q16_basis,
        })
        # Store mapping of information field names to their batch section
        new_answers["__batch_section__"] = "Initial_ADM"

    elif key in sub1_keys:
        # Sub-ADM questions require feature context
        # feature_name should be passed in from the caller when a sub-ADM feature is being evaluated
        
        data, raw_json, elapsed, reasoning_tokens = await consult_llm_batch(
            client, context_text, SubADM1_Batch, "Technical Character",
            keys_to_fetch=sub1_keys, case_name=case_name, train_data=train_data, history_msgs=history_msgs,
            feature_name=feature_name
        )
        full_responses_log["Sub_ADM_1"] = data.model_dump()
        new_answers.update({
            "Q17": data.q17_tech_cont, "Q19": data.q19_dist_feat,
            "Q20": data.q20_circumvent, "Q21": data.q21_tech_adapt,
            "Q22": data.q22_intended, "Q23": data.q23_tech_use,
            "Q24": data.q24_specifc_purpose, "Q25": data.q25_func_limited,
            "Q26": data.q26_unxpected, "Q27": data.q27_precise,
            "Q28": data.q28_one_way, "Q29": data.q29_credible,
            "Q30": data.q30_claim_contains, "Q31": data.q31_suff_dis,
        })

    elif key in main_inter_keys:
        data, raw_json, elapsed, reasoning_tokens = await consult_llm_batch(
            client, context_text, MainADM_Inter_Batch, "Objective Technical Problem (Synergy & Interaction)",
            keys_to_fetch=main_inter_keys, case_name=case_name, train_data=train_data, history_msgs=history_msgs
        )
        full_responses_log["Main_Inter_ADM"] = data.model_dump()
        new_answers.update({
            "Q32": data.q32_synergy,
            "Q33": data.q33_func_int,
        })

    elif key in sub2_keys:
        # Sub-ADM 2 questions require OTP context
        # feature_name parameter is used for both sub-ADM 1 (features) and sub-ADM 2 (OTP)
        
        data, raw_json, elapsed, reasoning_tokens = await consult_llm_batch(
            client, context_text, SubADM2_Batch, "Problem-Solution Approach",
            keys_to_fetch=sub2_keys, case_name=case_name, train_data=train_data, history_msgs=history_msgs,
            feature_name=feature_name
        )
        full_responses_log["Sub_ADM_2"] = data.model_dump()
        new_answers.update({
            "Q34": data.q34_encompassed, "Q36": data.q36_scope,
            "Q38": data.q38_hindsight, "Q39": data.q39_would,
        })

    elif key in main_no_sub1_keys:
        data, raw_json, elapsed, reasoning_tokens = await consult_llm_batch(
            client, context_text, MainADM_No_Sub_1, "Technical Factors (No Sub-ADM 1)",
            keys_to_fetch=main_no_sub1_keys, case_name=case_name, train_data=train_data, history_msgs=history_msgs
        )
        full_responses_log["Main_ADM_No_Sub_1"] = data.model_dump()
        new_answers.update({
            "Q100": data.q100_dist_feat, "Q101": data.q101_tech_cont,
            "Q102": data.q102_unexpected, "Q103": data.q103_precise,
            "Q104": data.q104_one_way, "Q105": data.q105_credible,
            "Q106": data.q106_claimcontains, "Q107": data.q107_suff_dis,
        })

    elif key in main_no_sub2_keys:
        data, raw_json, elapsed, reasoning_tokens = await consult_llm_batch(
            client, context_text, MainADM_No_Sub_2, "Obviousness Factors (No Sub-ADM 2)",
            keys_to_fetch=main_no_sub2_keys, case_name=case_name, train_data=train_data, history_msgs=history_msgs
        )
        full_responses_log["Main_ADM_No_Sub_2"] = data.model_dump()
        new_answers.update({
            "obj_t_problem": data.obj_t_problem,
            "Q200": data.q200_encompassed, "Q201": data.q201_scope,
            "Q202": data.q202_hindsight, "Q203": data.q203_would,
        })

    elif key in secondary_keys:
        data, raw_json, elapsed, reasoning_tokens = await consult_llm_batch(
            client, context_text, SecondaryIndicators_Batch, "Secondary Indicators",
            keys_to_fetch=secondary_keys, case_name=case_name, train_data=train_data, history_msgs=history_msgs
        )
        full_responses_log["Secondary_Indicators"] = data.model_dump()
        new_answers.update({
            "Q99": data.q99_agree_otp, "Q40": data.q40_disadvantage,
            "Q41": data.q41_foresee, "Q42": data.q42_advantage,
            "Q43": data.q43_biotech, "Q44": data.q44_antibody,
            "Q45": data.q45_pred_results, "Q46": data.q46_reasonable,
            "Q47": data.q47_known_tech, "Q48": data.q48_overcome,
            "Q49": data.q49_gap_filled, "Q50": data.q50_well_known,
            "Q51": data.q51_known_prop, "Q52": data.q52_analog_use,
            "Q53": data.q53_known_device, "Q54": data.q54_obvs_combo,
            "Q55": data.q55_analog_sub, "Q56": data.q56_equal_alt,
            "Q57": data.q57_normal_design, "Q58": data.q58_simple_extra,
            "Q59": data.q59_chem_select,
        })
        
    return new_answers

async def run_ui_with_tool_batch(client, case_name, context_text, run_id, metadata, train_data=False):
    async with REQUEST_SEMAPHORE:
        case_ref_token = CURRENT_CASE_REF.set(case_name)
        logger.debug(f"\nSTARTING TOOL MODE: {case_name} (Run {run_id})")
        start_time_session = time.time()
        
        config_num = metadata.get('config') if metadata and 'config' in metadata else 'X'
        mode = metadata.get('mode') if metadata and 'mode' in metadata else 'tool'

        if train_data:
            log_dir = os.path.join(BASE_CASE_DIR, case_name, f"run_{run_id}", f"config_{config_num}", "train", str(ADM_CONFIG), str(ADM_INITIAL))
        else:
            log_dir = os.path.join(BASE_CASE_DIR, case_name, f"run_{run_id}", f"config_{config_num}", "tool", str(ADM_CONFIG), str(ADM_INITIAL))

        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "log.json")
        if os.path.exists(log_file):
            os.remove(log_file)
                   
        answers_buffer = {}
        full_responses_log = {}
        turn_logs = []
        last_answer_sent = ""
        last_answer_type = ""
        pending_sub_adm_conclusion = ""
        last_logged_sub_adm_conclusion = ""
        
        buffer = [] 
        full_session_output = "" 
        
        #build subprocess args and only include --adm_initial flag when True
        subprocess_args = [
            sys.executable, '-u', ADM_SCRIPT_PATH,
            '--run_id', str(run_id),
            '--config', str(config_num),
            '--mode', str(mode),
            '--folder_base', str(BASE_CASE_DIR),
            '--adm_config', str(ADM_CONFIG),
        ]
        if ADM_INITIAL:
            subprocess_args.append('--adm_initial')
        
        process = await asyncio.create_subprocess_exec(
            *subprocess_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )

        try:
            while True:
                timed_out = False
                try:
                    chunk = await asyncio.wait_for(process.stdout.read(4096), timeout=0.25)
                    if not chunk:
                        break
                    decoded_chunk = chunk.decode('utf-8', errors='replace')
                    buffer.append(decoded_chunk)
                    full_session_output += decoded_chunk
                    
                    if decoded_chunk.strip():
                        print(f"[UI.py] {decoded_chunk.strip()}") 
                except asyncio.TimeoutError:
                    timed_out = True

                combined = "".join(buffer)
                clean = ADM_text_clean(combined)

                # Keep the latest final ADM output summary for final verdict context
                latest_case_outcome = extract_latest_case_outcome_block(full_session_output)
                if latest_case_outcome:
                    full_responses_log["Final_ADM_Output"] = latest_case_outcome

                # Capture sub-ADM conclusions/early-stop blocks from UI output
                sub_adm_conclusion = extract_sub_adm_conclusion_block(clean)
                if sub_adm_conclusion and sub_adm_conclusion != last_logged_sub_adm_conclusion:
                    conclusions = full_responses_log.setdefault("Sub_ADM_Conclusions", [])
                    if isinstance(conclusions, list):
                        conclusions.append(sub_adm_conclusion)

                    pending_sub_adm_conclusion = sub_adm_conclusion
                    last_logged_sub_adm_conclusion = sub_adm_conclusion

                if not clean and process.returncode is None:
                    continue
                
                if process.returncode is not None and not clean:
                    break

                if not timed_out:
                    continue



                needed_key = None
                is_dynamic_loop = False 
                
                match = re.search(r"\[(Q\d+)\]", clean)
                
                # 1. EXPLICIT NUMBERED QUESTIONS MUST BE CHECKED FIRST
                if match:
                    q_num = match.group(1)
                    if q_num == "Q380":  # Hindsight check is dynamic
                        is_dynamic_loop = True
                    else:
                        needed_key = q_num
                        
                # 2. Information Questions & Dynamic loops (only triggers if NO Q-tag exists)
                else:
                    lower_clean = clean.lower()
                    if "invalid input" in lower_clean:
                        expects_number = "enter the number" in lower_clean or "only give a number" in lower_clean
                        expects_yes_no = "(y/n)" in lower_clean or "yes' or 'no'" in lower_clean

                        can_resend = False
                        if expects_number and last_answer_type == "number" and re.fullmatch(r"\d+", last_answer_sent):
                            can_resend = True
                        elif expects_yes_no and last_answer_type == "yesno" and last_answer_sent in {"y", "n"}:
                            can_resend = True
                        elif not expects_number and not expects_yes_no and last_answer_sent:
                            can_resend = True

                        if can_resend:
                            logger.warning("UI rejected input; resending previous %s answer: %s", last_answer_type or "", last_answer_sent)
                            try:
                                process.stdin.write(f"{last_answer_sent}\n".encode())
                                await process.stdin.drain()
                            except (ConnectionResetError, BrokenPipeError):
                                break
                        else:
                            logger.warning("UI rejected input but no compatible previous answer is available; waiting for next prompt.")
                        buffer = []
                        continue
                    # Handle case name automatically (before any LLM logic)
                    if "enter case name" in clean.lower():
                        logger.info(f"Auto-filling case name: {case_name}")
                        try:
                            process.stdin.write((case_name + "\n").encode('utf-8'))
                            await process.stdin.drain()
                        except (ConnectionResetError, BrokenPipeError) as e:
                            logger.error(f"ADM subprocess stdin closed while writing case name: {e}")
                            break
                        buffer = []
                        continue
                    elif "title of your invention" in lower_clean:
                        needed_key = "invention title"
                    # Check for dynamic prompts FIRST before checking for information questions
                    # This prevents false matches (e.g., "closest prior art" matching "prior art")
                    elif "describe the candidate for the closest prior art" in lower_clean:
                        needed_key = "closest prior art description"
                    elif "description of your invention" in lower_clean or "brief description of your invention" in lower_clean:
                        needed_key = "description"
                    elif "technical field of the invention" in lower_clean:
                        needed_key = "technical field"
                    elif "describe the relevant prior art" in lower_clean or "briefly describe the relevant prior art" in lower_clean:
                        needed_key = "prior art"
                    elif "describe the common general knowledge" in lower_clean or "briefly describe the common general knowledge" in lower_clean:
                        needed_key = "common general knowledge"
                    elif "describe the objective technical problem" in lower_clean or "briefly describe the objective technical problem" in lower_clean:
                        needed_key = "obj_t_problem" 
                    elif "[q]" in lower_clean or "enter your choice" in lower_clean or "enter the number" in lower_clean or "list the features" in lower_clean:
                        is_dynamic_loop = True

                if not needed_key and not is_dynamic_loop:
                    if clean.strip().endswith(":") or clean.strip().endswith("?") or "(y/n)" in clean.lower():
                        logger.warning("Unrecognized prompt detected. Falling back to Dynamic LLM Loop.")
                        is_dynamic_loop = True
                    else:
                        continue

               # Route A: Dynamic / Sequential Approach
                if is_dynamic_loop:
                    logger.info("*** Dynamic UI Prompt Detected! Switching to Dynamic LLM mode... ***")
                    if is_skilled_person_nature_question(clean):
                        q10_obj = answers_buffer.get("Q10")
                        q10_answer = ""
                        q10_reasoning = ""
                        if hasattr(q10_obj, "answer"):
                            q10_answer = str(getattr(q10_obj, "answer", ""))
                            q10_reasoning = str(getattr(q10_obj, "reasoning", ""))
                        elif isinstance(q10_obj, dict):
                            q10_answer = str(q10_obj.get("answer", ""))
                            q10_reasoning = str(q10_obj.get("reasoning", ""))

                        logger.info(
                            "[SKILLED_PERSON_DEBUG] Routing dynamically without reroute | q10_answer=%r | q10_reasoning_len=%d",
                            q10_answer,
                            len(q10_reasoning),
                        )
                        logger.info(
                            "[SKILLED_PERSON_DEBUG] Clean prompt repr before send: %r",
                            clean,
                        )
                    
                    data, raw_json, elapsed, reasoning_tokens = await consult_llm_dynamic(
                        client, context_text, clean, full_responses_log,
                        case_name, train_data=train_data
                    )
                    
                    answer_to_send = str(data.answer)

                    logged_question = clean
                    if pending_sub_adm_conclusion and pending_sub_adm_conclusion not in clean:
                        logged_question = f"{pending_sub_adm_conclusion}\n\n{clean}"
                    pending_sub_adm_conclusion = ""
                    
                    turn_logs.append(create_log_entry(
                        len(turn_logs)+1, 
                        question=logged_question,
                        answer=answer_to_send, 
                        reasoning=data.reasoning, 
                        score=0, 
                        raw_json=raw_json, 
                        elapsed=elapsed, 
                        metadata=metadata,
                        hidden_reasoning=reasoning_tokens
                    ))
                    
                    if "Sequential_Features" not in full_responses_log:
                        full_responses_log["Sequential_Features"] = {}
                    feat_idx = len(full_responses_log["Sequential_Features"]) + 1
                    full_responses_log["Sequential_Features"][f"Feature_{feat_idx}"] = {
                        "question": clean,  # Store the actual question from UI
                        "answer": answer_to_send,
                        "reasoning": data.reasoning,
                        "answer_json": raw_json  # Store full JSON response for context
                    }
                    
                    logger.info(f"  -> Sending Dynamic Answer: {answer_to_send}")
                    try:
                        process.stdin.write(f"{answer_to_send}\n".encode())
                        await process.stdin.drain()
                        last_answer_sent = answer_to_send
                        if re.fullmatch(r"\d+", answer_to_send):
                            last_answer_type = "number"
                        elif answer_to_send in {"y", "n"}:
                            last_answer_type = "yesno"
                        else:
                            last_answer_type = "text"
                    except (ConnectionResetError, BrokenPipeError):
                        break
                    
                    buffer = [] 
                    continue 
                
                # Route B: Batched Approach
                elif needed_key:
                    
                    # For sub-ADM questions, cache key includes item name to allow per-item batches
                    sub1_keys_list = [f"Q{i}" for i in [17, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31]]
                    sub2_keys_list = ['Q34', 'Q36', 'Q38', 'Q39']
                    
                    # Only extract item name from prompt for sub-ADM questions
                    item_name_for_batch = None
                    if needed_key in sub1_keys_list or needed_key in sub2_keys_list:
                        # Sub-ADM 1 uses "Feature:" while Sub-ADM 2 uses "Problem name:"
                        feature_match = re.search(r"Feature:\s*(.+?)(?:\n|$)", clean)
                        problem_match = re.search(r"Problem name:\s*(.+?)(?:\n|$)", clean)
                        
                        if feature_match:
                            item_name_for_batch = feature_match.group(1).strip()
                            logger.info(f"  -> Detected feature for sub-ADM 1 batch: {item_name_for_batch}")
                        elif problem_match:
                            item_name_for_batch = problem_match.group(1).strip()
                            logger.info(f"  -> Detected OTP for sub-ADM 2 batch: {item_name_for_batch[:100]}...")
                        else:
                            # If no feature/problem name found in sub-ADM question, use placeholder and log error
                            item_name_for_batch = "MISSING_FEATURE_NAME"
                            logger.error(f"No feature/problem name detected in sub-ADM question prompt. Using placeholder: {item_name_for_batch}")
                    
                    if (needed_key in sub1_keys_list or needed_key in sub2_keys_list) and item_name_for_batch:
                        # Use truncated version for cache key to avoid excessively long keys
                        cache_item_name = item_name_for_batch[:100] if len(item_name_for_batch) > 100 else item_name_for_batch
                        cache_key = f"{needed_key}__{cache_item_name}"
                    else:
                        cache_key = needed_key
                        
                    if cache_key not in answers_buffer:
                        logger.info(f"*** New section detected (needs {needed_key}). Pausing ADM to fetch LLM batch... ***")
                        new_batch = await fetch_batch_for_key(
                            client, context_text, needed_key, full_responses_log, case_name, 
                            train_data=train_data, feature_name=item_name_for_batch
                        )                    
                        if new_batch:
                            # Store with cache_key for sub-ADM questions
                            if (needed_key in sub1_keys_list or needed_key in sub2_keys_list) and item_name_for_batch:
                                # Store each answer with item-specific cache key
                                cache_item_name = item_name_for_batch[:100] if len(item_name_for_batch) > 100 else item_name_for_batch
                                for key, value in new_batch.items():
                                    if key != "__batch_section__":
                                        answers_buffer[f"{key}__{cache_item_name}"] = value
                                    else:
                                        answers_buffer[key] = value
                            else:
                                answers_buffer.update(new_batch)
                            batch_section = new_batch.get("__batch_section__", "Unknown")
                        else:
                            logger.warning(f"Could not fetch batch for '{needed_key}'.")
                            batch_section = None

                    max_batch_answer_attempts = 3
                    max_dynamic_fallback_attempts = 2
                    answer_to_send = None
                    reasoning = ""
                    score = 0
                    log_raw_json = "Precomputed Batch"
                    log_elapsed = 0.0
                    log_hidden_reasoning = ""
                    answer_mode_label = "Batched"

                    for batch_attempt in range(max_batch_answer_attempts):
                        ans_obj = answers_buffer.get(cache_key)

                        if not ans_obj:
                            logger.warning(
                                "Missing batch answer for %s (cache_key=%s). Refetching batch (attempt %d/%d).",
                                needed_key,
                                cache_key,
                                batch_attempt + 1,
                                max_batch_answer_attempts,
                            )
                            new_batch = await fetch_batch_for_key(
                                client,
                                context_text,
                                needed_key,
                                full_responses_log,
                                case_name,
                                train_data=train_data,
                                feature_name=item_name_for_batch,
                            )
                            if new_batch:
                                if (needed_key in sub1_keys_list or needed_key in sub2_keys_list) and item_name_for_batch:
                                    cache_item_name = item_name_for_batch[:100] if len(item_name_for_batch) > 100 else item_name_for_batch
                                    for key, value in new_batch.items():
                                        if key != "__batch_section__":
                                            answers_buffer[f"{key}__{cache_item_name}"] = value
                                        else:
                                            answers_buffer[key] = value
                                else:
                                    answers_buffer.update(new_batch)
                            continue

                        if hasattr(ans_obj, 'answer'):
                            raw_answer = str(ans_obj.answer)
                            reasoning = getattr(ans_obj, 'reasoning', '')
                        elif isinstance(ans_obj, dict):
                            raw_answer = str(ans_obj.get("answer", ""))
                            reasoning = ans_obj.get("reasoning", "")
                        else:
                            raw_answer = str(ans_obj)
                            reasoning = ""

                        raw_answer = raw_answer.strip().replace("**", "")

                        if needed_key.startswith("Q"):
                            normalized_answer = _normalize_mcq_answer(raw_answer, needed_key)
                            if normalized_answer is None or not _is_valid_normalized_answer(needed_key, normalized_answer):
                                logger.warning(
                                    "Invalid batch answer for %s: %r (normalized=%r). Refetching batch (attempt %d/%d).",
                                    needed_key,
                                    raw_answer,
                                    normalized_answer,
                                    batch_attempt + 1,
                                    max_batch_answer_attempts,
                                )
                                answers_buffer.pop(cache_key, None)
                                new_batch = await fetch_batch_for_key(
                                    client,
                                    context_text,
                                    needed_key,
                                    full_responses_log,
                                    case_name,
                                    train_data=train_data,
                                    feature_name=item_name_for_batch,
                                )
                                if new_batch:
                                    if (needed_key in sub1_keys_list or needed_key in sub2_keys_list) and item_name_for_batch:
                                        cache_item_name = item_name_for_batch[:100] if len(item_name_for_batch) > 100 else item_name_for_batch
                                        for key, value in new_batch.items():
                                            if key != "__batch_section__":
                                                answers_buffer[f"{key}__{cache_item_name}"] = value
                                            else:
                                                answers_buffer[key] = value
                                    else:
                                        answers_buffer.update(new_batch)
                                continue
                            answer_to_send = normalized_answer
                        else:
                            if not raw_answer:
                                logger.warning(
                                    "Empty batch answer for %s. Refetching batch (attempt %d/%d).",
                                    needed_key,
                                    batch_attempt + 1,
                                    max_batch_answer_attempts,
                                )
                                answers_buffer.pop(cache_key, None)
                                new_batch = await fetch_batch_for_key(
                                    client,
                                    context_text,
                                    needed_key,
                                    full_responses_log,
                                    case_name,
                                    train_data=train_data,
                                    feature_name=item_name_for_batch,
                                )
                                if new_batch:
                                    if (needed_key in sub1_keys_list or needed_key in sub2_keys_list) and item_name_for_batch:
                                        cache_item_name = item_name_for_batch[:100] if len(item_name_for_batch) > 100 else item_name_for_batch
                                        for key, value in new_batch.items():
                                            if key != "__batch_section__":
                                                answers_buffer[f"{key}__{cache_item_name}"] = value
                                            else:
                                                answers_buffer[key] = value
                                    else:
                                        answers_buffer.update(new_batch)
                                continue
                            answer_to_send = raw_answer

                        if answer_to_send is not None:
                            break

                    if answer_to_send is None:
                        logger.warning(
                            "Batch answer failed for %s after %d attempts. Falling back to dynamic mode.",
                            needed_key,
                            max_batch_answer_attempts,
                        )

                        for dynamic_attempt in range(max_dynamic_fallback_attempts):
                            try:
                                data, raw_json, elapsed, reasoning_tokens = await consult_llm_dynamic(
                                    client,
                                    context_text,
                                    clean,
                                    full_responses_log,
                                    case_name,
                                    train_data=train_data,
                                )
                            except Exception as dynamic_error:
                                logger.warning(
                                    "Dynamic fallback failed for %s (attempt %d/%d): %s",
                                    needed_key,
                                    dynamic_attempt + 1,
                                    max_dynamic_fallback_attempts,
                                    dynamic_error,
                                )
                                continue

                            dynamic_raw_answer = str(data.answer).strip().replace("**", "")

                            if needed_key.startswith("Q"):
                                normalized_dynamic = _normalize_mcq_answer(dynamic_raw_answer, needed_key)
                                if normalized_dynamic is None or not _is_valid_normalized_answer(needed_key, normalized_dynamic):
                                    logger.warning(
                                        "Invalid dynamic fallback answer for %s: %r (normalized=%r). Retrying (attempt %d/%d).",
                                        needed_key,
                                        dynamic_raw_answer,
                                        normalized_dynamic,
                                        dynamic_attempt + 1,
                                        max_dynamic_fallback_attempts,
                                    )
                                    continue
                                answer_to_send = normalized_dynamic
                            else:
                                if not dynamic_raw_answer:
                                    logger.warning(
                                        "Empty dynamic fallback answer for %s. Retrying (attempt %d/%d).",
                                        needed_key,
                                        dynamic_attempt + 1,
                                        max_dynamic_fallback_attempts,
                                    )
                                    continue
                                answer_to_send = dynamic_raw_answer

                            reasoning = getattr(data, "reasoning", "")
                            score = getattr(data, "confidence_score", 0) if hasattr(data, "confidence_score") else 0
                            log_raw_json = raw_json
                            log_elapsed = elapsed
                            log_hidden_reasoning = reasoning_tokens
                            answer_mode_label = "Dynamic Fallback"
                            break

                    if answer_to_send is None:
                        raise RuntimeError(
                            f"Failed to obtain a valid answer for {needed_key} after {max_batch_answer_attempts} batch and {max_dynamic_fallback_attempts} dynamic attempts."
                        )

                    logger.info(f"  -> Sending {answer_mode_label} Answer for {needed_key}: {answer_to_send}")

                    logged_question = clean
                    if pending_sub_adm_conclusion and pending_sub_adm_conclusion not in clean:
                        logged_question = f"{pending_sub_adm_conclusion}\n\n{clean}"
                    pending_sub_adm_conclusion = ""
                    
                    turn_logs.append(create_log_entry(
                        len(turn_logs)+1, 
                        question=logged_question,
                        answer=answer_to_send, 
                        reasoning=reasoning, 
                        score=score, 
                        raw_json=log_raw_json, 
                        elapsed=log_elapsed, 
                        metadata=metadata,
                        hidden_reasoning=log_hidden_reasoning
                    ))
                    
                    try:
                        process.stdin.write(f"{answer_to_send}\n".encode())
                        await process.stdin.drain()
                        last_answer_sent = answer_to_send
                        if re.fullmatch(r"\d+", answer_to_send):
                            last_answer_type = "number"
                        elif answer_to_send in {"y", "n"}:
                            last_answer_type = "yesno"
                        else:
                            last_answer_type = "text"
                    except (ConnectionResetError, BrokenPipeError):
                        break
                    
                    buffer = []

        except Exception as e:
            logger.error(f"Controller Exception: {e}")
            import traceback
            traceback.print_exc()
            
        finally:
            if process.returncode is None:
                process.terminate()
            logger.info("UI.py process finished.")

            # Ensure final ADM output is present for final-verdict context at minimum
            if not full_responses_log.get("Final_ADM_Output"):
                latest_case_outcome = extract_latest_case_outcome_block(full_session_output)
                if latest_case_outcome:
                    full_responses_log["Final_ADM_Output"] = latest_case_outcome
                elif full_session_output.strip():
                    # Fallback: include recent UI session tail if no explicit Case Outcome block found
                    full_responses_log["Final_ADM_Output"] = full_session_output[-4000:].strip()
            
            # --- FINAL VERDICT LOGIC ---
            # Always attempt to get a final verdict, even if UI exited early (early stop scenario)
            # Use comprehensive context from all collected responses, not just minimal recent history
            
            # Build comprehensive context from full_responses_log for better final verdict
            verdict_context_msgs = build_final_verdict_context(full_responses_log)
            
            # If no comprehensive context available, fall back to minimal history
            if not verdict_context_msgs:
                verdict_context_msgs = build_history_messages(full_responses_log)
            
            # Use the comprehensive verdict context directly (dynamic Q&A is already in full_responses_log)
            all_history = verdict_context_msgs

            # Build an explicit log payload showing ADM context sent to the final-verdict LLM
            history_payload_for_verdict = "\n\n".join(
                [
                    f"[{msg.get('role', 'unknown').upper()}]\n{msg.get('content', '')}"
                    for msg in all_history
                    if isinstance(msg, dict)
                ]
            )
            final_verdict_question_log = (
                "FINAL VERDICT\n\n"
                "=== ADM CONTEXT SENT TO FINAL LLM ===\n"
                f"{history_payload_for_verdict if history_payload_for_verdict else '[No history context available]'}"
            )
            
            final_verdict = "ERROR"
            
            # Always attempt final verdict call with whatever context we have
            # This ensures early-stop cases still get a proper verdict
            try:
                if all_history or full_responses_log:  # Call if we have ANY history or responses
                    logger.info("==> Calling LLM for FINAL VERDICT (with comprehensive context)...")
                    data, raw_json, elapsed, reasoning_tokens = await consult_final_verdict(
                        client, context_text, all_history, case_name, train_data
                    )
                    
                    turn_logs.append(create_log_entry(
                        len(turn_logs)+1, 
                        question=final_verdict_question_log,
                        answer=str(data.answer), 
                        reasoning=data.reasoning if hasattr(data, 'reasoning') else "", 
                        score=data.confidence_score if hasattr(data, 'confidence_score') else 0, 
                        raw_json=raw_json, 
                        elapsed=elapsed, 
                        metadata=metadata,
                        hidden_reasoning=reasoning_tokens
                    ))
                    
                    final_verdict = str(data.answer)
                else:
                    logger.warning("No history or responses available for final verdict. Case may have failed to process.")
                    final_verdict = "ERROR"
            except Exception as verdict_error:
                logger.error(f"Final verdict call failed: {verdict_error}")
                final_verdict = "ERROR"
            
            total_elapsed = time.time() - start_time_session
            print(f"Tool Session for {case_name} (Run {run_id}) Finished. Verdict: {final_verdict}. Time: {total_elapsed:.2f}s")
            
            log_file = os.path.join(log_dir, "log.json")
            with open(log_file, "w") as f:
                json.dump(turn_logs, f, indent=4)
            logger.info(f"Saved complete run log to {log_file}")
            CURRENT_CASE_REF.reset(case_ref_token)
            
            return final_verdict

async def run_experiment_batch(data_path, dataset, experiment_config, mode, num_runs, client):
    if not os.path.exists(data_path):
        print(f"Error: Data path {data_path} does not exist.")
        return

    cases = sorted([d for d in os.listdir(data_path) if os.path.isdir(os.path.join(data_path, d))])
    print(f"Found {len(cases)} cases in {dataset} set. Starting {num_runs} runs...")

    all_runs_results = {}

    for i in range(1, num_runs + 1):
        print(f"\n{'==='} STARTING RUN {i}/{num_runs} {'==='}")
        
        tasks = []
        case_list_for_run = []
        
        metadata = {
            "dataset": dataset,
            "mode": mode,
            "config": experiment_config,
            "run_id": i,
            "model": CURRENT_CONFIG["id"]
        }
        counter = 0
        for case in cases:
            context = load_context(data_path, case, dataset, experiment_config)
            
            if not context:
                print(f"Skipping {case} (Missing context)")
                continue
                
            case_list_for_run.append(case)
            
            if mode == 'train':
                tasks.append(run_ui_with_tool_batch(client, case, context, i, metadata, train_data=True))
            else:
                tasks.append(run_ui_with_tool_batch(client, case, context, i, metadata, train_data=False))
            
            if counter == 5:
                #break
                pass
                   
            counter += 1
        
        results = await asyncio.gather(*tasks)
        
        run_key = f"run_{i}"
        all_runs_results[run_key] = dict(zip(case_list_for_run, results))
        
        await asyncio.sleep(1)

        json_filename = f"{BASE_CASE_DIR}/results_{dataset}_{mode}_config{experiment_config}_{str(ADM_CONFIG)}_{str(ADM_INITIAL)}.json"
        try:
            with open(json_filename, 'w') as f:
                json.dump(all_runs_results, f, indent=4)
            print(f"\nRun {i} Completed. Results saved to {json_filename}")
        except Exception as e:
            logger.error(f"Failed to save consolidated JSON: {e}")

    print(f"\nAll {num_runs} Runs Completed Successfully.")

# --- MAIN EXECUTION ---
async def async_main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="gpt", choices=["gpt", "llama", "qwen"]) 
    parser.add_argument('--gpu', type=str, default='gpu31')
    parser.add_argument('--port', type=str, default='8000')
    parser.add_argument('--dataset', type=str, choices=['comvik', 'main'], required=True)
    parser.add_argument('--data_path', type=str, default="../Data/VALIDATION")
    parser.add_argument('--exp_config', type=int, required=True)
    parser.add_argument('--temperature', type=float, default=0.0)
    parser.add_argument('--mode', type=str, default='tool', choices=['tool', 'baseline','ensemble','train'])
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--raw_data', type=str, default="../Data/Inv_Step_Sampled_Valid.pkl")
    parser.add_argument('--base_case_dir', type=str, default="../Outputs/Valid_Cases")
    parser.add_argument('--adm_config',type=str,choices=['both','none','sub_adm_1','sub_adm_2'],default='both') 
    parser.add_argument('--adm_initial', action='store_true') 

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)        
        print("--- DEBUG MODE ENABLED ---")
    
    API_BASE = f"http://{args.gpu}.barkla2.liv.alces.network:{args.port}/v1"
    
    global ADM_CONFIG, ADM_INITIAL
    ADM_CONFIG = args.adm_config if args.adm_config else None
    ADM_INITIAL = bool(args.adm_initial)

    global CURRENT_CONFIG, BASE_CASE_DIR, RAW_DATA, LLM_TEMPERATURE
    CURRENT_CONFIG = MODELS.get(args.model, MODELS['gpt'])
    BASE_CASE_DIR = args.base_case_dir
    LLM_TEMPERATURE = args.temperature
    
    try:
        RAW_DATA = pd.read_pickle(args.raw_data)
    except Exception as e:
        logger.warning(f"Could not load RAW_DATA from {args.raw_data}: {e}")
        RAW_DATA = pd.DataFrame()

    logger.info(f"Connecting to vLLM at: {API_BASE}")
    
    try:
        client = AsyncOpenAI(base_url=API_BASE, api_key="EMPTY")
    except Exception:
        print("Error: LLM API unreachable.")
        return
    
    try:
        await run_experiment_batch(args.data_path, args.dataset, args.exp_config, args.mode, args.runs, client)
    except Exception as e:
        logger.error(f"Test Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(async_main())