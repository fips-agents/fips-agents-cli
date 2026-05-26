"""Tests for the patch command and the patching tools layer."""

import json
from pathlib import Path

import pytest

from fips_agents_cli.cli import cli
from fips_agents_cli.tools import patching
from fips_agents_cli.tools.patching import (
    AGENT_FILE_CATEGORIES,
    AGENT_NEVER_PATCH,
    MCP_FILE_CATEGORIES,
    MCP_NEVER_PATCH,
    discover_manifest_categories,
    get_categories_for_type,
    get_project_type,
)
from fips_agents_cli.tools.validation import find_fips_project_root

# ---------------------------------------------------------------------------
# Unit tests — pure helpers
# ---------------------------------------------------------------------------


class TestGetProjectType:
    def test_reads_type_from_template_info(self):
        assert get_project_type({"template": {"type": "agent"}}) == "agent"

    def test_defaults_to_mcp_server_when_missing(self):
        # Backwards compat: pre-#13 projects had no template.type
        assert get_project_type({"template": {"url": "x"}}) == "mcp-server"
        assert get_project_type({}) == "mcp-server"


class TestGetCategoriesForType:
    def test_mcp_server(self):
        cats, never = get_categories_for_type("mcp-server")
        assert cats is MCP_FILE_CATEGORIES
        assert never is MCP_NEVER_PATCH

    @pytest.mark.parametrize("project_type", ["agent", "workflow"])
    def test_agent_and_workflow_share_categories(self, project_type):
        cats, never = get_categories_for_type(project_type)
        assert cats is AGENT_FILE_CATEGORIES
        assert never is AGENT_NEVER_PATCH

    @pytest.mark.parametrize("project_type", ["gateway", "ui", "sandbox", "bogus"])
    def test_unsupported_types_raise(self, project_type):
        with pytest.raises(ValueError, match=project_type):
            get_categories_for_type(project_type)

    def test_agent_categories_have_no_framework_language(self):
        # Per project convention: avoid "framework" in user-facing strings
        for category, config in AGENT_FILE_CATEGORIES.items():
            assert "framework" not in category.lower()
            assert "framework" not in config["description"].lower()


class TestMcpCategoryPatterns:
    """Patterns for MCP categories must match the files the template ships.

    Regression tests for issue #42: the original `core` patterns had a literal
    space in `src/*/__ init__.py`, and `claude` was missing entirely.
    """

    def test_core_init_pattern_has_no_space_typo(self):
        # `src/*/__init__.py` must NOT have a space — that pattern matched nothing
        patterns = MCP_FILE_CATEGORIES["core"]["patterns"]
        assert "src/*/__init__.py" in patterns
        assert not any(" " in p for p in patterns), patterns

    def test_core_init_pattern_matches_real_init_files(self):
        # Path.match validates the fix — a real package __init__.py matches now
        assert Path("src/core/__init__.py").match("src/*/__init__.py")
        assert Path("src/middleware/__init__.py").match("src/*/__init__.py")

    def test_core_includes_main_entry_point(self):
        # src/main.py is the MCP server entry point and ships with the template
        assert "src/main.py" in MCP_FILE_CATEGORIES["core"]["patterns"]

    def test_claude_category_exists_for_mcp(self):
        # MCP template ships .claude/commands/*.md — must be patchable
        assert "claude" in MCP_FILE_CATEGORIES
        patterns = MCP_FILE_CATEGORIES["claude"]["patterns"]
        assert ".claude/commands/**/*" in patterns
        assert MCP_FILE_CATEGORIES["claude"]["ask_before_patch"] is False

    def test_docs_includes_recently_added_files(self):
        # AGENTS.md, CONTRIBUTING.md and friends ship in the MCP template root
        patterns = MCP_FILE_CATEGORIES["docs"]["patterns"]
        for expected in [
            "AGENTS.md",
            "CONTRIBUTING.md",
            "DEVELOPMENT_PROCESS.md",
            "OPENSHIFT_DEPLOYMENT.md",
        ]:
            assert expected in patterns, f"{expected} missing from MCP docs patterns"

    def test_build_includes_root_dotfiles(self):
        patterns = MCP_FILE_CATEGORIES["build"]["patterns"]
        for expected in [".dockerignore", ".gitignore", ".gitleaks.toml"]:
            assert expected in patterns, f"{expected} missing from MCP build patterns"


class TestAgentCategoryPatterns:
    """Regression tests for issue #42: agent template gaps."""

    def test_claude_category_includes_rules(self):
        # Agent template ships .claude/rules/agent-development.md
        patterns = AGENT_FILE_CATEGORIES["claude"]["patterns"]
        assert ".claude/commands/**/*" in patterns
        assert ".claude/rules/**/*" in patterns


