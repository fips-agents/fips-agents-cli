"""Tests for vendor commit tracking functionality."""

import git
import pytest

from fips_agents_cli.tools.project import vendor_fipsagents_from_clone


class TestVendorCommitTracking:
    """Tests for vendor commit tracking in VENDORED marker."""

    def _create_monorepo_fixture(self, path):
        """
        Create a real git repository with monorepo structure for testing.

        This mimics the fips-agents/agent-template repository structure:
        packages/fipsagents/src/fipsagents with a real git history.
        """
        path.mkdir(parents=True, exist_ok=True)

        # Create directory structure
        pkg_root = path / "packages" / "fipsagents"
        pkg_src = pkg_root / "src" / "fipsagents"
        pkg_src.mkdir(parents=True)

        baseagent = pkg_src / "baseagent"
        baseagent.mkdir()

        # Create pyproject.toml
        (pkg_root / "pyproject.toml").write_text(
            "[project]\n"
            'name = "fipsagents"\n'
            'version = "0.1.0"\n'
            'dependencies = ["litellm>=1.83.0"]\n'
        )

        # Create __init__.py files
        (pkg_src / "__init__.py").write_text('"""fipsagents package."""\n')
        (baseagent / "__init__.py").write_text('"""BaseAgent module."""\n\n__version__ = "1.2.3"\n')

        # Initialize git repository
        repo = git.Repo.init(str(path))

        # Configure git user (required for commits)
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")

        # Add all files and create initial commit
        repo.index.add(
            [
                "packages/fipsagents/pyproject.toml",
                "packages/fipsagents/src/fipsagents/__init__.py",
                "packages/fipsagents/src/fipsagents/baseagent/__init__.py",
            ]
        )
        repo.index.commit("Initial commit: Add fipsagents package")

        return repo

    def test_vendored_marker_contains_commit(self, temp_dir):
        """Test that VENDORED marker contains commit and commit_short fields with valid hex values."""
        # Create monorepo fixture
        clone_path = temp_dir / "agent-template"
        _repo = self._create_monorepo_fixture(clone_path)

        # Create project directory
        project_path = temp_dir / "my-agent"
        project_path.mkdir()
        (project_path / "src").mkdir()

        # Vendor the package
        vendor_fipsagents_from_clone(clone_path, project_path)

        # Read VENDORED marker
        marker_path = project_path / "src" / "fipsagents" / "VENDORED"
        assert marker_path.exists()
        marker_content = marker_path.read_text()

        # Verify commit fields are present
        assert "commit:" in marker_content
        assert "commit_short:" in marker_content

        # Verify they're not "unknown"
        assert "commit: unknown" not in marker_content
        assert "commit_short: unknown" not in marker_content

        # Extract commit hash and verify it's valid hex
        for line in marker_content.splitlines():
            if line.startswith("commit:"):
                commit_hash = line.split(":", 1)[1].strip()
                # Should be 40 character hex string
                assert len(commit_hash) == 40
                assert all(c in "0123456789abcdef" for c in commit_hash.lower())
            if line.startswith("commit_short:"):
                commit_short = line.split(":", 1)[1].strip()
                # Should be 7 character hex string
                assert len(commit_short) == 7
                assert all(c in "0123456789abcdef" for c in commit_short.lower())

    def test_vendored_marker_commit_matches_repo(self, temp_dir):
        """Test that the commit hash in VENDORED matches the actual HEAD commit of the source repo."""
        # Create monorepo fixture
        clone_path = temp_dir / "agent-template"
        repo = self._create_monorepo_fixture(clone_path)

        # Get actual HEAD commit
        expected_commit = repo.head.commit.hexsha
        expected_short = expected_commit[:7]

        # Create project directory
        project_path = temp_dir / "my-agent"
        project_path.mkdir()
        (project_path / "src").mkdir()

        # Vendor the package
        vendor_fipsagents_from_clone(clone_path, project_path)

        # Read VENDORED marker
        marker_path = project_path / "src" / "fipsagents" / "VENDORED"
        marker_content = marker_path.read_text()

        # Verify commit matches
        assert f"commit: {expected_commit}" in marker_content
        assert f"commit_short: {expected_short}" in marker_content

    def test_vendored_marker_contains_version(self, temp_dir):
        """Test that VENDORED marker contains the correct version from __init__.py."""
        # Create monorepo fixture
        clone_path = temp_dir / "agent-template"
        _repo = self._create_monorepo_fixture(clone_path)

        # Create project directory
        project_path = temp_dir / "my-agent"
        project_path.mkdir()
        (project_path / "src").mkdir()

        # Vendor the package
        vendor_fipsagents_from_clone(clone_path, project_path)

        # Read VENDORED marker
        marker_path = project_path / "src" / "fipsagents" / "VENDORED"
        marker_content = marker_path.read_text()

        # Verify version is present
        assert "version: 1.2.3" in marker_content

    def test_vendored_copies_source(self, temp_dir):
        """Test that vendoring actually copies the source files to the project."""
        # Create monorepo fixture
        clone_path = temp_dir / "agent-template"
        _repo = self._create_monorepo_fixture(clone_path)

        # Create project directory
        project_path = temp_dir / "my-agent"
        project_path.mkdir()
        (project_path / "src").mkdir()

        # Vendor the package
        vendor_fipsagents_from_clone(clone_path, project_path)

        # Verify source files were copied
        dest = project_path / "src" / "fipsagents"
        assert dest.exists()
        assert dest.is_dir()
        assert (dest / "__init__.py").exists()
        assert (dest / "baseagent" / "__init__.py").exists()

        # Verify content matches
        baseagent_init = (dest / "baseagent" / "__init__.py").read_text()
        assert '__version__ = "1.2.3"' in baseagent_init

    def test_vendored_copies_upstream_toml(self, temp_dir):
        """Test that pyproject.toml is copied as UPSTREAM.toml for provenance."""
        # Create monorepo fixture
        clone_path = temp_dir / "agent-template"
        _repo = self._create_monorepo_fixture(clone_path)

        # Create project directory
        project_path = temp_dir / "my-agent"
        project_path.mkdir()
        (project_path / "src").mkdir()

        # Vendor the package
        vendor_fipsagents_from_clone(clone_path, project_path)

        # Verify UPSTREAM.toml was copied
        upstream_toml = project_path / "src" / "fipsagents" / "UPSTREAM.toml"
        assert upstream_toml.exists()

        # Verify content matches original pyproject.toml
        content = upstream_toml.read_text()
        assert 'name = "fipsagents"' in content
        assert 'version = "0.1.0"' in content

    def test_vendored_replaces_existing_source(self, temp_dir):
        """Test that vendoring removes existing vendored source before copying."""
        # Create monorepo fixture
        clone_path = temp_dir / "agent-template"
        _repo = self._create_monorepo_fixture(clone_path)

        # Create project directory with existing vendored source
        project_path = temp_dir / "my-agent"
        project_path.mkdir()
        (project_path / "src").mkdir()

        existing_dest = project_path / "src" / "fipsagents"
        existing_dest.mkdir()
        (existing_dest / "old_file.py").write_text("# This should be removed\n")

        # Vendor the package
        vendor_fipsagents_from_clone(clone_path, project_path)

        # Verify old file is gone and new files exist
        assert not (existing_dest / "old_file.py").exists()
        assert (existing_dest / "__init__.py").exists()
        assert (existing_dest / "baseagent" / "__init__.py").exists()

    def test_vendored_marker_contains_all_required_fields(self, temp_dir):
        """Test that VENDORED marker contains all required fields."""
        # Create monorepo fixture
        clone_path = temp_dir / "agent-template"
        _repo = self._create_monorepo_fixture(clone_path)

        # Create project directory
        project_path = temp_dir / "my-agent"
        project_path.mkdir()
        (project_path / "src").mkdir()

        # Vendor the package
        vendor_fipsagents_from_clone(clone_path, project_path)

        # Read VENDORED marker
        marker_path = project_path / "src" / "fipsagents" / "VENDORED"
        marker_content = marker_path.read_text()

        # Verify all required fields are present
        assert "version:" in marker_content
        assert "vendored:" in marker_content
        assert "source:" in marker_content
        assert "commit:" in marker_content
        assert "commit_short:" in marker_content
        assert "https://github.com/fips-agents/agent-template" in marker_content

    def test_multiple_commits_in_history(self, temp_dir):
        """Test that vendoring tracks the latest commit when repo has multiple commits."""
        # Create monorepo fixture
        clone_path = temp_dir / "agent-template"
        repo = self._create_monorepo_fixture(clone_path)

        # Add a second commit
        readme_path = clone_path / "README.md"
        readme_path.write_text("# Agent Template\n")
        repo.index.add(["README.md"])
        repo.index.commit("docs: Add README")

        # Get the latest commit
        expected_commit = repo.head.commit.hexsha
        expected_short = expected_commit[:7]

        # Create project directory
        project_path = temp_dir / "my-agent"
        project_path.mkdir()
        (project_path / "src").mkdir()

        # Vendor the package
        vendor_fipsagents_from_clone(clone_path, project_path)

        # Read VENDORED marker
        marker_path = project_path / "src" / "fipsagents" / "VENDORED"
        marker_content = marker_path.read_text()

        # Verify it tracks the second (latest) commit, not the first
        assert f"commit: {expected_commit}" in marker_content
        assert f"commit_short: {expected_short}" in marker_content

    def test_missing_package_source_raises_error(self, temp_dir):
        """Test that vendoring fails gracefully when package source is missing."""
        # Create incomplete monorepo (missing fipsagents package)
        clone_path = temp_dir / "agent-template"
        clone_path.mkdir()

        # Initialize git but don't create the expected package structure
        repo = git.Repo.init(str(clone_path))
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test User")
            config.set_value("user", "email", "test@example.com")

        # Create project directory
        project_path = temp_dir / "my-agent"
        project_path.mkdir()
        (project_path / "src").mkdir()

        # Vendoring should raise FileNotFoundError
        with pytest.raises(FileNotFoundError, match="Expected fipsagents source at"):
            vendor_fipsagents_from_clone(clone_path, project_path)
