"""Unit tests for huginn.skill — YAML frontmatter parsing, verification extraction."""

from pathlib import Path

import pytest

from huginn.skill import Skill, _extract_verification, list_skills, parse_skill


# Path to the real post-generator skill that ships with the repo
REPO_ROOT = Path(__file__).parent.parent
POST_GENERATOR_DIR = REPO_ROOT / "pipelines" / "post-generator"
ANALYZE_SKILL = POST_GENERATOR_DIR / "skills" / "01-analyze.md"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_skill_file(tmp_path):
    """A minimal valid skill file."""
    skill_md = tmp_path / "minimal.md"
    skill_md.write_text(
        "---\nname: test-skill\nmodel: qwen3:8b\n---\n\nDo the thing.\n",
        encoding="utf-8",
    )
    return skill_md


@pytest.fixture()
def full_skill_file(tmp_path):
    """A skill file with all optional fields and a verification section."""
    skill_md = tmp_path / "full.md"
    skill_md.write_text(
        """---
name: full-skill
model: qwen2.5:7b
backend: mac
temperature: 0.5
max_iterations: 5
tools: [file_read, file_write]
constraints:
  network: true
  shell: false
  timeout_minutes: 30
---

# Full Skill

Do something complex.

## Verification
1. Output must be valid JSON
2. Output is 100-500 words
- No banned phrases from style guide
""",
        encoding="utf-8",
    )
    return skill_md


# ---------------------------------------------------------------------------
# parse_skill — real pipeline file
# ---------------------------------------------------------------------------


class TestParseSkillRealFile:
    def test_file_exists(self):
        """Sanity check that the fixture file is present."""
        assert ANALYZE_SKILL.exists(), f"Skill file missing: {ANALYZE_SKILL}"

    def test_parses_name(self):
        skill = parse_skill(ANALYZE_SKILL)
        assert skill.name == "source-analyzer"

    def test_parses_model(self):
        skill = parse_skill(ANALYZE_SKILL)
        assert skill.model == "qwen2.5:7b"

    def test_parses_temperature(self):
        skill = parse_skill(ANALYZE_SKILL)
        assert skill.temperature == pytest.approx(0.3)

    def test_parses_tools(self):
        skill = parse_skill(ANALYZE_SKILL)
        assert "file_read" in skill.tools

    def test_has_system_prompt(self):
        skill = parse_skill(ANALYZE_SKILL)
        assert len(skill.system_prompt) > 0

    def test_extracts_verification_rules(self):
        skill = parse_skill(ANALYZE_SKILL)
        # The skill has "Output must be valid JSON" in its Verification section
        assert len(skill.verification) >= 1
        combined = " ".join(skill.verification).lower()
        assert "json" in combined

    def test_source_path_set(self):
        skill = parse_skill(ANALYZE_SKILL)
        assert skill.source_path == ANALYZE_SKILL


# ---------------------------------------------------------------------------
# parse_skill — minimal file
# ---------------------------------------------------------------------------


class TestParseSkillMinimal:
    def test_parses_name_and_model(self, minimal_skill_file):
        skill = parse_skill(minimal_skill_file)
        assert skill.name == "test-skill"
        assert skill.model == "qwen3:8b"

    def test_default_temperature(self, minimal_skill_file):
        skill = parse_skill(minimal_skill_file)
        assert skill.temperature == pytest.approx(0.7)

    def test_default_max_iterations(self, minimal_skill_file):
        skill = parse_skill(minimal_skill_file)
        assert skill.max_iterations == 10

    def test_default_tools(self, minimal_skill_file):
        skill = parse_skill(minimal_skill_file)
        assert skill.tools == ["file_read"]

    def test_default_backend_is_none(self, minimal_skill_file):
        skill = parse_skill(minimal_skill_file)
        assert skill.backend is None

    def test_empty_verification_when_no_section(self, minimal_skill_file):
        skill = parse_skill(minimal_skill_file)
        assert skill.verification == []


# ---------------------------------------------------------------------------
# parse_skill — full file
# ---------------------------------------------------------------------------


