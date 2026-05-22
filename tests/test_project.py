"""Tests for project customization utilities."""

import pytest
import tomlkit

from fips_agents_cli.tools.project import (
    customize_agent_project,
    customize_agent_team_project,
    customize_go_project,
    to_module_name,
    validate_project_name,
)


class TestProjectValidation:
    """Tests for project name validation."""

    def test_validate_valid_names(self):
        """Test that valid project names pass validation."""
        valid_names = [
            "test",
            "test-server",
            "test_server",
            "myproject",
            "a",
            "test123",
            "test-123-server",
        ]

        for name in valid_names:
            is_valid, error = validate_project_name(name)
            assert is_valid, f"Expected {name} to be valid, got error: {error}"
            assert error is None

    def test_validate_invalid_names(self):
        """Test that invalid project names fail validation."""
        invalid_names = [
            "Test",  # Uppercase
            "TEST",  # All uppercase
            "test@server",  # Special char
            "test.server",  # Period
            "123test",  # Starts with number
            "-test",  # Starts with hyphen
            "_test",  # Starts with underscore
            "",  # Empty
        ]

        for name in invalid_names:
            is_valid, error = validate_project_name(name)
            assert not is_valid, f"Expected {name} to be invalid"
            assert error is not None

    def test_validate_empty_name(self):
        """Test that empty project name returns appropriate error."""
        is_valid, error = validate_project_name("")
        assert not is_valid
        assert "empty" in error.lower()


class TestModuleNameConversion:
    """Tests for converting project names to module names."""

    def test_hyphens_to_underscores(self):
        """Test that hyphens are converted to underscores."""
        assert to_module_name("test-server") == "test_server"
        assert to_module_name("my-mcp-server") == "my_mcp_server"
        assert to_module_name("test-123-server") == "test_123_server"

    def test_underscores_unchanged(self):
        """Test that existing underscores remain unchanged."""
        assert to_module_name("test_server") == "test_server"
        assert to_module_name("my_mcp_server") == "my_mcp_server"

    def test_no_hyphens(self):
        """Test that names without hyphens are unchanged."""
        assert to_module_name("testserver") == "testserver"
        assert to_module_name("myproject") == "myproject"

    def test_mixed_hyphens_underscores(self):
        """Test names with both hyphens and underscores."""
        assert to_module_name("test-server_name") == "test_server_name"
        assert to_module_name("my_test-server") == "my_test_server"


