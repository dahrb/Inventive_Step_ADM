"""
Batched Hybrid ADM System with LLMs driving the reasoning

Last Updated: 06.04.26

Status: In Progress

Test Coverage: Manual Tests

Version History:
v_1: initial version
v_2: added batching
v_3: added baseline + ensemble approach

To Do:
- check ensemble works
- check baseline works 
- verify all 3 llms work properly over train set on each mode
- manual check
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
from inventive_step_ADM import adm_initial, adm_main, load_questions, set_questions

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
    # id              — model name sent to vLLM
    # guided_json     — use response_format json_schema for structured output
    # reasoning_effort — send reasoning_effort="medium" (OpenAI-style thinking budget)
    # thinking        — model has internal chain-of-thought; do NOT send enable_thinking=False
    # seed            — supports seed parameter
    # max_tokens      — safe max_tokens for calls
    "gpt": {
        "id": "gpt-oss-120b",
        "guided_json": True, "reasoning_effort": True, "thinking": True,
        "seed": True, "max_tokens": 8000,
    },
    "llama": {
        "id": "Llama-3.3-70B-Instruct-FP8",
        "guided_json": True, "reasoning_effort": False, "thinking": False,
        "seed": True, "max_tokens": 1200,
    },
    "qwen": {
        "id": "Qwen-3-80B",
        "guided_json": False, "reasoning_effort": False, "thinking": False,
        "seed": True, "max_tokens": 8000,
    },
}

# ── ensemble personas────────────────────────

ENSEMBLE_PERSONA_A = (
    "You are a sceptical patent examiner who tends to find that the skilled person "
    "WOULD have arrived at the claimed invention without inventive effort. "
    "You look hard for combinations in the prior art and downplay unexpected effects."
)

ENSEMBLE_PERSONA_B = (
    "You are a pro-patentee advocate who looks for genuine technical contributions and "
    "unexpected advantages that the skilled person would NOT have foreseen. "
    "You give the benefit of the doubt to the applicant where the evidence allows."
)

# ── LLM helpers ──────────────────────────────────────────────────────────────

# Context window limits per model (tokens). Used to clamp max_tokens dynamically.
_CONTEXT_WINDOW = {
    "gpt-oss-120b":               131072,
    "Llama-3.3-70B-Instruct-FP8": 32000,
    "Qwen-3-80B":                 32000,
}
# Minimum output tokens we always want to guarantee
_MIN_OUTPUT = 200

# Maximum tokens allowed for the CPA document in baseline context.
# Prevents oversized prior-art documents from exceeding model context windows.
# Qwen-3-80B (Instruct) has a 32k context; 10k tokens for the CPA is a safe
# ceiling leaving room for instructions and output (~40k chars).
CPA_MAX_TOKENS = 10_000


def _estimate_tokens(messages: list[dict]) -> int:
    return sum(len(str(m.get("content", ""))) for m in messages) // 4



def _build_request(messages: list[dict], schema=None, max_tokens: int | None = None) -> dict:
    """Build kwargs for client.chat.completions.create based on current model config.

    For models with tight context windows (e.g. Qwen-3-80B at 8 000 tokens) the
    requested max_tokens is clamped so that input_tokens + max_tokens never
    exceeds the window.  Token count is estimated at 4 chars per token.
    """
    cfg = CURRENT_CONFIG or {}
    desired = max_tokens or cfg.get("max_tokens", 8000)

    # Dynamically clamp to fit the context window
    model_id  = cfg.get("id", "")
    ctx_limit = _CONTEXT_WINDOW.get(model_id, 131072)

    req_messages = messages
    prompt_tokens_est = _estimate_tokens(req_messages)
    available = max(_MIN_OUTPUT, ctx_limit - prompt_tokens_est - 64)  # 64-token safety margin
    capped = min(desired, available)

    kwargs: dict = {
        "model": model_id,
        "messages": req_messages,
        "temperature": LLM_TEMPERATURE,
        "max_tokens": capped,
        "top_p": 1,
    }
    if cfg.get("seed"):
        kwargs["seed"] = 42
    if cfg.get("reasoning_effort"):
        kwargs["reasoning_effort"] = "medium"
    if schema is not None and cfg.get("guided_json"):
        # Use vLLM's structured-output via response_format (strict JSON schema).
        # This is the correct API; extra_body guided_json is a legacy alias that
        # some model versions ignore, leading to free-form schema invention.
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "strict": True,
                "schema": schema,
            },
        }
    # Disable thinking mode explicitly for Instruct models (Llama, Qwen-3-80B).
    # Only GPT has thinking=True and must not receive this flag.
    if not cfg.get("thinking"):
        kwargs.setdefault("extra_body", {})["chat_template_kwargs"] = {"enable_thinking": False}
    return kwargs


def _get_content(resp) -> str:
    """Extract text from an LLM response — .content only.

    For thinking models (e.g. GPT) the structured answer is always in .content
    once the model finishes its chain-of-thought.  We do NOT fall back to
    reasoning_content: an empty .content means the model hit its token limit
    mid-thinking and never emitted a final answer — the caller's retry logic
    should handle that.
    """
    return (resp.choices[0].message.content or "").strip()


def _parse_json(raw: str) -> dict:
    """Simple JSON parse: find the first { and try json.loads from there.

    Like the old code: json.loads -> .get("answer"). No brace completion,
    no multi-stage extraction. If it fails, return empty dict.
    """
    if not raw:
        return {}
    start = raw.find("{")
    if start == -1:
        return {}
    # find the matching closing brace
    depth, in_str, esc = 0, False, False
    for i in range(start, len(raw)):
        c = raw[i]
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
                try:
                    return json.loads(raw[start:i + 1])
                except json.JSONDecodeError:
                    return {}
    # unbalanced — try anyway
    try:
        return json.loads(raw[start:])
    except json.JSONDecodeError:
        return {}

# ── question introspection ───────────────────────────────────────────────────

def _extract_questions(adm_instance) -> dict:
    """build {lowercase_key: formatted_question_text} from an adm instance."""
    qs = {}

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

    qs["closest prior art description"] = "[Q] Please describe the candidate for the closest prior art:"

    if not hasattr(adm_instance, "questionOrder"):
        return qs

    for item_name in adm_instance.questionOrder:
        if hasattr(adm_instance, "information_questions") and item_name in adm_instance.information_questions:
            continue

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

        elif hasattr(adm_instance, "nodes") and item_name in adm_instance.nodes:
            node = adm_instance.nodes[item_name]

            if hasattr(node, "sub_adm") and callable(node.sub_adm):
                try:
                    sample = node.sub_adm("sample_item")
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
                    if hasattr(sample, "nodes"):
                        for sn, snode in sample.nodes.items():
                            if hasattr(snode, "question") and snode.question:
                                m3 = re.search(r"\[(Q\d+)\]", snode.question)
                                tag3 = m3.group(1).lower() if m3 else sn.lower()
                                fmt3 = snode.question + "\n\nAnswer 'yes' or 'no' only (y/n):"
                                qs[tag3] = fmt3.strip()
                except Exception as e:
                    logger.warning("could not extract sub-adm questions for %s: %s", item_name, e)

            elif hasattr(node, "question") and node.question:
                m4 = re.search(r"\[(Q\d+)\]", node.question)
                tag4 = m4.group(1).lower() if m4 else item_name.lower()
                fmt4 = node.question + "\nAnswer 'yes' or 'no' only (y/n):"
                qs[tag4] = fmt4.strip()

    return qs

# pre-extract all question dictionaries at module load
def _build_question_caches():
    """(Re-)build the module-level question caches from the current questions registry.

    Called once at import time, and again after --questions_file is loaded so
    that batched prompts pick up the new question text.
    """
    global INITIAL_ADM_QUESTIONS, MAIN_ADM_QUESTIONS, MAIN_ADM_NO_SUB_1_QUESTIONS
    global MAIN_ADM_NO_SUB_2_QUESTIONS, MAIN_ADM_NO_SUB_BOTH_QUESTIONS, ALL_EXACT_QUESTIONS
    INITIAL_ADM_QUESTIONS         = _extract_questions(adm_initial())
    MAIN_ADM_QUESTIONS            = _extract_questions(adm_main(True, True))
    MAIN_ADM_NO_SUB_1_QUESTIONS   = _extract_questions(adm_main(False, True))
    MAIN_ADM_NO_SUB_2_QUESTIONS   = _extract_questions(adm_main(True, False))
    MAIN_ADM_NO_SUB_BOTH_QUESTIONS = _extract_questions(adm_main(False, False))
    ALL_EXACT_QUESTIONS = {**INITIAL_ADM_QUESTIONS, **MAIN_ADM_QUESTIONS}

INITIAL_ADM_QUESTIONS = {}
MAIN_ADM_QUESTIONS = {}
MAIN_ADM_NO_SUB_1_QUESTIONS = {}
MAIN_ADM_NO_SUB_2_QUESTIONS = {}
MAIN_ADM_NO_SUB_BOTH_QUESTIONS = {}
ALL_EXACT_QUESTIONS = {}
_build_question_caches()


def _question_text(key: str) -> str:
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

    # JSON rescue: if the raw string looks like a JSON object (possibly malformed),
    # try to extract "answer" field via regex before doing anything else.
    # This handles cases where _parse_json fails on malformed JSON (e.g. trailing '"').
    if "{" in cleaned:
        m = re.search(r'"answer"\s*:\s*"([^"]*)"', cleaned, re.IGNORECASE)
        if m:
            json_ans = m.group(1).strip().lower().replace("**", "")
            if json_ans in ("y", "yes"):
                return "y"
            if json_ans in ("n", "no"):
                return "n"
            if json_ans in allowed if allowed else re.fullmatch(r"\d+", json_ans):
                return json_ans

    nums = re.findall(r"\d+", cleaned)
    if nums:
        if allowed:
            for num in nums:
                if num in allowed:
                    return num
        if not allowed:
            return nums[0]

    for word, digit in {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5"}.items():
        if re.search(rf"\b{word}\b", low):
            if not allowed or digit in allowed:
                return digit

    omap = _option_text_map(key)
    if omap:
        norm_raw = re.sub(r"\s+", " ", low).strip(" .,:;!?\"'`")
        for num, opt_text in omap.items():
            norm_opt = re.sub(r"\s+", " ", opt_text.lower()).strip(" .,:;!?\"'`")
            if not norm_opt:
                continue
            if norm_opt in norm_raw or (len(norm_raw) >= 8 and norm_raw in norm_opt):
                return num

    if _expects_yes_no(key):
        ym = re.search(r"\b(yes|no)\b", low)
        if ym:
            return "y" if ym.group(1) == "yes" else "n"

    logger.warning("cannot normalize answer for %s: %r", key, raw)
    return None


def _valid_answer(key: str, norm: str) -> bool:
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
_SECONDARY_KEYS = [f"Q{i}" for i in range(40, 60)]

_SECTIONS = [
    (_INITIAL_KEYS,    InitialADM_Batch,          "Initial Preconditions"),
    (_SUB1_KEYS,       SubADM1_Batch,             "Technical Character"),
    (_INTER_KEYS,      MainADM_Inter_Batch,       "Synergy & Interaction"),
    (_SUB2_KEYS,       SubADM2_Batch,             "Problem-Solution Approach"),
    (_NO_SUB1_KEYS,    MainADM_No_Sub_1,          "Technical Factors (No Sub-ADM 1)"),
    (_NO_SUB2_KEYS,    MainADM_No_Sub_2,          "Obviousness Factors (No Sub-ADM 2)"),
    (_SECONDARY_KEYS,  SecondaryIndicators_Batch,  "Secondary Indicators"),
]

def _section_for_key(key: str):
    """return (model_class, label, keys_list) or None."""
    for keys, model_class, label in _SECTIONS:
        if key in keys:
            return model_class, label, keys
    return None


_FIELD_TO_KEY = {
    "invention_title": "invention title", "invention_description": "description",
    "technical_field": "technical field", "relevant_prior_art": "prior art",
    "common_general_knowledge": "common general knowledge",
    "closest_prior_art_description": "closest prior art description",
    "q1_similar_purpose": "Q1", "q2_similar_effects": "Q2", "q3_same_field": "Q3",
    "q4_contested": "Q4", "q5_cgk_evidence": "Q5", "q6_skilled_in": "Q6",
    "q7_average": "Q7", "q8_aware": "Q8", "q9_access": "Q9", "q10_skilled_person": "Q10",
    "q11_cpa": "Q11", "q12_minmod": "Q12", "q13_combo_attempt": "Q13",
    "q14_combined": "Q14", "q15_combo_motive": "Q15", "q16_basis": "Q16",
    "q17_tech_cont": "Q17", "q19_dist_feat": "Q19", "q20_circumvent": "Q20",
    "q21_tech_adapt": "Q21", "q22_intended": "Q22", "q23_tech_use": "Q23",
    "q24_specific_purpose": "Q24", "q25_func_limited": "Q25", "q26_unexpected": "Q26",
    "q27_precise": "Q27", "q28_one_way": "Q28", "q29_credible": "Q29",
    "q30_claim_contains": "Q30", "q31_suff_dis": "Q31",
    "q32_synergy": "Q32", "q33_func_int": "Q33",
    "q34_encompassed": "Q34", "q36_scope": "Q36", "q38_hindsight": "Q38", "q39_would": "Q39",
    "q100_dist_feat": "Q100", "q101_tech_cont": "Q101", "q102_unexpected": "Q102",
    "q103_precise": "Q103", "q104_one_way": "Q104", "q105_credible": "Q105",
    "q106_claimcontains": "Q106", "q107_suff_dis": "Q107",
    "obj_t_problem": "obj_t_problem", "q200_encompassed": "Q200", "q201_scope": "Q201",
    "q202_hindsight": "Q202", "q203_would": "Q203",
    "q40_disadvantage": "Q40", "q41_foresee": "Q41",
    "q42_advantage": "Q42", "q43_biotech": "Q43", "q44_antibody": "Q44",
    "q45_pred_results": "Q45", "q46_reasonable": "Q46", "q47_known_tech": "Q47",
    "q48_overcome": "Q48", "q49_gap_filled": "Q49", "q50_well_known": "Q50",
    "q51_known_prop": "Q51", "q52_analog_use": "Q52", "q53_known_device": "Q53",
    "q54_obvs_combo": "Q54", "q55_analog_sub": "Q55", "q56_equal_alt": "Q56",
    "q57_normal_design": "Q57", "q58_simple_extra": "Q58", "q59_chem_select": "Q59",
}

# ── prompts ──────────────────────────────────────────────────────────────────

def _system_prompt(context: str, case_name: str, train: bool = False) -> str:
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


def _last_2_qa(qa_log: list[dict]) -> list[dict]:
    msgs = []
    for entry in qa_log[-2:]:
        msgs.append({"role": "user", "content": entry["question"]})
        msgs.append({"role": "assistant", "content": json.dumps({
            "answer": entry["answer"],
            "reasoning": entry.get("reasoning", ""),
        })})
    return msgs

# ── LLM calls ────────────────────────────────────────────────────────────────
# Simple approach (like old code):
#   1. Build messages  2. Call API (with retries)  3. json.loads → .get("answer")

MAX_RETRIES = 5
BASE_BACKOFF = 2
ENSEMBLE_TEMP = 0.7  # temperature for the two opinion calls


async def _get_ensemble_opinions(
        client, sys_prompt: str, history: list[dict],
        model_class, section_label: str, keys: list[str],
        q_text: str, ctx: str, guided_schema, task_suffix: str) -> list[dict]:
    """Fire two parallel full-batch calls — one per persona — and return their opinions.

    Each call gets the same batch schema (model_class / all keys) as the main batch
    call, but with the persona injected as a prefix to the system prompt and
    ENSEMBLE_TEMP for diversity.  Returns a list of two dicts:
      [{"persona": ..., "answers": {answer_key: {"answer": ..., "reasoning": ...}}}, ...]
    Failures are swallowed so the main batch call degrades gracefully.
    """
    async def _one_opinion(persona_label: str, persona_text: str) -> dict:
        persona_sys = f"{persona_text}\n\n{sys_prompt}"
        messages = ([{"role": "system", "content": persona_sys}]
                    + history
                    + [{"role": "user", "content": f"{q_text}{ctx}{task_suffix}"}])

        req = _build_request(messages, schema=guided_schema)
        req["temperature"] = ENSEMBLE_TEMP
        req.pop("seed", None)  # diversity — no fixed seed

        try:
            resp = await client.chat.completions.create(**req)
            raw = _get_content(resp)
            # parse with pydantic, fall back to plain json
            answers = {}
            try:
                json_start = raw.find("{")
                parsed = model_class.model_validate_json(raw if json_start <= 0 else raw[json_start:])
                for field_name, field_val in parsed.model_dump().items():
                    answer_key = _FIELD_TO_KEY.get(field_name)
                    if answer_key:
                        answers[answer_key] = field_val
            except Exception:
                data = _parse_json(raw)
                if data:
                    for field_name, field_val in data.items():
                        answer_key = _FIELD_TO_KEY.get(field_name)
                        if answer_key and isinstance(field_val, dict):
                            answers[answer_key] = field_val
            logger.info("ensemble opinion '%s' parsed %d answers", persona_label, len(answers))
            return {"persona": persona_label, "answers": answers}
        except Exception as e:
            logger.warning("ensemble opinion '%s' failed: %s", persona_label, e)
            return {"persona": persona_label, "answers": {}}

    opinion_a, opinion_b = await asyncio.gather(
        _one_opinion("Persona A (sceptical examiner)", ENSEMBLE_PERSONA_A),
        _one_opinion("Persona B (pro-patentee advocate)", ENSEMBLE_PERSONA_B),
    )
    return [opinion_a, opinion_b]


async def _call_batch(client, sys_prompt: str, history: list[dict],
                      model_class, section_label: str, keys: list[str],
                      feature_name: str = None,
                      ensemble: bool = False) -> tuple[dict, list]:
    """Call LLM once with a batched structured schema.

    Returns (results, messages) where results is
    {answer_key: {"answer": ..., "reasoning": ...}} for whatever parsed
    successfully, and messages is the full prompt list sent to the LLM.
    Missing/broken answers are simply absent — the caller falls back to
    dynamic for those when the question is actually asked.

    ensemble: if True, fires two parallel persona-batch calls first and injects
    their full per-question answers into the main batch prompt.
    """
    # pick question dictionary
    if "No Sub-ADM 1" in section_label and "No Sub-ADM 2" not in section_label:
        qdict = MAIN_ADM_NO_SUB_1_QUESTIONS
    elif "No Sub-ADM 2" in section_label and "No Sub-ADM 1" not in section_label:
        qdict = MAIN_ADM_NO_SUB_2_QUESTIONS
    elif "No Sub-ADM 1" in section_label and "No Sub-ADM 2" in section_label:
        qdict = MAIN_ADM_NO_SUB_BOTH_QUESTIONS
    else:
        qdict = ALL_EXACT_QUESTIONS

    # build question text
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

    # schema: guided_json or prompt-embedded
    cfg = CURRENT_CONFIG or {}
    schema = model_class.model_json_schema()
    if not cfg.get("guided_json"):
        schema_str = json.dumps(schema, indent=2)
        q_text += (
            f"\n\nTASK: Fill out the structured JSON schema completely.\n"
            f"Return ONLY a single valid JSON object matching this schema (no prose, no markdown fences):\n"
            f"```json\n{schema_str}\n```"
        )
        task_suffix = ""
        guided_schema = None
    else:
        task_suffix = "\nTASK: Fill out the structured JSON schema completely."
        guided_schema = schema

    # append ensemble opinions if provided
    # Each opinion contains a full batch of answers (one per question key),
    # formatted so the main batch call can see what each persona answered.
    opinions_block = ""
    if ensemble:
        logger.info("generating ensemble opinions for '%s'", section_label)
        opinions = await _get_ensemble_opinions(
            client, sys_prompt, history,
            model_class, section_label, keys,
            q_text, ctx, guided_schema, task_suffix,
        )
        opinions_block = "\n\n=== ADDITIONAL EXPERT OPINIONS ===\n"
        for op in opinions:
            persona = op.get("persona", "Opinion")
            answers = op.get("answers", {})
            opinions_block += f"\n[{persona}]\n"
            for k in keys:
                ans_val = answers.get(k, {})
                ans_text = ans_val.get("answer", "(no answer)") if isinstance(ans_val, dict) else str(ans_val)
                reas_text = ans_val.get("reasoning", "") if isinstance(ans_val, dict) else ""
                opinions_block += f"  {k}: {ans_text}"
                if reas_text:
                    # truncate reasoning to keep context size manageable
                    opinions_block += f" — {reas_text[:200]}"
                opinions_block += "\n"
        opinions_block += (
            "\n=== END OPINIONS ===\n"
            "Consider the above opinions carefully but use your own independent judgment "
            "when filling the schema below.\n"
        )

    messages = [{"role": "system", "content": sys_prompt}] + history
    messages.append({"role": "user", "content": f"{q_text}{ctx}{opinions_block}{task_suffix}"})

    # call with retries
    for attempt in range(MAX_RETRIES):
        try:
            req = _build_request(messages, schema=guided_schema)
            resp = await client.chat.completions.create(**req)
            raw = _get_content(resp)
            if not raw:
                raise ValueError("empty response")
            break
        except Exception as e:
            logger.warning("batch %s attempt %d failed: %s", section_label, attempt + 1, e)
            if attempt == MAX_RETRIES - 1:
                logger.error("batch %s failed after %d attempts", section_label, MAX_RETRIES)
                return {}, messages
            await asyncio.sleep(BASE_BACKOFF * (2 ** attempt))

    # parse: try pydantic, fall back to plain json.loads
    results = {}
    try:
        json_start = raw.find("{")
        parsed = model_class.model_validate_json(raw if json_start <= 0 else raw[json_start:])
        for field_name, field_val in parsed.model_dump().items():
            answer_key = _FIELD_TO_KEY.get(field_name)
            if answer_key:
                results[answer_key] = field_val
    except Exception:
        data = _parse_json(raw)
        if data:
            for field_name, field_val in data.items():
                answer_key = _FIELD_TO_KEY.get(field_name)
                if answer_key and isinstance(field_val, dict):
                    results[answer_key] = field_val

    logger.info("batch '%s' returned %d/%d answers", section_label, len(results), len(keys))
    return results, messages


async def _call_dynamic(client, sys_prompt: str, history: list[dict],
                        question_text: str) -> tuple[str, str, list]:
    """Call LLM with a single question. Returns (answer, reasoning, messages).

    Like the old consult_llm: json.loads → .get("answer"). If parsing fails,
    raw text is the answer.  The third return value is the full messages list
    sent to the LLM (system prompt + history + question) for logging.
    """
    cfg = CURRENT_CONFIG or {}
    schema = QuestionResponse.model_json_schema()

    if cfg.get("guided_json"):
        instruction = (
            "\n\nIMPORTANT OUTPUT FORMAT: Return exactly one JSON object: "
            '{"answer": "...", "reasoning": "..."}.'
        )
        guided_schema = schema
    else:
        instruction = (
            "\n\nIMPORTANT OUTPUT FORMAT: Return ONLY a single JSON object — no prose, no markdown fences:\n"
            '{"answer": "<your answer>", "reasoning": "<your step-by-step reasoning>"}'
        )
        guided_schema = None

    messages = [{"role": "system", "content": sys_prompt}] + history
    messages.append({"role": "user", "content": question_text + instruction})

    for attempt in range(MAX_RETRIES):
        try:
            req = _build_request(messages, schema=guided_schema)
            resp = await client.chat.completions.create(**req)
            raw = _get_content(resp)
            if not raw:
                raise ValueError("empty response")

            # simple parse like old code
            parsed = _parse_json(raw)
            if parsed and parsed.get("answer") is not None:
                answer = str(parsed.get("answer")).strip()
            else:
                # _parse_json failed (e.g. malformed JSON with stray quotes);
                # fall back to regex extraction of "answer" field
                m = re.search(r'"answer"\s*:\s*"([^"]*)"', raw, re.IGNORECASE)
                answer = m.group(1).strip() if m else raw
            reasoning = parsed.get("reasoning", raw) if parsed else raw
            return answer, reasoning, messages

        except Exception as e:
            logger.warning("dynamic attempt %d failed: %s", attempt + 1, e)
            if attempt == MAX_RETRIES - 1:
                raise
            await asyncio.sleep(BASE_BACKOFF * (2 ** attempt))


async def _call_final_verdict(client, sys_prompt: str, adm_context: list[dict],
                              case_name: str, train: bool) -> tuple[str, str, int, list]:
    """Get the final inventive step verdict. Returns (answer, reasoning, confidence_score, messages)."""
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
        sp = sys_prompt + "\n\nIMPORTANT: Your response MUST be a single valid JSON object."
        guided_schema = schema
    else:
        sp = (
            sys_prompt
            + "\n\nIMPORTANT: Return ONLY a single JSON object — no prose, no markdown fences:\n"
            + '{"answer": "Yes or No", "reasoning": "...", "confidence_score": <0-100>}'
        )
        guided_schema = None

    messages = [{"role": "system", "content": sp}] + adm_context
    messages.append({"role": "user", "content": question})

    # Trim context if too large. Qwen-3-80B (Instruct, 32k context) gets a
    # tighter threshold than 128k models to stay safely within its window.
    trim_threshold = 8000 if cfg.get("id", "") == "Qwen-3-80B" else 20000
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    if total_chars // 4 > trim_threshold:
        logger.warning("final verdict context too large (%d est tokens, threshold %d), trimming",
                       total_chars // 4, trim_threshold)
        kept = [messages[0]]
        for m in messages[1:-1]:
            c = str(m.get("content", ""))
            if "Final ADM Output" in c or "Sub-ADM Conclusion" in c:
                kept.append(m)
        kept.extend(messages[-3:])
        messages = kept

    for attempt in range(MAX_RETRIES):
        try:
            req = _build_request(messages, schema=guided_schema)
            resp = await client.chat.completions.create(**req)
            raw = _get_content(resp)
            if not raw:
                raise ValueError("empty response")

            parsed = _parse_json(raw)
            answer = str(parsed.get("answer", "")).strip()
            reasoning = str(parsed.get("reasoning", raw))
            confidence = int(parsed.get("confidence_score", 50))

            # must find yes/no
            if re.search(r"\b(yes|no)\b", answer, re.IGNORECASE):
                return answer, reasoning, confidence, messages

            # regex recovery from raw
            am = re.search(r"\b(Yes|No)\b", raw, re.IGNORECASE)
            if am:
                return am.group(1).capitalize(), reasoning, confidence, messages

            raise ValueError(f"no yes/no found in verdict: {answer[:100]}")

        except Exception as e:
            logger.warning("final verdict attempt %d failed: %s", attempt + 1, e)
            if attempt == MAX_RETRIES - 1:
                raise
            await asyncio.sleep(BASE_BACKOFF * (2 ** attempt))

# ── ui text helpers ──────────────────────────────────────────────────────────

def _strip_decorators(text: str) -> str:
    lines = text.splitlines()
    out = [l for l in lines if not (len(l.strip()) >= 3 and l.strip()[0] in "=-_~*" and len(set(l.strip())) == 1)]
    return "\n".join(out).strip()


def _extract_case_outcome(full_output: str) -> str:
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
    fm = re.search(r"Feature:\s*(.+?)(?:\n|$)", text)
    if fm:
        return fm.group(1).strip()
    pm = re.search(r"Problem name:\s*(.+?)(?:\n|$)", text)
    if pm:
        return pm.group(1).strip()
    return None

# ── data loading ─────────────────────────────────────────────────────────────

def _read_cpa(path: str) -> str:
    """Read a CPA file and truncate to CPA_MAX_TOKENS if needed."""
    text = open(path).read()
    max_chars = CPA_MAX_TOKENS * 4
    if len(text) > max_chars:
        text = text[:max_chars]
        logger.warning("CPA truncated to %d tokens for %s", CPA_MAX_TOKENS, path)
    return text


def _load_context(data_path: str, case_name: str, dataset: str, config: int) -> str:
    path = os.path.join(data_path, case_name)
    parts = []

    if dataset == "comvik":
        cpa = os.path.join(path, "CPA.txt")
        if os.path.exists(cpa):
            parts.append(f"--- CLOSEST PRIOR ART INFORMATION ---\n{_read_cpa(cpa)}")
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
                parts.append(f"--- CLOSEST PRIOR ART DOCUMENT/S ---\n{_read_cpa(cpa)}")
        elif config == 3:
            if os.path.exists(appeal):
                parts.append(f"--- SUMMARY OF FACTS FROM THE APPEAL ---\n{open(appeal).read()}")
            if os.path.exists(claims):
                parts.append(f"--- PATENT APPLICATION CLAIMS ---\n{open(claims).read()}")
            if os.path.exists(cpa):
                parts.append(f"--- CLOSEST PRIOR ART DOCUMENT/S ---\n{_read_cpa(cpa)}")

    try:
        year = str(RAW_DATA.loc[RAW_DATA["Reference"] == case_name, "Year"].iloc[0]) if RAW_DATA is not None and not RAW_DATA.empty else "UNKNOWN"
    except Exception:
        year = "UNKNOWN"
    parts.append(f"--- COMMON KNOWLEDGE DATE CUTOFF ---\n{year}")
    return "\n\n".join(parts)

# ── baseline runner ─────────────────────────────────────────────────────────

async def _run_baseline_case(client, case_name: str, context_text: str, run_id: int,
                              metadata: dict, train: bool = False) -> str:
    """Single-shot baseline: one prompt → yes/no verdict, no UI.py subprocess.

    Mirrors the old run_baseline_session from hybrid_patent_system.py.
    Saves a one-entry log.json in {BASE_CASE_DIR}/{case}/{run_N}/config_X/baseline/.
    If train=True, injects Decision Reasons + Order as a system message (oracle guidance).
    """
    async with REQUEST_SEMAPHORE:
        case_token = CURRENT_CASE_REF.set(case_name)
        t_start = time.time()
        config_num = metadata.get("config", "X")

        log_dir = os.path.join(BASE_CASE_DIR, case_name, f"run_{run_id}",
                               f"config_{config_num}", "baseline")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "log.json")
        if os.path.exists(log_path):
            os.remove(log_path)

        cfg = CURRENT_CONFIG or {}
        schema = FinalVerdictResponse.model_json_schema()

        if cfg.get("guided_json"):
            fmt_instruction = "\n\nIMPORTANT: Return a single valid JSON object matching the schema."
            guided_schema = schema
        else:
            fmt_instruction = (
                "\n\nIMPORTANT: Return ONLY a single JSON object — no prose, no markdown fences:\n"
                + '{"answer": "Yes or No", "reasoning": "...", "confidence_score": <0-100>}'
            )
            guided_schema = None

        # ── build oracle context if in train mode ──────────────────────────
        reasons, decision = "", ""
        if train and RAW_DATA is not None and not RAW_DATA.empty:
            try:
                reasons = str(RAW_DATA.loc[RAW_DATA["Reference"] == case_name, "Decision Reasons"].iloc[0])
                decision = str(RAW_DATA.loc[RAW_DATA["Reference"] == case_name, "Order"].iloc[0])
            except Exception:
                reasons, decision = "", ""

        if train:
            sys_content = (
                "You are objectively assessing Inventive Step for the European Patent Office (EPO). "
                "These cases are appeals against the examining boards' original decisions.\n"
                "Use the data provided. Do not rely on outside knowledge, but you may make reasonable "
                "assumptions about common general knowledge prior to the cut-off date given.\n\n"
                f"=== CASE DATA ===\n{context_text}\n=== END CASE DATA ===\n\n"
                f"=== REASONS FOR DECISION ===\n{reasons}\n=== END REASONS FOR DECISION ===\n\n"
                f"=== DECISION ===\n{decision}\n=== END DECISION ===\n\n"
                "INSTRUCTIONS:\n"
                "1. Provide a step-by-step reasoning trace with explicit reference to the case data as to why you gave your answer.\n"
                "2. Conclude with a final 'Yes' (inventive step present) or 'No' answer.\n"
                "3. Provide a confidence score 0-100.\n"
                "4. Follow the reasoning from the 'reasons for decision' as closely as possible.\n"
                "5. You MUST try and follow the actual decision of the case as closely as possible."
                + fmt_instruction
            )
            prompt = "Determine whether the patent fulfils the inventive step criteria." + fmt_instruction
            messages = [
                {"role": "system", "content": sys_content},
                {"role": "user",   "content": prompt},
            ]
        else:
            prompt = (
                "You are objectively assessing Inventive Step for the European Patent Office (EPO). "
                "These cases are appeals against the examining board's original decision.\n"
                "Use the data provided. Do not rely on outside knowledge, but you may make reasonable "
                "assumptions about common general knowledge prior to the cut-off date given.\n"
                "Do not simply accept the conclusions of either party — critically analyse the evidence.\n"
                "Determine whether the patent fulfils the inventive step criteria.\n\n"
                f"=== CASE DATA ===\n{context_text}\n=== END CASE DATA ===\n\n"
                "INSTRUCTIONS:\n"
                "1. Provide a step-by-step reasoning trace with explicit reference to the case data.\n"
                "2. Conclude with a final 'Yes' (inventive step present) or 'No' answer.\n"
                "3. Provide a confidence score 0-100."
                + fmt_instruction
            )
            messages = [{"role": "user", "content": prompt}]

        req = _build_request(messages, schema=guided_schema)
        req.pop("seed", None)  # reproducibility optional for baseline

        verdict = "ERROR"
        reasoning = ""
        confidence = 50
        raw = ""

        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.chat.completions.create(**req)
                raw = _get_content(resp)
                if not raw:
                    raise ValueError("empty response")

                parsed = _parse_json(raw)
                answer = str(parsed.get("answer", "")).strip()
                reasoning = str(parsed.get("reasoning", raw))
                confidence = int(parsed.get("confidence_score", 50))

                if re.search(r"\b(yes|no)\b", answer, re.IGNORECASE):
                    verdict = answer.capitalize()
                    break
                # last-resort regex scan of raw text
                am = re.search(r"\b(Yes|No)\b", raw, re.IGNORECASE)
                if am:
                    verdict = am.group(1).capitalize()
                    reasoning = reasoning or raw
                    break
                raise ValueError(f"no yes/no in baseline response: {answer[:80]}")

            except Exception as e:
                logger.warning("baseline attempt %d failed: %s", attempt + 1, e)
                if attempt == MAX_RETRIES - 1:
                    logger.error("baseline failed for %s", case_name)
                    break
                await asyncio.sleep(BASE_BACKOFF * (2 ** attempt))

        elapsed = time.time() - t_start
        turn_log = [_log_entry(1, prompt, verdict, reasoning, confidence, "baseline", elapsed, metadata, full_prompt=messages)]
        with open(log_path, "w") as f:
            json.dump(turn_log, f, indent=4)

        print(f"Baseline {case_name} (run {run_id}) done. Verdict: {verdict}. Time: {elapsed:.2f}s")
        CURRENT_CASE_REF.reset(case_token)
        return verdict


# ── main controller ──────────────────────────────────────────────────────────

def _log_entry(turn, question, answer, reasoning, score, source, elapsed, metadata,
               full_prompt: list | None = None):
    return {
        "turn": turn,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "question": question,
        "answer": answer,
        "reasoning": reasoning,
        "score": score,
        "source": source,
        "elapsed_seconds": elapsed,
        "model_id": metadata.get("model", "Unknown"),
        "metadata": metadata,
        "full_prompt": full_prompt,
    }


async def _run_case(client, case_name: str, context_text: str, run_id: int,
                    metadata: dict, train: bool = False,
                    ensemble: bool = False) -> str:
    """Drive ui.py for one case, returning the final verdict string.

    Flow:
      1. First question in a batch section triggers ONE batch call.
         In ensemble mode, two extra persona opinions are generated first
         (parallel dynamic calls) and passed into the batch prompt.
      2. Cache whatever answers parse successfully.
      3. For each question: use cache if valid, otherwise call dynamic ONCE.
         Dynamic fallback is always single-opinion regardless of ensemble flag.
    """
    async with REQUEST_SEMAPHORE:
        case_token = CURRENT_CASE_REF.set(case_name)
        t_start = time.time()
        config_num = metadata.get("config", "X")
        mode = metadata.get("mode", "tool")

        log_subdir = "train" if train else ("ensemble" if ensemble else "tool")
        log_dir = os.path.join(BASE_CASE_DIR, case_name, f"run_{run_id}",
                               f"config_{config_num}", log_subdir,
                               str(ADM_CONFIG), str(ADM_INITIAL))
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "log.json")
        if os.path.exists(log_path):
            os.remove(log_path)

        # state
        answers_cache: dict = {}          # cache_key → {"answer": ..., "reasoning": ...}
        fetched_sections: set = set()     # batch IDs already fetched (no re-fetching)
        batch_prompt_cache: dict = {}     # batch_id → full messages list sent to LLM
        qa_log: list[dict] = []
        turn_logs: list[dict] = []
        full_output = ""
        buffer: list[str] = []
        full_responses_log: dict = {}
        last_sent = ""
        last_type = ""
        pending_conclusion = ""
        last_conclusion = ""

        sys_prompt = _system_prompt(context_text, case_name, train)

        # spawn ui.py
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
                last_type = "number" if re.fullmatch(r"\d+", text) else ("yesno" if text in {"y", "n"} else "text")
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

                # capture adm outcomes
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

                # invalid input — resend
                if "invalid input" in lower_clean:
                    expects_num = "enter the number" in lower_clean or "only give a number" in lower_clean
                    expects_yn = "(y/n)" in lower_clean or "yes' or 'no'" in lower_clean
                    can_resend = (
                        (expects_num and last_type == "number" and re.fullmatch(r"\d+", last_sent)) or
                        (expects_yn and last_type == "yesno" and last_sent in {"y", "n"}) or
                        (not expects_num and not expects_yn and last_sent)
                    )
                    if can_resend:
                        logger.warning("ui rejected input; resending: %s", last_sent)
                        await _send(last_sent)
                    buffer = []
                    continue

                # auto-fill case name
                if "enter case name" in lower_clean:
                    logger.info("auto-filling case name: %s", case_name)
                    await _send(case_name)
                    buffer = []
                    continue

                # [Qxx] tag
                q_match = re.search(r"\[(Q\d+)\]", clean)
                if q_match:
                    q_num = q_match.group(1)
                    if q_num == "Q380":
                        go_dynamic = True
                    else:
                        needed_key = q_num

                # information questions
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

                history = _last_2_qa(qa_log)

                # ── dynamic route (unknown / special questions) ──────────

                if go_dynamic:
                    logger.info("dynamic mode for: %s", clean[:80])
                    prompt = clean
                    if pending_conclusion and pending_conclusion not in clean:
                        prompt = f"{pending_conclusion}\n\n{clean}"

                    answer, reasoning, dyn_msgs = await _call_dynamic(client, sys_prompt, history, prompt)
                    qa_log.append({"question": clean, "answer": answer, "reasoning": reasoning})
                    turn_logs.append(_log_entry(len(turn_logs) + 1, prompt, answer, reasoning, 0, "dynamic", 0, metadata, full_prompt=dyn_msgs))
                    pending_conclusion = ""
                    logger.info("  → dynamic: %s", answer)
                    await _send(answer)
                    buffer = []
                    continue

                # ── batch route ──────────────────────────────────────────

                section = _section_for_key(needed_key)
                if section is None:
                    # unknown key — dynamic
                    answer, reasoning, dyn_msgs = await _call_dynamic(client, sys_prompt, history, clean)
                    qa_log.append({"question": clean, "answer": answer, "reasoning": reasoning})
                    turn_logs.append(_log_entry(len(turn_logs) + 1, clean, answer, reasoning, 0, "dynamic", 0, metadata, full_prompt=dyn_msgs))
                    await _send(answer)
                    buffer = []
                    continue

                model_class, section_label, section_keys = section

                # sub-adm: include item name in cache key
                item_name = None
                if needed_key in _SUB1_KEYS or needed_key in _SUB2_KEYS:
                    item_name = _detect_item_name(clean) or "UNKNOWN"

                cache_suffix = f"__{item_name[:100]}" if item_name else ""
                batch_id = f"{section_label}{cache_suffix}"

                # fetch batch ONCE per section+item
                if batch_id not in fetched_sections:
                    fetched_sections.add(batch_id)
                    logger.info("batch fetch '%s' (triggered by %s)", section_label, needed_key)

                    batch_results, batch_msgs = await _call_batch(
                        client, sys_prompt, history, model_class,
                        section_label, section_keys,
                        feature_name=item_name, ensemble=ensemble,
                    )
                    # store batch prompt so it can be attached to each answer logged from this batch
                    batch_prompt_cache[batch_id] = batch_msgs
                    for answer_key, val in batch_results.items():
                        ck = f"{answer_key}{cache_suffix}" if item_name and answer_key in (_SUB1_KEYS + _SUB2_KEYS) else answer_key
                        answers_cache[ck] = val

                # look up cache
                cache_key = f"{needed_key}{cache_suffix}"
                cached = answers_cache.get(cache_key)
                answer_to_send = None
                reasoning = ""

                if cached:
                    raw_ans = str(cached.get("answer", "")).strip().replace("**", "")
                    reasoning = cached.get("reasoning", "")
                    if needed_key.startswith("Q"):
                        norm = _normalize_answer(raw_ans, needed_key)
                        if norm and _valid_answer(needed_key, norm):
                            answer_to_send = norm
                    elif raw_ans:
                        answer_to_send = raw_ans

                # cache miss or bad → single dynamic call
                answer_full_prompt = batch_prompt_cache.get(batch_id)
                if answer_to_send is None:
                    logger.info("cache miss for %s → dynamic", needed_key)
                    prompt = clean
                    if pending_conclusion and pending_conclusion not in clean:
                        prompt = f"{pending_conclusion}\n\n{clean}"
                    dyn_answer, dyn_reasoning, dyn_msgs = await _call_dynamic(client, sys_prompt, history, prompt)
                    if needed_key.startswith("Q"):
                        norm = _normalize_answer(dyn_answer, needed_key)
                        answer_to_send = norm if norm and _valid_answer(needed_key, norm) else dyn_answer
                    else:
                        answer_to_send = dyn_answer
                    reasoning = dyn_reasoning
                    answer_full_prompt = dyn_msgs

                # log and send
                logged_q = clean
                if pending_conclusion and pending_conclusion not in clean:
                    logged_q = f"{pending_conclusion}\n\n{clean}"
                pending_conclusion = ""

                qa_log.append({"question": clean, "answer": answer_to_send, "reasoning": reasoning})
                turn_logs.append(_log_entry(len(turn_logs) + 1, logged_q, answer_to_send, reasoning, 0, "batch", 0, metadata, full_prompt=answer_full_prompt))

                logger.info("  → %s: %s", needed_key, answer_to_send)
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

            # ensure final adm output captured
            if not full_responses_log.get("Final_ADM_Output"):
                outcome = _extract_case_outcome(full_output)
                full_responses_log["Final_ADM_Output"] = outcome or full_output[-4000:].strip()

            # ── final verdict ────────────────────────────────────────

            verdict_msgs = []
            fao = str(full_responses_log.get("Final_ADM_Output", "")).strip()
            if fao:
                verdict_msgs.append({"role": "user", "content": f"Final ADM Output Summary:\n{fao}"})
                verdict_msgs.append({"role": "assistant", "content": "Final ADM outcome captured."})

            subs = full_responses_log.get("Sub_ADM_Conclusions", [])
            if subs:
                packed = "\n\n---\n\n".join(str(b).strip()[:1200] for b in subs[-4:] if str(b).strip())
                if packed:
                    verdict_msgs.append({"role": "user", "content": f"Sub-ADM Conclusion Summaries:\n{packed}"})
                    verdict_msgs.append({"role": "assistant", "content": "Sub-ADM conclusions noted."})

            verdict_msgs.extend(_last_2_qa(qa_log))

            history_text = "\n\n".join(
                f"[{m.get('role', '?').upper()}]\n{m.get('content', '')}"
                for m in verdict_msgs if isinstance(m, dict)
            )
            verdict_question_log = f"FINAL VERDICT\n\n=== ADM CONTEXT ===\n{history_text or '[No context]'}"

            final_verdict = "ERROR"
            try:
                answer, reasoning, confidence, verdict_full_msgs = await _call_final_verdict(
                    client, sys_prompt, verdict_msgs, case_name, train,
                )
                turn_logs.append(_log_entry(
                    len(turn_logs) + 1, verdict_question_log,
                    answer, reasoning, confidence, "final_verdict", 0, metadata,
                    full_prompt=verdict_full_msgs,
                ))
                final_verdict = answer
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
            if mode == "baseline":
                tasks.append(_run_baseline_case(client, case, ctx, run, meta, train=False))
            elif mode == "train_baseline":
                tasks.append(_run_baseline_case(client, case, ctx, run, meta, train=True))
            elif mode == "ensemble":
                tasks.append(_run_case(client, case, ctx, run, meta, ensemble=True))
            else:
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

async def _async_main():
    
    #store arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="gpt", choices=list(MODELS.keys()))
    parser.add_argument("--gpu", type=str, default="gpu31")
    parser.add_argument("--port", type=str, default="8000")
    parser.add_argument("--dataset", type=str, choices=["comvik", "main"], required=True)
    parser.add_argument("--data_path", type=str, default="../Data/VALIDATION")
    parser.add_argument("--exp_config", type=int, required=True)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--mode", type=str, default="tool", choices=["tool", "baseline", "train_baseline", "ensemble", "train"])
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--raw_data", type=str, default="../Data/Inv_Step_Sampled_Valid.pkl")
    parser.add_argument("--base_case_dir", type=str, default="../Outputs/Valid_Cases")
    parser.add_argument("--adm_config", type=str, choices=["both", "none", "sub_adm_1", "sub_adm_2"], default="both")
    parser.add_argument("--adm_initial", action="store_true")
    parser.add_argument(
        "--questions_file", type=str, default=None,
        help="Path to a questions JSON file (default: ADM/questions.json). "
             "Use a modified copy for prompt ablation experiments.",
    )
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        print("--- debug mode ---")

    #set global vars
    global ADM_CONFIG, ADM_INITIAL, CURRENT_CONFIG, BASE_CASE_DIR, RAW_DATA, LLM_TEMPERATURE
    ADM_CONFIG = args.adm_config
    ADM_INITIAL = bool(args.adm_initial)
    CURRENT_CONFIG = MODELS.get(args.model, MODELS["gpt"]).copy()
    BASE_CASE_DIR = args.base_case_dir
    LLM_TEMPERATURE = args.temperature

    #load custom questions BEFORE rebuilding the question caches
    if args.questions_file:
        logger.info("loading questions from %s", args.questions_file)
        load_questions(args.questions_file)   # stores in inventive_step_ADM module cache
        set_questions(load_questions())       # no-op if already loaded; ensures consistency
        _build_question_caches()             # rebuild batched prompt dicts with new text
        logger.info("question caches rebuilt from %s", args.questions_file)

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
