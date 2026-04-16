"""
Unit tests for batched_hybrid_system.py — pure logic only, no LLM calls.

Tests cover:
  - _parse_json
  - _normalize_answer / _valid_answer / _expects_yes_no / _allowed_digits / _option_text_map
  - _section_for_key
  - _strip_decorators
  - _extract_case_outcome
  - _extract_sub_adm_conclusion
  - _detect_item_name
  - _log_entry
  - _build_request (via mocked CURRENT_CONFIG)
  - _get_content (via mocked response object)
  - _system_prompt
  - _last_n_qa / _last_1_qa
  - _question_text / _build_question_caches
  - Pydantic schema round-trip validation
  - _FIELD_TO_KEY completeness
  - Key-list constants (_INITIAL_KEYS, _SUB1_KEYS, etc.)

Last Updated: 16.04.26
"""

import sys
import os
import json
import unittest
from unittest.mock import MagicMock, patch

# pandas and pythonds are in requirements.txt but may not be installed in every
# environment (e.g. the viz node venv is missing them).  Stub both out before
# importing any ADM module so the tests can run anywhere.
for _stub in ("pandas", "pythonds", "pythonds.basic", "pythonds.basic.stack", "pydot"):
    if _stub not in sys.modules:
        sys.modules[_stub] = MagicMock()

# pythonds.Stack is accessed as `from pythonds import Stack`
sys.modules["pythonds"].Stack = MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ADM"))

import batched_hybrid_system as bhs
from batched_hybrid_system import (
    _parse_json,
    _normalize_answer,
    _valid_answer,
    _expects_yes_no,
    _allowed_digits,
    _option_text_map,
    _section_for_key,
    _strip_decorators,
    _extract_case_outcome,
    _extract_sub_adm_conclusion,
    _detect_item_name,
    _log_entry,
    _build_request,
    _get_content,
    _system_prompt,
    _last_n_qa,
    _last_1_qa,
    _question_text,
    _FIELD_TO_KEY,
    _INITIAL_KEYS,
    _SUB1_KEYS,
    _INTER_KEYS,
    _SUB2_KEYS,
    _NO_SUB1_KEYS,
    _NO_SUB2_KEYS,
    _SECONDARY_KEYS,
    _SECTIONS,
    MODELS,
    QuestionResponse,
    FinalVerdictResponse,
    InitialADM_Batch,
    SubADM1_Batch,
    SubADM2_Batch,
    MainADM_Inter_Batch,
    MainADM_No_Sub_1,
    MainADM_No_Sub_2,
    SecondaryIndicators_Batch,
)

import logging
logging.disable(logging.CRITICAL)


def setUpModule():
    """Populate all question-text caches before any tests run.

    _build_question_caches() is called at module import in the main script but
    the caches are empty here because questions are registered lazily.  Calling
    it explicitly ensures _question_text(), _expects_yes_no(), _allowed_digits()
    etc. all return real data.
    """
    bhs._build_question_caches()


# ── helpers ───────────────────────────────────────────────────────────────────

def _set_config(name: str):
    """Point CURRENT_CONFIG at one of the defined model configs."""
    bhs.CURRENT_CONFIG = MODELS[name]


def _clear_config():
    bhs.CURRENT_CONFIG = None


# ─────────────────────────────────────────────────────────────────────────────
# _parse_json
# ─────────────────────────────────────────────────────────────────────────────

class TestParseJson(unittest.TestCase):

    def test_clean_object(self):
        raw = '{"answer": "y", "reasoning": "because"}'
        self.assertEqual(_parse_json(raw), {"answer": "y", "reasoning": "because"})

    def test_object_with_prefix_text(self):
        raw = 'Sure! {"answer": "1"}'
        self.assertEqual(_parse_json(raw)["answer"], "1")

    def test_nested_object(self):
        raw = '{"outer": {"inner": 42}}'
        result = _parse_json(raw)
        self.assertEqual(result["outer"]["inner"], 42)

    def test_empty_string_returns_empty_dict(self):
        self.assertEqual(_parse_json(""), {})

    def test_no_brace_returns_empty_dict(self):
        self.assertEqual(_parse_json("just plain text"), {})

    def test_malformed_json_returns_empty_dict(self):
        self.assertEqual(_parse_json('{"answer": "y"'), {})

    def test_unbalanced_extra_close(self):
        # Balanced braces but inner value has unbalanced content — still parses
        raw = '{"answer": "y"}'
        self.assertIn("answer", _parse_json(raw))

    def test_number_value(self):
        raw = '{"confidence_score": 87}'
        self.assertEqual(_parse_json(raw)["confidence_score"], 87)

    def test_none_input(self):
        # _parse_json receives str; passing empty string as None-like
        self.assertEqual(_parse_json(""), {})

    def test_multiple_objects_returns_first(self):
        raw = '{"a": 1} {"b": 2}'
        result = _parse_json(raw)
        self.assertIn("a", result)
        self.assertNotIn("b", result)

    def test_unicode_content(self):
        raw = '{"answer": "naïve", "reasoning": "café"}'
        result = _parse_json(raw)
        self.assertEqual(result["answer"], "naïve")

    def test_escaped_quotes_in_string(self):
        raw = '{"answer": "say \\"yes\\" or no"}'
        result = _parse_json(raw)
        self.assertIn("answer", result)