class TestEvalsCategory:
    """Issue #44: agent / workflow templates ship a full eval harness
    that needs its own patch category, separated from user-authored
    test plans and fixtures.
    """

    def test_evals_category_only_in_agent_categories(self):
        assert "evals" in AGENT_FILE_CATEGORIES
        assert "evals" not in MCP_FILE_CATEGORIES

    def test_evals_patterns_cover_harness_files(self):
        patterns = AGENT_FILE_CATEGORIES["evals"]["patterns"]
        for expected in [
            "evals/__init__.py",
            "evals/assertions.py",
            "evals/discovery.py",
            "evals/mock_factory.py",
            "evals/run_evals.py",
            "evals/README.md",
        ]:
            assert expected in patterns, f"{expected} missing from evals patterns"

    def test_evals_asks_before_patch(self):
        # Users may have customized the harness — show diffs and confirm
        assert AGENT_FILE_CATEGORIES["evals"]["ask_before_patch"] is True

    def test_user_authored_eval_inputs_are_never_patched(self):
        # The user owns evals.yaml (the test plan) and evals/fixtures/ (data)
        assert "evals/evals.yaml" in AGENT_NEVER_PATCH
        assert "evals/fixtures/**" in AGENT_NEVER_PATCH


class TestAgentNeverPatchExtensions:
    """`add` writes user-customized files into well-known directories.
    Those paths must be in NEVER_PATCH so a future pattern broadening
    cannot clobber them.
    """

    @pytest.mark.parametrize(
        "expected",
        [
            "tools/**",
            "examples/**",
            "prompts/**",
            "rules/**",
            "skills/**",
            ".memoryhub.yaml",
        ],
    )
    def test_user_directory_is_never_patched(self, expected):
        assert expected in AGENT_NEVER_PATCH


class TestShouldNeverPatch:
    """Issue #47: bare patterns like "README.md" used to match nested
    files (evals/README.md, docs/foo/README.md) because Path.match
    matches from the right. The matcher now anchors to the full path
    via fnmatch.fnmatchcase.
    """

    @pytest.mark.parametrize(
        "rel_path,expected",
        [
            # The bug from #47 — bare README.md must NOT lock out nested ones
            ("evals/README.md", False),
            ("docs/sub/README.md", False),
            # The project-root README.md must still be protected
            ("README.md", True),
            # Negative: a non-README file is unaffected
            ("evals/discovery.py", False),
        ],
    )
    def test_bare_filename_matches_only_root(self, rel_path, expected):
        # Minimal never_patch list — just the bare filename
        assert patching._should_never_patch(Path(rel_path), ["README.md"]) is expected

    @pytest.mark.parametrize(
        "rel_path,expected",
        [
            ("agent.yaml", True),
            ("not-agent.yaml", False),
            ("chart/values.yaml", True),
            ("chart/templates/values.yaml", False),
            ("src/agent.py", True),
            ("src/agents.py", False),
        ],
    )
    def test_exact_path_patterns(self, rel_path, expected):
        patterns = ["agent.yaml", "chart/values.yaml", "src/agent.py"]
        assert patching._should_never_patch(Path(rel_path), patterns) is expected

    @pytest.mark.parametrize(
        "rel_path,expected",
        [
            ("src/fipsagents/foo.py", True),
            ("src/fipsagents/sub/foo.py", True),
            ("src/fipsagents/sub/deeper/foo.py", True),
            ("src/other/foo.py", False),
        ],
    )
    def test_recursive_glob(self, rel_path, expected):
        assert patching._should_never_patch(Path(rel_path), ["src/fipsagents/**"]) is expected

    @pytest.mark.parametrize(
        "rel_path,expected",
        [
            # tests/**/*.py requires at least one nested directory
            ("tests/foo/bar.py", True),
            ("tests/foo/bar/baz.py", True),
            ("tests/foo.py", False),  # No nested dir
            ("other/foo.py", False),
        ],
    )
    def test_tests_recursive_pattern(self, rel_path, expected):
        assert patching._should_never_patch(Path(rel_path), ["tests/**/*.py"]) is expected

    @pytest.mark.parametrize(
        "rel_path,expected",
        [
            (".env", True),
            (".env.local", True),
            (".env.production", True),
            ("env", False),
            ("not-.env", False),
        ],
    )
    def test_dotenv_glob(self, rel_path, expected):
        assert patching._should_never_patch(Path(rel_path), [".env*"]) is expected

    def test_empty_pattern_list_never_matches(self):
        assert patching._should_never_patch(Path("anything.py"), []) is False

    def test_real_never_patch_lists_protect_root_readme_only(self):
        # Regression: the actual constants must not lock out evals/README.md
        # (which the agent template ships as part of the eval harness).
        assert patching._should_never_patch(Path("README.md"), AGENT_NEVER_PATCH) is True
        assert patching._should_never_patch(Path("evals/README.md"), AGENT_NEVER_PATCH) is False
        # Same expectation for the MCP list
        assert patching._should_never_patch(Path("README.md"), MCP_NEVER_PATCH) is True
        assert patching._should_never_patch(Path("docs/README.md"), MCP_NEVER_PATCH) is False


# ---------------------------------------------------------------------------
# Unit tests — find_fips_project_root walks up to .template-info
# ---------------------------------------------------------------------------


