"""Tests for the create command."""

from pathlib import Path
from unittest.mock import patch

from fips_agents_cli.cli import cli


class TestCreateMcpServer:
    """Tests for the 'create mcp-server' command."""

    def test_help_message(self, cli_runner):
        """Test that help message is displayed correctly."""
        result = cli_runner.invoke(cli, ["create", "mcp-server", "--help"])
        assert result.exit_code == 0
        assert "Create a new MCP server project" in result.output
        assert "PROJECT_NAME" in result.output

    def test_invalid_project_name_uppercase(self, cli_runner):
        """Test that uppercase letters in project name are rejected."""
        result = cli_runner.invoke(cli, ["create", "mcp-server", "TestServer"])
        assert result.exit_code == 1
        assert "Invalid project name" in result.output

    def test_invalid_project_name_special_chars(self, cli_runner):
        """Test that special characters in project name are rejected."""
        result = cli_runner.invoke(cli, ["create", "mcp-server", "test@server"])
        assert result.exit_code == 1
        assert "Invalid project name" in result.output

    def test_invalid_project_name_starts_with_number(self, cli_runner):
        """Test that project name starting with number is rejected."""
        result = cli_runner.invoke(cli, ["create", "mcp-server", "123test"])
        assert result.exit_code == 1
        assert "Invalid project name" in result.output

    def test_invalid_project_name_empty(self, cli_runner):
        """Test that empty project name is rejected."""
        result = cli_runner.invoke(cli, ["create", "mcp-server", ""])
        # Click will handle this as missing argument
        assert result.exit_code != 0

    def test_valid_project_names(self, cli_runner):
        """Test that various valid project names are accepted."""
        valid_names = [
            "test",
            "test-server",
            "test_server",
            "test123",
            "test-server-123",
            "myserver",
            "a",  # Single letter
        ]

        for name in valid_names:
            # We'll mock the git operations to avoid actual cloning
            with (
                patch("fips_agents_cli.commands.create.clone_template"),
                patch("fips_agents_cli.commands.create.update_project_name"),
                patch("fips_agents_cli.commands.create.cleanup_template_files"),
                patch("fips_agents_cli.commands.create.init_repository"),
                patch("fips_agents_cli.commands.create.is_git_installed", return_value=True),
            ):

                result = cli_runner.invoke(
                    cli, ["create", "mcp-server", name, "--target-dir", str(Path.cwd() / "temp")]
                )
                # Should pass validation (though may fail on other steps in isolation)
                assert "Invalid project name" not in result.output

    @patch("fips_agents_cli.commands.create.is_gh_installed", return_value=False)
    @patch("fips_agents_cli.commands.create.is_git_installed", return_value=True)
    def test_existing_directory_error(
        self, mock_is_git_installed, mock_is_gh_installed, cli_runner, temp_dir
    ):
        """Test that existing directory causes an error."""
        existing_dir = temp_dir / "existing-project"
        existing_dir.mkdir()

        result = cli_runner.invoke(
            cli, ["create", "mcp-server", "existing-project", "--target-dir", str(temp_dir)]
        )
        assert result.exit_code == 1
        assert "already exists" in result.output

    @patch("fips_agents_cli.commands.create.is_gh_installed", return_value=False)
    @patch("fips_agents_cli.commands.create.is_git_installed")
    def test_git_not_installed(
        self, mock_is_git_installed, mock_is_gh_installed, cli_runner, temp_dir
    ):
        """Test that missing git installation is detected."""
        mock_is_git_installed.return_value = False

        result = cli_runner.invoke(
            cli, ["create", "mcp-server", "test-server", "--target-dir", str(temp_dir)]
        )
        assert result.exit_code == 1
        assert "Git is not installed" in result.output

    @patch("fips_agents_cli.commands.create.clone_template")
    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.is_gh_installed")
    def test_clone_failure(
        self, mock_gh_installed, mock_is_git_installed, mock_clone, cli_runner, temp_dir
    ):
        """Test handling of git clone failures."""
        mock_is_git_installed.return_value = True
        mock_gh_installed.return_value = False  # Skip GitHub flow
        mock_clone.side_effect = Exception("Connection timeout")

        result = cli_runner.invoke(
            cli, ["create", "mcp-server", "test-server", "--target-dir", str(temp_dir)]
        )
        assert result.exit_code == 1
        assert "Failed to clone template" in result.output

    @patch("fips_agents_cli.commands.create.clone_template")
    @patch("fips_agents_cli.commands.create.update_project_name")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.init_repository")
    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.is_gh_installed")
    def test_successful_creation(
        self,
        mock_gh_installed,
        mock_is_git_installed,
        mock_init_repo,
        mock_cleanup,
        mock_update,
        mock_clone,
        cli_runner,
        temp_dir,
    ):
        """Test successful project creation with all steps."""
        mock_is_git_installed.return_value = True
        mock_gh_installed.return_value = False  # Skip GitHub flow

        # Mock the clone to create a minimal structure
        def create_minimal_structure(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        mock_clone.side_effect = create_minimal_structure

        result = cli_runner.invoke(
            cli, ["create", "mcp-server", "my-server", "--target-dir", str(temp_dir)]
        )

        # Verify all steps were called
        assert mock_clone.called
        assert mock_update.called
        assert mock_cleanup.called
        assert mock_init_repo.called

        # Check success message
        assert result.exit_code == 0
        assert "Successfully created MCP server project" in result.output
        assert "my-server" in result.output

    @patch("fips_agents_cli.commands.create.clone_template")
    @patch("fips_agents_cli.commands.create.update_project_name")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.is_gh_installed")
    def test_no_git_flag(
        self,
        mock_gh_installed,
        mock_is_git_installed,
        mock_cleanup,
        mock_update,
        mock_clone,
        cli_runner,
        temp_dir,
    ):
        """Test that --no-git flag skips git initialization."""
        mock_is_git_installed.return_value = True
        mock_gh_installed.return_value = False  # Skip GitHub flow

        def create_minimal_structure(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        mock_clone.side_effect = create_minimal_structure

        with patch("fips_agents_cli.commands.create.init_repository") as mock_init:
            result = cli_runner.invoke(
                cli,
                ["create", "mcp-server", "my-server", "--target-dir", str(temp_dir), "--no-git"],
            )

            # Verify git init was NOT called
            assert not mock_init.called
            assert result.exit_code == 0

    def test_target_dir_option(self, cli_runner, temp_dir):
        """Test that --target-dir option works correctly."""
        with (
            patch("fips_agents_cli.commands.create.clone_template"),
            patch("fips_agents_cli.commands.create.update_project_name"),
            patch("fips_agents_cli.commands.create.cleanup_template_files"),
            patch("fips_agents_cli.commands.create.init_repository"),
            patch("fips_agents_cli.commands.create.is_git_installed", return_value=True),
            patch("fips_agents_cli.commands.create.is_gh_installed", return_value=False),
        ):

            result = cli_runner.invoke(
                cli, ["create", "mcp-server", "test-server", "--target-dir", str(temp_dir)]
            )

            # Should include the target directory in output
            assert str(temp_dir) in result.output or "test-server" in result.output


class TestCreateMcpServerGitHub:
    """Tests for GitHub integration in 'create mcp-server' command."""

    def test_github_and_local_mutually_exclusive(self, cli_runner):
        """Test that --github and --local cannot be used together."""
        result = cli_runner.invoke(
            cli, ["create", "mcp-server", "test-server", "--github", "--local"]
        )
        assert result.exit_code == 1
        assert "Cannot use --github and --local together" in result.output

    def test_remote_only_and_local_mutually_exclusive(self, cli_runner):
        """Test that --remote-only and --local cannot be used together."""
        result = cli_runner.invoke(
            cli, ["create", "mcp-server", "test-server", "--remote-only", "--local"]
        )
        assert result.exit_code == 1
        assert "Cannot use --remote-only with --local" in result.output

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.check_gh_prerequisites")
    def test_github_flag_requires_gh_cli(
        self, mock_check_gh, mock_is_git_installed, cli_runner, temp_dir
    ):
        """Test that --github flag fails if gh CLI is not ready."""
        mock_is_git_installed.return_value = True
        mock_check_gh.return_value = (False, "GitHub CLI (gh) is not installed.")

        result = cli_runner.invoke(
            cli,
            ["create", "mcp-server", "test-server", "--github", "--target-dir", str(temp_dir)],
        )
        assert result.exit_code == 1
        assert "not installed" in result.output

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.is_gh_installed")
    @patch("fips_agents_cli.commands.create.is_gh_authenticated")
    def test_local_flag_skips_github_check(
        self, mock_gh_auth, mock_gh_installed, mock_is_git_installed, cli_runner, temp_dir
    ):
        """Test that --local flag skips GitHub even when gh is available."""
        mock_is_git_installed.return_value = True
        mock_gh_installed.return_value = True
        mock_gh_auth.return_value = True

        with (
            patch("fips_agents_cli.commands.create.clone_template") as mock_clone,
            patch("fips_agents_cli.commands.create.update_project_name"),
            patch("fips_agents_cli.commands.create.cleanup_template_files"),
            patch("fips_agents_cli.commands.create.init_repository"),
            patch("fips_agents_cli.commands.create.create_github_repo") as mock_create_gh,
        ):

            def create_minimal_structure(url, target_path, branch=None):
                target_path.mkdir(parents=True, exist_ok=True)
                (target_path / "pyproject.toml").write_text("[project]\nname = 'test'")

            mock_clone.side_effect = create_minimal_structure

            result = cli_runner.invoke(
                cli,
                ["create", "mcp-server", "test-server", "--local", "--target-dir", str(temp_dir)],
            )

            # GitHub repo should NOT be created
            assert not mock_create_gh.called
            assert result.exit_code == 0

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.check_gh_prerequisites")
    @patch("fips_agents_cli.commands.create.create_github_repo")
    @patch("fips_agents_cli.commands.create.get_github_username")
    @patch("fips_agents_cli.commands.create.clone_template")
    @patch("fips_agents_cli.commands.create.update_project_name")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.init_repository")
    @patch("fips_agents_cli.commands.create.add_remote")
    @patch("fips_agents_cli.commands.create.push_to_remote")
    def test_github_flow_creates_repo_and_pushes(
        self,
        mock_push,
        mock_add_remote,
        mock_init_repo,
        mock_cleanup,
        mock_update,
        mock_clone,
        mock_get_username,
        mock_create_gh,
        mock_check_gh,
        mock_is_git_installed,
        cli_runner,
        temp_dir,
    ):
        """Test full GitHub flow creates repo and pushes code."""
        mock_is_git_installed.return_value = True
        mock_check_gh.return_value = (True, None)
        mock_create_gh.return_value = (True, "https://github.com/testuser/my-server", None)
        mock_get_username.return_value = "testuser"
        mock_push.return_value = True

        def create_minimal_structure(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        mock_clone.side_effect = create_minimal_structure

        result = cli_runner.invoke(
            cli,
            ["create", "mcp-server", "my-server", "--github", "--target-dir", str(temp_dir)],
        )

        assert result.exit_code == 0
        assert mock_create_gh.called
        assert mock_add_remote.called
        assert mock_push.called
        assert "Successfully created" in result.output
        assert "https://github.com/testuser/my-server" in result.output

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.check_gh_prerequisites")
    @patch("fips_agents_cli.commands.create.create_github_repo")
    def test_github_repo_creation_failure(
        self, mock_create_gh, mock_check_gh, mock_is_git_installed, cli_runner, temp_dir
    ):
        """Test handling of GitHub repo creation failure."""
        mock_is_git_installed.return_value = True
        mock_check_gh.return_value = (True, None)
        mock_create_gh.return_value = (False, None, "Repository 'my-server' already exists")

        result = cli_runner.invoke(
            cli,
            ["create", "mcp-server", "my-server", "--github", "--target-dir", str(temp_dir)],
        )

        assert result.exit_code == 1
        assert "already exists" in result.output

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.check_gh_prerequisites")
    @patch("fips_agents_cli.commands.create.create_github_repo")
    @patch("fips_agents_cli.commands.create.get_github_username")
    def test_remote_only_mode(
        self,
        mock_get_username,
        mock_create_gh,
        mock_check_gh,
        mock_is_git_installed,
        cli_runner,
    ):
        """Test --remote-only creates GitHub repo without local clone."""
        mock_is_git_installed.return_value = True
        mock_check_gh.return_value = (True, None)
        mock_create_gh.return_value = (True, "https://github.com/testuser/my-server", None)
        mock_get_username.return_value = "testuser"

        with patch("fips_agents_cli.commands.create.clone_template") as mock_clone:
            result = cli_runner.invoke(
                cli, ["create", "mcp-server", "my-server", "--github", "--remote-only"]
            )

            assert result.exit_code == 0
            # Clone should NOT be called in remote-only mode
            assert not mock_clone.called
            assert "Successfully created GitHub repository" in result.output

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.check_gh_prerequisites")
    @patch("fips_agents_cli.commands.create.create_github_repo")
    @patch("fips_agents_cli.commands.create.get_github_username")
    @patch("fips_agents_cli.commands.create.clone_template")
    @patch("fips_agents_cli.commands.create.update_project_name")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.init_repository")
    @patch("fips_agents_cli.commands.create.add_remote")
    @patch("fips_agents_cli.commands.create.push_to_remote")
    def test_private_repo_option(
        self,
        mock_push,
        mock_add_remote,
        mock_init_repo,
        mock_cleanup,
        mock_update,
        mock_clone,
        mock_get_username,
        mock_create_gh,
        mock_check_gh,
        mock_is_git_installed,
        cli_runner,
        temp_dir,
    ):
        """Test --private flag creates private GitHub repo."""
        mock_is_git_installed.return_value = True
        mock_check_gh.return_value = (True, None)
        mock_create_gh.return_value = (True, "https://github.com/testuser/my-server", None)
        mock_get_username.return_value = "testuser"
        mock_push.return_value = True

        def create_minimal_structure(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        mock_clone.side_effect = create_minimal_structure

        result = cli_runner.invoke(
            cli,
            [
                "create",
                "mcp-server",
                "my-server",
                "--github",
                "--private",
                "--target-dir",
                str(temp_dir),
            ],
        )

        assert result.exit_code == 0
        # Verify private=True was passed
        mock_create_gh.assert_called_with(
            name="my-server", private=True, org=None, description=None
        )

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.check_gh_prerequisites")
    @patch("fips_agents_cli.commands.create.create_github_repo")
    @patch("fips_agents_cli.commands.create.get_github_username")
    @patch("fips_agents_cli.commands.create.clone_template")
    @patch("fips_agents_cli.commands.create.update_project_name")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.init_repository")
    @patch("fips_agents_cli.commands.create.add_remote")
    @patch("fips_agents_cli.commands.create.push_to_remote")
    def test_org_option(
        self,
        mock_push,
        mock_add_remote,
        mock_init_repo,
        mock_cleanup,
        mock_update,
        mock_clone,
        mock_get_username,
        mock_create_gh,
        mock_check_gh,
        mock_is_git_installed,
        cli_runner,
        temp_dir,
    ):
        """Test --org flag creates repo in organization."""
        mock_is_git_installed.return_value = True
        mock_check_gh.return_value = (True, None)
        mock_create_gh.return_value = (True, "https://github.com/myorg/my-server", None)
        mock_get_username.return_value = "testuser"
        mock_push.return_value = True

        def create_minimal_structure(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        mock_clone.side_effect = create_minimal_structure

        result = cli_runner.invoke(
            cli,
            [
                "create",
                "mcp-server",
                "my-server",
                "--github",
                "--org",
                "myorg",
                "--target-dir",
                str(temp_dir),
            ],
        )

        assert result.exit_code == 0
        mock_create_gh.assert_called_with(
            name="my-server", private=False, org="myorg", description=None
        )

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.is_gh_installed")
    @patch("fips_agents_cli.commands.create.is_gh_authenticated")
    def test_yes_flag_uses_github_when_available(
        self, mock_gh_auth, mock_gh_installed, mock_is_git_installed, cli_runner, temp_dir
    ):
        """Test --yes flag defaults to GitHub when gh is available."""
        mock_is_git_installed.return_value = True
        mock_gh_installed.return_value = True
        mock_gh_auth.return_value = True

        with (
            patch("fips_agents_cli.commands.create.check_gh_prerequisites") as mock_check,
            patch("fips_agents_cli.commands.create.create_github_repo") as mock_create_gh,
            patch("fips_agents_cli.commands.create.get_github_username") as mock_username,
            patch("fips_agents_cli.commands.create.clone_template") as mock_clone,
            patch("fips_agents_cli.commands.create.update_project_name"),
            patch("fips_agents_cli.commands.create.cleanup_template_files"),
            patch("fips_agents_cli.commands.create.init_repository"),
            patch("fips_agents_cli.commands.create.add_remote"),
            patch("fips_agents_cli.commands.create.push_to_remote") as mock_push,
        ):
            mock_check.return_value = (True, None)
            mock_create_gh.return_value = (True, "https://github.com/testuser/my-server", None)
            mock_username.return_value = "testuser"
            mock_push.return_value = True

            def create_minimal_structure(url, target_path, branch=None):
                target_path.mkdir(parents=True, exist_ok=True)
                (target_path / "pyproject.toml").write_text("[project]\nname = 'test'")

            mock_clone.side_effect = create_minimal_structure

            result = cli_runner.invoke(
                cli,
                ["create", "mcp-server", "my-server", "--yes", "--target-dir", str(temp_dir)],
            )

            # Should use GitHub flow automatically
            assert mock_create_gh.called
            assert result.exit_code == 0

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.is_gh_installed")
    def test_yes_flag_uses_local_when_gh_not_available(
        self, mock_gh_installed, mock_is_git_installed, cli_runner, temp_dir
    ):
        """Test --yes flag uses local when gh is not available."""
        mock_is_git_installed.return_value = True
        mock_gh_installed.return_value = False  # gh not installed

        with (
            patch("fips_agents_cli.commands.create.clone_template") as mock_clone,
            patch("fips_agents_cli.commands.create.update_project_name"),
            patch("fips_agents_cli.commands.create.cleanup_template_files"),
            patch("fips_agents_cli.commands.create.init_repository"),
            patch("fips_agents_cli.commands.create.create_github_repo") as mock_create_gh,
        ):

            def create_minimal_structure(url, target_path, branch=None):
                target_path.mkdir(parents=True, exist_ok=True)
                (target_path / "pyproject.toml").write_text("[project]\nname = 'test'")

            mock_clone.side_effect = create_minimal_structure

            result = cli_runner.invoke(
                cli,
                ["create", "mcp-server", "my-server", "--yes", "--target-dir", str(temp_dir)],
            )

            # Should NOT call GitHub
            assert not mock_create_gh.called
            assert result.exit_code == 0


class TestCreateAgent:
    """Tests for the 'create agent' command."""

    def test_help_message(self, cli_runner):
        """Test that help message is displayed correctly."""
        result = cli_runner.invoke(cli, ["create", "agent", "--help"])
        assert result.exit_code == 0
        assert "Create a new AI agent project" in result.output
        assert "PROJECT_NAME" in result.output

    def test_invalid_project_name_uppercase(self, cli_runner):
        """Test that uppercase letters in project name are rejected."""
        result = cli_runner.invoke(cli, ["create", "agent", "TestAgent"])
        assert result.exit_code == 1
        assert "Invalid project name" in result.output

    def test_invalid_project_name_special_chars(self, cli_runner):
        """Test that special characters in project name are rejected."""
        result = cli_runner.invoke(cli, ["create", "agent", "test@agent"])
        assert result.exit_code == 1
        assert "Invalid project name" in result.output

    def test_invalid_project_name_starts_with_number(self, cli_runner):
        """Test that project name starting with number is rejected."""
        result = cli_runner.invoke(cli, ["create", "agent", "123agent"])
        assert result.exit_code == 1
        assert "Invalid project name" in result.output

    @patch("fips_agents_cli.commands.create.is_gh_installed", return_value=False)
    @patch("fips_agents_cli.commands.create.is_git_installed", return_value=True)
    def test_existing_directory_error(
        self, mock_is_git_installed, mock_is_gh_installed, cli_runner, temp_dir
    ):
        """Test that existing directory causes an error."""
        existing_dir = temp_dir / "existing-agent"
        existing_dir.mkdir()

        result = cli_runner.invoke(
            cli, ["create", "agent", "existing-agent", "--target-dir", str(temp_dir)]
        )
        assert result.exit_code == 1
        assert "already exists" in result.output

    @patch("fips_agents_cli.commands.create.is_gh_installed", return_value=False)
    @patch("fips_agents_cli.commands.create.is_git_installed")
    def test_git_not_installed(
        self, mock_is_git_installed, mock_is_gh_installed, cli_runner, temp_dir
    ):
        """Test that missing git installation is detected."""
        mock_is_git_installed.return_value = False

        result = cli_runner.invoke(
            cli, ["create", "agent", "test-agent", "--target-dir", str(temp_dir)]
        )
        assert result.exit_code == 1
        assert "Git is not installed" in result.output

    @patch("fips_agents_cli.commands.create.clone_template_subdir")
    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.is_gh_installed")
    def test_clone_failure(
        self, mock_gh_installed, mock_is_git_installed, mock_clone, cli_runner, temp_dir
    ):
        """Test handling of template clone failures."""
        mock_is_git_installed.return_value = True
        mock_gh_installed.return_value = False
        mock_clone.side_effect = Exception("Connection timeout")

        result = cli_runner.invoke(
            cli, ["create", "agent", "test-agent", "--target-dir", str(temp_dir)]
        )
        assert result.exit_code == 1
        assert "Failed to clone agent template" in result.output

    @patch("fips_agents_cli.commands.create.clone_template_subdir")
    @patch("fips_agents_cli.commands.create.customize_agent_project")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.init_repository")
    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.is_gh_installed")
    def test_successful_creation(
        self,
        mock_gh_installed,
        mock_is_git_installed,
        mock_init_repo,
        mock_cleanup,
        mock_customize,
        mock_clone,
        cli_runner,
        temp_dir,
    ):
        """Test successful agent project creation with all steps."""
        mock_is_git_installed.return_value = True
        mock_gh_installed.return_value = False

        def create_minimal_structure(url, target_path, subdir, branch=None, **kwargs):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "pyproject.toml").write_text('[project]\nname = "agent-template"')

        mock_clone.side_effect = create_minimal_structure

        result = cli_runner.invoke(
            cli, ["create", "agent", "my-agent", "--target-dir", str(temp_dir)]
        )

        assert mock_clone.called
        assert mock_customize.called
        assert mock_cleanup.called
        assert mock_init_repo.called
        assert result.exit_code == 0
        assert "Successfully created agent project" in result.output
        assert "my-agent" in result.output

    @patch("fips_agents_cli.commands.create.clone_template_subdir")
    @patch("fips_agents_cli.commands.create.customize_agent_project")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.is_gh_installed")
    def test_no_git_flag(
        self,
        mock_gh_installed,
        mock_is_git_installed,
        mock_cleanup,
        mock_customize,
        mock_clone,
        cli_runner,
        temp_dir,
    ):
        """Test that --no-git flag skips git initialization."""
        mock_is_git_installed.return_value = True
        mock_gh_installed.return_value = False

        def create_minimal_structure(url, target_path, subdir, branch=None, **kwargs):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "pyproject.toml").write_text('[project]\nname = "agent-template"')

        mock_clone.side_effect = create_minimal_structure

        with patch("fips_agents_cli.commands.create.init_repository") as mock_init:
            result = cli_runner.invoke(
                cli,
                ["create", "agent", "my-agent", "--target-dir", str(temp_dir), "--no-git"],
            )

            assert not mock_init.called
            assert result.exit_code == 0


class TestCreateAgentGitHub:
    """Tests for GitHub integration in 'create agent' command."""

    def test_github_and_local_mutually_exclusive(self, cli_runner):
        """Test that --github and --local cannot be used together."""
        result = cli_runner.invoke(cli, ["create", "agent", "test-agent", "--github", "--local"])
        assert result.exit_code == 1
        assert "Cannot use --github and --local together" in result.output

    def test_remote_only_and_local_mutually_exclusive(self, cli_runner):
        """Test that --remote-only and --local cannot be used together."""
        result = cli_runner.invoke(
            cli, ["create", "agent", "test-agent", "--remote-only", "--local"]
        )
        assert result.exit_code == 1
        assert "Cannot use --remote-only with --local" in result.output

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.check_gh_prerequisites")
    @patch("fips_agents_cli.commands.create.create_github_repo")
    @patch("fips_agents_cli.commands.create.get_github_username")
    @patch("fips_agents_cli.commands.create.clone_template_subdir")
    @patch("fips_agents_cli.commands.create.customize_agent_project")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.init_repository")
    @patch("fips_agents_cli.commands.create.add_remote")
    @patch("fips_agents_cli.commands.create.push_to_remote")
    def test_github_flow_creates_repo_and_pushes(
        self,
        mock_push,
        mock_add_remote,
        mock_init_repo,
        mock_cleanup,
        mock_customize,
        mock_clone,
        mock_get_username,
        mock_create_gh,
        mock_check_gh,
        mock_is_git_installed,
        cli_runner,
        temp_dir,
    ):
        """Test full GitHub flow creates repo and pushes code."""
        mock_is_git_installed.return_value = True
        mock_check_gh.return_value = (True, None)
        mock_create_gh.return_value = (True, "https://github.com/testuser/my-agent", None)
        mock_get_username.return_value = "testuser"
        mock_push.return_value = True

        def create_minimal_structure(url, target_path, subdir, branch=None, **kwargs):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "pyproject.toml").write_text('[project]\nname = "agent-template"')

        mock_clone.side_effect = create_minimal_structure

        result = cli_runner.invoke(
            cli,
            ["create", "agent", "my-agent", "--github", "--target-dir", str(temp_dir)],
        )

        assert result.exit_code == 0
        assert mock_create_gh.called
        assert mock_add_remote.called
        assert mock_push.called
        assert "Successfully created" in result.output

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.check_gh_prerequisites")
    @patch("fips_agents_cli.commands.create.create_github_repo")
    @patch("fips_agents_cli.commands.create.get_github_username")
    def test_remote_only_mode(
        self,
        mock_get_username,
        mock_create_gh,
        mock_check_gh,
        mock_is_git_installed,
        cli_runner,
    ):
        """Test --remote-only creates GitHub repo without local clone."""
        mock_is_git_installed.return_value = True
        mock_check_gh.return_value = (True, None)
        mock_create_gh.return_value = (True, "https://github.com/testuser/my-agent", None)
        mock_get_username.return_value = "testuser"

        with patch("fips_agents_cli.commands.create.clone_template_subdir") as mock_clone:
            result = cli_runner.invoke(
                cli, ["create", "agent", "my-agent", "--github", "--remote-only"]
            )

            assert result.exit_code == 0
            assert not mock_clone.called
            assert "Successfully created GitHub repository" in result.output

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.check_gh_prerequisites")
    @patch("fips_agents_cli.commands.create.create_github_repo")
    @patch("fips_agents_cli.commands.create.get_github_username")
    @patch("fips_agents_cli.commands.create.clone_template_subdir")
    @patch("fips_agents_cli.commands.create.customize_agent_project")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.init_repository")
    @patch("fips_agents_cli.commands.create.add_remote")
    @patch("fips_agents_cli.commands.create.push_to_remote")
    def test_private_repo_option(
        self,
        mock_push,
        mock_add_remote,
        mock_init_repo,
        mock_cleanup,
        mock_customize,
        mock_clone,
        mock_get_username,
        mock_create_gh,
        mock_check_gh,
        mock_is_git_installed,
        cli_runner,
        temp_dir,
    ):
        """Test --private flag creates private GitHub repo."""
        mock_is_git_installed.return_value = True
        mock_check_gh.return_value = (True, None)
        mock_create_gh.return_value = (True, "https://github.com/testuser/my-agent", None)
        mock_get_username.return_value = "testuser"
        mock_push.return_value = True

        def create_minimal_structure(url, target_path, subdir, branch=None, **kwargs):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "pyproject.toml").write_text('[project]\nname = "agent-template"')

        mock_clone.side_effect = create_minimal_structure

        result = cli_runner.invoke(
            cli,
            [
                "create",
                "agent",
                "my-agent",
                "--github",
                "--private",
                "--target-dir",
                str(temp_dir),
            ],
        )

        assert result.exit_code == 0
        mock_create_gh.assert_called_with(name="my-agent", private=True, org=None, description=None)


class TestCreateGateway:
    """Tests for the 'create gateway' command."""

    def test_help_message(self, cli_runner):
        """Test that help message is displayed correctly."""
        result = cli_runner.invoke(cli, ["create", "gateway", "--help"])
        assert result.exit_code == 0
        assert "gateway" in result.output.lower()
        assert "PROJECT_NAME" in result.output

    def test_invalid_project_name_uppercase(self, cli_runner):
        """Test that uppercase letters in project name are rejected."""
        result = cli_runner.invoke(cli, ["create", "gateway", "MyGateway"])
        assert result.exit_code == 1
        assert "Invalid project name" in result.output

    @patch("fips_agents_cli.commands.create.clone_template")
    @patch("fips_agents_cli.commands.create.customize_go_project")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.init_repository")
    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.is_gh_installed")
    def test_successful_creation(
        self,
        mock_gh_installed,
        mock_is_git_installed,
        mock_init_repo,
        mock_cleanup,
        mock_customize,
        mock_clone,
        cli_runner,
        temp_dir,
    ):
        """Test successful gateway project creation."""
        mock_is_git_installed.return_value = True
        mock_gh_installed.return_value = False

        def create_minimal_structure(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "go.mod").write_text("module gateway-template\n\ngo 1.22\n")

        mock_clone.side_effect = create_minimal_structure

        result = cli_runner.invoke(
            cli, ["create", "gateway", "my-gateway", "--local", "--target-dir", str(temp_dir)]
        )

        assert mock_clone.called
        mock_clone.assert_called_once()
        # Verify the URL passed to clone_template
        call_args = mock_clone.call_args
        assert call_args[0][0] == "https://github.com/fips-agents/gateway-template"
        assert mock_customize.called
        assert mock_cleanup.called
        assert mock_init_repo.called
        assert result.exit_code == 0
        assert "Successfully created gateway project" in result.output
        assert "my-gateway" in result.output


class TestCreateUi:
    """Tests for the 'create ui' command."""

    def test_help_message(self, cli_runner):
        """Test that help message is displayed correctly."""
        result = cli_runner.invoke(cli, ["create", "ui", "--help"])
        assert result.exit_code == 0
        assert "chat UI" in result.output or "ui" in result.output.lower()
        assert "PROJECT_NAME" in result.output

    def test_invalid_project_name_uppercase(self, cli_runner):
        """Test that uppercase letters in project name are rejected."""
        result = cli_runner.invoke(cli, ["create", "ui", "MyUI"])
        assert result.exit_code == 1
        assert "Invalid project name" in result.output

    @patch("fips_agents_cli.commands.create.clone_template")
    @patch("fips_agents_cli.commands.create.customize_go_project")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.init_repository")
    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.is_gh_installed")
    def test_successful_creation(
        self,
        mock_gh_installed,
        mock_is_git_installed,
        mock_init_repo,
        mock_cleanup,
        mock_customize,
        mock_clone,
        cli_runner,
        temp_dir,
    ):
        """Test successful UI project creation."""
        mock_is_git_installed.return_value = True
        mock_gh_installed.return_value = False

        def create_minimal_structure(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "go.mod").write_text("module ui-template\n\ngo 1.22\n")

        mock_clone.side_effect = create_minimal_structure

        result = cli_runner.invoke(
            cli, ["create", "ui", "my-chat-ui", "--local", "--target-dir", str(temp_dir)]
        )

        assert mock_clone.called
        call_args = mock_clone.call_args
        assert call_args[0][0] == "https://github.com/fips-agents/ui-template"
        assert mock_customize.called
        assert mock_cleanup.called
        assert mock_init_repo.called
        assert result.exit_code == 0
        assert "Successfully created chat UI project" in result.output
        assert "my-chat-ui" in result.output


class TestDetermineGithubMode:
    """Tests for _determine_github_mode helper.

    Regression coverage for issue #40: non-TTY shells (CI, agent-driven) hung
    on the `Create GitHub repository?` prompt and exited with an empty
    `Unexpected error:` message.
    """

    def _call(self, **overrides):
        from fips_agents_cli.commands.create import _determine_github_mode

        kwargs = {"use_github": False, "use_local": False, "yes": False}
        kwargs.update(overrides)
        return _determine_github_mode(**kwargs)

    def test_local_flag_short_circuits(self):
        with patch("sys.stdin.isatty", return_value=False):
            assert self._call(use_local=True) is False

    def test_github_flag_short_circuits(self):
        assert self._call(use_github=True) is True

    @patch("fips_agents_cli.commands.create.is_gh_installed", return_value=False)
    def test_falls_back_to_local_when_gh_missing(self, _mock_installed):
        assert self._call() is False

    @patch("fips_agents_cli.commands.create.is_gh_authenticated", return_value=False)
    @patch("fips_agents_cli.commands.create.is_gh_installed", return_value=True)
    def test_falls_back_to_local_when_gh_unauthenticated(self, *_mocks):
        assert self._call() is False

    @patch("fips_agents_cli.commands.create.is_gh_authenticated", return_value=True)
    @patch("fips_agents_cli.commands.create.is_gh_installed", return_value=True)
    def test_yes_flag_chooses_github_when_gh_available(self, *_mocks):
        assert self._call(yes=True) is True

    @patch("sys.stdin.isatty", return_value=False)
    @patch("fips_agents_cli.commands.create.is_gh_authenticated", return_value=True)
    @patch("fips_agents_cli.commands.create.is_gh_installed", return_value=True)
    def test_non_tty_falls_back_to_local_without_prompting(self, *_mocks):
        # The fix for issue #40: never prompt when stdin isn't a TTY.
        with patch("click.confirm") as mock_confirm:
            assert self._call() is False
            mock_confirm.assert_not_called()

    @patch("sys.stdin.isatty", return_value=True)
    @patch("fips_agents_cli.commands.create.is_gh_authenticated", return_value=True)
    @patch("fips_agents_cli.commands.create.is_gh_installed", return_value=True)
    def test_tty_prompts_user(self, *_mocks):
        with patch("click.confirm", return_value=True) as mock_confirm:
            assert self._call() is True
            mock_confirm.assert_called_once()

    @patch("sys.stdin.isatty", return_value=True)
    @patch("fips_agents_cli.commands.create.is_gh_authenticated", return_value=True)
    @patch("fips_agents_cli.commands.create.is_gh_installed", return_value=True)
    def test_tty_with_aborted_confirm_falls_back_to_local(self, *_mocks):
        # Defensive: if the prompt aborts (e.g. closed stdin while isatty
        # claimed otherwise), we should not crash with `Unexpected error:`.
        import click as _click

        with patch("click.confirm", side_effect=_click.exceptions.Abort()):
            assert self._call() is False


class TestCreateAgentTeam:
    """Tests for the 'create agent-team' command."""

    def test_help_message(self, cli_runner):
        """Test that help message is displayed correctly."""
        result = cli_runner.invoke(cli, ["create", "agent-team", "--help"])
        assert result.exit_code == 0
        assert "Create a new agent team project" in result.output
        assert "PROJECT_NAME" in result.output

    def test_invalid_project_name_uppercase(self, cli_runner):
        """Test that uppercase letters in project name are rejected."""
        result = cli_runner.invoke(cli, ["create", "agent-team", "TestTeam"])
        assert result.exit_code == 1
        assert "Invalid project name" in result.output

    def test_invalid_project_name_special_chars(self, cli_runner):
        """Test that special characters in project name are rejected."""
        result = cli_runner.invoke(cli, ["create", "agent-team", "test@team"])
        assert result.exit_code == 1
        assert "Invalid project name" in result.output

    def test_invalid_project_name_starts_with_number(self, cli_runner):
        """Test that project name starting with number is rejected."""
        result = cli_runner.invoke(cli, ["create", "agent-team", "123team"])
        assert result.exit_code == 1
        assert "Invalid project name" in result.output

    @patch("fips_agents_cli.commands.create.is_gh_installed", return_value=False)
    @patch("fips_agents_cli.commands.create.is_git_installed", return_value=True)
    def test_existing_directory_error(
        self, mock_is_git_installed, mock_is_gh_installed, cli_runner, temp_dir
    ):
        """Test that existing directory causes an error."""
        existing_dir = temp_dir / "existing-team"
        existing_dir.mkdir()

        result = cli_runner.invoke(
            cli, ["create", "agent-team", "existing-team", "--target-dir", str(temp_dir)]
        )
        assert result.exit_code == 1
        assert "already exists" in result.output

    @patch("fips_agents_cli.commands.create.is_gh_installed", return_value=False)
    @patch("fips_agents_cli.commands.create.is_git_installed")
    def test_git_not_installed(
        self, mock_is_git_installed, mock_is_gh_installed, cli_runner, temp_dir
    ):
        """Test that missing git installation is detected."""
        mock_is_git_installed.return_value = False

        result = cli_runner.invoke(
            cli, ["create", "agent-team", "test-team", "--target-dir", str(temp_dir)]
        )
        assert result.exit_code == 1
        assert "Git is not installed" in result.output

    @patch("fips_agents_cli.commands.create.clone_template")
    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.is_gh_installed")
    def test_clone_failure(
        self, mock_gh_installed, mock_is_git_installed, mock_clone, cli_runner, temp_dir
    ):
        """Test handling of git clone failures."""
        mock_is_git_installed.return_value = True
        mock_gh_installed.return_value = False
        mock_clone.side_effect = Exception("Connection timeout")

        result = cli_runner.invoke(
            cli, ["create", "agent-team", "test-team", "--target-dir", str(temp_dir)]
        )
        assert result.exit_code == 1
        assert "Failed to clone agent team template" in result.output

    @patch("fips_agents_cli.commands.create.clone_template")
    @patch("fips_agents_cli.commands.create.customize_agent_team_project")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.init_repository")
    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.is_gh_installed")
    def test_successful_creation(
        self,
        mock_gh_installed,
        mock_is_git_installed,
        mock_init_repo,
        mock_cleanup,
        mock_customize,
        mock_clone,
        cli_runner,
        temp_dir,
    ):
        """Test successful project creation with all steps."""
        mock_is_git_installed.return_value = True
        mock_gh_installed.return_value = False

        # Mock the clone to create a minimal structure
        def create_minimal_structure(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        mock_clone.side_effect = create_minimal_structure

        result = cli_runner.invoke(
            cli, ["create", "agent-team", "my-team", "--target-dir", str(temp_dir)]
        )

        # Verify all steps were called
        assert mock_clone.called
        assert mock_customize.called
        assert mock_cleanup.called
        assert mock_init_repo.called

        # Check success message
        assert result.exit_code == 0
        assert "Successfully created agent team project" in result.output
        assert "my-team" in result.output

    @patch("fips_agents_cli.commands.create.clone_template")
    @patch("fips_agents_cli.commands.create.customize_agent_team_project")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.is_gh_installed")
    def test_no_git_flag(
        self,
        mock_gh_installed,
        mock_is_git_installed,
        mock_cleanup,
        mock_customize,
        mock_clone,
        cli_runner,
        temp_dir,
    ):
        """Test that --no-git flag skips git initialization."""
        mock_is_git_installed.return_value = True
        mock_gh_installed.return_value = False

        def create_minimal_structure(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        mock_clone.side_effect = create_minimal_structure

        with patch("fips_agents_cli.commands.create.init_repository") as mock_init:
            result = cli_runner.invoke(
                cli,
                ["create", "agent-team", "my-team", "--target-dir", str(temp_dir), "--no-git"],
            )

            # Verify git init was NOT called
            assert not mock_init.called
            assert result.exit_code == 0


class TestCreateAgentTeamGitHub:
    """Tests for GitHub integration in 'create agent-team' command."""

    def test_github_and_local_mutually_exclusive(self, cli_runner):
        """Test that --github and --local cannot be used together."""
        result = cli_runner.invoke(
            cli, ["create", "agent-team", "test-team", "--github", "--local"]
        )
        assert result.exit_code == 1
        assert "Cannot use --github and --local together" in result.output

    def test_remote_only_and_local_mutually_exclusive(self, cli_runner):
        """Test that --remote-only and --local cannot be used together."""
        result = cli_runner.invoke(
            cli, ["create", "agent-team", "test-team", "--remote-only", "--local"]
        )
        assert result.exit_code == 1
        assert "Cannot use --remote-only with --local" in result.output

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.check_gh_prerequisites")
    @patch("fips_agents_cli.commands.create.create_github_repo")
    @patch("fips_agents_cli.commands.create.get_github_username")
    @patch("fips_agents_cli.commands.create.clone_template")
    @patch("fips_agents_cli.commands.create.customize_agent_team_project")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.init_repository")
    @patch("fips_agents_cli.commands.create.add_remote")
    @patch("fips_agents_cli.commands.create.push_to_remote")
    def test_github_flow_creates_repo_and_pushes(
        self,
        mock_push,
        mock_add_remote,
        mock_init_repo,
        mock_cleanup,
        mock_customize,
        mock_clone,
        mock_get_username,
        mock_create_gh,
        mock_check_gh,
        mock_is_git_installed,
        cli_runner,
        temp_dir,
    ):
        """Test full GitHub flow creates repo and pushes code."""
        mock_is_git_installed.return_value = True
        mock_check_gh.return_value = (True, None)
        mock_create_gh.return_value = (True, "https://github.com/testuser/my-team", None)
        mock_get_username.return_value = "testuser"
        mock_push.return_value = True

        def create_minimal_structure(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        mock_clone.side_effect = create_minimal_structure

        result = cli_runner.invoke(
            cli,
            ["create", "agent-team", "my-team", "--github", "--target-dir", str(temp_dir)],
        )

        assert result.exit_code == 0
        assert mock_create_gh.called
        assert mock_add_remote.called
        assert mock_push.called
        assert "Successfully created" in result.output
        assert "https://github.com/testuser/my-team" in result.output

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.check_gh_prerequisites")
    @patch("fips_agents_cli.commands.create.create_github_repo")
    @patch("fips_agents_cli.commands.create.get_github_username")
    def test_remote_only_mode(
        self,
        mock_get_username,
        mock_create_gh,
        mock_check_gh,
        mock_is_git_installed,
        cli_runner,
    ):
        """Test --remote-only creates GitHub repo without local clone."""
        mock_is_git_installed.return_value = True
        mock_check_gh.return_value = (True, None)
        mock_create_gh.return_value = (True, "https://github.com/testuser/my-team", None)
        mock_get_username.return_value = "testuser"

        with patch("fips_agents_cli.commands.create.clone_template") as mock_clone:
            result = cli_runner.invoke(
                cli, ["create", "agent-team", "my-team", "--github", "--remote-only"]
            )

            assert result.exit_code == 0
            # Clone should NOT be called in remote-only mode
            assert not mock_clone.called
            assert "Successfully created GitHub repository" in result.output

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.check_gh_prerequisites")
    @patch("fips_agents_cli.commands.create.create_github_repo")
    @patch("fips_agents_cli.commands.create.get_github_username")
    @patch("fips_agents_cli.commands.create.clone_template")
    @patch("fips_agents_cli.commands.create.customize_agent_team_project")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.init_repository")
    @patch("fips_agents_cli.commands.create.add_remote")
    @patch("fips_agents_cli.commands.create.push_to_remote")
    def test_private_repo_option(
        self,
        mock_push,
        mock_add_remote,
        mock_init_repo,
        mock_cleanup,
        mock_customize,
        mock_clone,
        mock_get_username,
        mock_create_gh,
        mock_check_gh,
        mock_is_git_installed,
        cli_runner,
        temp_dir,
    ):
        """Test --private flag creates private GitHub repo."""
        mock_is_git_installed.return_value = True
        mock_check_gh.return_value = (True, None)
        mock_create_gh.return_value = (True, "https://github.com/testuser/my-team", None)
        mock_get_username.return_value = "testuser"
        mock_push.return_value = True

        def create_minimal_structure(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        mock_clone.side_effect = create_minimal_structure

        result = cli_runner.invoke(
            cli,
            [
                "create",
                "agent-team",
                "my-team",
                "--github",
                "--private",
                "--target-dir",
                str(temp_dir),
            ],
        )

        assert result.exit_code == 0
        # Verify private=True was passed
        mock_create_gh.assert_called_with(name="my-team", private=True, org=None, description=None)

    @patch("fips_agents_cli.commands.create.is_git_installed")
    @patch("fips_agents_cli.commands.create.check_gh_prerequisites")
    @patch("fips_agents_cli.commands.create.create_github_repo")
    @patch("fips_agents_cli.commands.create.get_github_username")
    @patch("fips_agents_cli.commands.create.clone_template")
    @patch("fips_agents_cli.commands.create.customize_agent_team_project")
    @patch("fips_agents_cli.commands.create.cleanup_template_files")
    @patch("fips_agents_cli.commands.create.init_repository")
    @patch("fips_agents_cli.commands.create.add_remote")
    @patch("fips_agents_cli.commands.create.push_to_remote")
    def test_org_option(
        self,
        mock_push,
        mock_add_remote,
        mock_init_repo,
        mock_cleanup,
        mock_customize,
        mock_clone,
        mock_get_username,
        mock_create_gh,
        mock_check_gh,
        mock_is_git_installed,
        cli_runner,
        temp_dir,
    ):
        """Test --org flag creates repo in organization."""
        mock_is_git_installed.return_value = True
        mock_check_gh.return_value = (True, None)
        mock_create_gh.return_value = (True, "https://github.com/myorg/my-team", None)
        mock_get_username.return_value = "testuser"
        mock_push.return_value = True

        def create_minimal_structure(url, target_path, branch=None):
            target_path.mkdir(parents=True, exist_ok=True)
            (target_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        mock_clone.side_effect = create_minimal_structure

        result = cli_runner.invoke(
            cli,
            [
                "create",
                "agent-team",
                "my-team",
                "--github",
                "--org",
                "myorg",
                "--target-dir",
                str(temp_dir),
            ],
        )

        assert result.exit_code == 0
        mock_create_gh.assert_called_with(
            name="my-team", private=False, org="myorg", description=None
        )