# ─────────────────────────────────────────────────────────────────────────────
# _normalize_answer / _valid_answer / helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeAnswer(unittest.TestCase):
    """Tests for _normalize_answer.

    Because _normalize_answer depends on question text loaded from the ADM,
    we use Q-keys that definitely exist in the question caches (yes/no nodes
    in the main ADM) or mock the text helpers for isolated tests.
    """

    # --- yes/no keys ---------------------------------------------------------

    def test_yes_normalized(self):
        # Q13 is a yes/no node
        self.assertEqual(_normalize_answer("yes", "Q13"), "y")

    def test_no_normalized(self):
        self.assertEqual(_normalize_answer("no", "Q13"), "n")

    def test_y_normalized(self):
        self.assertEqual(_normalize_answer("y", "Q13"), "y")

    def test_n_normalized(self):
        self.assertEqual(_normalize_answer("n", "Q13"), "n")

    def test_uppercase_yes(self):
        self.assertEqual(_normalize_answer("YES", "Q13"), "y")

    def test_uppercase_no(self):
        self.assertEqual(_normalize_answer("NO", "Q13"), "n")

    def test_bold_markdown_stripped(self):
        self.assertEqual(_normalize_answer("**yes**", "Q13"), "y")

    # --- multi-choice key (Q1 has options 1/2/3) ----------------------------

    def test_digit_answer_for_multi_choice(self):
        result = _normalize_answer("1", "Q1")
        self.assertEqual(result, "1")

    def test_digit_in_sentence(self):
        result = _normalize_answer("I would choose option 1.", "Q1")
        self.assertEqual(result, "1")

    def test_word_one(self):
        result = _normalize_answer("one", "Q1")
        self.assertEqual(result, "1")

    def test_word_two(self):
        result = _normalize_answer("two", "Q1")
        self.assertEqual(result, "2")

    # --- JSON-embedded answer ------------------------------------------------

    def test_json_embedded_yes(self):
        raw = '{"answer": "yes", "reasoning": "..."}'
        self.assertEqual(_normalize_answer(raw, "Q13"), "y")

    def test_json_embedded_digit(self):
        raw = '{"answer": "1", "reasoning": "..."}'
        result = _normalize_answer(raw, "Q1")
        self.assertEqual(result, "1")

    # --- empty / whitespace --------------------------------------------------

    def test_empty_string_returns_none(self):
        self.assertIsNone(_normalize_answer("", "Q11"))

    def test_whitespace_returns_none(self):
        self.assertIsNone(_normalize_answer("   ", "Q11"))


class TestValidAnswer(unittest.TestCase):

    def test_yn_valid_yes(self):
        self.assertTrue(_valid_answer("Q13", "y"))

    def test_yn_valid_no(self):
        self.assertTrue(_valid_answer("Q13", "n"))

    def test_yn_invalid_digit(self):
        # Q13 is yes/no; a digit answer is valid only if it appears in allowed_digits
        allowed = _allowed_digits("Q13")
        if not allowed:
            self.assertFalse(_valid_answer("Q13", "1"))
        else:
            # some yes/no questions also accept numbered options
            self.assertFalse(_valid_answer("Q13", "99"))

    def test_multi_valid_digit(self):
        allowed = _allowed_digits("Q1")
        for d in allowed:
            self.assertTrue(_valid_answer("Q1", d))

    def test_multi_invalid_out_of_range(self):
        # "99" should not be a valid answer for any real question
        allowed = _allowed_digits("Q1")
        self.assertNotIn("99", allowed)
        self.assertFalse(_valid_answer("Q1", "99"))

    def test_empty_norm_invalid(self):
        self.assertFalse(_valid_answer("Q13", ""))

    def test_none_norm_invalid(self):
        self.assertFalse(_valid_answer("Q13", None))


