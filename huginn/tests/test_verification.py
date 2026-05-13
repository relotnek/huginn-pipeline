"""Unit tests for the _verify_output function in huginn.agent."""

import json

import pytest

from huginn.agent import _verify_output


# ---------------------------------------------------------------------------
# Word count checks
# ---------------------------------------------------------------------------


class TestVerifyOutputWordCount:
    def test_word_count_passes_within_range(self):
        # Generate exactly 200 words
        text = " ".join(["word"] * 200)
        passed, failures = _verify_output(text, ["Output is 150-300 words"])
        assert passed is True
        assert failures == []

    def test_word_count_fails_below_range(self):
        text = " ".join(["word"] * 50)  # 50 words — below 150
        passed, failures = _verify_output(text, ["Output is 150-300 words"])
        assert passed is False
        assert len(failures) == 1
        assert "50 words" in failures[0]

    def test_word_count_fails_above_range(self):
        text = " ".join(["word"] * 400)  # 400 words — above 300
        passed, failures = _verify_output(text, ["Output is 150-300 words"])
        assert passed is False
        assert len(failures) == 1

    def test_word_count_passes_at_lower_bound(self):
        text = " ".join(["word"] * 150)
        passed, failures = _verify_output(text, ["Output is 150-300 words"])
        assert passed is True

    def test_word_count_passes_at_upper_bound(self):
        text = " ".join(["word"] * 300)
        passed, failures = _verify_output(text, ["Output is 150-300 words"])
        assert passed is True

    def test_word_count_fewer_than_passes(self):
        text = " ".join(["word"] * 10)
        passed, failures = _verify_output(text, ["fewer than 50 words"])
        assert passed is True

    def test_word_count_fewer_than_fails(self):
        text = " ".join(["word"] * 60)
        passed, failures = _verify_output(text, ["fewer than 50 words"])
        assert passed is False

    def test_word_count_at_least_passes(self):
        text = " ".join(["word"] * 100)
        passed, failures = _verify_output(text, ["at least 50 words"])
        assert passed is True

    def test_word_count_at_least_fails(self):
        text = " ".join(["word"] * 20)
        passed, failures = _verify_output(text, ["at least 50 words"])
        assert passed is False


# ---------------------------------------------------------------------------
# JSON validity checks
# ---------------------------------------------------------------------------


class TestVerifyOutputJsonValidity:
    def test_valid_json_object_passes(self):
        text = json.dumps({"key": "value", "number": 42})
        passed, failures = _verify_output(text, ["Output must be valid JSON"])
        assert passed is True
        assert failures == []

    def test_valid_json_array_passes(self):
        text = json.dumps([1, 2, 3])
        passed, failures = _verify_output(text, ["Output must be valid JSON"])
        assert passed is True

    def test_invalid_json_fails(self):
        text = "This is not JSON at all"
        passed, failures = _verify_output(text, ["Output must be valid JSON"])
        assert passed is False
        assert len(failures) == 1

    def test_partial_json_fails(self):
        text = '{"key": "value"'  # missing closing brace
        passed, failures = _verify_output(text, ["Output must be valid JSON"])
        assert passed is False

    def test_json_rule_case_insensitive(self):
        text = json.dumps({"ok": True})
        passed, failures = _verify_output(text, ["output must be VALID JSON"])
        assert passed is True


# ---------------------------------------------------------------------------
# Banned phrase checks
# ---------------------------------------------------------------------------


class TestVerifyOutputBannedPhrases:
    def test_clean_output_passes(self):
        text = "Here is a clear and direct explanation of the topic."
        passed, failures = _verify_output(text, ["No banned phrases from style guide"])
        assert passed is True

    def test_output_with_leverage_fails(self):
        text = "We need to leverage existing tools to drive adoption."
        passed, failures = _verify_output(text, ["No banned phrases from style guide"])
        assert passed is False
        assert "leverage" in failures[0]

    def test_output_with_delve_fails(self):
        text = "Let us delve into the problem space."
        passed, failures = _verify_output(text, ["No banned phrases from style guide"])
        assert passed is False
        assert "delve" in failures[0]

    def test_output_with_best_practices_fails(self):
        text = "Following best practices ensures quality."
        passed, failures = _verify_output(text, ["No banned phrases from style guide"])
        assert passed is False

    def test_multiple_banned_phrases_all_reported(self):
        text = "We leverage best practices to deliver robust solutions."
        passed, failures = _verify_output(text, ["No banned phrases from style guide"])
        assert passed is False
        # Should list all found banned words in the single failure message
        assert len(failures) == 1
        assert "leverage" in failures[0]
        assert "best practices" in failures[0]

    def test_banned_phrase_trigger_variations(self):
        # Both wordings should match the ban check
        for rule in ["No banned phrases from style guide", "banned phrase check"]:
            text = "This is straightforward to implement."
            passed, _ = _verify_output(text, [rule])
            assert passed is False


# ---------------------------------------------------------------------------
# Content containment checks
# ---------------------------------------------------------------------------


class TestVerifyOutputContainment:
    def test_contains_required_string_passes(self):
        text = "The output includes a summary section."
        passed, failures = _verify_output(text, ["Must contain 'summary'"])
        assert passed is True

    def test_missing_required_string_fails(self):
        text = "This output is missing the required section."
        passed, failures = _verify_output(text, ["Must contain 'summary'"])
        assert passed is False
        assert len(failures) == 1

    def test_containment_case_insensitive(self):
        text = "The SUMMARY of the work follows."
        passed, failures = _verify_output(text, ["Must contain 'summary'"])
        assert passed is True

    def test_double_quoted_target_works(self):
        text = 'The output has a "conclusion" section.'
        passed, failures = _verify_output(text, ['Must contain "conclusion"'])
        assert passed is True


# ---------------------------------------------------------------------------
# Multiple rules — pass only when all pass
# ---------------------------------------------------------------------------


class TestVerifyOutputMultipleRules:
    def test_all_rules_pass(self):
        text = json.dumps({"result": "clean text with no bad words " + " ".join(["word"] * 200)})
        # This JSON is valid; we test both rules independently
        passed, failures = _verify_output(text, ["Output must be valid JSON"])
        assert passed is True

    def test_one_failing_rule_causes_overall_failure(self):
        text = "Good output with no banned stuff."
        rules = [
            "at least 500 words",  # will fail — text is short
            "No banned phrases from style guide",  # will pass
        ]
        passed, failures = _verify_output(text, rules)
        assert passed is False
        assert len(failures) == 1  # only the word count fails

    def test_empty_rules_always_passes(self):
        passed, failures = _verify_output("anything", [])
        assert passed is True
        assert failures == []