class TestCustomizeAgentProject:
    """Tests for agent project customization."""

    def _create_agent_template(self, path):
        """Create a minimal agent template structure for testing."""
        path.mkdir(parents=True, exist_ok=True)

        (path / "pyproject.toml").write_text(
            '[build-system]\nrequires = ["setuptools>=68"]\n\n'
            '[project]\nname = "agent-template"\nversion = "0.1.0"\n'
        )
        (path / "Makefile").write_text(
            "PROJECT     ?= agent-template\nIMAGE_NAME  ?= agent-template\n"
        )
        (path / "AGENTS.md").write_text("# agent-template\n\nA BaseAgent built on the template.\n")
        (path / "Containerfile").write_text(
            'LABEL io.opencontainers.image.title="agent-template"\n'
        )

        chart = path / "chart"
        chart.mkdir()
        (chart / "Chart.yaml").write_text("name: agent-template\nversion: 0.1.0\n")
        (chart / "values.yaml").write_text("image:\n  repository: agent-template\n")

    def test_updates_pyproject_name(self, temp_dir):
        """Test that pyproject.toml name field is updated."""
        project = temp_dir / "my-agent"
        self._create_agent_template(project)

        customize_agent_project(project, "my-agent")

        pyproject = tomlkit.parse((project / "pyproject.toml").read_text())
        assert pyproject["project"]["name"] == "my-agent"

    def test_updates_chart_name(self, temp_dir):
        """Test that chart/Chart.yaml name is updated."""
        project = temp_dir / "my-agent"
        self._create_agent_template(project)

        customize_agent_project(project, "my-agent")

        content = (project / "chart" / "Chart.yaml").read_text()
        assert "name: my-agent" in content
        assert "agent-template" not in content

    def test_updates_values_image(self, temp_dir):
        """Test that chart/values.yaml image repository is updated."""
        project = temp_dir / "my-agent"
        self._create_agent_template(project)

        customize_agent_project(project, "my-agent")

        content = (project / "chart" / "values.yaml").read_text()
        assert "repository: my-agent" in content
        assert "agent-template" not in content

    def test_updates_makefile(self, temp_dir):
        """Test that Makefile IMAGE_NAME and PROJECT are updated."""
        project = temp_dir / "my-agent"
        self._create_agent_template(project)

        customize_agent_project(project, "my-agent")

        content = (project / "Makefile").read_text()
        assert "IMAGE_NAME  ?= my-agent" in content
        assert "PROJECT     ?= my-agent" in content
        assert "agent-template" not in content

    def test_updates_agents_md(self, temp_dir):
        """Test that AGENTS.md heading is updated."""
        project = temp_dir / "my-agent"
        self._create_agent_template(project)

        customize_agent_project(project, "my-agent")

        content = (project / "AGENTS.md").read_text()
        assert "# my-agent" in content
        assert "agent-template" not in content

    def test_updates_containerfile(self, temp_dir):
        """Test that Containerfile image title label is updated."""
        project = temp_dir / "my-agent"
        self._create_agent_template(project)

        customize_agent_project(project, "my-agent")

        content = (project / "Containerfile").read_text()
        assert 'image.title="my-agent"' in content
        assert "agent-template" not in content

    def test_updates_helm_helpers(self, temp_dir):
        """Test that Helm _helpers.tpl define names are updated."""
        project = temp_dir / "my-agent"
        self._create_agent_template(project)
        templates_dir = project / "chart" / "templates"
        templates_dir.mkdir(parents=True)
        (templates_dir / "_helpers.tpl").write_text(
            '{{- define "agent-template.name" -}}\n'
            '{{- define "agent-template.fullname" -}}\n'
            '{{- define "agent-template.labels" -}}\n'
        )

        customize_agent_project(project, "my-agent")

        content = (templates_dir / "_helpers.tpl").read_text()
        assert "agent-template" not in content
        assert '"my-agent.name"' in content
        assert '"my-agent.fullname"' in content

    def test_updates_deploy_sh(self, temp_dir):
        """Test that deploy.sh agent-template references are updated."""
        project = temp_dir / "my-agent"
        self._create_agent_template(project)
        (project / "deploy.sh").write_text("helm upgrade --install agent-template chart/\n")

        customize_agent_project(project, "my-agent")

        content = (project / "deploy.sh").read_text()
        assert "agent-template" not in content

    def test_replaces_owner_repo_with_github(self, temp_dir):
        """Test that OWNER/REPO is replaced with github_repo when provided."""
        project = temp_dir / "my-agent"
        self._create_agent_template(project)
        (project / "Containerfile").write_text(
            'LABEL io.opencontainers.image.title="agent-template"\n'
            '      io.opencontainers.image.source="https://github.com/OWNER/REPO"\n'
        )

        customize_agent_project(project, "my-agent", github_repo="rdwj/my-agent")

        content = (project / "Containerfile").read_text()
        assert "OWNER/REPO" not in content
        assert "rdwj/my-agent" in content

    def test_replaces_owner_repo_without_github(self, temp_dir):
        """Test that OWNER/REPO gets a helpful placeholder when no github_repo."""
        project = temp_dir / "my-agent"
        self._create_agent_template(project)
        (project / "Containerfile").write_text(
            'LABEL io.opencontainers.image.source="https://github.com/OWNER/REPO"\n'
        )

        customize_agent_project(project, "my-agent")

        content = (project / "Containerfile").read_text()
        assert "OWNER/REPO" not in content
        assert "OWNER/my-agent" in content

    def test_missing_pyproject_raises_error(self, temp_dir):
        """Test that missing pyproject.toml raises FileNotFoundError."""
        project = temp_dir / "my-agent"
        project.mkdir()

        with pytest.raises(FileNotFoundError):
            customize_agent_project(project, "my-agent")

    def test_missing_optional_files_no_error(self, temp_dir):
        """Test that missing optional files (chart, Makefile, etc.) don't cause errors."""
        project = temp_dir / "my-agent"
        project.mkdir()
        # Only create pyproject.toml — everything else is optional
        (project / "pyproject.toml").write_text('[project]\nname = "agent-template"\n')

        # Should not raise
        customize_agent_project(project, "my-agent")

        pyproject = tomlkit.parse((project / "pyproject.toml").read_text())
        assert pyproject["project"]["name"] == "my-agent"