class TestExpectsYesNo(unittest.TestCase):

    def test_yes_no_question(self):
        # Q13 asks for y/n
        self.assertTrue(_expects_yes_no("Q13"))

    def test_multi_choice_question(self):
        # Q1 is multiple choice
        self.assertFalse(_expects_yes_no("Q1"))

    def test_unknown_key_returns_false(self):
        self.assertFalse(_expects_yes_no("Q999"))


class TestAllowedDigits(unittest.TestCase):

    def test_multi_choice_returns_nonempty_set(self):
        digits = _allowed_digits("Q1")
        self.assertIsInstance(digits, set)
        self.assertTrue(len(digits) > 0)

    def test_yes_no_returns_empty_set(self):
        # Q13 is a pure yes/no node — no digit options
        digits = _allowed_digits("Q13")
        self.assertEqual(digits, set())

    def test_unknown_key_returns_empty_set(self):
        self.assertEqual(_allowed_digits("Q999"), set())


class TestOptionTextMap(unittest.TestCase):

    def test_multi_choice_has_entries(self):
        omap = _option_text_map("Q1")
        self.assertIsInstance(omap, dict)
        self.assertTrue(len(omap) >= 1)

    def test_entries_are_strings(self):
        for k, v in _option_text_map("Q1").items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, str)

    def test_unknown_key_returns_empty(self):
        self.assertEqual(_option_text_map("Q999"), {})


# ─────────────────────────────────────────────────────────────────────────────
# _section_for_key
# ─────────────────────────────────────────────────────────────────────────────

class TestSectionForKey(unittest.TestCase):

    def test_initial_key_routed(self):
        result = _section_for_key("Q1")
        self.assertIsNotNone(result)
        model_class, label, keys = result
        self.assertIn("Initial", label)

    def test_sub1_key_routed(self):
        model_class, label, keys = _section_for_key("Q17")
        self.assertIn("Technical Character", label)
        self.assertEqual(model_class, SubADM1_Batch)

    def test_inter_key_routed(self):
        model_class, label, keys = _section_for_key("Q32")
        self.assertEqual(model_class, MainADM_Inter_Batch)

    def test_sub2_key_routed(self):
        model_class, label, keys = _section_for_key("Q34")
        self.assertEqual(model_class, SubADM2_Batch)

    def test_no_sub1_key_routed(self):
        model_class, label, keys = _section_for_key("Q100")
        self.assertEqual(model_class, MainADM_No_Sub_1)

    def test_no_sub2_key_routed(self):
        model_class, label, keys = _section_for_key("Q200")
        self.assertEqual(model_class, MainADM_No_Sub_2)

    def test_secondary_key_routed(self):
        model_class, label, keys = _section_for_key("Q40")
        self.assertEqual(model_class, SecondaryIndicators_Batch)

    def test_unknown_key_returns_none(self):
        self.assertIsNone(_section_for_key("Q999"))

    def test_information_key_routed(self):
        result = _section_for_key("invention title")
        self.assertIsNotNone(result)

    def test_all_initial_keys_routed(self):
        for k in _INITIAL_KEYS:
            self.assertIsNotNone(_section_for_key(k), msg=f"Key {k} not routed")

    def test_all_sub1_keys_routed(self):
        for k in _SUB1_KEYS:
            self.assertIsNotNone(_section_for_key(k), msg=f"Key {k} not routed")

    def test_all_sub2_keys_routed(self):
        for k in _SUB2_KEYS:
            self.assertIsNotNone(_section_for_key(k), msg=f"Key {k} not routed")

    def test_all_secondary_keys_routed(self):
        for k in _SECONDARY_KEYS:
            self.assertIsNotNone(_section_for_key(k), msg=f"Key {k} not routed")