class TestFindFipsProjectRoot:
    def test_returns_none_when_no_template_info(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert find_fips_project_root() is None

    def test_finds_template_info_in_cwd(self, tmp_path, monkeypatch):
        info = {"template": {"type": "agent"}}
        (tmp_path / ".template-info").write_text(json.dumps(info))
        monkeypatch.chdir(tmp_path)

        result = find_fips_project_root()
        assert result is not None
        root, template_info = result
        assert root == tmp_path
        assert template_info == info

    def test_walks_up_to_parent(self, tmp_path, monkeypatch):
        info = {"template": {"type": "mcp-server"}}
        (tmp_path / ".template-info").write_text(json.dumps(info))
        nested = tmp_path / "src" / "tools"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        result = find_fips_project_root()
        assert result is not None
        root, _ = result
        assert root == tmp_path


# ---------------------------------------------------------------------------
# Unit tests — .fips-template.yaml manifest loader (issue #45)
# ---------------------------------------------------------------------------


def _write_manifest(template_root: Path, body: str) -> Path:
    """Drop a `.fips-template.yaml` file into a template root for testing."""
    manifest = template_root / ".fips-template.yaml"
    manifest.write_text(body)
    return manifest


class TestLoadTemplateManifest:
    def test_returns_none_when_manifest_absent(self, tmp_path):
        # Legacy template — no manifest, no warning, falls through silently
        assert patching._load_template_manifest(tmp_path) is None

    def test_loads_well_formed_manifest(self, tmp_path):
        _write_manifest(
            tmp_path,
            "schema_version: 1\npatch:\n  categories: {}\n  never_patch: []\n",
        )
        manifest = patching._load_template_manifest(tmp_path)
        assert manifest is not None
        assert manifest["schema_version"] == 1

    def test_returns_none_on_malformed_yaml(self, tmp_path, capsys):
        _write_manifest(tmp_path, "this is: : not valid: yaml: at: all:\n  - [bad")
        assert patching._load_template_manifest(tmp_path) is None
        # The user is told why we fell back — no silent surprise
        captured = capsys.readouterr()
        assert "Could not parse" in captured.out or "fall" in captured.out.lower()

    def test_returns_none_when_root_is_not_mapping(self, tmp_path, capsys):
        _write_manifest(tmp_path, "- just a list\n- nothing useful\n")
        assert patching._load_template_manifest(tmp_path) is None

    def test_returns_none_for_unsupported_schema_version(self, tmp_path, capsys):
        _write_manifest(tmp_path, "schema_version: 99\npatch: {}\n")
        assert patching._load_template_manifest(tmp_path) is None
        captured = capsys.readouterr()
        assert "schema_version" in captured.out

    def test_returns_none_when_schema_version_missing(self, tmp_path):
        # Explicit contract — no schema_version means the file is not for us
        _write_manifest(tmp_path, "patch:\n  categories: {}\n")
        assert patching._load_template_manifest(tmp_path) is None


class TestCategoriesFromManifest:
    def test_extracts_categories_and_never_patch(self):
        manifest = {
            "schema_version": 1,
            "patch": {
                "categories": {
                    "chart": {
                        "description": "Helm chart templates",
                        "patterns": ["chart/templates/**/*"],
                        "ask_before_patch": True,
                    },
                    "claude": {
                        "description": "Claude Code commands",
                        "patterns": [".claude/commands/**/*"],
                        "ask_before_patch": False,
                    },
                },
                "never_patch": ["src/agent.py", "agent.yaml"],
            },
        }
        result = patching._categories_from_manifest(manifest)
        assert result is not None
        cats, never = result
        assert set(cats.keys()) == {"chart", "claude"}
        assert cats["chart"]["patterns"] == ["chart/templates/**/*"]
        assert cats["chart"]["ask_before_patch"] is True
        assert cats["claude"]["ask_before_patch"] is False
        assert never == ["src/agent.py", "agent.yaml"]

    def test_fills_in_default_description(self):
        # description is optional; defaults to the category name
        manifest = {
            "patch": {
                "categories": {
                    "build": {"patterns": ["Makefile"]},
                },
                "never_patch": [],
            },
        }
        result = patching._categories_from_manifest(manifest)
        assert result is not None
        cats, _ = result
        assert cats["build"]["description"] == "build"

    def test_defaults_ask_before_patch_to_false(self):
        manifest = {
            "patch": {
                "categories": {
                    "build": {"patterns": ["Makefile"]},
                },
                "never_patch": [],
            },
        }
        cats, _ = patching._categories_from_manifest(manifest)
        assert cats["build"]["ask_before_patch"] is False

    def test_defaults_never_patch_to_empty(self):
        manifest = {"patch": {"categories": {}}}
        result = patching._categories_from_manifest(manifest)
        assert result is not None
        _, never = result
        assert never == []

    def test_returns_none_when_patch_block_missing(self):
        assert patching._categories_from_manifest({"schema_version": 1}) is None

    def test_returns_none_when_categories_not_a_mapping(self):
        manifest = {"patch": {"categories": ["chart", "build"]}}
        assert patching._categories_from_manifest(manifest) is None

    def test_returns_none_when_patterns_missing(self):
        manifest = {
            "patch": {
                "categories": {"build": {"description": "no patterns"}},
            },
        }
        assert patching._categories_from_manifest(manifest) is None

    def test_returns_none_when_pattern_is_not_a_string(self):
        manifest = {
            "patch": {
                "categories": {"build": {"patterns": ["Makefile", 42]}},
            },
        }
        assert patching._categories_from_manifest(manifest) is None


class TestResolveCategories:
    """`_resolve_categories` is the integration point: prefer the manifest
    when valid, otherwise fall back to the constants keyed by project type.
    """

    def test_falls_back_to_constants_when_manifest_absent(self, tmp_path):
        info = {"template": {"type": "agent"}}
        cats, never = patching._resolve_categories(tmp_path, info)
        assert cats is patching.AGENT_FILE_CATEGORIES
        assert never is patching.AGENT_NEVER_PATCH

    def test_manifest_overrides_constants(self, tmp_path):
        _write_manifest(
            tmp_path,
            """\
schema_version: 1
patch:
  categories:
    only-this:
      description: A custom category
      patterns:
        - foo/bar.txt
      ask_before_patch: true
  never_patch:
    - keep/me.yaml
""",
        )
        info = {"template": {"type": "agent"}}
        cats, never = patching._resolve_categories(tmp_path, info)
        assert set(cats.keys()) == {"only-this"}
        assert cats["only-this"]["description"] == "A custom category"
        assert never == ["keep/me.yaml"]

    def test_falls_back_when_manifest_is_malformed(self, tmp_path, capsys):
        # Manifest exists but is missing required fields
        _write_manifest(tmp_path, "schema_version: 1\npatch:\n  not_categories: 42\n")
        info = {"template": {"type": "mcp-server"}}
        cats, never = patching._resolve_categories(tmp_path, info)
        assert cats is patching.MCP_FILE_CATEGORIES
        assert never is patching.MCP_NEVER_PATCH
        captured = capsys.readouterr()
        assert "missing required fields" in captured.out

    def test_manifest_works_for_unsupported_project_type(self, tmp_path):
        # `gateway` raises in get_categories_for_type, so before #45 it
        # was unpatchable. With a manifest the template can opt in.
        _write_manifest(
            tmp_path,
            """\
schema_version: 1
patch:
  categories:
    chart:
      patterns: [chart/templates/**/*]
  never_patch: []
""",
        )
        info = {"template": {"type": "gateway"}}
        cats, never = patching._resolve_categories(tmp_path, info)
        assert "chart" in cats
        assert never == []


class TestPatchUnsupportedForProjectType:
    """Issue #50: when the project type has no built-in category set and
    no usable manifest, _resolve_categories raises a clean exception
    that the CLI layer can catch — no Python tracebacks for sandbox
    users (today) or for any future template that hasn't shipped a
    manifest yet.
    """

    @pytest.mark.parametrize("project_type", ["sandbox", "bogus"])
    def test_resolve_categories_raises_when_no_manifest_and_unsupported_type(
        self, tmp_path, project_type
    ):
        # No manifest in tmp_path, project type has no constants — must raise
        info = {"template": {"type": project_type}}
        with pytest.raises(patching.PatchUnsupportedForProjectType, match=project_type):
            patching._resolve_categories(tmp_path, info)

    def test_resolve_categories_raises_when_manifest_malformed_and_unsupported(self, tmp_path):
        # Manifest present but useless (missing required fields). Falls back
        # to constants which raise — that ValueError must convert to the
        # cleaner PatchUnsupportedForProjectType.
        _write_manifest(tmp_path, "schema_version: 1\npatch:\n  not_categories: 42\n")
        info = {"template": {"type": "sandbox"}}
        with pytest.raises(patching.PatchUnsupportedForProjectType, match="sandbox"):
            patching._resolve_categories(tmp_path, info)

    def test_error_message_mentions_manifest_filename(self, tmp_path):
        info = {"template": {"type": "sandbox"}}
        try:
            patching._resolve_categories(tmp_path, info)
        except patching.PatchUnsupportedForProjectType as e:
            assert ".fips-template.yaml" in str(e)
        else:  # pragma: no cover
            pytest.fail("expected PatchUnsupportedForProjectType")

    def test_supported_types_still_work_without_manifest(self, tmp_path):
        # Regression: agent / mcp-server / workflow must still fall back to
        # constants without the new exception interfering.
        for project_type in ("agent", "workflow", "mcp-server"):
            info = {"template": {"type": project_type}}
            cats, _ = patching._resolve_categories(tmp_path, info)
            assert cats  # non-empty


# ---------------------------------------------------------------------------
# Unit tests — _clone_template_for_patch handles subdirs
# ---------------------------------------------------------------------------


class TestCloneTemplateForPatch:
    def test_standalone_repo_returns_clone_root(self, tmp_path, monkeypatch):
        def fake_clone(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "Makefile").write_text("# fake\n")
            return "abc123"

        monkeypatch.setattr(patching, "clone_template", fake_clone)

        info = {"template": {"url": "https://example.com/repo.git"}}
        result = patching._clone_template_for_patch(info, tmp_path)
        assert result == tmp_path
        assert (result / "Makefile").exists()

    def test_monorepo_subdir_returns_subdir_root(self, tmp_path, monkeypatch):
        def fake_clone(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            sub = target_path / "templates" / "agent-loop"
            sub.mkdir(parents=True)
            (sub / "Makefile").write_text("# agent makefile\n")
            (target_path / "README.md").write_text("# monorepo root\n")
            return "abc123"

        monkeypatch.setattr(patching, "clone_template", fake_clone)

        info = {
            "template": {
                "url": "https://example.com/agent-template",
                "subdir": "templates/agent-loop",
            }
        }
        result = patching._clone_template_for_patch(info, tmp_path)
        assert result == tmp_path / "templates" / "agent-loop"
        assert (result / "Makefile").exists()
        # Crucially, monorepo-root files are NOT visible to the patch comparator
        assert not (result / "README.md").exists()

    def test_missing_subdir_raises(self, tmp_path, monkeypatch):
        def fake_clone(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            return "abc123"

        monkeypatch.setattr(patching, "clone_template", fake_clone)

        info = {
            "template": {
                "url": "https://example.com/agent-template",
                "subdir": "templates/missing",
            }
        }
        with pytest.raises(FileNotFoundError, match="templates/missing"):
            patching._clone_template_for_patch(info, tmp_path)


# ---------------------------------------------------------------------------
# E2E test — `patch check` on a freshly-scaffolded agent project
# ---------------------------------------------------------------------------


def _make_fake_agent_template(
    template_root: Path, makefile_body: str = "# template makefile\n"
) -> None:
    """Build a minimal agent-loop template tree under template_root."""
    template_root.mkdir(parents=True, exist_ok=True)
    (template_root / "Makefile").write_text(makefile_body)
    (template_root / "Containerfile").write_text("FROM ubi9\n")
    (template_root / "AGENTS.md").write_text("# template\n")

    chart = template_root / "chart"
    (chart / "templates").mkdir(parents=True)
    (chart / "Chart.yaml").write_text("name: agent-template\nversion: 0.1.0\n")
    (chart / "values.yaml").write_text("image: agent-template\n")
    (chart / "templates" / "deployment.yaml").write_text("# deploy\n")

    claude = template_root / ".claude" / "commands"
    claude.mkdir(parents=True)
    (claude / "plan-agent.md").write_text("# plan command\n")


def _make_fake_agent_project(project_root: Path) -> None:
    """Build a minimal scaffolded agent project, simulating create-agent output."""
    project_root.mkdir(parents=True, exist_ok=True)
    # Match the template baseline so most files are unchanged
    _make_fake_agent_template(project_root)
    # User-customized values (must never be patched)
    (project_root / "chart" / "values.yaml").write_text("image: my-agent\n")
    (project_root / "src").mkdir()
    (project_root / "src" / "agent.py").write_text("# user code\n")
    (project_root / "agent.yaml").write_text("model:\n  name: my-model\n")
    (project_root / "pyproject.toml").write_text('[project]\nname = "my-agent"\n')

    info = {
        "generator": {"tool": "fips-agents-cli", "version": "0.0.0-test"},
        "template": {
            "url": "https://github.com/fips-agents/agent-template",
            "type": "agent",
            "subdir": "templates/agent-loop",
            "commit": "abcdef123456",
            "full_commit": "abcdef1234567890",
        },
        "project": {"name": "my-agent", "created_at": "2026-01-01T00:00:00+00:00"},
    }
    (project_root / ".template-info").write_text(json.dumps(info, indent=2))


class TestPatchAgentE2E:
    """End-to-end: scaffolded agent project + `patch check` finds drift correctly."""

    @pytest.fixture
    def agent_project(self, tmp_path):
        project = tmp_path / "my-agent"
        _make_fake_agent_project(project)
        return project

    def test_patch_check_reports_no_drift_when_template_unchanged(
        self, agent_project, monkeypatch, cli_runner
    ):
        # Stub clone_template to drop the same content the project was scaffolded from
        def fake_clone(url, target_path, branch=None):
            sub = target_path / "templates" / "agent-loop"
            _make_fake_agent_template(sub)
            return "abcdef1234567890"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        monkeypatch.chdir(agent_project)

        result = cli_runner.invoke(cli, ["patch", "check"])
        assert result.exit_code == 0, result.output
        assert "up to date" in result.output

    def test_patch_check_reports_drift_in_agent_categories(
        self, agent_project, monkeypatch, cli_runner
    ):
        # Template's Makefile has changed since scaffold time → "build" should appear
        def fake_clone(url, target_path, branch=None):
            sub = target_path / "templates" / "agent-loop"
            _make_fake_agent_template(sub, makefile_body="# UPDATED template makefile\n")
            return "newcommit12345"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        monkeypatch.chdir(agent_project)

        result = cli_runner.invoke(cli, ["patch", "check"])
        assert result.exit_code == 0, result.output
        assert "Available Updates" in result.output
        assert "build" in result.output
        # Crucially, MCP-only categories must NOT appear for an agent project
        assert "generators" not in result.output
        assert "core" not in result.output

    def test_patch_chart_applies_change_to_agent_project(
        self, agent_project, monkeypatch, cli_runner
    ):
        # Template's chart/templates/deployment.yaml has changed
        def fake_clone(url, target_path, branch=None):
            sub = target_path / "templates" / "agent-loop"
            _make_fake_agent_template(sub)
            (sub / "chart" / "templates" / "deployment.yaml").write_text("# UPDATED deploy\n")
            return "newcommit12345"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        monkeypatch.chdir(agent_project)

        # `chart` has ask_before_patch=True, so use --skip-confirmation via `all`?
        # Simpler: invoke patch chart with `input="y\n"` to accept the diff
        result = cli_runner.invoke(cli, ["patch", "chart"], input="y\n")
        assert result.exit_code == 0, result.output

        # values.yaml is in NEVER_PATCH — must NOT be touched
        assert (agent_project / "chart" / "values.yaml").read_text() == "image: my-agent\n"
        # User's agent.py is also off-limits
        assert (agent_project / "src" / "agent.py").read_text() == "# user code\n"
        # The drifted template file should now match the template
        assert (
            agent_project / "chart" / "templates" / "deployment.yaml"
        ).read_text() == "# UPDATED deploy\n"

    def test_mcp_only_subcommand_rejected_in_agent_project(
        self, agent_project, monkeypatch, cli_runner
    ):
        # Running `patch generators` (MCP-only) inside an agent project must fail
        # with a clear, type-aware error message — no clone should happen.
        called = {"clone": False}

        def fake_clone(url, target_path, branch=None):
            called["clone"] = True
            return "x"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        monkeypatch.chdir(agent_project)

        result = cli_runner.invoke(cli, ["patch", "generators"])
        assert result.exit_code == 1
        assert "agent" in result.output
        assert "generators" in result.output
        # Must enumerate the available agent categories
        for cat in AGENT_FILE_CATEGORIES:
            assert cat in result.output

    def test_template_manifest_overrides_constants_in_check(
        self, agent_project, monkeypatch, cli_runner
    ):
        # When a template ships .fips-template.yaml, those categories
        # are what `patch check` reports — not the hardcoded constants.
        def fake_clone(url, target_path, branch=None):
            sub = target_path / "templates" / "agent-loop"
            _make_fake_agent_template(sub)
            # Drift a file the manifest's custom category covers
            (sub / "Makefile").write_text("# UPDATED via manifest category\n")
            (sub / ".fips-template.yaml").write_text("""\
schema_version: 1
patch:
  categories:
    template-managed:
      description: Template-managed scaffolding files
      patterns:
        - Makefile
        - Containerfile
      ask_before_patch: true
  never_patch:
    - chart/values.yaml
""")
            return "manifestcommit"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        monkeypatch.chdir(agent_project)

        result = cli_runner.invoke(cli, ["patch", "check"])
        assert result.exit_code == 0, result.output
        assert "Available Updates" in result.output
        # Manifest's category name surfaces
        assert "template-managed" in result.output
        # Built-in agent categories that are NOT in the manifest must NOT show
        assert "chart" not in result.output
        assert "claude" not in result.output


# ---------------------------------------------------------------------------
# E2E test — issue #50: graceful error when project type has no manifest
# ---------------------------------------------------------------------------


def _make_fake_sandbox_project(project_root: Path) -> None:
    """Build a minimal scaffolded sandbox project. Sandbox is the canonical
    'no manifest, no built-in category set' case today.
    """
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "Makefile").write_text("# sandbox makefile\n")
    (project_root / "pyproject.toml").write_text('[project]\nname = "my-sandbox"\n')

    info = {
        "generator": {"tool": "fips-agents-cli", "version": "0.0.0-test"},
        "template": {
            "url": "https://github.com/fips-agents/code-sandbox",
            "type": "sandbox",
            "commit": "abcdef123456",
            "full_commit": "abcdef1234567890",
        },
        "project": {"name": "my-sandbox", "created_at": "2026-01-01T00:00:00+00:00"},
    }
    (project_root / ".template-info").write_text(json.dumps(info, indent=2))


class TestPatchUnsupportedTypeE2E:
    """Issue #50: gateway / ui / sandbox projects whose template ships no
    manifest must produce clean errors, not Python tracebacks.

    Uses sandbox as the test subject because gateway / ui / agent / mcp
    all ship manifests as of v0.12.0 — sandbox is the only type still
    bare in the wild.
    """

    @pytest.fixture
    def sandbox_project(self, tmp_path):
        project = tmp_path / "my-sandbox"
        _make_fake_sandbox_project(project)
        return project

    def test_patch_check_exits_cleanly_with_helpful_message(
        self, sandbox_project, monkeypatch, cli_runner
    ):
        # Clone returns a bare template with no manifest — the worst case
        def fake_clone(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "Makefile").write_text("# upstream\n")
            return "deadbeef0000"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        monkeypatch.chdir(sandbox_project)

        result = cli_runner.invoke(cli, ["patch", "check"])
        assert result.exit_code == 1, result.output
        # No Python traceback escaped
        assert "Traceback" not in result.output
        # Clean message, mentions the project type and the manifest filename
        assert "sandbox" in result.output
        assert ".fips-template.yaml" in result.output

    def test_patch_category_exits_cleanly_with_helpful_message(
        self, sandbox_project, monkeypatch, cli_runner
    ):
        def fake_clone(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            return "deadbeef0000"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        monkeypatch.chdir(sandbox_project)

        # Use any registered subcommand — `chart` is fine, the failure mode
        # is "no built-in categories at all", not a category mismatch.
        result = cli_runner.invoke(cli, ["patch", "chart"])
        assert result.exit_code == 1, result.output
        assert "Traceback" not in result.output
        assert "sandbox" in result.output
        assert ".fips-template.yaml" in result.output

    def test_patch_all_exits_cleanly_with_helpful_message(
        self, sandbox_project, monkeypatch, cli_runner
    ):
        # `patch all` now falls back to discover_manifest_categories for
        # unsupported types — it clones to look for a manifest, but when
        # no manifest is found it exits cleanly (no ValueError traceback).
        def fake_clone(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            # No .fips-template.yaml — bare template
            return "x"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        monkeypatch.chdir(sandbox_project)

        result = cli_runner.invoke(cli, ["patch", "all"])
        assert result.exit_code == 1, result.output
        assert "Traceback" not in result.output
        assert "sandbox" in result.output
        assert ".fips-template.yaml" in result.output

    def test_manifest_makes_sandbox_patchable(self, sandbox_project, monkeypatch, cli_runner):
        # Once the sandbox template ships a manifest, `patch check` works
        # — this test future-proofs the fix.
        def fake_clone(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "Makefile").write_text("# upstream sandbox makefile\n")
            (target_path / ".fips-template.yaml").write_text("""\
schema_version: 1
patch:
  categories:
    build:
      patterns: [Makefile]
      ask_before_patch: true
  never_patch: []
""")
            return "deadbeef0000"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        monkeypatch.chdir(sandbox_project)

        result = cli_runner.invoke(cli, ["patch", "check"])
        assert result.exit_code == 0, result.output
        # Drift in build surfaces because the project's Makefile differs
        assert "build" in result.output


# ---------------------------------------------------------------------------
# Unit tests — discover_manifest_categories (issue #45 / agent-team support)
# ---------------------------------------------------------------------------


def _agent_team_template_info(**overrides) -> dict:
    """Return a realistic template_info dict for an agent-team project."""
    info = {
        "template": {
            "url": "https://github.com/fips-agents/agent-template",
            "type": "agent-team",
            "commit": "abc123",
            "full_commit": "abc1234567890abcdef",
        },
        "project": {"name": "test-team", "created_at": "2026-05-01T00:00:00+00:00"},
        "generator": {"tool": "fips-agents-cli", "version": "0.13.1"},
    }
    info["template"].update(overrides)
    return info


class TestDiscoverManifestCategories:
    def test_returns_category_names_from_valid_manifest(self, tmp_path, monkeypatch):
        """When the template ships a well-formed .fips-template.yaml,
        discover_manifest_categories returns the category names as a list."""

        def fake_clone(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / ".fips-template.yaml").write_text(
                "schema_version: 1\n"
                "patch:\n"
                "  categories:\n"
                "    docs:\n"
                "      description: Documentation files\n"
                "      patterns:\n"
                "        - CLAUDE.md\n"
                '        - "docs/**/*"\n'
                "      ask_before_patch: false\n"
                "    build:\n"
                "      description: Build files\n"
                "      patterns:\n"
                "        - Makefile\n"
                "      ask_before_patch: true\n"
                "    claude:\n"
                "      description: Claude commands\n"
                "      patterns:\n"
                '        - ".claude/commands/**/*"\n'
                "      ask_before_patch: false\n"
                "  never_patch:\n"
                '    - "src/**/*"\n'
            )
            return "abc123"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        info = _agent_team_template_info()
        result = discover_manifest_categories(info)

        assert result is not None
        assert set(result) == {"docs", "build", "claude"}

    def test_returns_none_when_manifest_absent(self, tmp_path, monkeypatch):
        """Legacy template with no .fips-template.yaml returns None."""

        def fake_clone(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "Makefile").write_text("# bare template\n")
            return "abc123"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        info = _agent_team_template_info()

        assert discover_manifest_categories(info) is None

    def test_returns_none_when_manifest_malformed(self, tmp_path, monkeypatch):
        """Manifest exists but is missing required fields (no patch.categories)."""

        def fake_clone(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / ".fips-template.yaml").write_text(
                "schema_version: 1\n" "patch:\n" "  not_categories: 42\n"
            )
            return "abc123"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        info = _agent_team_template_info()

        assert discover_manifest_categories(info) is None

    def test_returns_none_for_wrong_schema_version(self, monkeypatch):
        """Manifest with unsupported schema_version returns None."""

        def fake_clone(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / ".fips-template.yaml").write_text(
                "schema_version: 99\n" "patch:\n" "  categories: {}\n"
            )
            return "abc123"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        info = _agent_team_template_info()

        assert discover_manifest_categories(info) is None

    def test_respects_subdir_in_template_info(self, monkeypatch):
        """When template_info declares a subdir, the manifest is read
        from the subdirectory, not the clone root."""

        def fake_clone(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            sub = target_path / "templates" / "agent-team"
            sub.mkdir(parents=True)
            (sub / ".fips-template.yaml").write_text(
                "schema_version: 1\n"
                "patch:\n"
                "  categories:\n"
                "    docs:\n"
                "      patterns: [CLAUDE.md]\n"
                "  never_patch: []\n"
            )
            return "abc123"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        info = _agent_team_template_info(subdir="templates/agent-team")

        result = discover_manifest_categories(info)
        assert result == ["docs"]


# ---------------------------------------------------------------------------
# E2E test — `patch all` fallback to manifest for manifest-only project types
# ---------------------------------------------------------------------------


def _make_fake_agent_team_project(project_root: Path) -> None:
    """Build a minimal scaffolded agent-team project. Agent-team is a
    manifest-only type — no built-in category set in the CLI."""
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "Makefile").write_text("# team makefile\n")
    (project_root / "CLAUDE.md").write_text("# team CLAUDE\n")

    claude_cmds = project_root / ".claude" / "commands"
    claude_cmds.mkdir(parents=True)
    (claude_cmds / "plan.md").write_text("# plan\n")

    info = _agent_team_template_info()
    (project_root / ".template-info").write_text(json.dumps(info, indent=2))


class TestPatchAllManifestFallback:
    """When `patch all` encounters a project type with no built-in category
    set (like agent-team), it falls back to discover_manifest_categories
    to enumerate the categories from the template's .fips-template.yaml.
    """

    @pytest.fixture
    def agent_team_project(self, tmp_path):
        project = tmp_path / "test-team"
        _make_fake_agent_team_project(project)
        return project

    def test_patch_all_processes_manifest_categories(
        self, agent_team_project, monkeypatch, cli_runner
    ):
        """patch all --dry-run discovers categories from the manifest and
        processes each one without exiting with an error."""

        def fake_clone(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            # Lay down template files that match the manifest's patterns
            (target_path / "Makefile").write_text("# UPDATED team makefile\n")
            (target_path / "CLAUDE.md").write_text("# UPDATED CLAUDE\n")
            claude_cmds = target_path / ".claude" / "commands"
            claude_cmds.mkdir(parents=True)
            (claude_cmds / "plan.md").write_text("# UPDATED plan\n")
            # Ship the manifest
            (target_path / ".fips-template.yaml").write_text(
                "schema_version: 1\n"
                "patch:\n"
                "  categories:\n"
                "    docs:\n"
                "      description: Documentation files\n"
                "      patterns:\n"
                "        - CLAUDE.md\n"
                "      ask_before_patch: false\n"
                "    build:\n"
                "      description: Build files\n"
                "      patterns:\n"
                "        - Makefile\n"
                "      ask_before_patch: false\n"
                "    claude:\n"
                "      description: Claude commands\n"
                "      patterns:\n"
                '        - ".claude/commands/**/*"\n'
                "      ask_before_patch: false\n"
                "  never_patch:\n"
                '    - "src/**/*"\n'
            )
            return "abc123"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        monkeypatch.chdir(agent_team_project)

        result = cli_runner.invoke(cli, ["patch", "all", "--dry-run", "--skip-confirmation"])
        assert result.exit_code == 0, result.output
        # The manifest fallback message should appear
        assert "No built-in categories" in result.output
        assert "checking template manifest" in result.output
        # All three categories are processed
        for cat in ("docs", "build", "claude"):
            assert f"Processing category: {cat}" in result.output

    def test_patch_all_exits_cleanly_when_manifest_also_missing(
        self, agent_team_project, monkeypatch, cli_runner
    ):
        """When the project type has no built-in categories AND the template
        ships no manifest, patch all exits with a clean error."""

        def fake_clone(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            # No .fips-template.yaml
            return "abc123"

        monkeypatch.setattr(patching, "clone_template", fake_clone)
        monkeypatch.chdir(agent_team_project)

        result = cli_runner.invoke(cli, ["patch", "all", "--skip-confirmation"])
        assert result.exit_code == 1, result.output
        assert "Traceback" not in result.output
        assert "agent-team" in result.output
        assert ".fips-template.yaml" in result.output