class TestCustomizeGoProject:
    """Tests for Go project customization."""

    def _create_go_template(self, path, sentinel="gateway-template"):
        """Create a minimal Go template structure for testing."""
        path.mkdir(parents=True, exist_ok=True)

        (path / "go.mod").write_text(
            f"module github.com/redhat-ai-americas/{sentinel}\n\ngo 1.22\n"
        )
        (path / "Makefile").write_text(f"PROJECT     ?= {sentinel}\nIMAGE_NAME  ?= {sentinel}\n")
        (path / "Containerfile").write_text(f'LABEL io.opencontainers.image.title="{sentinel}"\n')
        (path / "README.md").write_text(f"# {sentinel}\n\nAn API gateway.\n")
        (path / "CLAUDE.md").write_text(f"# {sentinel}\n\nDevelopment guide.\n")

        chart = path / "chart"
        chart.mkdir()
        (chart / "Chart.yaml").write_text(f"name: {sentinel}\nversion: 0.1.0\n")
        (chart / "values.yaml").write_text(f"image:\n  repository: {sentinel}\n")

        templates = chart / "templates"
        templates.mkdir()
        (templates / "_helpers.tpl").write_text(
            f'{{{{- define "{sentinel}.name" -}}}}\n{sentinel}\n{{{{- end }}}}\n'
        )

    def test_updates_go_mod(self, temp_dir):
        """Test that go.mod module path is updated."""
        project = temp_dir / "my-gateway"
        self._create_go_template(project)

        customize_go_project(project, "my-gateway", "gateway-template")

        content = (project / "go.mod").read_text()
        assert "my-gateway" in content
        assert "gateway-template" not in content

    def test_updates_chart_name(self, temp_dir):
        """Test that chart/Chart.yaml name is updated."""
        project = temp_dir / "my-gateway"
        self._create_go_template(project)

        customize_go_project(project, "my-gateway", "gateway-template")

        content = (project / "chart" / "Chart.yaml").read_text()
        assert "name: my-gateway" in content
        assert "gateway-template" not in content

    def test_updates_values_image(self, temp_dir):
        """Test that chart/values.yaml image repository is updated."""
        project = temp_dir / "my-gateway"
        self._create_go_template(project)

        customize_go_project(project, "my-gateway", "gateway-template")

        content = (project / "chart" / "values.yaml").read_text()
        assert "repository: my-gateway" in content
        assert "gateway-template" not in content

    def test_updates_helpers_tpl(self, temp_dir):
        """Test that chart/templates/_helpers.tpl is updated."""
        project = temp_dir / "my-gateway"
        self._create_go_template(project)

        customize_go_project(project, "my-gateway", "gateway-template")

        content = (project / "chart" / "templates" / "_helpers.tpl").read_text()
        assert "my-gateway" in content
        assert "gateway-template" not in content

    def test_updates_makefile(self, temp_dir):
        """Test that Makefile PROJECT and IMAGE_NAME are updated."""
        project = temp_dir / "my-gateway"
        self._create_go_template(project)

        customize_go_project(project, "my-gateway", "gateway-template")

        content = (project / "Makefile").read_text()
        assert "IMAGE_NAME  ?= my-gateway" in content
        assert "PROJECT     ?= my-gateway" in content
        assert "gateway-template" not in content

    def test_updates_containerfile(self, temp_dir):
        """Test that Containerfile image title label is updated."""
        project = temp_dir / "my-gateway"
        self._create_go_template(project)

        customize_go_project(project, "my-gateway", "gateway-template")

        content = (project / "Containerfile").read_text()
        assert 'image.title="my-gateway"' in content
        assert "gateway-template" not in content

    def test_updates_readme(self, temp_dir):
        """Test that README.md heading is updated."""
        project = temp_dir / "my-gateway"
        self._create_go_template(project)

        customize_go_project(project, "my-gateway", "gateway-template")

        content = (project / "README.md").read_text()
        assert "# my-gateway" in content
        assert "gateway-template" not in content

    def test_updates_claude_md(self, temp_dir):
        """Test that CLAUDE.md heading is updated."""
        project = temp_dir / "my-gateway"
        self._create_go_template(project)

        customize_go_project(project, "my-gateway", "gateway-template")

        content = (project / "CLAUDE.md").read_text()
        assert "# my-gateway" in content
        assert "gateway-template" not in content

    def test_updates_html_in_static(self, temp_dir):
        """Test that HTML files in static/ directory are updated."""
        project = temp_dir / "my-ui"
        self._create_go_template(project, sentinel="ui-template")

        static = project / "static"
        static.mkdir()
        (static / "index.html").write_text("<title>ui-template</title>\n")

        customize_go_project(project, "my-ui", "ui-template")

        content = (static / "index.html").read_text()
        assert "<title>my-ui</title>" in content
        assert "ui-template" not in content

    def test_missing_go_mod_raises_error(self, temp_dir):
        """Test that missing go.mod raises FileNotFoundError."""
        project = temp_dir / "my-gateway"
        project.mkdir()

        with pytest.raises(FileNotFoundError):
            customize_go_project(project, "my-gateway", "gateway-template")

    def test_missing_optional_files_no_error(self, temp_dir):
        """Test that missing optional files don't cause errors."""
        project = temp_dir / "my-gateway"
        project.mkdir()
        # Only create go.mod — everything else is optional
        (project / "go.mod").write_text("module gateway-template\n\ngo 1.22\n")

        # Should not raise
        customize_go_project(project, "my-gateway", "gateway-template")

        content = (project / "go.mod").read_text()
        assert "my-gateway" in content
        assert "gateway-template" not in content