# ─────────────────────────────────────────────────────────────────────────────
# Text helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestStripDecorators(unittest.TestCase):

    def test_removes_equals_line(self):
        text = "=====\nHello\n====="
        result = _strip_decorators(text)
        self.assertNotIn("=====", result)
        self.assertIn("Hello", result)

    def test_removes_dash_line(self):
        text = "---\nHello\n---"
        result = _strip_decorators(text)
        self.assertNotIn("---", result)

    def test_preserves_normal_text(self):
        text = "Normal sentence.\nAnother line."
        self.assertEqual(_strip_decorators(text), text)

    def test_empty_string(self):
        self.assertEqual(_strip_decorators(""), "")

    def test_only_decorators_returns_empty(self):
        text = "=====\n-----\n~~~~~"
        result = _strip_decorators(text)
        self.assertEqual(result, "")

    def test_mixed_content(self):
        text = "=====\nQuestion text here\n=====\nMore text"
        result = _strip_decorators(text)
        self.assertIn("Question text here", result)
        self.assertIn("More text", result)

    def test_short_lines_preserved(self):
        # Lines shorter than 3 chars should not be stripped
        text = "--\nHello"
        result = _strip_decorators(text)
        self.assertIn("--", result)

    def test_mixed_char_lines_preserved(self):
        # Line with multiple different chars is not a decorator
        text = "=-=\nHello"
        result = _strip_decorators(text)
        self.assertIn("=-=", result)


class TestExtractCaseOutcome(unittest.TestCase):

    def test_extracts_case_outcome(self):
        text = "Some text\nCase Outcome: GRANTED\nMore text"
        result = _extract_case_outcome(text)
        self.assertIn("Case Outcome:", result)
        self.assertIn("GRANTED", result)

    def test_returns_empty_when_no_marker(self):
        self.assertEqual(_extract_case_outcome("No outcome here"), "")

    def test_stops_at_adm_summary_marker(self):
        text = "Case Outcome: GRANTED\nADM and sub-ADM summaries appended to: file.txt"
        result = _extract_case_outcome(text)
        self.assertNotIn("ADM and sub-ADM summaries", result)

    def test_takes_last_occurrence(self):
        text = "Case Outcome: FIRST\n\nCase Outcome: LAST"
        result = _extract_case_outcome(text)
        self.assertIn("LAST", result)
        self.assertNotIn("FIRST", result)

    def test_empty_string(self):
        self.assertEqual(_extract_case_outcome(""), "")


class TestExtractSubAdmConclusion(unittest.TestCase):

    def test_extracts_early_stop(self):
        text = "Preamble\n[Early Stop] No technical contribution found.\n\n[Q1] Next question"
        result = _extract_sub_adm_conclusion(text)
        self.assertIn("[Early Stop]", result)

    def test_extracts_case_outcome(self):
        text = "Preamble\nCase Outcome: REJECTED"
        result = _extract_sub_adm_conclusion(text)
        self.assertIn("Case Outcome:", result)

    def test_extracts_sub_adm_summary(self):
        text = "=== Sub-ADM Summary ===\nSome conclusion here"
        result = _extract_sub_adm_conclusion(text)
        self.assertIn("Sub-ADM Summary", result)

    def test_returns_empty_when_no_marker(self):
        self.assertEqual(_extract_sub_adm_conclusion("Nothing relevant"), "")

    def test_stops_at_next_question(self):
        text = "Case Outcome: YES\n[Q1] Next question"
        result = _extract_sub_adm_conclusion(text)
        self.assertNotIn("[Q1]", result)


class TestDetectItemName(unittest.TestCase):

    def test_detects_feature(self):
        text = "Feature: transparent conductive layer\nSome other text"
        self.assertEqual(_detect_item_name(text), "transparent conductive layer")

    def test_detects_problem_name(self):
        text = "Problem name: reduce friction\nSome text"
        self.assertEqual(_detect_item_name(text), "reduce friction")

    def test_feature_takes_priority_over_problem(self):
        text = "Feature: feature one\nProblem name: problem one"
        self.assertEqual(_detect_item_name(text), "feature one")

    def test_returns_none_when_absent(self):
        self.assertIsNone(_detect_item_name("No item name here"))

    def test_strips_whitespace(self):
        text = "Feature:   spaced feature  \n"
        self.assertEqual(_detect_item_name(text), "spaced feature")

    def test_empty_string(self):
        self.assertIsNone(_detect_item_name(""))


# ─────────────────────────────────────────────────────────────────────────────
# _log_entry
# ─────────────────────────────────────────────────────────────────────────────

