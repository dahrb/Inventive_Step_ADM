"""
Batched Hybrid ADM System — clean refactor.

Drives UI.py as a subprocess, answering its questions via an LLM.
Batch-first: pre-fetches a whole section of answers in one structured call.
Dynamic fallback: if the question is unrecognised, outside a batch, or the
LLM answer cannot be extracted, switches to a single-question dynamic mode
feeding the raw UI output to the LLM.

Every LLM call receives: system prompt → last 2 Q/A pairs → current question.
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
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from inventive_step_ADM import adm_initial, adm_main

# ── logging ──────────────────────────────────────────────────────────────────

logger = logging.getLogger("Hybrid_ADM_System")

CURRENT_CASE_REF = contextvars.ContextVar("current_case_ref", default="NO_CASE")

class _CaseFilter(logging.Filter):
    def filter(self, record):
        record.case_ref = CURRENT_CASE_REF.get()
        return True

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(case_ref)s]: %(message)s")
for _h in logging.getLogger().handlers:
    _h.addFilter(_CaseFilter())

# ── globals ──────────────────────────────────────────────────────────────────

REQUEST_SEMAPHORE = asyncio.Semaphore(20)
BASE_CASE_DIR = "../Outputs/Valid_Cases"
ADM_SCRIPT_PATH = "../ADM/UI.py"
RAW_DATA = None
CURRENT_CONFIG = None
LLM_TEMPERATURE = 0.0
ADM_CONFIG = "both"
ADM_INITIAL = False

MODELS = {
    # id            — model name sent to vLLM
    # guided_json   — supports extra_body guided_json structured output
    # reasoning_effort — supports 'reasoning_effort' parameter (thinking models)
    # thinking_mode — Qwen-3-style thinking: needs temperature>=0.6, reasoning_content field
    # seed          — supports seed parameter
    # min_temp      — minimum temperature the model accepts (0 = no restriction)
    # max_tokens_dynamic — safe max_tokens for single-question calls
    "gpt": {
        "id": "gpt-oss-120b",
        "guided_json": True, "reasoning_effort": True, "thinking_mode": True,
        "seed": True, "min_temp": 0.0, "max_tokens_dynamic": 8000,
    },
    "llama": {
        "id": "Llama-3.3-70B-Instruct-FP8",
        "guided_json": True, "reasoning_effort": False, "thinking_mode": False,
        "seed": True, "min_temp": 0.0, "max_tokens_dynamic": 1200,
    },
    "qwen": {
        "id": "Qwen-3-80B",
        "guided_json": False, "reasoning_effort": True, "thinking_mode": True,
        "seed": False, "min_temp": 0.0, "max_tokens_dynamic": 8000,
    },
}


def _call_kwargs(schema=None, max_tokens: int = 1200, reasoning_effort: str = "medium",
                 temperature: float | None = None) -> dict:
    """build the kwargs dict for a chat.completions.create call for the current model."""
    cfg = CURRENT_CONFIG or {}
    temp = temperature if temperature is not None else LLM_TEMPERATURE
    min_temp = cfg.get("min_temp", 0.0)
    if temp < min_temp:
        logger.warning(
            "temperature %.2f is below the recommended minimum %.2f for model '%s' — "
            "pass --temperature %.1f or higher to avoid degraded outputs",
            temp, min_temp, cfg.get("id", "?"), min_temp,
        )

    kwargs: dict = {
        "model": cfg.get("id", ""),
        "temperature": temp,
        "max_tokens": max_tokens,
        "top_p": 1,
    }

    if cfg.get("seed"):
        kwargs["seed"] = 42

    if cfg.get("reasoning_effort"):
        kwargs["reasoning_effort"] = reasoning_effort

    if schema is not None and cfg.get("guided_json"):
        kwargs["extra_body"] = {"guided_json": schema}

    return kwargs


def _extract_content(choice) -> str:
    """extract text from a completion choice, falling back to reasoning_content for thinking models."""
    content = (choice.message.content or "").strip()
    if content:
        return content
    # Qwen-3 thinking mode may return the answer only in reasoning_content
    rc = getattr(choice.message, "reasoning_content", None) or ""
    if rc:
        # reasoning_content often contains both <think> block and the final JSON
        # extract the last {...} block which is usually the structured answer
        last_brace = rc.rfind("{")
        if last_brace != -1:
            return rc[last_brace:]
    return ""

# ── json helpers ─────────────────────────────────────────────────────────────

def _complete_brace(raw: str) -> str:
    """try to close a truncated json object."""
    s = raw.rstrip()
    if s.endswith("}"):
        return s
    if s.endswith('"'):
        return s + "\n}"
    if s.endswith(","):
        return s[:-1] + "\n}"
    return s + "\n}"


def _extract_json(text: str) -> str:
    """extract the first balanced {...} from text."""
    if not text:
        return ""
    start = text.find("{")
    if start == -1:
        return ""
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:]


def _parse_model(model_class, raw: str):
    """robust parse: direct → extracted → brace-completed."""
    if not raw:
        raise ValueError("empty llm response")
    candidate = raw.strip()
    try:
        return model_class.model_validate_json(candidate), candidate
    except Exception:
        pass
    extracted = _extract_json(candidate)
    if extracted:
        try:
            return model_class.model_validate_json(extracted), extracted
        except Exception:
            pass
        completed = _complete_brace(extracted)
        if completed != extracted:
            try:
                return model_class.model_validate_json(completed), completed
            except Exception:
                pass
    completed = _complete_brace(candidate)
    if completed != candidate:
        return model_class.model_validate_json(completed), completed
    return model_class.model_validate_json(candidate), candidate

# ── question introspection ───────────────────────────────────────────────────

def _extract_questions(adm_instance) -> dict:
    """build {lowercase_key: formatted_question_text} from an adm instance."""
    qs = {}

    #information questions
    info_map = {
        "INVENTION_TITLE": "invention title",
        "INVENTION_DESCRIPTION": "description",
        "INVENTION_TECHNICAL_FIELD": "technical field",
        "REL_PRIOR_ART": "prior art",
        "CGK": "common general knowledge",
        "OBJ_T_PROBLEM": "obj_t_problem",
    }
    if hasattr(adm_instance, "information_questions"):
        for k, qt in adm_instance.information_questions.items():
            qs[info_map.get(k, k.lower())] = f"[Q] {qt}:"

    #hardcoded factual ascription prompts
    qs["closest prior art description"] = "[Q] Please describe the candidate for the closest prior art:"

    if not hasattr(adm_instance, "questionOrder"):
        return qs

    for item_name in adm_instance.questionOrder:
        #skip info questions already handled
        if hasattr(adm_instance, "information_questions") and item_name in adm_instance.information_questions:
            continue

        #question instantiators (mcq)
        if hasattr(adm_instance, "question_instantiators") and item_name in adm_instance.question_instantiators:
            inst = adm_instance.question_instantiators[item_name]
            q_text = inst.get("question", "")
            m = re.search(r"\[(Q\d+)\]", q_text)
            tag = m.group(1).lower() if m else item_name.lower()
            fmt = q_text + "\n"
            for i, opt in enumerate(inst.get("blf_mapping", {}).keys(), 1):
                fmt += f"{i}. {opt}\n"
            fmt += "\nEnter the number of the answer you wish to choose (only enter the chosen number):"
            qs[tag] = fmt.strip()

        #regular nodes and sub-adm nodes
        elif hasattr(adm_instance, "nodes") and item_name in adm_instance.nodes:
            node = adm_instance.nodes[item_name]

            #sub-adm nodes: recurse into a sample sub-adm
            if hasattr(node, "sub_adm") and callable(node.sub_adm):
                try:
                    sample = node.sub_adm("sample_item")
                    #instantiators inside sub-adm
                    if hasattr(sample, "question_instantiators") and isinstance(sample.question_instantiators, dict):
                        for _qn, inst in sample.question_instantiators.items():
                            qt = inst.get("question", "")
                            m2 = re.search(r"\[(Q\d+)\]", qt)
                            tag2 = m2.group(1).lower() if m2 else _qn.lower()
                            fmt2 = qt + "\n"
                            for i, opt in enumerate(inst.get("blf_mapping", {}).keys(), 1):
                                fmt2 += f"{i}. {opt}\n"
                            fmt2 += "\nEnter the number of the answer you wish to choose (only enter the chosen number):"
                            qs[tag2] = fmt2.strip()
                    #regular nodes inside sub-adm
                    if hasattr(sample, "nodes"):
                        for sn, snode in sample.nodes.items():
                            if hasattr(snode, "question") and snode.question:
                                m3 = re.search(r"\[(Q\d+)\]", snode.question)
                                tag3 = m3.group(1).lower() if m3 else sn.lower()
                                fmt3 = snode.question + "\n"
                                fmt3 += "\nAnswer 'yes' or 'no' only (y/n):"
                                qs[tag3] = fmt3.strip()
                except Exception as e:
                    logger.warning("could not extract sub-adm questions for %s: %s", item_name, e)

            elif hasattr(node, "question") and node.question:
                m4 = re.search(r"\[(Q\d+)\]", node.question)
                tag4 = m4.group(1).lower() if m4 else item_name.lower()
                fmt4 = node.question + "\nAnswer 'yes' or 'no' only (y/n):"
                qs[tag4] = fmt4.strip()

    return qs

#pre-extract all question dictionaries at module load
INITIAL_ADM_QUESTIONS = _extract_questions(adm_initial())
MAIN_ADM_QUESTIONS = _extract_questions(adm_main(True, True))
MAIN_ADM_NO_SUB_1_QUESTIONS = _extract_questions(adm_main(False, True))
MAIN_ADM_NO_SUB_2_QUESTIONS = _extract_questions(adm_main(True, False))
MAIN_ADM_NO_SUB_BOTH_QUESTIONS = _extract_questions(adm_main(False, False))
ALL_EXACT_QUESTIONS = {**INITIAL_ADM_QUESTIONS, **MAIN_ADM_QUESTIONS}


def _question_text(key: str) -> str:
    """look up full question text across all known dictionaries."""
    k = key.lower()
    for src in (ALL_EXACT_QUESTIONS, INITIAL_ADM_QUESTIONS, MAIN_ADM_QUESTIONS,
                MAIN_ADM_NO_SUB_1_QUESTIONS, MAIN_ADM_NO_SUB_2_QUESTIONS,
                MAIN_ADM_NO_SUB_BOTH_QUESTIONS):
        if k in src:
            return src[k]
    return ""


def _expects_yes_no(key: str) -> bool:
    t = _question_text(key).lower()
    return "answer 'yes' or 'no' only" in t or "(y/n)" in t


def _allowed_digits(key: str) -> set[str]:
    return set(re.findall(r"^\s*(\d+)\.\s", _question_text(key), flags=re.MULTILINE))


def _option_text_map(key: str) -> dict[str, str]:
    """return {digit: option_text} from the formatted question."""
    result = {}
    for num, txt in re.findall(r"^\s*(\d+)\.\s*(.+)$", _question_text(key), flags=re.MULTILINE):
        if txt.strip():
            result[num] = txt.strip()
    return result


def _normalize_answer(raw: str, key: str) -> str | None:
    """normalize an llm answer to a digit or y/n. returns None on failure."""
    cleaned = (raw or "").strip().replace("**", "")
    low = cleaned.lower()
    allowed = _allowed_digits(key)

    if low in ("y", "yes"):
        return "y"
    if low in ("n", "no"):
        return "n"

    #try to find digits
    #important: for mcq keys, prefer digits that are valid options for that exact question.
    #this avoids misreading labels like "Q32"/"Q101" as the selected answer.
    nums = re.findall(r"\d+", cleaned)
    if nums:
        if allowed:
            for num in nums:
                if num in allowed:
                    return num
        #fallback: no option list known for this key, use first number
        if not allowed:
            return nums[0]

    #word numbers
    for word, digit in {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5"}.items():
        if re.search(rf"\b{word}\b", low):
            if not allowed or digit in allowed:
                return digit

    #match against option text (handles model returning full option text)
    omap = _option_text_map(key)
    if omap:
        norm_raw = re.sub(r"\s+", " ", low).strip(" .,:;!?\"'`")
        for num, opt_text in omap.items():
            norm_opt = re.sub(r"\s+", " ", opt_text.lower()).strip(" .,:;!?\"'`")
            if not norm_opt:
                continue
            if norm_opt in norm_raw or (len(norm_raw) >= 8 and norm_raw in norm_opt):
                return num

    #last resort yes/no extraction
    if _expects_yes_no(key):
        ym = re.search(r"\b(yes|no)\b", low)
        if ym:
            return "y" if ym.group(1) == "yes" else "n"

    logger.warning("cannot normalize answer for %s: %r", key, raw)
    return None


def _valid_answer(key: str, norm: str) -> bool:
    """check that a normalised answer is valid for the given question key."""
    if not norm:
        return False
    allowed = _allowed_digits(key)
    if _expects_yes_no(key):
        return norm in {"y", "n"} or (bool(allowed) and norm in allowed)
    if allowed:
        return norm in allowed
    return bool(re.fullmatch(r"\d+", norm))

# ── pydantic schemas ─────────────────────────────────────────────────────────

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
    q17_tech_cont: QuestionResponse = Field(description="[Q17] please only give the number corresponding to the chosen answer")
    q19_dist_feat: QuestionResponse = Field(description="[Q19]")
    q20_circumvent: QuestionResponse = Field(description="[Q20]")
    q21_tech_adapt: QuestionResponse = Field(description="[Q21]")
    q22_intended: QuestionResponse = Field(description="[Q22]")
    q23_tech_use: QuestionResponse = Field(description="[Q23]")
    q24_specific_purpose: QuestionResponse = Field(description="[Q24]")
    q25_func_limited: QuestionResponse = Field(description="[Q25]")
    q26_unexpected: QuestionResponse = Field(description="[Q26]")
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

# ── batch section routing ────────────────────────────────────────────────────
#maps each question key to (pydantic_model, section_label, all_keys_in_section)

_INITIAL_KEYS = (
    ["invention title", "description", "technical field", "prior art",
     "common general knowledge", "closest prior art description"]
    + [f"Q{i}" for i in range(1, 17)]
)
_SUB1_KEYS = ["Q17", "Q19", "Q20", "Q21", "Q22", "Q23", "Q24", "Q25",
              "Q26", "Q27", "Q28", "Q29", "Q30", "Q31"]
_INTER_KEYS = ["Q32", "Q33"]
_SUB2_KEYS = ["Q34", "Q36", "Q38", "Q39"]
_NO_SUB1_KEYS = [f"Q{i}" for i in range(100, 108)]
_NO_SUB2_KEYS = ["obj_t_problem"] + [f"Q{i}" for i in range(200, 204)]
_SECONDARY_KEYS = ["Q99"] + [f"Q{i}" for i in range(40, 60)]


def _section_for_key(key: str):
    """return (model_class, label, keys_list) or None."""
    if key in _INITIAL_KEYS:
        return InitialADM_Batch, "Initial Preconditions", _INITIAL_KEYS
    if key in _SUB1_KEYS:
        return SubADM1_Batch, "Technical Character", _SUB1_KEYS
    if key in _INTER_KEYS:
        return MainADM_Inter_Batch, "Synergy & Interaction", _INTER_KEYS
    if key in _SUB2_KEYS:
        return SubADM2_Batch, "Problem-Solution Approach", _SUB2_KEYS
    if key in _NO_SUB1_KEYS:
        return MainADM_No_Sub_1, "Technical Factors (No Sub-ADM 1)", _NO_SUB1_KEYS
    if key in _NO_SUB2_KEYS:
        return MainADM_No_Sub_2, "Obviousness Factors (No Sub-ADM 2)", _NO_SUB2_KEYS
    if key in _SECONDARY_KEYS:
        return SecondaryIndicators_Batch, "Secondary Indicators", _SECONDARY_KEYS
    return None


#maps pydantic field names → answer keys per schema
_FIELD_TO_KEY = {
    #initial
    "invention_title": "invention title", "invention_description": "description",
    "technical_field": "technical field", "relevant_prior_art": "prior art",
    "common_general_knowledge": "common general knowledge",
    "closest_prior_art_description": "closest prior art description",
    "q1_similar_purpose": "Q1", "q2_similar_effects": "Q2", "q3_same_field": "Q3",
    "q4_contested": "Q4", "q5_cgk_evidence": "Q5", "q6_skilled_in": "Q6",
    "q7_average": "Q7", "q8_aware": "Q8", "q9_access": "Q9", "q10_skilled_person": "Q10",
    "q11_cpa": "Q11", "q12_minmod": "Q12", "q13_combo_attempt": "Q13",
    "q14_combined": "Q14", "q15_combo_motive": "Q15", "q16_basis": "Q16",
    #sub-adm 1
    "q17_tech_cont": "Q17", "q19_dist_feat": "Q19", "q20_circumvent": "Q20",
    "q21_tech_adapt": "Q21", "q22_intended": "Q22", "q23_tech_use": "Q23",
    "q24_specific_purpose": "Q24", "q25_func_limited": "Q25", "q26_unexpected": "Q26",
    "q27_precise": "Q27", "q28_one_way": "Q28", "q29_credible": "Q29",
    "q30_claim_contains": "Q30", "q31_suff_dis": "Q31",
    #inter
    "q32_synergy": "Q32", "q33_func_int": "Q33",
    #sub-adm 2
    "q34_encompassed": "Q34", "q36_scope": "Q36", "q38_hindsight": "Q38", "q39_would": "Q39",
    #no-sub1
    "q100_dist_feat": "Q100", "q101_tech_cont": "Q101", "q102_unexpected": "Q102",
    "q103_precise": "Q103", "q104_one_way": "Q104", "q105_credible": "Q105",
    "q106_claimcontains": "Q106", "q107_suff_dis": "Q107",
    #no-sub2
    "obj_t_problem": "obj_t_problem", "q200_encompassed": "Q200", "q201_scope": "Q201",
    "q202_hindsight": "Q202", "q203_would": "Q203",
    #secondary
    "q99_agree_otp": "Q99", "q40_disadvantage": "Q40", "q41_foresee": "Q41",
    "q42_advantage": "Q42", "q43_biotech": "Q43", "q44_antibody": "Q44",
    "q45_pred_results": "Q45", "q46_reasonable": "Q46", "q47_known_tech": "Q47",
    "q48_overcome": "Q48", "q49_gap_filled": "Q49", "q50_well_known": "Q50",
    "q51_known_prop": "Q51", "q52_analog_use": "Q52", "q53_known_device": "Q53",
    "q54_obvs_combo": "Q54", "q55_analog_sub": "Q55", "q56_equal_alt": "Q56",
    "q57_normal_design": "Q57", "q58_simple_extra": "Q58", "q59_chem_select": "Q59",
}

# ── prompts ──────────────────────────────────────────────────────────────────

def _system_prompt(context: str, case_name: str, train: bool = False) -> str:
    """build the system prompt, optionally including train-mode decision data."""
    base = (
        "You are helping to objectively assess Inventive Step for the European Patent Office (EPO). "
        "These cases are appeals against the examining boards' original decisions.\n"
        "Your job is to critically analyse the information given to you to come to an informed, reasoned judgment "
        "to objectively assess the presence of inventive step within the invention.\n"
        "You will be asked questions generated from an argumentation tool, called an ADM (ANGELIC DOMAIN MODEL) "
        "designed for inventive step to help you reason to a conclusion on whether inventive step is present.\n"
        "An ADM is a hierarchical tree-like model which ascribes legal facts to 'base level factors' which are "
        "then processed using sets of prioritised acceptance conditions linked to more abstract factors to determine a conclusion.\n"
        "Each question you answer corresponds to a base-level factor (BLF). Try to answer each question as if you were "
        "a legal ascriber mapping evidence to a reasoning framework.\n\n"
        f"=== CASE DATA ===\n{context}\n=== END CASE DATA ===\n\n"
    )

    if train and RAW_DATA is not None and not RAW_DATA.empty:
        try:
            reasons = str(RAW_DATA.loc[RAW_DATA["Reference"] == case_name, "Decision Reasons"].iloc[0])
            decision = str(RAW_DATA.loc[RAW_DATA["Reference"] == case_name, "Order"].iloc[0])
        except Exception:
            reasons, decision = "", ""
        base += (
            f"=== REASONS FOR DECISION ===\n{reasons}\n=== END REASONS FOR DECISION ===\n\n"
            f"=== DECISION ===\n{decision}\n=== END DECISION ===\n\n"
            "INSTRUCTIONS:\n"
            "1. Provide a step-by-step reasoning trace with explicit reference to the case data as to why you gave your answer..\n"
            "2. Conclude with a final 'Yes' or 'No' answer, or the specific text requested.\n"
            "3. Use the data provided. Do not refer to case law, patents or other specific inventions you have not been provided with.\n"
            "4. You may make reasonable assumptions about the skilled person or common general knowledge.\n"
            "5. Follow the reasoning from the 'reasons for decision' as closely as possible when ascribing factors.\n"
            "6. You MUST try and follow the actual decision of the case as closely as possible.\n"
        )
    else:
        base += (
            "INSTRUCTIONS:\n"
            "1. Provide a step-by-step reasoning trace with explicit reference to the case data as to why you gave your answer.\n"
            "2. Conclude with a final 'Yes' or 'No' answer, or the specific text requested.\n"
            "3. Use the data provided. Do not refer to case law, patents or other specific inventions you have not been provided with.\n"
            "4. You may make reasonable assumptions about the skilled person or common general knowledge.\n"
            "5. Do not follow any conclusions in the case data blindly — critically assess all information.\n"
            "6. Ensure you remember that these questions are here to guide your reasoning, think about"
        )
    return base

# ── conversation context ─────────────────────────────────────────────────────

def _last_2_qa(qa_log: list[dict]) -> list[dict]:
    """return message list for the last 2 question/answer pairs from the qa log.
    each entry in qa_log is {question, answer, reasoning}."""
    msgs = []
    for entry in qa_log[-2:]:
        msgs.append({"role": "user", "content": entry["question"]})
        msgs.append({"role": "assistant", "content": json.dumps({
            "answer": entry["answer"],
            "reasoning": entry.get("reasoning", ""),
        })})
    return msgs

# ── llm call: batch ──────────────────────────────────────────────────────────

async def _call_batch(client, sys_prompt: str, history: list[dict],
                      model_class, section_label: str, keys: list[str],
                      feature_name: str = None) -> tuple:
    """call llm with a batched structured schema. returns (parsed_data, raw_json, elapsed)."""

    #select the right question dictionary based on section label
    if "No Sub-ADM 1" in section_label and "No Sub-ADM 2" not in section_label:
        qdict = MAIN_ADM_NO_SUB_1_QUESTIONS
    elif "No Sub-ADM 2" in section_label and "No Sub-ADM 1" not in section_label:
        qdict = MAIN_ADM_NO_SUB_2_QUESTIONS
    elif "No Sub-ADM 1" in section_label and "No Sub-ADM 2" in section_label:
        qdict = MAIN_ADM_NO_SUB_BOTH_QUESTIONS
    else:
        qdict = ALL_EXACT_QUESTIONS

    #build question text
    q_text = "QUESTIONS TO ANSWER:\n"
    for k in keys:
        qt = qdict.get(k.lower(), f"Question {k} not found.")
        if feature_name and isinstance(qt, str):
            qt = qt.replace("sample_item", feature_name)
        q_text += f"\n--- {k.upper()} ---\n{qt}\n"

    ctx = ""
    if feature_name:
        sub2_tags = {"q34", "q36", "q38", "q39"}
        is_sub2 = any(t in str(keys).lower() for t in sub2_tags)
        kind = "objective technical problem" if is_sub2 else "feature"
        ctx = f"\n[CONTEXT: Evaluating {kind}: {feature_name}]"

    # if guided_json is not supported, embed the schema in the prompt
    cfg = CURRENT_CONFIG or {}
    if not cfg.get("guided_json"):
        schema_str = json.dumps(model_class.model_json_schema(), indent=2)
        q_text += (
            f"\n\nTASK: Fill out the structured JSON schema completely.\n"
            f"Return ONLY a single valid JSON object matching this schema (no prose, no markdown fences):\n"
            f"```json\n{schema_str}\n```"
        )
        task_suffix = ""
    else:
        task_suffix = "\nTASK: Fill out the structured JSON schema completely."

    messages = [{"role": "system", "content": sys_prompt}] + history
    messages.append({"role": "user", "content": f"{q_text}{ctx}{task_suffix}"})

    #estimate tokens and cap (thinking models need headroom for <think> block)
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    est_input = total_chars // 4
    thinking_headroom = 8000 if cfg.get("thinking_mode") else 0
    max_tokens = min(12000, max(3000, 32000 - est_input - 500 - thinking_headroom))

    schema = model_class.model_json_schema() if cfg.get("guided_json") else None

    for attempt in range(5):
        t0 = time.time()
        try:
            kwargs = _call_kwargs(schema=schema, max_tokens=max_tokens)
            kwargs["messages"] = messages
            comp = await client.chat.completions.create(**kwargs)
            elapsed = time.time() - t0
            raw = _extract_content(comp.choices[0])
            if not raw:
                raise ValueError("empty response from model")
            parsed, norm_json = _parse_model(model_class, raw)
            return parsed, norm_json, elapsed
        except Exception as e:
            logger.warning("batch %s attempt %d failed: %s", section_label, attempt + 1, e)
            if attempt == 4:
                raise
            await asyncio.sleep(2 * (2 ** attempt))

# ── llm call: dynamic (single question) ─────────────────────────────────────

async def _call_dynamic(client, sys_prompt: str, history: list[dict],
                        question_text: str) -> tuple:
    """call llm with a single question. returns (parsed_data, raw_json, elapsed)."""
    cfg = CURRENT_CONFIG or {}
    schema = QuestionResponse.model_json_schema()

    if cfg.get("guided_json"):
        instruction = (
            "\n\nIMPORTANT OUTPUT FORMAT: Return exactly one JSON object matching this schema: "
            '{"answer": "...", "reasoning": "..."}. '
            "Both fields are required. Do not omit 'reasoning'."
        )
        extra_body_schema = schema
    else:
        instruction = (
            "\n\nIMPORTANT OUTPUT FORMAT: Return ONLY a single JSON object — no prose, no markdown fences:\n"
            '{"answer": "<your answer>", "reasoning": "<your step-by-step reasoning>"}\n'
            "Both fields are required."
        )
        extra_body_schema = None

    messages = [{"role": "system", "content": sys_prompt}] + history
    messages.append({"role": "user", "content": question_text + instruction})

    max_tokens_dynamic = cfg.get("max_tokens_dynamic", 1200)

    for attempt in range(5):
        t0 = time.time()
        try:
            kwargs = _call_kwargs(schema=extra_body_schema, max_tokens=max_tokens_dynamic)
            kwargs["messages"] = messages
            comp = await client.chat.completions.create(**kwargs)
            elapsed = time.time() - t0
            raw = _extract_content(comp.choices[0])
            if not raw:
                raise ValueError("empty response from model")
            parsed, norm_json = _parse_model(QuestionResponse, raw)

            #reject BLANK answers with retry
            if parsed.answer.strip().upper() == "BLANK" and attempt < 4:
                logger.warning("llm returned BLANK, retrying (%d/5)", attempt + 1)
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content":
                    "The answer 'BLANK' is not acceptable. Provide a proper answer based on the case data."})
                continue

            return parsed, norm_json, elapsed
        except Exception as e:
            logger.warning("dynamic attempt %d failed: %s", attempt + 1, e)
            if attempt == 4:
                raise
            await asyncio.sleep(2 * (2 ** attempt))

# ── llm call: final verdict ──────────────────────────────────────────────────

async def _call_final_verdict(client, sys_prompt: str, adm_context: list[dict],
                              case_name: str, train: bool) -> tuple:
    """get the final inventive step verdict. returns (parsed_data, raw_json, elapsed)."""
    if train:
        question = (
            "FINAL_VERDICT\n"
            "Based on the session interaction above, what was the final outcome from the tool?\n"
            "State 'Yes' or 'No' for inventive step. Explain whether you agree with the tool's outcome "
            "by comparing to the real decision. Provide a confidence score 0-100."
        )
    else:
        question = (
            "FINAL_VERDICT\n"
            "Based on the session interaction above, what was the final outcome?\n"
            "State 'Yes' or 'No' for inventive step. Explain whether you agree with the tool's outcome. "
            "Provide a confidence score 0-100."
        )

    cfg = CURRENT_CONFIG or {}
    schema = FinalVerdictResponse.model_json_schema()

    if cfg.get("guided_json"):
        sp = sys_prompt + "\n\nIMPORTANT: Your response MUST be a single valid JSON object ending with '}'."
        extra_body_schema = schema
    else:
        sp = (
            sys_prompt
            + "\n\nIMPORTANT: Return ONLY a single JSON object — no prose, no markdown fences:\n"
            + '{"answer": "Yes or No", "reasoning": "...", "confidence_score": <0-100>}'
        )
        extra_body_schema = None

    messages = [{"role": "system", "content": sp}] + adm_context
    messages.append({"role": "user", "content": question})

    #trim if too large
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    if total_chars // 4 > 20000:
        logger.warning("final verdict context too large, trimming")
        kept = [messages[0]]
        for m in messages[1:-1]:
            c = str(m.get("content", ""))
            if "Final ADM Output" in c or "Sub-ADM Conclusion" in c:
                kept.append(m)
        kept.extend(messages[-3:])
        messages = kept

    est_input = sum(len(str(m.get("content", ""))) for m in messages) // 4
    thinking_headroom = 8000 if cfg.get("thinking_mode") else 0
    max_tokens = min(12000, max(5000, 32000 - est_input - 1000 - thinking_headroom))

    for attempt in range(10):
        t0 = time.time()
        try:
            kwargs = _call_kwargs(schema=extra_body_schema, max_tokens=max_tokens)
            kwargs["messages"] = messages
            comp = await client.chat.completions.create(**kwargs)
            elapsed = time.time() - t0
            raw = _extract_content(comp.choices[0])
            if not raw:
                raise ValueError("empty response from model")
            try:
                parsed, _ = _parse_model(FinalVerdictResponse, raw)
                return parsed, raw, elapsed
            except Exception:
                #regex recovery
                am = re.search(r'"answer"\s*:\s*["\']?([Yy][Ee][Ss]|[Nn][Oo])["\']?', raw)
                rm = re.search(r'"reasoning"\s*:\s*["\'](.+?)["\']\s*(,|\}|$)', raw, re.DOTALL)
                cm = re.search(r'"confidence_score"\s*:\s*(\d+)', raw)
                if am and rm and cm:
                    recovered = FinalVerdictResponse(
                        answer=am.group(1).capitalize(),
                        reasoning=rm.group(1).strip(),
                        confidence_score=int(cm.group(1)),
                    )
                    return recovered, raw, elapsed
        except Exception as e:
            logger.warning("final verdict attempt %d failed: %s", attempt + 1, e)
        await asyncio.sleep(2 * (2 ** attempt))
    raise RuntimeError("final verdict failed after all attempts")

# ── ui text helpers ──────────────────────────────────────────────────────────

def _strip_decorators(text: str) -> str:
    """remove decorative separator lines."""
    lines = text.splitlines()
    out = [l for l in lines if not (len(l.strip()) >= 3 and l.strip()[0] in "=-_~*" and len(set(l.strip())) == 1)]
    return "\n".join(out).strip()


def _extract_case_outcome(full_output: str) -> str:
    """extract the latest 'Case Outcome:' block from full ui output."""
    marker = "Case Outcome:"
    idx = full_output.rfind(marker)
    if idx == -1:
        return ""
    tail = full_output[idx:]
    ends = ["ADM and sub-ADM summaries appended to:", "\n[Q]", "\nINFO: ADM created"]
    positions = [p for m in ends if (p := tail.find(m)) != -1]
    end = min(positions) if positions else len(tail)
    return tail[:end].strip()


def _extract_sub_adm_conclusion(text: str) -> str:
    """extract an early-stop / case outcome block from recent ui text."""
    starts = [text.find("[Early Stop]"), text.find("Case Outcome:"), text.find("Sub-ADM Summary ===")]
    valid = [i for i in starts if i != -1]
    if not valid:
        return ""
    s = min(valid)
    tail = text[s:]
    ends = ["\n[Q", "\nINFO: ADM created", "\n--- Item", "\n=== Evaluating"]
    positions = [p for m in ends if (p := tail.find(m)) != -1]
    end = min(positions) if positions else len(tail)
    return tail[:end].strip()


def _detect_item_name(text: str) -> str | None:
    """extract feature: or problem name: from ui text."""
    fm = re.search(r"Feature:\s*(.+?)(?:\n|$)", text)
    if fm:
        return fm.group(1).strip()
    pm = re.search(r"Problem name:\s*(.+?)(?:\n|$)", text)
    if pm:
        return pm.group(1).strip()
    return None

# ── data loading ─────────────────────────────────────────────────────────────

def _load_context(data_path: str, case_name: str, dataset: str, config: int) -> str:
    path = os.path.join(data_path, case_name)
    parts = []

    if dataset == "comvik":
        cpa = os.path.join(path, "CPA.txt")
        if os.path.exists(cpa):
            parts.append(f"--- CLOSEST PRIOR ART INFORMATION ---\n{open(cpa).read()}")
        if config == 1:
            pat = os.path.join(path, "patent.txt")
            if os.path.exists(pat):
                parts.append(f"--- PATENT APPLICATION CLAIMS ---\n{open(pat).read()}")
        elif config == 2:
            full = os.path.join(path, "full.txt")
            if os.path.exists(full):
                parts.append(f"--- FULL REASONING ABOUT THE PATENT APPLICATION ---\n{open(full).read()}")
    else:
        appeal = os.path.join(path, "appeal.txt")
        claims = os.path.join(path, "claims.txt")
        cpa = os.path.join(path, "CPA.txt")
        if config == 1:
            if os.path.exists(appeal):
                parts.append(f"--- SUMMARY OF FACTS FROM THE APPEAL ---\n{open(appeal).read()}")
        elif config == 2:
            if os.path.exists(claims):
                parts.append(f"--- PATENT APPLICATION CLAIMS ---\n{open(claims).read()}")
            if os.path.exists(cpa):
                parts.append(f"--- CLOSEST PRIOR ART DOCUMENT/S ---\n{open(cpa).read()}")
        elif config == 3:
            if os.path.exists(appeal):
                parts.append(f"--- SUMMARY OF FACTS FROM THE APPEAL ---\n{open(appeal).read()}")
            if os.path.exists(claims):
                parts.append(f"--- PATENT APPLICATION CLAIMS ---\n{open(claims).read()}")
            if os.path.exists(cpa):
                parts.append(f"--- CLOSEST PRIOR ART DOCUMENT/S ---\n{open(cpa).read()}")

    try:
        year = str(RAW_DATA.loc[RAW_DATA["Reference"] == case_name, "Year"].iloc[0]) if RAW_DATA is not None and not RAW_DATA.empty else "UNKNOWN"
    except Exception:
        year = "UNKNOWN"
    parts.append(f"--- COMMON KNOWLEDGE DATE CUTOFF ---\n{year}")
    return "\n\n".join(parts)

# ── main controller ──────────────────────────────────────────────────────────

def _log_entry(turn: int, question: str, answer: str, reasoning: str,
               score: int, raw_json: str, elapsed: float, metadata: dict) -> dict:
    return {
        "turn": turn,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "question": question,
        "answer": answer,
        "reasoning": reasoning,
        "score": score,
        "raw_content": raw_json,
        "elapsed_seconds": elapsed,
        "model_id": metadata.get("model", "Unknown"),
        "metadata": metadata,
    }


async def _run_case(client, case_name: str, context_text: str, run_id: int,
                    metadata: dict, train: bool = False) -> str:
    """drive ui.py for one case, returning the final verdict string."""
    async with REQUEST_SEMAPHORE:
        case_token = CURRENT_CASE_REF.set(case_name)
        t_start = time.time()
        config_num = metadata.get("config", "X")
        mode = metadata.get("mode", "tool")

        log_subdir = "train" if train else "tool"
        log_dir = os.path.join(BASE_CASE_DIR, case_name, f"run_{run_id}",
                               f"config_{config_num}", log_subdir,
                               str(ADM_CONFIG), str(ADM_INITIAL))
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "log.json")
        if os.path.exists(log_path):
            os.remove(log_path)

        #state
        answers_cache: dict = {}        #cache_key → QuestionResponse
        qa_log: list[dict] = []         #chronological q/a pairs for context
        turn_logs: list[dict] = []      #full turn log for json output
        full_output = ""                #accumulated ui stdout
        buffer: list[str] = []          #current chunk buffer
        full_responses_log: dict = {}   #batch response data for final verdict
        last_sent = ""
        last_type = ""
        pending_conclusion = ""
        last_conclusion = ""

        #build the system prompt once
        sys_prompt = _system_prompt(context_text, case_name, train)

        #spawn ui.py subprocess
        proc_args = [
            sys.executable, "-u", ADM_SCRIPT_PATH,
            "--run_id", str(run_id),
            "--config", str(config_num),
            "--mode", str(mode),
            "--folder_base", str(BASE_CASE_DIR),
            "--adm_config", str(ADM_CONFIG),
        ]
        if ADM_INITIAL:
            proc_args.append("--adm_initial")

        proc = await asyncio.create_subprocess_exec(
            *proc_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async def _send(text: str):
            nonlocal last_sent, last_type
            try:
                proc.stdin.write(f"{text}\n".encode("utf-8"))
                await proc.stdin.drain()
                last_sent = text
                if re.fullmatch(r"\d+", text):
                    last_type = "number"
                elif text in {"y", "n"}:
                    last_type = "yesno"
                else:
                    last_type = "text"
            except (ConnectionResetError, BrokenPipeError):
                raise StopIteration("stdin closed")

        try:
            while True:
                timed_out = False
                try:
                    chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=0.25)
                    if not chunk:
                        break
                    decoded = chunk.decode("utf-8", errors="replace")
                    buffer.append(decoded)
                    full_output += decoded
                    if decoded.strip():
                        print(f"[UI.py] {decoded.strip()}")
                except asyncio.TimeoutError:
                    timed_out = True

                combined = "".join(buffer)
                clean = _strip_decorators(combined)

                #capture adm outcomes for final verdict
                case_outcome = _extract_case_outcome(full_output)
                if case_outcome:
                    full_responses_log["Final_ADM_Output"] = case_outcome

                sub_conclusion = _extract_sub_adm_conclusion(clean)
                if sub_conclusion and sub_conclusion != last_conclusion:
                    full_responses_log.setdefault("Sub_ADM_Conclusions", []).append(sub_conclusion)
                    pending_conclusion = sub_conclusion
                    last_conclusion = sub_conclusion

                if not clean and proc.returncode is None:
                    continue
                if proc.returncode is not None and not clean:
                    break
                if not timed_out:
                    continue

                # ── classify the prompt ──────────────────────────────────

                needed_key = None
                go_dynamic = False
                lower_clean = clean.lower()

                #handle "invalid input" retries
                if "invalid input" in lower_clean:
                    expects_num = "enter the number" in lower_clean or "only give a number" in lower_clean
                    expects_yn = "(y/n)" in lower_clean or "yes' or 'no'" in lower_clean
                    can_resend = False
                    if expects_num and last_type == "number" and re.fullmatch(r"\d+", last_sent):
                        can_resend = True
                    elif expects_yn and last_type == "yesno" and last_sent in {"y", "n"}:
                        can_resend = True
                    elif not expects_num and not expects_yn and last_sent:
                        can_resend = True
                    if can_resend:
                        logger.warning("ui rejected input; resending: %s", last_sent)
                        await _send(last_sent)
                    buffer = []
                    continue

                #auto-fill case name
                if "enter case name" in lower_clean:
                    logger.info("auto-filling case name: %s", case_name)
                    await _send(case_name)
                    buffer = []
                    continue

                #check for explicit [Qxx] tag
                q_match = re.search(r"\[(Q\d+)\]", clean)
                if q_match:
                    q_num = q_match.group(1)
                    if q_num == "Q380":
                        go_dynamic = True
                    else:
                        needed_key = q_num

                #information questions / other prompts (only if no q-tag)
                if not needed_key and not go_dynamic:
                    if "title of your invention" in lower_clean:
                        needed_key = "invention title"
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
                        go_dynamic = True

                if not needed_key and not go_dynamic:
                    if clean.strip().endswith(":") or clean.strip().endswith("?") or "(y/n)" in lower_clean:
                        go_dynamic = True
                    else:
                        continue

                #build history: system prompt is always included; then last 2 qa pairs
                history = _last_2_qa(qa_log)

                # ── route a: dynamic mode ────────────────────────────────

                if go_dynamic:
                    logger.info("dynamic mode for prompt: %s", clean[:80])

                    #include adm output context if available
                    prompt = clean
                    if pending_conclusion and pending_conclusion not in clean:
                        prompt = f"{pending_conclusion}\n\n{clean}"

                    data, raw_json, elapsed = await _call_dynamic(client, sys_prompt, history, prompt)
                    answer = str(data.answer)

                    qa_log.append({"question": clean, "answer": answer, "reasoning": data.reasoning})
                    turn_logs.append(_log_entry(len(turn_logs) + 1, prompt, answer,
                                                data.reasoning, 0, raw_json, elapsed, metadata))
                    pending_conclusion = ""

                    logger.info("  → dynamic answer: %s", answer)
                    await _send(answer)
                    buffer = []
                    continue

                # ── route b: batch mode ──────────────────────────────────

                section = _section_for_key(needed_key)
                if section is None:
                    #key not in any known batch section — fall back to dynamic
                    logger.warning("key %s not in any batch section, using dynamic", needed_key)
                    data, raw_json, elapsed = await _call_dynamic(client, sys_prompt, history, clean)
                    answer = str(data.answer)
                    qa_log.append({"question": clean, "answer": answer, "reasoning": data.reasoning})
                    turn_logs.append(_log_entry(len(turn_logs) + 1, clean, answer,
                                                data.reasoning, 0, raw_json, elapsed, metadata))
                    await _send(answer)
                    buffer = []
                    continue

                model_class, section_label, section_keys = section

                #for sub-adm questions, include item name in cache key
                item_name = None
                if needed_key in _SUB1_KEYS or needed_key in _SUB2_KEYS:
                    item_name = _detect_item_name(clean)
                    if not item_name:
                        item_name = "UNKNOWN"
                        logger.warning("no feature/problem name found for %s", needed_key)

                cache_suffix = f"__{item_name[:100]}" if item_name else ""
                cache_key = f"{needed_key}{cache_suffix}"

                #fetch batch if not cached
                if cache_key not in answers_cache:
                    logger.info("fetching batch for section '%s' (triggered by %s)", section_label, needed_key)
                    try:
                        parsed, raw_json, elapsed = await _call_batch(
                            client, sys_prompt, history, model_class,
                            section_label, section_keys, feature_name=item_name,
                        )
                        #unpack pydantic fields into cache
                        for field_name, field_val in parsed.model_dump().items():
                            answer_key = _FIELD_TO_KEY.get(field_name)
                            if answer_key:
                                ck = f"{answer_key}{cache_suffix}" if item_name and answer_key in (_SUB1_KEYS + _SUB2_KEYS) else answer_key
                                answers_cache[ck] = field_val
                    except Exception as e:
                        logger.error("batch fetch failed for %s: %s", section_label, e)

                #extract answer from cache
                answer_to_send = None
                reasoning = ""
                log_raw = "batch"
                log_elapsed = 0.0

                for _retry in range(3):
                    cached = answers_cache.get(cache_key)
                    if not cached:
                        #refetch
                        try:
                            parsed, _, _ = await _call_batch(
                                client, sys_prompt, history, model_class,
                                section_label, section_keys, feature_name=item_name,
                            )
                            for fn, fv in parsed.model_dump().items():
                                ak = _FIELD_TO_KEY.get(fn)
                                if ak:
                                    ck2 = f"{ak}{cache_suffix}" if item_name and ak in (_SUB1_KEYS + _SUB2_KEYS) else ak
                                    answers_cache[ck2] = fv
                            cached = answers_cache.get(cache_key)
                        except Exception:
                            continue
                        if not cached:
                            continue

                    raw_ans = str(cached.get("answer", "") if isinstance(cached, dict) else cached).strip().replace("**", "")
                    reasoning = cached.get("reasoning", "") if isinstance(cached, dict) else ""

                    if needed_key.startswith("Q"):
                        norm = _normalize_answer(raw_ans, needed_key)
                        if norm and _valid_answer(needed_key, norm):
                            answer_to_send = norm
                            break
                        logger.warning("invalid batch answer for %s: %r → %r, retrying", needed_key, raw_ans, norm)
                        answers_cache.pop(cache_key, None)
                    else:
                        if raw_ans:
                            answer_to_send = raw_ans
                            break
                        answers_cache.pop(cache_key, None)

                #dynamic fallback if batch failed
                if answer_to_send is None:
                    logger.warning("batch exhausted for %s, falling back to dynamic", needed_key)
                    for _dyn_retry in range(2):
                        try:
                            data, raw_json, elapsed = await _call_dynamic(
                                client, sys_prompt, history, clean,
                            )
                        except Exception:
                            continue
                        raw_dyn = str(data.answer).strip().replace("**", "")
                        if needed_key.startswith("Q"):
                            norm_dyn = _normalize_answer(raw_dyn, needed_key)
                            if norm_dyn and _valid_answer(needed_key, norm_dyn):
                                answer_to_send = norm_dyn
                                reasoning = data.reasoning
                                log_raw = raw_json
                                log_elapsed = elapsed
                                break
                        else:
                            if raw_dyn:
                                answer_to_send = raw_dyn
                                reasoning = data.reasoning
                                log_raw = raw_json
                                log_elapsed = elapsed
                                break

                if answer_to_send is None:
                    raise RuntimeError(f"failed to get valid answer for {needed_key}")

                #log and send
                logged_q = clean
                if pending_conclusion and pending_conclusion not in clean:
                    logged_q = f"{pending_conclusion}\n\n{clean}"
                pending_conclusion = ""

                qa_log.append({"question": clean, "answer": answer_to_send, "reasoning": reasoning})
                turn_logs.append(_log_entry(len(turn_logs) + 1, logged_q, answer_to_send,
                                            reasoning, 0, log_raw, log_elapsed, metadata))

                logger.info("  → batch answer for %s: %s", needed_key, answer_to_send)
                await _send(answer_to_send)
                buffer = []

        except StopIteration:
            pass
        except Exception as e:
            logger.error("controller exception: %s", e)
            traceback.print_exc()
        finally:
            if proc.returncode is None:
                proc.terminate()
            logger.info("ui.py process finished")

            #ensure final adm output is captured
            if not full_responses_log.get("Final_ADM_Output"):
                outcome = _extract_case_outcome(full_output)
                full_responses_log["Final_ADM_Output"] = outcome or full_output[-4000:].strip()

            # ── final verdict ────────────────────────────────────────

            #build comprehensive context for verdict
            verdict_msgs = []

            #include final adm output
            fao = str(full_responses_log.get("Final_ADM_Output", "")).strip()
            if fao:
                verdict_msgs.append({"role": "user", "content": f"Final ADM Output Summary:\n{fao}"})
                verdict_msgs.append({"role": "assistant", "content": "Final ADM outcome captured."})

            #include sub-adm conclusions
            subs = full_responses_log.get("Sub_ADM_Conclusions", [])
            if subs:
                packed = "\n\n---\n\n".join(str(b).strip()[:1200] for b in subs[-4:] if str(b).strip())
                if packed:
                    verdict_msgs.append({"role": "user", "content": f"Sub-ADM Conclusion Summaries:\n{packed}"})
                    verdict_msgs.append({"role": "assistant", "content": "Sub-ADM conclusions noted."})

            #add last 2 qa pairs
            verdict_msgs.extend(_last_2_qa(qa_log))

            #build log payload
            history_text = "\n\n".join(
                f"[{m.get('role', '?').upper()}]\n{m.get('content', '')}"
                for m in verdict_msgs if isinstance(m, dict)
            )
            verdict_question_log = (
                "FINAL VERDICT\n\n=== ADM CONTEXT SENT TO FINAL LLM ===\n"
                f"{history_text or '[No context]'}"
            )

            final_verdict = "ERROR"
            try:
                data, raw_json, elapsed = await _call_final_verdict(
                    client, sys_prompt, verdict_msgs, case_name, train,
                )
                turn_logs.append(_log_entry(
                    len(turn_logs) + 1, verdict_question_log,
                    str(data.answer), data.reasoning,
                    data.confidence_score, raw_json, elapsed, metadata,
                ))
                final_verdict = str(data.answer)
            except Exception as e:
                logger.error("final verdict failed: %s", e)

            elapsed_total = time.time() - t_start
            print(f"Case {case_name} (run {run_id}) done. Verdict: {final_verdict}. Time: {elapsed_total:.2f}s")

            with open(log_path, "w") as f:
                json.dump(turn_logs, f, indent=4)
            logger.info("saved log to %s", log_path)
            CURRENT_CASE_REF.reset(case_token)

            return final_verdict

# ── experiment runner ────────────────────────────────────────────────────────

async def _run_experiment(data_path: str, dataset: str, config: int, mode: str,
                          num_runs: int, client):
    if not os.path.exists(data_path):
        print(f"error: data path {data_path} does not exist")
        return

    cases = sorted(d for d in os.listdir(data_path) if os.path.isdir(os.path.join(data_path, d)))
    print(f"found {len(cases)} cases. starting {num_runs} run(s)...")

    all_results = {}
    for run in range(1, num_runs + 1):
        print(f"\n=== RUN {run}/{num_runs} ===")
        meta = {"dataset": dataset, "mode": mode, "config": config, "run_id": run, "model": CURRENT_CONFIG["id"]}
        tasks = []
        case_names = []

        for case in cases:
            ctx = _load_context(data_path, case, dataset, config)
            if not ctx:
                print(f"skipping {case} (missing context)")
                continue
            case_names.append(case)
            tasks.append(_run_case(client, case, ctx, run, meta, train=(mode == "train")))

        results = await asyncio.gather(*tasks)
        all_results[f"run_{run}"] = dict(zip(case_names, results))
        await asyncio.sleep(1)

        json_file = f"{BASE_CASE_DIR}/results_{dataset}_{mode}_config{config}_{ADM_CONFIG}_{ADM_INITIAL}.json"
        try:
            with open(json_file, "w") as f:
                json.dump(all_results, f, indent=4)
            print(f"run {run} saved to {json_file}")
        except Exception as e:
            logger.error("failed to save results: %s", e)

    print(f"\nall {num_runs} run(s) complete.")

# ── main ─────────────────────────────────────────────────────────────────────

async def _async_main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="gpt",
                        choices=list(MODELS.keys()),
                        help="model key from MODELS dict (vllm or or-* for openrouter)")
    parser.add_argument("--gpu", type=str, default="gpu31")
    parser.add_argument("--port", type=str, default="8000")
    parser.add_argument("--dataset", type=str, choices=["comvik", "main"], required=True)
    parser.add_argument("--data_path", type=str, default="../Data/VALIDATION")
    parser.add_argument("--exp_config", type=int, required=True)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--mode", type=str, default="tool", choices=["tool", "baseline", "ensemble", "train"])
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--raw_data", type=str, default="../Data/Inv_Step_Sampled_Valid.pkl")
    parser.add_argument("--base_case_dir", type=str, default="../Outputs/Valid_Cases")
    parser.add_argument("--adm_config", type=str, choices=["both", "none", "sub_adm_1", "sub_adm_2"], default="both")
    parser.add_argument("--adm_initial", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        print("--- debug mode ---")

    global ADM_CONFIG, ADM_INITIAL, CURRENT_CONFIG, BASE_CASE_DIR, RAW_DATA, LLM_TEMPERATURE
    ADM_CONFIG = args.adm_config
    ADM_INITIAL = bool(args.adm_initial)
    CURRENT_CONFIG = MODELS.get(args.model, MODELS["gpt"]).copy()
    BASE_CASE_DIR = args.base_case_dir
    LLM_TEMPERATURE = args.temperature

    try:
        RAW_DATA = pd.read_pickle(args.raw_data)
    except Exception as e:
        logger.warning("could not load raw data: %s", e)
        RAW_DATA = pd.DataFrame()

    api_base = f"http://{args.gpu}.barkla2.liv.alces.network:{args.port}/v1"
    logger.info("connecting to vllm at %s", api_base)
    client = AsyncOpenAI(base_url=api_base, api_key="EMPTY")

    await _run_experiment(args.data_path, args.dataset, args.exp_config, args.mode, args.runs, client)


if __name__ == "__main__":
    asyncio.run(_async_main())