class TestParseSkillFull:
    def test_parses_backend(self, full_skill_file):
        skill = parse_skill(full_skill_file)
        assert skill.backend == "mac"

    def test_parses_temperature(self, full_skill_file):
        skill = parse_skill(full_skill_file)
        assert skill.temperature == pytest.approx(0.5)

    def test_parses_max_iterations(self, full_skill_file):
        skill = parse_skill(full_skill_file)
        assert skill.max_iterations == 5

    def test_parses_tools(self, full_skill_file):
        skill = parse_skill(full_skill_file)
        assert "file_write" in skill.tools

    def test_parses_constraints_network(self, full_skill_file):
        skill = parse_skill(full_skill_file)
        assert skill.network_allowed is True

    def test_parses_constraints_shell(self, full_skill_file):
        skill = parse_skill(full_skill_file)
        assert skill.shell_allowed is False

    def test_parses_constraints_timeout(self, full_skill_file):
        skill = parse_skill(full_skill_file)
        assert skill.timeout_minutes == 30

    def test_extracts_multiple_verification_rules(self, full_skill_file):
        skill = parse_skill(full_skill_file)
        assert len(skill.verification) == 3

    def test_verification_strips_numbering(self, full_skill_file):
        skill = parse_skill(full_skill_file)
        # Should not start with "1." or "2."
        for rule in skill.verification:
            assert not rule[0].isdigit()


# ---------------------------------------------------------------------------
# parse_skill — error cases
# ---------------------------------------------------------------------------


class TestParseSkillErrors:
    def test_raises_for_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_skill(tmp_path / "ghost.md")

    def test_raises_for_non_md_file(self, tmp_path):
        f = tmp_path / "skill.txt"
        f.write_text("---\nname: x\nmodel: y\n---\n", encoding="utf-8")
        with pytest.raises(ValueError, match=".md"):
            parse_skill(f)

    def test_raises_for_missing_name(self, tmp_path):
        f = tmp_path / "no_name.md"
        f.write_text("---\nmodel: qwen3:8b\n---\n\nContent.\n", encoding="utf-8")
        with pytest.raises(ValueError, match="name"):
            parse_skill(f)

    def test_raises_for_missing_model(self, tmp_path):
        f = tmp_path / "no_model.md"
        f.write_text("---\nname: my-skill\n---\n\nContent.\n", encoding="utf-8")
        with pytest.raises(ValueError, match="model"):
            parse_skill(f)


# ---------------------------------------------------------------------------
# _extract_verification (private helper)
# ---------------------------------------------------------------------------


class TestExtractVerification:
    def test_empty_body_returns_empty(self):
        assert _extract_verification("") == []

    def test_no_verification_section_returns_empty(self):
        body = "# My Skill\n\nDo some stuff.\n"
        assert _extract_verification(body) == []

    def test_extracts_numbered_rules(self):
        body = "## Verification\n1. Rule one\n2. Rule two\n"
        rules = _extract_verification(body)
        assert rules == ["Rule one", "Rule two"]

    def test_extracts_bullet_rules(self):
        body = "## Verification\n- Rule alpha\n- Rule beta\n"
        rules = _extract_verification(body)
        assert "Rule alpha" in rules
        assert "Rule beta" in rules

    def test_stops_at_next_header(self):
        body = "## Verification\n1. Keep this\n\n## Other Section\n2. Drop this\n"
        rules = _extract_verification(body)
        assert len(rules) == 1
        assert rules[0] == "Keep this"

    def test_case_insensitive_header(self):
        body = "## VERIFICATION\n- uppercase header rule\n"
        rules = _extract_verification(body)
        assert len(rules) == 1


# ---------------------------------------------------------------------------
# list_skills
# ---------------------------------------------------------------------------


class TestListSkills:
    def test_empty_dir_returns_empty(self, tmp_path):
        result = list_skills(tmp_path / "nonexistent")
        assert result == []

    def test_lists_valid_skills(self, tmp_path):
        f = tmp_path / "skill-a.md"
        f.write_text("---\nname: skill-a\nmodel: qwen3:8b\n---\n\nDo it.\n", encoding="utf-8")
        result = list_skills(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "skill-a"

    def test_handles_invalid_skill_gracefully(self, tmp_path):
        bad = tmp_path / "bad.md"
        bad.write_text("---\n# missing required fields\n---\n", encoding="utf-8")
        result = list_skills(tmp_path)
        assert result[0]["model"] == "ERROR"