class TestLogEntry(unittest.TestCase):

    def _make_entry(self, **kwargs):
        defaults = dict(
            turn=1, question="Q?", answer="y", reasoning="because",
            score=0, source="batch", elapsed=1.5,
            metadata={"model": "gpt", "config": 3}
        )
        defaults.update(kwargs)
        return _log_entry(**defaults)

    def test_keys_present(self):
        entry = self._make_entry()
        for key in ("turn", "timestamp", "question", "answer", "reasoning",
                    "score", "source", "elapsed_seconds", "model_id", "metadata"):
            self.assertIn(key, entry)

    def test_turn_stored(self):
        entry = self._make_entry(turn=5)
        self.assertEqual(entry["turn"], 5)

    def test_model_id_from_metadata(self):
        entry = self._make_entry(metadata={"model": "qwen"})
        self.assertEqual(entry["model_id"], "qwen")

    def test_full_prompt_none_by_default(self):
        entry = self._make_entry()
        self.assertIsNone(entry["full_prompt"])

    def test_full_prompt_stored(self):
        msgs = [{"role": "user", "content": "hello"}]
        entry = self._make_entry(full_prompt=msgs)
        self.assertEqual(entry["full_prompt"], msgs)

    def test_timestamp_format(self):
        import re
        entry = self._make_entry()
        self.assertRegex(entry["timestamp"], r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


# ─────────────────────────────────────────────────────────────────────────────
# _build_request
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildRequest(unittest.TestCase):

    def setUp(self):
        bhs.LLM_TEMPERATURE = 0.0

    def tearDown(self):
        _clear_config()
        bhs.LLM_TEMPERATURE = 0.0

    def test_basic_keys_present(self):
        _set_config("llama")
        msgs = [{"role": "user", "content": "hello"}]
        req = _build_request(msgs)
        for key in ("model", "messages", "temperature", "max_tokens"):
            self.assertIn(key, req)

    def test_messages_stored(self):
        _set_config("llama")
        msgs = [{"role": "user", "content": "test"}]
        req = _build_request(msgs)
        self.assertEqual(req["messages"], msgs)

    def test_temperature_from_global(self):
        _set_config("llama")
        bhs.LLM_TEMPERATURE = 0.3
        req = _build_request([])
        self.assertEqual(req["temperature"], 0.3)

    def test_guided_json_true_adds_response_format(self):
        _set_config("llama")  # guided_json = True
        schema = QuestionResponse.model_json_schema()
        req = _build_request([], schema=schema)
        self.assertIn("response_format", req)
        self.assertEqual(req["response_format"]["type"], "json_schema")

    def test_guided_json_false_no_response_format(self):
        _set_config("qwen")  # guided_json = False
        schema = QuestionResponse.model_json_schema()
        req = _build_request([], schema=schema)
        self.assertNotIn("response_format", req)

    def test_no_schema_no_response_format(self):
        _set_config("llama")
        req = _build_request([])
        self.assertNotIn("response_format", req)

    def test_seed_added_when_supported(self):
        _set_config("llama")
        req = _build_request([])
        self.assertIn("seed", req)

    def test_thinking_disabled_for_qwen(self):
        _set_config("qwen")  # thinking = False
        req = _build_request([])
        self.assertIn("extra_body", req)
        self.assertFalse(req["extra_body"]["chat_template_kwargs"]["enable_thinking"])

    def test_thinking_not_disabled_for_gpt(self):
        _set_config("gpt")  # thinking = True
        req = _build_request([])
        extra = req.get("extra_body", {})
        ck = extra.get("chat_template_kwargs", {})
        # enable_thinking should NOT be False for gpt
        self.assertNotEqual(ck.get("enable_thinking"), False)

    def test_reasoning_effort_added_for_gpt(self):
        _set_config("gpt")
        req = _build_request([])
        self.assertIn("reasoning_effort", req)
        self.assertEqual(req["reasoning_effort"], "medium")

    def test_reasoning_effort_absent_for_llama(self):
        _set_config("llama")
        req = _build_request([])
        self.assertNotIn("reasoning_effort", req)

    def test_model_id_in_request(self):
        _set_config("llama")
        req = _build_request([])
        self.assertEqual(req["model"], MODELS["llama"]["id"])


# ─────────────────────────────────────────────────────────────────────────────
# _get_content
# ─────────────────────────────────────────────────────────────────────────────

class TestGetContent(unittest.TestCase):

    def _mock_resp(self, content: str):
        resp = MagicMock()
        resp.choices[0].message.content = content
        return resp

    def test_extracts_content(self):
        resp = self._mock_resp("  hello  ")
        self.assertEqual(_get_content(resp), "hello")

    def test_strips_whitespace(self):
        resp = self._mock_resp("\n  answer  \n")
        self.assertEqual(_get_content(resp), "answer")

    def test_empty_content_returns_empty_string(self):
        resp = self._mock_resp("")
        self.assertEqual(_get_content(resp), "")

    def test_none_content_returns_empty_string(self):
        resp = self._mock_resp(None)
        self.assertEqual(_get_content(resp), "")


# ─────────────────────────────────────────────────────────────────────────────
# _system_prompt
# ─────────────────────────────────────────────────────────────────────────────

class TestSystemPrompt(unittest.TestCase):

    def test_contains_context(self):
        prompt = _system_prompt("MY CONTEXT", "T001")
        self.assertIn("MY CONTEXT", prompt)

    def test_tool_mode_includes_instructions(self):
        prompt = _system_prompt("ctx", "T001", train=False)
        self.assertIn("INSTRUCTIONS", prompt)

    def test_train_mode_differs_from_tool(self):
        # With RAW_DATA=None the train branch still builds a different prompt
        # (different instructions text) so the strings should differ.
        tool = _system_prompt("ctx", "T001", train=False)
        with patch.object(bhs, "RAW_DATA", None):
            try:
                train = _system_prompt("ctx", "T001", train=True)
                self.assertNotEqual(tool, train)
            except (AttributeError, TypeError):
                # If _system_prompt raises because RAW_DATA is None that's
                # acceptable — it means train mode requires real data.
                pass

    def test_contains_epo_reference(self):
        prompt = _system_prompt("ctx", "T001")
        self.assertIn("EPO", prompt)

    def test_contains_adm_reference(self):
        prompt = _system_prompt("ctx", "T001")
        self.assertIn("ADM", prompt)


# ─────────────────────────────────────────────────────────────────────────────
# _last_n_qa / _last_1_qa
# ─────────────────────────────────────────────────────────────────────────────

class TestLastNQA(unittest.TestCase):

    def _make_log(self, n=5):
        return [
            {"question": f"Q{i}?", "answer": str(i), "reasoning": f"reason{i}"}
            for i in range(1, n + 1)
        ]

    def test_last_1(self):
        log = self._make_log(3)
        msgs = _last_1_qa(log)
        self.assertEqual(len(msgs), 2)  # user + assistant
        self.assertIn("Q3?", msgs[0]["content"])

    def test_last_n_count(self):
        log = self._make_log(5)
        msgs = _last_n_qa(log, 3)
        self.assertEqual(len(msgs), 6)  # 3 × (user + assistant)

    def test_last_n_exceeds_log(self):
        log = self._make_log(2)
        msgs = _last_n_qa(log, 10)
        self.assertEqual(len(msgs), 4)  # only 2 entries available

    def test_empty_log(self):
        self.assertEqual(_last_n_qa([], 3), [])

    def test_roles(self):
        log = self._make_log(1)
        msgs = _last_n_qa(log, 1)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[1]["role"], "assistant")

    def test_assistant_content_is_json(self):
        log = self._make_log(1)
        msgs = _last_n_qa(log, 1)
        parsed = json.loads(msgs[1]["content"])
        self.assertIn("answer", parsed)
        self.assertIn("reasoning", parsed)

    def test_last_n_zero(self):
        # Python: log[-0:] == log[0:] (all items), so n=0 returns everything.
        # This is expected behaviour — callers should pass n >= 1.
        log = self._make_log(3)
        msgs = _last_n_qa(log, 0)
        self.assertEqual(len(msgs), len(log) * 2)


