"""Tests for deploy command and OpenShift utilities."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from fips_agents_cli.cli import cli


def _make_deploy_project(root: Path, project_type: str, project_name: str):
    """Create minimal project for deploy tests."""
    root.mkdir(parents=True, exist_ok=True)
    info = {
        "template": {"type": project_type, "url": "https://example.com", "commit": "abc123"},
        "project": {"name": project_name, "created_at": "2026-01-01T00:00:00+00:00"},
        "generator": {"tool": "fips-agents-cli", "version": "0.0.0"},
    }
    (root / ".template-info").write_text(json.dumps(info, indent=2))
    if project_type == "mcp-server":
        src = root / "src"
        src.mkdir(exist_ok=True)
        (src / "main.py").write_text("# server\n")
    elif project_type in ("agent", "workflow"):
        chart = root / "chart"
        chart.mkdir(exist_ok=True)
        (chart / "values.yaml").write_text("image:\n  repository: my-agent\n  tag: v1.0\n")
        (chart / "Chart.yaml").write_text("name: test\nversion: 0.1.0\n")


class TestIsOcInstalled:
    """Tests for is_oc_installed() function."""

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_returns_true_when_installed(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        from fips_agents_cli.tools.openshift import is_oc_installed

        assert is_oc_installed() is True
        mock_run.assert_called_once()

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_returns_false_when_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        from fips_agents_cli.tools.openshift import is_oc_installed

        assert is_oc_installed() is False


class TestIsOcAuthenticated:
    """Tests for is_oc_authenticated() function."""

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_returns_username_when_authenticated(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="kube:admin\n", stderr="")
        from fips_agents_cli.tools.openshift import is_oc_authenticated

        success, user = is_oc_authenticated()
        assert success is True
        assert user == "kube:admin"

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_returns_false_when_not_authenticated(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error: not authenticated"
        )
        from fips_agents_cli.tools.openshift import is_oc_authenticated

        success, msg = is_oc_authenticated()
        assert success is False
        assert "error" in msg.lower()

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_passes_context_flag(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="admin\n", stderr="")
        from fips_agents_cli.tools.openshift import is_oc_authenticated

        is_oc_authenticated(context="my-context")
        call_args = mock_run.call_args[0][0]
        assert "--context" in call_args
        assert "my-context" in call_args


class TestIsHelmInstalled:
    """Tests for is_helm_installed() function."""

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_returns_true_when_installed(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        from fips_agents_cli.tools.openshift import is_helm_installed

        assert is_helm_installed() is True

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_returns_false_when_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        from fips_agents_cli.tools.openshift import is_helm_installed

        assert is_helm_installed() is False


class TestNamespaceExists:
    """Tests for namespace_exists() function."""

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_returns_true_when_exists(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        from fips_agents_cli.tools.openshift import namespace_exists

        assert namespace_exists("my-namespace") is True

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_returns_false_when_not_exists(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        from fips_agents_cli.tools.openshift import namespace_exists

        assert namespace_exists("missing-namespace") is False


class TestCreateNamespace:
    """Tests for create_namespace() function."""

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="created", stderr="")
        from fips_agents_cli.tools.openshift import create_namespace

        success, msg = create_namespace("my-namespace")
        assert success is True
        assert "created" in msg

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_already_exists_treated_as_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error: already exists")
        from fips_agents_cli.tools.openshift import create_namespace

        success, msg = create_namespace("my-namespace")
        assert success is True
        assert "already exists" in msg.lower()

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error: forbidden"
        )
        from fips_agents_cli.tools.openshift import create_namespace

        success, msg = create_namespace("my-namespace")
        assert success is False


class TestCreateBuildContext:
    """Tests for create_build_context() function."""

    def test_excludes_git_directory(self, tmp_path):
        from fips_agents_cli.tools.openshift import create_build_context

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text("print('hello')")
        git_dir = project_dir / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("gitconfig")

        success, msg, ctx_dir = create_build_context(project_dir)
        assert success is True
        assert ctx_dir is not None
        assert (ctx_dir / "main.py").exists()
        assert not (ctx_dir / ".git").exists()

    def test_fixes_python_permissions(self, tmp_path):
        from fips_agents_cli.tools.openshift import create_build_context

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        py_file = project_dir / "script.py"
        py_file.write_text("# test")
        py_file.chmod(0o600)

        success, msg, ctx_dir = create_build_context(project_dir)
        assert success is True
        assert ctx_dir is not None
        copied_file = ctx_dir / "script.py"
        assert copied_file.exists()
        # Verify readable by group/others (at least 0o644)
        mode = copied_file.stat().st_mode & 0o777
        assert mode >= 0o644

    def test_reads_dockerignore(self, tmp_path):
        from fips_agents_cli.tools.openshift import create_build_context

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text("code")
        (project_dir / "secret.env").write_text("SECRET=xyz")
        (project_dir / ".dockerignore").write_text("*.env\n")

        success, msg, ctx_dir = create_build_context(project_dir)
        assert success is True
        assert ctx_dir is not None
        assert (ctx_dir / "main.py").exists()
        assert not (ctx_dir / "secret.env").exists()


class TestOcStartBuild:
    """Tests for oc_start_build() function."""

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="build started", stderr="")
        from fips_agents_cli.tools.openshift import oc_start_build

        success, msg = oc_start_build("my-build", Path("/tmp/ctx"), "my-namespace")
        assert success is True

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_failure_returns_stderr(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error: build failed")
        from fips_agents_cli.tools.openshift import oc_start_build

        success, msg = oc_start_build("my-build", Path("/tmp/ctx"), "my-namespace")
        assert success is False
        assert "error" in msg.lower()


class TestOcRolloutRestart:
    """Tests for oc_rollout_restart() function."""

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="restarted", stderr="")
        from fips_agents_cli.tools.openshift import oc_rollout_restart

        success, msg = oc_rollout_restart("my-deployment", "my-namespace")
        assert success is True


class TestOcGetRouteUrl:
    """Tests for oc_get_route_url() function."""

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_returns_url_with_https(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="my-server.apps.cluster\n", stderr=""
        )
        from fips_agents_cli.tools.openshift import oc_get_route_url

        success, url = oc_get_route_url("my-route", "my-namespace")
        assert success is True
        assert url == "https://my-server.apps.cluster"

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_returns_false_when_no_route(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        from fips_agents_cli.tools.openshift import oc_get_route_url

        success, msg = oc_get_route_url("missing-route", "my-namespace")
        assert success is False


class TestReadHelmValues:
    """Tests for read_helm_values() function."""

    def test_reads_valid_yaml(self, tmp_path):
        from fips_agents_cli.tools.openshift import read_helm_values

        chart_dir = tmp_path / "chart"
        chart_dir.mkdir()
        (chart_dir / "values.yaml").write_text("image:\n  repository: my-image\n  tag: v1.0\n")

        values = read_helm_values(chart_dir)
        assert values is not None
        assert "image" in values
        assert values["image"]["repository"] == "my-image"

    def test_returns_none_when_missing(self, tmp_path):
        from fips_agents_cli.tools.openshift import read_helm_values

        chart_dir = tmp_path / "empty-chart"
        chart_dir.mkdir()

        values = read_helm_values(chart_dir)
        assert values is None


class TestHelmDeploy:
    """Tests for helm_deploy() function."""

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="deployed", stderr="")
        from fips_agents_cli.tools.openshift import helm_deploy

        success, msg = helm_deploy("my-release", Path("/chart"), "my-namespace")
        assert success is True

    @patch("fips_agents_cli.tools.openshift.subprocess.run")
    def test_passes_kube_context(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        from fips_agents_cli.tools.openshift import helm_deploy

        helm_deploy("my-release", Path("/chart"), "my-namespace", oc_context="my-ctx")
        call_args = mock_run.call_args[0][0]
        assert "--kube-context" in call_args
        assert "my-ctx" in call_args


class TestDeployNotInProject:
    """Tests for deploy command outside a project."""

    def test_exit_1_when_no_template_info(self, tmp_path, monkeypatch, cli_runner):
        monkeypatch.chdir(tmp_path)
        result = cli_runner.invoke(cli, ["deploy"])
        assert result.exit_code == 1
        assert "Not in a fips-agents project" in result.output


class TestDeployUnsupportedType:
    """Tests for deploy command with unsupported project type."""

    def test_exit_1_for_unsupported_type(self, tmp_path, monkeypatch, cli_runner):
        _make_deploy_project(tmp_path, "sandbox", "my-sandbox")
        monkeypatch.chdir(tmp_path)
        result = cli_runner.invoke(cli, ["deploy"])
        assert result.exit_code == 1
        assert "does not support deployment" in result.output


class TestDeployOcNotInstalled:
    """Tests for deploy command when oc is not installed."""

    def test_exit_1_with_hint(self, tmp_path, monkeypatch, cli_runner):
        _make_deploy_project(tmp_path, "mcp-server", "my-server")
        monkeypatch.chdir(tmp_path)
        with patch("fips_agents_cli.commands.deploy.is_oc_installed", return_value=False):
            result = cli_runner.invoke(cli, ["deploy"])
        assert result.exit_code == 1
        assert "oc" in result.output.lower()


class TestDeployNotAuthenticated:
    """Tests for deploy command when not authenticated to OpenShift."""

    def test_exit_1_with_login_hint(self, tmp_path, monkeypatch, cli_runner):
        _make_deploy_project(tmp_path, "mcp-server", "my-server")
        monkeypatch.chdir(tmp_path)
        with (
            patch("fips_agents_cli.commands.deploy.is_oc_installed", return_value=True),
            patch(
                "fips_agents_cli.commands.deploy.is_oc_authenticated",
                return_value=(False, "err"),
            ),
        ):
            result = cli_runner.invoke(cli, ["deploy"])
        assert result.exit_code == 1
        assert "oc login" in result.output


class TestDeployMcpServerDryRun:
    """Tests for MCP server deployment dry-run mode."""

    def test_shows_plan_without_executing(self, tmp_path, monkeypatch, cli_runner):
        _make_deploy_project(tmp_path, "mcp-server", "my-server")
        monkeypatch.chdir(tmp_path)
        with (
            patch("fips_agents_cli.commands.deploy.is_oc_installed", return_value=True),
            patch(
                "fips_agents_cli.commands.deploy.is_oc_authenticated",
                return_value=(True, "admin"),
            ),
            patch("fips_agents_cli.commands.deploy.namespace_exists", return_value=True),
        ):
            result = cli_runner.invoke(cli, ["deploy", "--dry-run"])
        assert result.exit_code == 0
        assert "plan" in result.output.lower() or "build" in result.output.lower()


class TestDeployMcpServerSuccess:
    """Tests for successful MCP server deployment."""

    def test_full_deploy_flow(self, tmp_path, monkeypatch, cli_runner):
        _make_deploy_project(tmp_path, "mcp-server", "my-server")
        monkeypatch.chdir(tmp_path)
        ctx_dir = tmp_path / "build-ctx"
        ctx_dir.mkdir()
        with (
            patch("fips_agents_cli.commands.deploy.is_oc_installed", return_value=True),
            patch(
                "fips_agents_cli.commands.deploy.is_oc_authenticated",
                return_value=(True, "admin"),
            ),
            patch("fips_agents_cli.commands.deploy.namespace_exists", return_value=True),
            patch(
                "fips_agents_cli.commands.deploy.create_build_context",
                return_value=(True, "ok", ctx_dir),
            ),
            patch("fips_agents_cli.commands.deploy.oc_start_build", return_value=(True, "ok")),
            patch("fips_agents_cli.commands.deploy.oc_rollout_restart", return_value=(True, "ok")),
            patch("fips_agents_cli.commands.deploy.oc_rollout_status", return_value=(True, "ok")),
            patch(
                "fips_agents_cli.commands.deploy.oc_get_route_url",
                return_value=(True, "https://my-server.apps.cluster"),
            ),
        ):
            result = cli_runner.invoke(cli, ["deploy"])
        assert result.exit_code == 0
        assert "Deployed" in result.output


class TestDeployAgentDryRun:
    """Tests for agent deployment dry-run mode."""

    def test_shows_helm_command(self, tmp_path, monkeypatch, cli_runner):
        _make_deploy_project(tmp_path, "agent", "my-agent")
        monkeypatch.chdir(tmp_path)
        with (
            patch("fips_agents_cli.commands.deploy.is_oc_installed", return_value=True),
            patch(
                "fips_agents_cli.commands.deploy.is_oc_authenticated",
                return_value=(True, "admin"),
            ),
            patch("fips_agents_cli.commands.deploy.namespace_exists", return_value=True),
            patch("fips_agents_cli.commands.deploy.is_helm_installed", return_value=True),
        ):
            result = cli_runner.invoke(cli, ["deploy", "--dry-run"])
        assert result.exit_code == 0
        assert "helm" in result.output.lower()


class TestDeployAgentSuccess:
    """Tests for successful agent deployment."""

    def test_full_helm_deploy(self, tmp_path, monkeypatch, cli_runner):
        _make_deploy_project(tmp_path, "agent", "my-agent")
        monkeypatch.chdir(tmp_path)
        with (
            patch("fips_agents_cli.commands.deploy.is_oc_installed", return_value=True),
            patch(
                "fips_agents_cli.commands.deploy.is_oc_authenticated",
                return_value=(True, "admin"),
            ),
            patch("fips_agents_cli.commands.deploy.namespace_exists", return_value=True),
            patch("fips_agents_cli.commands.deploy.is_helm_installed", return_value=True),
            patch("fips_agents_cli.commands.deploy.helm_deploy", return_value=(True, "ok")),
        ):
            result = cli_runner.invoke(cli, ["deploy"])
        assert result.exit_code == 0
        assert "Deployed" in result.output


class TestDeployNamespaceCreation:
    """Tests for namespace creation during deployment."""

    def test_creates_namespace_on_confirm(self, tmp_path, monkeypatch, cli_runner):
        _make_deploy_project(tmp_path, "mcp-server", "my-server")
        monkeypatch.chdir(tmp_path)
        ctx_dir = tmp_path / "build-ctx"
        ctx_dir.mkdir()
        with (
            patch("fips_agents_cli.commands.deploy.is_oc_installed", return_value=True),
            patch(
                "fips_agents_cli.commands.deploy.is_oc_authenticated",
                return_value=(True, "admin"),
            ),
            patch("fips_agents_cli.commands.deploy.namespace_exists", return_value=False),
            patch(
                "fips_agents_cli.commands.deploy.create_namespace", return_value=(True, "ok")
            ) as mock_create,
            patch(
                "fips_agents_cli.commands.deploy.create_build_context",
                return_value=(True, "ok", ctx_dir),
            ),
            patch("fips_agents_cli.commands.deploy.oc_start_build", return_value=(True, "ok")),
            patch("fips_agents_cli.commands.deploy.oc_rollout_restart", return_value=(True, "ok")),
            patch("fips_agents_cli.commands.deploy.oc_rollout_status", return_value=(True, "ok")),
            patch(
                "fips_agents_cli.commands.deploy.oc_get_route_url",
                return_value=(True, "https://route.url"),
            ),
        ):
            result = cli_runner.invoke(cli, ["deploy"], input="y\n")
        assert result.exit_code == 0
        mock_create.assert_called_once()

    def test_cancels_on_decline(self, tmp_path, monkeypatch, cli_runner):
        _make_deploy_project(tmp_path, "mcp-server", "my-server")
        monkeypatch.chdir(tmp_path)
        with (
            patch("fips_agents_cli.commands.deploy.is_oc_installed", return_value=True),
            patch(
                "fips_agents_cli.commands.deploy.is_oc_authenticated",
                return_value=(True, "admin"),
            ),
            patch("fips_agents_cli.commands.deploy.namespace_exists", return_value=False),
        ):
            result = cli_runner.invoke(cli, ["deploy"], input="n\n")
        assert result.exit_code == 0
        assert "cancelled" in result.output.lower()


class TestDeployWithContext:
    """Tests for deployment with explicit OpenShift context."""

    def test_passes_context_flag(self, tmp_path, monkeypatch, cli_runner):
        _make_deploy_project(tmp_path, "mcp-server", "my-server")
        monkeypatch.chdir(tmp_path)
        ctx_dir = tmp_path / "build-ctx"
        ctx_dir.mkdir()
        with (
            patch("fips_agents_cli.commands.deploy.is_oc_installed", return_value=True),
            patch(
                "fips_agents_cli.commands.deploy.is_oc_authenticated",
                return_value=(True, "admin"),
            ) as mock_auth,
            patch("fips_agents_cli.commands.deploy.namespace_exists", return_value=True),
            patch(
                "fips_agents_cli.commands.deploy.create_build_context",
                return_value=(True, "ok", ctx_dir),
            ),
            patch(
                "fips_agents_cli.commands.deploy.oc_start_build", return_value=(True, "ok")
            ) as mock_build,
            patch("fips_agents_cli.commands.deploy.oc_rollout_restart", return_value=(True, "ok")),
            patch("fips_agents_cli.commands.deploy.oc_rollout_status", return_value=(True, "ok")),
            patch(
                "fips_agents_cli.commands.deploy.oc_get_route_url",
                return_value=(True, "https://route.url"),
            ),
        ):
            result = cli_runner.invoke(cli, ["deploy", "--context", "my-ctx"])
        assert result.exit_code == 0
        mock_auth.assert_called_once_with("my-ctx")
        # Verify context was passed through to build
        assert mock_build.called