class TestCustomizeAgentTeamProject:
    """Tests for agent-team project customization."""

    def _create_agent_team_template(self, path):
        """Create a minimal agent-team template structure for testing."""
        path.mkdir(parents=True, exist_ok=True)

        # pyproject.toml with scripts entry
        (path / "pyproject.toml").write_text(
            "[project]\n"
            'name = "agent-team-template"\n'
            'version = "0.1.0"\n\n'
            "[project.scripts]\n"
            'agent-team-template = "agent_team_design.cli:main"\n'
        )

        # Source package
        src = path / "src" / "agent_team_design"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text('"""Agent team design package."""\n')
        (src / "cli.py").write_text("from .core import run\n")

        # External test file referencing agent_team_design
        tests = path / "tests"
        tests.mkdir()
        (tests / "test_cli.py").write_text(
            "from agent_team_design.cli import main\n\n" "def test_main():\n" "    pass\n"
        )

        # Supporting files
        (path / "README.md").write_text("# agent-team-template\n")
        (path / "CLAUDE.md").write_text("# agent-team-template dev guide\n")
        (path / "Makefile").write_text("PROJECT = agent-team-template\n")
        (path / "Containerfile").write_text(
            "FROM python:3.12\n"
            'LABEL io.opencontainers.image.source="https://github.com/OWNER/REPO"\n'
        )

    def test_updates_pyproject_name(self, temp_dir):
        """Test that pyproject.toml name field is updated."""
        project = temp_dir / "my-team"
        self._create_agent_team_template(project)

        customize_agent_team_project(project, "my-team")

        pyproject = tomlkit.parse((project / "pyproject.toml").read_text())
        assert pyproject["project"]["name"] == "my-team"

    def test_renames_src_directory(self, temp_dir):
        """Test that src/agent_team_design/ is renamed to src/<module_name>/."""
        project = temp_dir / "my-team"
        self._create_agent_team_template(project)

        customize_agent_team_project(project, "my-team")

        old_path = project / "src" / "agent_team_design"
        new_path = project / "src" / "my_team"

        assert not old_path.exists()
        assert new_path.exists()
        assert (new_path / "__init__.py").exists()

    def test_updates_entry_point_scripts(self, temp_dir):
        """Test that entry point scripts are updated in pyproject.toml."""
        project = temp_dir / "my-team"
        self._create_agent_team_template(project)

        customize_agent_team_project(project, "my-team")

        pyproject = tomlkit.parse((project / "pyproject.toml").read_text())
        scripts = pyproject["project"]["scripts"]

        # Script key should be renamed from "agent-team-template" to "my-team"
        assert "my-team" in scripts
        assert "agent-team-template" not in scripts
        # Path should use new module name
        assert scripts["my-team"] == "my_team.cli:main"

    def test_updates_test_file_imports(self, temp_dir):
        """Test that test file imports are updated to use new module name."""
        project = temp_dir / "my-team"
        self._create_agent_team_template(project)

        customize_agent_team_project(project, "my-team")

        content = (project / "tests" / "test_cli.py").read_text()
        assert "from my_team.cli import main" in content
        assert "agent_team_design" not in content

    def test_updates_supporting_files(self, temp_dir):
        """Test that supporting files are updated with new project name."""
        project = temp_dir / "my-team"
        self._create_agent_team_template(project)

        customize_agent_team_project(project, "my-team")

        readme = (project / "README.md").read_text()
        assert "# my-team" in readme
        assert "agent-team-template" not in readme

        claude_md = (project / "CLAUDE.md").read_text()
        assert "# my-team" in claude_md
        assert "agent-team-template" not in claude_md

        makefile = (project / "Makefile").read_text()
        assert "PROJECT = my-team" in makefile
        assert "agent-team-template" not in makefile

    def test_updates_containerfile_label(self, temp_dir):
        """Test that Containerfile OWNER/REPO is replaced with github_repo."""
        project = temp_dir / "my-team"
        self._create_agent_team_template(project)

        customize_agent_team_project(project, "my-team", github_repo="myorg/my-team")

        content = (project / "Containerfile").read_text()
        assert "OWNER/REPO" not in content
        assert "myorg/my-team" in content

    def test_preserves_internal_package_files(self, temp_dir):
        """Test that files inside the renamed package preserve relative imports."""
        project = temp_dir / "my-team"
        self._create_agent_team_template(project)

        customize_agent_team_project(project, "my-team")

        # cli.py should still have its relative import unchanged
        cli_content = (project / "src" / "my_team" / "cli.py").read_text()
        assert "from .core import run" in cli_content

    def test_missing_pyproject_raises_error(self, temp_dir):
        """Test that missing pyproject.toml raises FileNotFoundError."""
        project = temp_dir / "my-team"
        project.mkdir()

        with pytest.raises(FileNotFoundError):
            customize_agent_team_project(project, "my-team")