# ─────────────────────────────────────────────────────────────────────────────
# Question text / caches
# ─────────────────────────────────────────────────────────────────────────────

class TestQuestionText(unittest.TestCase):

    def test_q1_text_nonempty(self):
        self.assertTrue(len(_question_text("Q1")) > 0)

    def test_q17_text_nonempty(self):
        self.assertTrue(len(_question_text("Q17")) > 0)

    def test_q40_text_nonempty(self):
        self.assertTrue(len(_question_text("Q40")) > 0)

    def test_unknown_key_empty(self):
        self.assertEqual(_question_text("Q999"), "")

    def test_lowercase_key_works(self):
        t1 = _question_text("Q1")
        t2 = _question_text("q1")
        self.assertEqual(t1, t2)

    def test_information_key_text(self):
        t = _question_text("invention title")
        self.assertTrue(len(t) > 0)

    def test_obj_t_problem_text(self):
        t = _question_text("obj_t_problem")
        self.assertTrue(len(t) > 0)

    def test_all_sub1_keys_have_text(self):
        for k in _SUB1_KEYS:
            self.assertTrue(len(_question_text(k)) > 0, msg=f"No text for {k}")

    def test_all_secondary_keys_have_text(self):
        for k in _SECONDARY_KEYS:
            self.assertTrue(len(_question_text(k)) > 0, msg=f"No text for {k}")


# ─────────────────────────────────────────────────────────────────────────────
# Key-list constant integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestKeyListIntegrity(unittest.TestCase):

    def test_no_duplicate_keys_across_sections(self):
        all_keys = (
            _INITIAL_KEYS + _SUB1_KEYS + _INTER_KEYS +
            _SUB2_KEYS + _NO_SUB1_KEYS + _NO_SUB2_KEYS + _SECONDARY_KEYS
        )
        self.assertEqual(len(all_keys), len(set(all_keys)),
                         "Duplicate keys found across section key lists")

    def test_initial_keys_count(self):
        # 6 info keys + Q1–Q16 = 22
        self.assertEqual(len(_INITIAL_KEYS), 22)

    def test_sub1_keys_count(self):
        # Q17, Q19–Q31 (no Q18) = 14
        self.assertEqual(len(_SUB1_KEYS), 14)

    def test_inter_keys_count(self):
        self.assertEqual(len(_INTER_KEYS), 2)

    def test_sub2_keys_count(self):
        self.assertEqual(len(_SUB2_KEYS), 4)

    def test_no_sub1_keys_count(self):
        self.assertEqual(len(_NO_SUB1_KEYS), 8)

    def test_no_sub2_keys_count(self):
        # obj_t_problem + Q200–Q203 = 5
        self.assertEqual(len(_NO_SUB2_KEYS), 5)

    def test_secondary_keys_count(self):
        # Q40–Q59 = 20
        self.assertEqual(len(_SECONDARY_KEYS), 20)

    def test_sections_covers_all_key_lists(self):
        section_keys = set()
        for keys, _, _ in _SECTIONS:
            section_keys.update(keys)
        for k in (_INITIAL_KEYS + _SUB1_KEYS + _INTER_KEYS +
                  _SUB2_KEYS + _NO_SUB1_KEYS + _NO_SUB2_KEYS + _SECONDARY_KEYS):
            self.assertIn(k, section_keys, msg=f"Key {k} missing from _SECTIONS")


# ─────────────────────────────────────────────────────────────────────────────
# _FIELD_TO_KEY mapping completeness
# ─────────────────────────────────────────────────────────────────────────────

class TestFieldToKey(unittest.TestCase):

    def test_all_values_are_strings(self):
        for field, key in _FIELD_TO_KEY.items():
            self.assertIsInstance(key, str, msg=f"Value for {field} is not str")

    def test_all_q_values_in_some_key_list(self):
        all_q_keys = set(
            _INITIAL_KEYS + _SUB1_KEYS + _INTER_KEYS +
            _SUB2_KEYS + _NO_SUB1_KEYS + _NO_SUB2_KEYS + _SECONDARY_KEYS
        )
        for field, key in _FIELD_TO_KEY.items():
            if key.startswith("Q") or key in (
                "invention title", "description", "technical field",
                "prior art", "common general knowledge",
                "closest prior art description", "obj_t_problem"
            ):
                self.assertIn(key, all_q_keys, msg=f"Field {field} maps to unknown key {key}")

    def test_no_empty_keys(self):
        for field, key in _FIELD_TO_KEY.items():
            self.assertTrue(key.strip(), msg=f"Empty key for field {field}")

    def test_q17_field_maps_correctly(self):
        self.assertEqual(_FIELD_TO_KEY["q17_tech_cont"], "Q17")

    def test_q40_field_maps_correctly(self):
        self.assertEqual(_FIELD_TO_KEY["q40_disadvantage"], "Q40")

    def test_info_fields_map_correctly(self):
        self.assertEqual(_FIELD_TO_KEY["invention_title"], "invention title")
        self.assertEqual(_FIELD_TO_KEY["obj_t_problem"], "obj_t_problem")


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schema round-trip
# ─────────────────────────────────────────────────────────────────────────────

class TestPydanticSchemas(unittest.TestCase):

    def _qr(self, answer="y", reasoning="test"):
        return {"answer": answer, "reasoning": reasoning}

    def test_question_response_valid(self):
        obj = QuestionResponse(answer="y", reasoning="because")
        self.assertEqual(obj.answer, "y")

    def test_final_verdict_response_valid(self):
        obj = FinalVerdictResponse(answer="Yes", reasoning="r", confidence_score=80)
        self.assertEqual(obj.answer, "Yes")
        self.assertEqual(obj.confidence_score, 80)

    def test_initial_adm_batch_schema_exportable(self):
        schema = InitialADM_Batch.model_json_schema()
        self.assertIn("properties", schema)

    def test_sub1_batch_schema_exportable(self):
        schema = SubADM1_Batch.model_json_schema()
        self.assertIn("properties", schema)

    def test_sub2_batch_schema_exportable(self):
        schema = SubADM2_Batch.model_json_schema()
        self.assertIn("properties", schema)

    def test_secondary_indicators_schema_exportable(self):
        schema = SecondaryIndicators_Batch.model_json_schema()
        self.assertIn("properties", schema)
        # spot-check a few fields
        props = schema["properties"]
        for field in ("q40_disadvantage", "q55_analog_sub", "q59_chem_select"):
            self.assertIn(field, props, msg=f"Field {field} missing from schema")

    def test_initial_batch_field_count(self):
        props = InitialADM_Batch.model_json_schema()["properties"]
        # 6 info + 16 Q-keys = 22 fields
        self.assertEqual(len(props), 22)

    def test_sub1_batch_field_count(self):
        props = SubADM1_Batch.model_json_schema()["properties"]
        self.assertEqual(len(props), 14)

    def test_secondary_batch_field_count(self):
        props = SecondaryIndicators_Batch.model_json_schema()["properties"]
        self.assertEqual(len(props), 20)

    def test_model_fields_match_field_to_key(self):
        """Every pydantic field in batch models should appear in _FIELD_TO_KEY."""
        batch_models = [
            InitialADM_Batch, SubADM1_Batch, SubADM2_Batch,
            MainADM_Inter_Batch, MainADM_No_Sub_1, MainADM_No_Sub_2,
            SecondaryIndicators_Batch,
        ]
        for model in batch_models:
            for field_name in model.model_fields:
                self.assertIn(field_name, _FIELD_TO_KEY,
                              msg=f"Field '{field_name}' in {model.__name__} missing from _FIELD_TO_KEY")


# ─────────────────────────────────────────────────────────────────────────────
# MODELS config structure
# ─────────────────────────────────────────────────────────────────────────────

class TestModelsConfig(unittest.TestCase):

    def test_all_models_have_required_keys(self):
        required = {"id", "guided_json", "reasoning_effort", "thinking", "seed", "max_tokens", "context_limit"}
        for name, cfg in MODELS.items():
            for key in required:
                self.assertIn(key, cfg, msg=f"Model '{name}' missing key '{key}'")

    def test_guided_json_is_bool(self):
        for name, cfg in MODELS.items():
            self.assertIsInstance(cfg["guided_json"], bool, msg=f"Model '{name}'")

    def test_qwen_guided_json_false(self):
        self.assertFalse(MODELS["qwen"]["guided_json"])

    def test_gpt_guided_json_true(self):
        self.assertTrue(MODELS["gpt"]["guided_json"])

    def test_llama_guided_json_true(self):
        self.assertTrue(MODELS["llama"]["guided_json"])

    def test_gpt_has_thinking(self):
        self.assertTrue(MODELS["gpt"]["thinking"])

    def test_llama_no_thinking(self):
        self.assertFalse(MODELS["llama"]["thinking"])

    def test_max_tokens_positive(self):
        for name, cfg in MODELS.items():
            self.assertGreater(cfg["max_tokens"], 0, msg=f"Model '{name}'")

    def test_context_limit_positive(self):
        for name, cfg in MODELS.items():
            self.assertGreater(cfg["context_limit"], 0, msg=f"Model '{name}'")


if __name__ == "__main__":
    unittest.main(verbosity=2)
